"""FFmpeg conversion: audio to 44.1 kHz Ogg Vorbis, video to a CriWare .usm (H.264 or VP9) via WannaCRI."""
import json
import os
import subprocess
import tempfile
from fractions import Fraction

import numpy as np
import soundfile as sf

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
AUDIO_EXTS = {".ogg", ".wav", ".flac"}  # readable without ffmpeg


class MediaError(RuntimeError):
    pass


def probe(ffprobe, path):
    out = subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         creationflags=NO_WINDOW)
    if out.returncode:
        raise MediaError(out.stderr.strip() or "ffprobe falló")
    return json.loads(out.stdout)


def media_info(ffprobe, path):
    """-> dict(duration, has_video, has_audio, title, artist)"""
    info = probe(ffprobe, path)
    tags = {k.lower(): v for k, v in info.get("format", {}).get("tags", {}).items()}
    kinds = [s.get("codec_type") for s in info.get("streams", [])
             if not s.get("disposition", {}).get("attached_pic")]
    return {
        "duration": float(info.get("format", {}).get("duration") or 0),
        "has_video": "video" in kinds,
        "has_audio": "audio" in kinds,
        "title": tags.get("title", ""),
        "artist": tags.get("artist", "") or tags.get("album_artist", ""),
    }


def run_ffmpeg(ffmpeg, args, duration=0.0, on_progress=None):
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-nostdin", "-progress", "pipe:1"] + args
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    for line in proc.stdout:
        if on_progress and duration and line.startswith("out_time_us="):
            try:
                on_progress(min(1.0, int(line.split("=")[1]) / 1e6 / duration))
            except ValueError:
                pass
    err = proc.stderr.read()
    if proc.wait():
        raise MediaError(err.strip()[-800:] or "ffmpeg falló")


def extract_audio(ffmpeg, src, dst_ogg, duration=0.0, on_progress=None):
    run_ffmpeg(ffmpeg, ["-i", src, "-vn", "-map", "0:a:0", "-af", "aresample=async=1:first_pts=0",
                        "-ac", "2", "-ar", "44100", "-c:a", "libvorbis", "-q:a", "8", dst_ogg],
               duration, on_progress)


def convert_audio_no_ffmpeg(src, dst_ogg):
    """Fallback for .ogg/.wav/.flac sources when ffmpeg is missing."""
    data, sr = sf.read(src, dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    data = data[:, :2]
    if sr != 44100:
        import soxr
        data = soxr.resample(data, sr, 44100)
    # libsndfile overflows the stack when a long Vorbis stream is written in one call
    with sf.SoundFile(dst_ogg, "w", 44100, 2, format="OGG", subtype="VORBIS") as f:
        for i in range(0, len(data), 16384):
            f.write(np.ascontiguousarray(data[i:i + 16384]))


VIDEO_HEIGHT = 720
MAX_FPS = 30


def video_fps(ffprobe, src):
    """Frame rate for the movie: the source rate (as a fraction) capped at MAX_FPS."""
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=avg_frame_rate,r_frame_rate", "-of", "json", src],
                         capture_output=True, text=True, creationflags=NO_WINDOW)
    rate = Fraction(MAX_FPS)
    try:
        stream = json.loads(out.stdout)["streams"][0]
        # nominal rate first: variable-frame-rate uploads report odd averages (e.g. 25.3 for a 30 fps video)
        for key in ("r_frame_rate", "avg_frame_rate"):
            num, den = (int(v) for v in stream.get(key, "0/0").split("/"))
            if num and den:
                rate = Fraction(num, den)
                break
    except (ValueError, KeyError, IndexError):
        pass
    if rate > MAX_FPS or rate < 10:
        rate = Fraction(MAX_FPS)
    # snap 23.976/29.97 style rates to their exact NTSC fractions
    for exact in (Fraction(24000, 1001), Fraction(30000, 1001), Fraction(24), Fraction(25), Fraction(30)):
        if abs(float(rate - exact)) < 0.02:
            return exact
    return rate.limit_denominator(1001)


def make_usm(ffmpeg, ffprobe, src, dst_usm, codec="h264", duration=0.0, on_progress=None):
    """720p constant-frame-rate movie in a CriWare USM. The frame rate is written explicitly:
    WannaCRI reads it from ffprobe, which reports twice the real rate for raw H.264 streams
    (the cause of movies playing at double speed). H.264 is encoded without B-frames, which the
    game's decoder handles poorly (stutter/freezes)."""
    from wannacri.usm import H264, OpMode, Usm, Vp9
    from wannacri.usm.types import ElementType

    fps = video_fps(ffprobe, src)
    width = VIDEO_HEIGHT * 16 // 9
    vf = (f"scale={width}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
          f"pad={width}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps.numerator}/{fps.denominator},"
          "format=yuv420p")
    gop = str(int(round(float(fps))))
    stem = os.path.splitext(os.path.basename(dst_usm))[0]
    with tempfile.TemporaryDirectory(prefix="divamgr_") as tmp:
        if codec == "vp9":
            es = os.path.join(tmp, stem + ".ivf")
            args = ["-i", src, "-an", "-sn", "-vf", vf, "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "33",
                    "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", "-g", gop, "-f", "ivf", es]
        else:
            es = os.path.join(tmp, stem + ".h264")
            args = ["-i", src, "-an", "-sn", "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "21",
                    "-maxrate", "5M", "-bufsize", "10M", "-profile:v", "main", "-level", "4.0", "-bf", "0",
                    "-g", gop, "-keyint_min", gop, "-sc_threshold", "0",
                    "-bsf:v", "h264_mp4toannexb", "-f", "h264", es]
        run_ffmpeg(ffmpeg, args, duration, on_progress)
        video = Vp9(es, ffprobe_path=ffprobe) if codec == "vp9" else H264(es, ffprobe_path=ffprobe)
        video.header_page.update("framerate_n", ElementType.I32, fps.numerator * 1000 // fps.denominator)
        video.header_page.update("framerate_d", ElementType.I32, 1000)
        ver = video.crid_page.get("fmtver")
        usm = Usm(videos=[video], key=None, version=ver.val)
        with open(dst_usm, "wb") as f:
            for packet in usm.stream(OpMode.NONE, encoding="shift-jis"):
                f.write(packet)
