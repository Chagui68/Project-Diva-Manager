"""Analysis + chart generation on synthetic songs: tempo, beat alignment, DSC round trip, pv_db.
Run: python tests\\test_charts.py"""
import math
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from divamgr import analysis, chartgen, dsc, pvdb  # noqa: E402
from synth import make_song  # noqa: E402

NAMES = {0: "△", 1: "○", 2: "×", 3: "□"}


def check_multi_shapes(targets):
    """Simultaneous notes use the official layouts: 2 = row or vertical pair, 3 = triangle (apex +
    level base, apex centred), 4 = rectangle."""
    groups = {}
    for t, typ, x, y in targets:
        if typ < 8:
            groups.setdefault(round(t, 4), []).append((round(x), round(y), typ))
    for pts in groups.values():
        xs = sorted({p[0] for p in pts})
        ys = sorted({p[1] for p in pts})
        assert len({p[2] for p in pts}) == len(pts), "botones repetidos en una nota múltiple"
        if len(pts) == 2:
            assert (len(ys) == 1 and len(xs) == 2) or (len(xs) == 1 and len(ys) == 2), f"pareja rara: {pts}"
        elif len(pts) == 3:
            assert len(ys) == 2 and len(xs) == 3, f"no es triángulo: {pts}"
            by_y = {y: [p for p in pts if p[1] == y] for y in ys}
            apex = next(v for v in by_y.values() if len(v) == 1)[0]
            base = next(v for v in by_y.values() if len(v) == 2)
            assert abs(apex[0] - (base[0][0] + base[1][0]) / 2) <= 1, "vértice no centrado"
        elif len(pts) == 4:
            assert len(xs) == 2 and len(ys) == 2, f"no es rectángulo: {pts}"


def check_multi_approach(path):
    """Notes of a multi-note fly in straight (no wave) from 880 px, each from outside the shape, so the
    incoming notes form a bigger figure that closes onto the targets."""
    groups = {}
    for t, typ, x, y, angle, dist, _amp, freq in dsc.read_targets(path, full=True):
        if typ < 8:
            groups.setdefault(round(t, 4), []).append((x, y, angle, dist, freq))
    checked = 0
    for pts in groups.values():
        if len(pts) < 2:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        for x, y, angle, dist, freq in pts:
            assert freq == 0, "las notas múltiples entran en línea recta"
            assert abs(dist - chartgen.MULTI_DISTANCE_PX) < 1, dist
            sx = x + math.sin(math.radians(angle)) * dist
            sy = y - math.cos(math.radians(angle)) * dist
            assert math.hypot(sx - cx, sy - cy) > math.hypot(x - cx, y - cy) + 400, "la nota no entra desde fuera"
        checked += 1
    return checked


def check_song(tmp, bpm):
    wav = make_song(os.path.join(tmp, f"synth_{int(bpm)}.wav"), bpm)
    a = analysis.analyze(wav)
    beat = 60 / bpm
    tb = a.beats[(a.beats > 4 * beat + 0.1) & (a.beats < a.duration - 3)]
    err = np.abs(tb - np.round(tb / beat) * beat)
    print(f"{bpm:5.0f} BPM -> {a.bpm:7.2f}  error de pulso máx {err.max() * 1000:.1f} ms")
    assert abs(a.bpm - bpm) < 0.5, "tempo incorrecto"
    assert err.max() < 0.005, "pulso desalineado"

    for d in pvdb.DIFFICULTIES:
        notes, stars = chartgen.generate(a, d)
        path = os.path.join(tmp, f"{d}.dsc")
        chartgen.build_script(a, notes, has_movie=True).save(path)
        back = dsc.read_targets(path)
        expected = sum(n.chain_pieces or 1 + len(n.extra) for n in notes)
        assert len(back) == expected, (len(back), expected)
        grid = beat * chartgen.CHAIN_STEP_BEATS  # chain pieces sit on 32nd notes, the rest on 16ths
        assert max(abs(h - round(h / grid) * grid) for h, *_ in back) < 0.002, "nota fuera de la rejilla"
        check_multi_shapes(back)
        check_multi_approach(path)
        types = {t for _, t, *_ in back}
        assert types <= set(range(8)) | {chartgen.SLIDE_L, chartgen.SLIDE_R, chartgen.CHAIN_L, chartgen.CHAIN_R}
        assert max(len(n.extra) for n in notes) + 1 <= max([1] + list(chartgen.DIFFS[d].multi_sizes))
        btn = {NAMES[k]: sum(n.button == k for n in notes) for k in range(4)}
        multi = {k: sum(len(n.extra) + 1 == k for n in notes) for k in (2, 3, 4)}
        slides = sum(n.slide in (chartgen.SLIDE_L, chartgen.SLIDE_R) for n in notes)
        chains = sum(bool(n.chain_pieces) for n in notes)
        print(f"   {d:8s} {len(notes):4d} notas {sum(n.hold for n in notes):3d} holds  múltiples {multi}  "
              f"desliz {slides:2d} cadenas {chains:2d}  ★{stars}  {btn}")
    return a


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for bpm in (97.0, 128.0, 174.0):
            a = check_song(tmp, bpm)
        db = pvdb.build(9999, "Test", "Tester", a.bpm, {"easy": 2, "hard": 6.5}, a.sabi_start, a.sabi_len)
        keys = [line.split("=")[0] for line in db.splitlines()]
        assert keys == sorted(keys, key=lambda k: k.encode()), "pv_db sin ordenar"
    print("\nTODO OK")


if __name__ == "__main__":
    main()
