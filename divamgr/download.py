"""Video download by URL (YouTube and other sites supported by yt-dlp) for importing as songs.
Only for videos the user has the right to download and use."""
import importlib
import importlib.util
import os
import re
import subprocess
import sys

from . import paths

URL_RE = re.compile(r"^https?://\S+$", re.I)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DEFAULT_DIR = os.path.join(paths.APP_DIR, "downloads")


def available():
    return importlib.util.find_spec("yt_dlp") is not None


def install(log=print):
    """pip install --user yt-dlp with the running Python."""
    log("Instalando yt-dlp con pip…")
    out = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", "yt-dlp"],
                         capture_output=True, text=True, creationflags=NO_WINDOW)
    if out.returncode:
        raise RuntimeError(out.stderr.strip()[-600:] or "pip falló")
    importlib.invalidate_caches()
    log("yt-dlp instalado.")


def parse_urls(text):
    """Valid URLs, one per line or separated by spaces; returns (urls, invalid)."""
    urls, invalid = [], []
    for token in text.split():
        (urls if URL_RE.match(token) else invalid).append(token)
    return list(dict.fromkeys(urls)), invalid


def split_title(title, artist=""):
    """'Artist - Title [Official MV]' -> ('Title', 'Artist')."""
    title = re.sub(r"\s*[\[(【](official|mv|pv|video|music video|lyrics?|audio|4k|hd)[^\])】]*[\])】]", "",
                   title, flags=re.I).strip()
    if not artist and " - " in title:
        artist, title = [s.strip() for s in title.split(" - ", 1)]
    return title, artist


class _Logger:
    def __init__(self, log):
        self.log = log

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.log("  aviso: " + msg)

    def error(self, msg):
        self.log("  " + msg)


def probe(url):
    """Title, artist and duration (s) of a video without downloading it."""
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
            "logger": _Logger(lambda m: None)}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    artist = info.get("artist") or info.get("creator") or ""
    title, artist = split_title(info.get("track") or info.get("title") or "", artist)
    return title, artist or info.get("uploader", ""), float(info.get("duration") or 0)


def download(url, out_dir, ffmpeg, progress=lambda f: None, log=print):
    """Downloads one video as .mp4 (max 720p, the movie resolution used in game). Returns (path, title, artist)."""
    import yt_dlp

    os.makedirs(out_dir, exist_ok=True)

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                progress(min(1.0, d.get("downloaded_bytes", 0) / total))

    opts = {
        "format": "bv*[height<=720]+ba/b[height<=720]/b",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(out_dir, "%(uploader)s - %(title)s [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,
        "progress_hooks": [hook],
        "logger": _Logger(log),
        "quiet": True,
        "no_warnings": True,
    }
    if ffmpeg:
        opts["ffmpeg_location"] = os.path.dirname(ffmpeg)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloads = info.get("requested_downloads") or []
        path = downloads[0]["filepath"] if downloads else ydl.prepare_filename(info)
    artist = info.get("artist") or info.get("creator") or ""
    title, artist = split_title(info.get("track") or info.get("title") or "", artist)
    return path, title, artist or info.get("uploader", "")
