"""Command-line "Actualizar todas": re-analyses every Diva Manager song (sync, all difficulties incl.
Extra Extreme) and rebuilds the 720p movie when the original file exists. Also installs the compiled
DivaLoader. Run with the game closed: python dev\\update_all.py [pv_id ...] [--sin-video]"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from divamgr import modloader, paths, pvdb, songs  # noqa: E402


def main():
    game = paths.find_game()
    settings = paths.load_settings()
    ff = paths.find_tool("ffmpeg", settings.get("ffmpeg", ""))
    fp = paths.find_tool("ffprobe", settings.get("ffmpeg", ""))
    if os.path.isfile(modloader.LOADER_BUILD):
        modloader.install_loader(game)
    only = {int(a) for a in sys.argv[1:] if a.isdigit()}  # optional PV IDs to limit the update
    keep_video = "--sin-video" in sys.argv  # charts only, keep the current .usm
    managed = [m for m in modloader.list_mods(game) if m.managed and (not only or m.meta.get("pv_id") in only)]
    failed = []
    for n, mod in enumerate(managed, 1):
        md = mod.meta
        t0 = time.time()
        print(f"\n[{n}/{len(managed)}] {mod.name}", flush=True)
        try:
            songs.regenerate(mod, md.get("density", 1.0), md.get("seed", 0), list(pvdb.DIFFICULTIES),
                             offset_ms=md.get("offset_ms", 0.0),
                             video=None if keep_video else md.get("video", "h264"),
                             ffmpeg=ff, ffprobe=fp, log=lambda m: print(m, flush=True))
            print(f"  ({time.time() - t0:.0f} s)", flush=True)
        except Exception as e:  # keep going with the rest
            failed.append(mod.name)
            print(f"  ERROR: {e}", flush=True)
    print(f"\nActualizadas {len(managed) - len(failed)} de {len(managed)}" +
          (f". Fallaron: {', '.join(failed)}" if failed else ""))


if __name__ == "__main__":
    main()
