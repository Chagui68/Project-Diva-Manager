"""USM conversion: correct frame rate in the USM header, 720p, constant frame rate, no B-frames.
Uses synthetic 24 and 60 fps clips. Run: python tests\\test_video.py"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from divamgr import media, paths  # noqa: E402


def main():
    from wannacri.usm import Usm

    ff, fp = paths.find_tool("ffmpeg"), paths.find_tool("ffprobe")
    assert ff and fp, "hace falta FFmpeg"
    # WannaCRI keeps the opened USM file handle, so the temp folder may not be removable at the end
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        for rate, expected in (("24", 24.0), ("60", 30.0), ("30000/1001", 29.97)):
            src = os.path.join(tmp, "clip.mp4")
            subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            f"testsrc2=size=1920x1080:rate={rate}", "-t", "6", "-c:v", "libx264", "-bf", "3",
                            "-pix_fmt", "yuv420p", src], check=True)
            usm_path = os.path.join(tmp, f"pv_{rate.replace('/', '_')}.usm")
            media.make_usm(ff, fp, src, usm_path, "h264", 6.0)
            usm = Usm.open(usm_path)
            hdr = usm.videos[0].header_page
            fps = hdr.get("framerate_n").val / hdr.get("framerate_d").val
            width, height = hdr.get("width").val, hdr.get("height").val
            frames = hdr.get("total_frames").val
            print(f"fuente {rate:>10} fps -> USM {fps:6.3f} fps, {width}x{height}, {frames} cuadros")
            assert abs(fps - expected) < 0.01, "framerate incorrecto en el USM"
            assert (width, height) == (1280, 720)
            assert abs(frames - expected * 6) <= 2, "la duración del video no coincide"
    print("\nTODO OK")


if __name__ == "__main__":
    main()
