"""Chart statistics for imported songs (nothing is written). Run: python dev\\chart_report.py [carpeta_mods]"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from divamgr import analysis, chartgen, modloader, paths, pvdb  # noqa: E402


def main():
    mods = sys.argv[1] if len(sys.argv) > 1 else modloader.mods_dir(paths.find_game())
    for meta_path in sorted(glob.glob(os.path.join(mods, "*", modloader.DM_META))):
        meta = json.load(open(meta_path, encoding="utf-8"))
        ogg = os.path.join(os.path.dirname(meta_path), "rom", "sound", "song", f"pv_{meta['pv_id']:03d}.ogg")
        a = analysis.analyze(ogg)
        print(f"{meta['title'][:40]}  ({a.bpm:.2f} BPM, vuelo {chartgen.flying_time(a.bpm):.2f} s)")
        for d in pvdb.DIFFICULTIES:
            notes, stars = chartgen.generate(a, d)
            multi = [sum(len(n.extra) + 1 == k for n in notes) for k in (2, 3, 4)]
            slides = sum(n.slide in (chartgen.SLIDE_L, chartgen.SLIDE_R) for n in notes)
            chains = sum(bool(n.chain_pieces) for n in notes)
            print(f"   {pvdb.DIFF_LABELS[d]:13s} {len(notes):4d} notas  holds {sum(n.hold for n in notes):3d}  "
                  f"x2/x3/x4 {multi}  desliz {slides:3d}  cadenas {chains:2d}  ★{stars}")


if __name__ == "__main__":
    main()
