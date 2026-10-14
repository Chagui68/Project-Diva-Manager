"""Most common multi-note layouts in the official charts: offsets from the group centre, approach angle
and distance of every note, plus where the centres sit. Aggregate counts only.
Run: python dev\\multi_patterns.py"""
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decompile import chart_notes, charts, open_game  # noqa: E402
from divamgr import gamedata  # noqa: E402


def main():
    g = open_game()
    patterns = {2: collections.Counter(), 3: collections.Counter(), 4: collections.Counter()}
    centres = {2: collections.Counter(), 3: collections.Counter(), 4: collections.Counter()}
    for (pv, d), (c, n) in charts(g).items():
        try:
            _sig, events = gamedata.decode_dsc(c.read(n))
        except ValueError:
            continue
        _bpm, notes = chart_notes(events)
        groups = collections.defaultdict(list)
        for note in notes:
            if note["type"] < 8:
                groups[round(note["t"], 4)].append(note)
        for grp in groups.values():
            k = len(grp)
            if k not in patterns:
                continue
            cx = sum(p["x"] for p in grp) / k
            cy = sum(p["y"] for p in grp) / k
            key = tuple(sorted((round(p["x"] - cx), round(p["y"] - cy), round(p["angle"]), round(p["dist"]))
                               for p in grp))
            patterns[k][key] += 1
            centres[k][(round(cx / 40) * 40, round(cy / 40) * 40)] += 1
    g.close()
    for k in (2, 3, 4):
        total = sum(patterns[k].values())
        print(f"\n=== {k} notas a la vez: {total} grupos, {len(patterns[k])} patrones distintos")
        for key, count in patterns[k].most_common(10):
            pts = "  ".join(f"({dx:+5d},{dy:+5d}) ang {a:3d}° d{dist}" for dx, dy, a, dist in key)
            print(f"  {count:5d}x  {pts}")
        print("  centros más comunes:", centres[k].most_common(6))


if __name__ == "__main__":
    main()
