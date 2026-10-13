"""Checks everything Diva Manager needs. Run: python dev\\check_env.py"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def line(ok, name, detail=""):
    print(f"{'OK ' if ok else 'FALTA'}  {name}" + (f"  ({detail})" if detail else ""))
    return ok


def main():
    print("Python:", sys.executable)
    missing = [m for m in ("numpy", "scipy", "soundfile", "soxr", "wannacri") if not importlib.util.find_spec(m)]
    line(not missing, "paquetes Python", ", ".join(missing) or "numpy scipy soundfile soxr wannacri")
    line(bool(importlib.util.find_spec("yt_dlp")), "yt-dlp (opcional, para URLs)")
    if missing:
        print("\n  Instala con: python -m pip install --user -r requirements.txt")
        return

    from divamgr import modloader, paths
    s = paths.load_settings()
    ff, fp = paths.find_tool("ffmpeg", s.get("ffmpeg", "")), paths.find_tool("ffprobe", s.get("ffmpeg", ""))
    line(bool(ff and fp), "FFmpeg + ffprobe", ff or "winget install Gyan.FFmpeg")
    line(os.path.isfile(modloader.LOADER_BUILD), "DivaLoader compilado", modloader.LOADER_BUILD)
    game = s.get("game_dir") if paths.is_game_dir(s.get("game_dir")) else paths.find_game()
    if line(bool(game), "juego", game or "no encontrado"):
        line(modloader.loader_kind(game) == modloader.LOADER_NAME, "DivaLoader instalado en el juego",
             modloader.loader_kind(game) or "sin dinput8.dll")
        mods = modloader.list_mods(game)
        line(True, "mods", ", ".join(m.folder for m in mods) or "ninguno")


if __name__ == "__main__":
    main()
