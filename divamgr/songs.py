"""Song import pipeline: media file -> DivaModLoader mod folder with ogg, usm, DSC charts and mod_pv_db."""
import json
import os
import re
import shutil
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date

from . import analysis, chartgen, media, modloader, pvdb

MOD_PREFIX = "DivaManager_"


@dataclass
class SongRequest:
    source: str
    title: str
    artist: str = ""
    chara: str = "MIK"
    pv_id: int = 9500
    difficulties: list = field(default_factory=lambda: list(pvdb.DIFFICULTIES))
    density: float = 1.0
    seed: int = 0
    video: str = "h264"  # h264 | vp9 | none
    offset_ms: float = 0.0  # notes later (+) or earlier (-) than the analysed beat


def slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return s[:40] or "song"


def mod_folder_name(pv_id, title):
    return f"{MOD_PREFIX}pv{pv_id}_{slug(title)}"


class Progress:
    """Maps sub-step progress onto a global 0..1 bar."""

    def __init__(self, cb, log):
        self.cb, self.log = cb, log
        self.lo, self.hi = 0.0, 1.0

    def stage(self, lo, hi, msg):
        self.lo, self.hi = lo, hi
        self.log(msg)
        self.cb(lo)

    def __call__(self, f, msg=""):
        self.cb(self.lo + (self.hi - self.lo) * f)


def write_charts(mod_path, pv_id, req, a, has_movie, log):
    p = f"pv_{pv_id:03d}"
    script_dir = os.path.join(mod_path, "rom", "script")
    os.makedirs(script_dir, exist_ok=True)
    for fn in os.listdir(script_dir):
        if fn.startswith(p + "_") and fn.endswith(".dsc"):
            os.remove(os.path.join(script_dir, fn))
    stars = {}
    for d in pvdb.DIFFICULTIES:
        if d not in req.difficulties:
            continue
        notes, st = chartgen.generate(a, d, density=req.density, seed=req.seed)
        chartgen.build_script(a, notes, has_movie, offset_ms=req.offset_ms).save(
            os.path.join(script_dir, pvdb.script_name(pv_id, d)))
        stars[d] = st
        holds = sum(n.hold for n in notes)
        multi = sum(bool(n.extra) for n in notes)
        slides = sum(bool(n.slide) for n in notes)
        log(f"  {pvdb.DIFF_LABELS[d]:13s} {len(notes):4d} notas · {holds} holds · {multi} múltiples · "
            f"{slides} deslizamientos  ★ {st:.1f}")
    db = pvdb.build(pv_id, req.title, req.artist, a.bpm, stars, a.sabi_start, a.sabi_len,
                    chara=req.chara, has_movie=has_movie)
    with open(os.path.join(mod_path, "rom", "mod_pv_db.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(db)
    return stars


def import_song(game_dir, req, ffmpeg, ffprobe, log=print, progress=lambda f: None):
    pr = Progress(progress, log)
    src = req.source
    ext = os.path.splitext(src)[1].lower()
    if not ffmpeg and ext not in media.AUDIO_EXTS:
        raise media.MediaError("Se necesita FFmpeg para importar archivos .mp4. Configúralo en la barra superior.")

    info = {"duration": 0.0, "has_video": False, "has_audio": True}
    if ffprobe:
        info = media.media_info(ffprobe, src)
        if not info["has_audio"]:
            raise media.MediaError("El archivo no tiene pista de audio.")
    want_video = req.video != "none" and info["has_video"] and bool(ffmpeg)

    folder = mod_folder_name(req.pv_id, req.title)
    mod_path = os.path.join(modloader.mods_dir(game_dir), folder)
    if os.path.exists(mod_path):
        raise FileExistsError(f"Ya existe la carpeta {folder}")
    p = f"pv_{req.pv_id:03d}"
    try:
        for sub in ("rom/sound/song", "rom/script", "rom/movie"):
            os.makedirs(os.path.join(mod_path, sub), exist_ok=True)
        ogg = os.path.join(mod_path, "rom", "sound", "song", p + ".ogg")

        pr.stage(0.0, 0.15, "Extrayendo audio → OGG 44100 Hz")
        if ffmpeg:
            media.extract_audio(ffmpeg, src, ogg, info["duration"], pr)
        else:
            media.convert_audio_no_ffmpeg(src, ogg)

        pr.stage(0.15, 0.45, "Analizando la canción (tempo, ritmo, timbre)")
        a = analysis.analyze(ogg, pr)
        log(f"  BPM ≈ {a.bpm:.1f}, duración {a.duration:.1f} s, estribillo en {a.sabi_start:.1f} s")

        pr.stage(0.45, 0.5, "Generando notas")
        write_charts(mod_path, req.pv_id, req, a, want_video, log)

        if want_video:
            pr.stage(0.5, 0.98, f"Convirtiendo video → USM ({req.video.upper()}); puede tardar")
            media.make_usm(ffmpeg, ffprobe, src, os.path.join(mod_path, "rom", "movie", p + ".usm"),
                           codec=req.video, duration=info["duration"], on_progress=pr)
        else:
            shutil.rmtree(os.path.join(mod_path, "rom", "movie"), ignore_errors=True)
            if req.video != "none":
                log("  Sin video (el archivo no tiene video o falta FFmpeg).")

        modloader.write_mod_config(mod_path, name=req.title, description=f"{req.artist} — generado por Diva Manager",
                                   version="1.0", date=date.today().strftime("%d.%m.%Y"), author="Diva Manager")
        meta = asdict(req)
        meta.update(bpm=round(a.bpm, 2), duration=round(a.duration, 2), has_movie=want_video)
        with open(os.path.join(mod_path, modloader.DM_META), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        prio = modloader.get_priority(game_dir)
        if prio is not None and folder not in prio:
            modloader.set_priority(game_dir, [folder] + prio)
    except BaseException:
        shutil.rmtree(mod_path, ignore_errors=True)
        raise
    pr.stage(1.0, 1.0, f"Listo: {folder}")
    return mod_path


def regenerate(mod, density, seed, difficulties=None, offset_ms=None, video=None, ffmpeg=None, ffprobe=None,
               log=print, progress=lambda f: None):
    """Re-run analysis + chart generation on the mod's own ogg. With `video` (h264/vp9) and the
    original source file still on disk, the .usm movie is rebuilt as well."""
    meta = dict(mod.meta)
    fields = SongRequest.__dataclass_fields__
    req = SongRequest(**{k: v for k, v in meta.items() if k in fields})
    req.density, req.seed = density, seed
    if difficulties:
        req.difficulties = list(difficulties)
    if offset_ms is not None:
        req.offset_ms = offset_ms
    p = f"pv_{req.pv_id:03d}"
    ogg = os.path.join(mod.path, "rom", "sound", "song", p + ".ogg")
    rebuild_video = bool(video and video != "none" and ffmpeg and ffprobe and os.path.isfile(req.source))
    pr = Progress(progress, log)
    pr.stage(0.0, 0.4 if rebuild_video else 0.9, "Analizando la canción")
    a = analysis.analyze(ogg, pr)
    log(f"  BPM ≈ {a.bpm:.2f} ({'tempo constante' if a.constant_tempo else 'tempo variable'})")
    has_movie = bool(meta.get("has_movie")) or rebuild_video
    pr.stage(0.4 if rebuild_video else 0.9, 0.45 if rebuild_video else 1.0, "Generando notas")
    write_charts(mod.path, req.pv_id, req, a, has_movie, log)
    if rebuild_video:
        pr.stage(0.45, 0.99, f"Reconvirtiendo video → USM ({video.upper()})")
        os.makedirs(os.path.join(mod.path, "rom", "movie"), exist_ok=True)
        info = media.media_info(ffprobe, req.source)
        media.make_usm(ffmpeg, ffprobe, req.source, os.path.join(mod.path, "rom", "movie", p + ".usm"),
                       codec=video, duration=info["duration"], on_progress=pr)
        meta["video"] = video
    meta.update(density=density, seed=seed, difficulties=req.difficulties, offset_ms=req.offset_ms,
                bpm=round(a.bpm, 2), has_movie=has_movie)
    with open(os.path.join(mod.path, modloader.DM_META), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    pr.stage(1.0, 1.0, "Canción actualizada")
