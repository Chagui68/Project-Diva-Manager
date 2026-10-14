"""Decompiler/analyser for the game's own charts (reads and decrypts your local installation).

  python dev\\decompile.py list                     songs, difficulties and levels
  python dev\\decompile.py dump <pv_id> <dificultad> chart as text in decompiled\\ (not part of the repo)
  python dev\\decompile.py stats                    aggregate statistics of every official chart,
                                                    saved to decompiled\\stats.json
  python dev\\decompile.py compare                  official charts vs the generated ones in mods\\

Difficulties: easy, normal, hard, extreme, extreme_1 (Extra Extreme)."""
import collections
import json
import math
import os
import re
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from divamgr import gamedata, paths  # noqa: E402

OUT_DIR = os.path.join(ROOT, "decompiled")
DIFFS = ("easy", "normal", "hard", "extreme", "extreme_1")
SCRIPT_RE = re.compile(r"rom/script/pv_(\d+)_(easy|normal|hard|extreme(?:_1)?)\.dsc$")
SLIDES = {12: "slide_L", 13: "slide_R", 15: "chain_L", 16: "chain_R"}


def open_game():
    game = paths.find_game()
    if not game:
        sys.exit("No se encontró el juego.")
    return gamedata.Game(game)


def charts(g):
    """{(pv_id, difficulty): (cpk, name)}; later archives override earlier ones."""
    found = {}
    for c, n in g.find(SCRIPT_RE.pattern):
        m = SCRIPT_RE.search(n)
        found[(int(m.group(1)), m.group(2))] = (c, n)
    return found


def level(db_entry, difficulty):
    group, index = ("extreme", "1") if difficulty == "extreme_1" else (difficulty, "0")
    raw = db_entry.get(f"difficulty.{group}.{index}.level", "")
    m = re.match(r"PV_LV_(\d+)_(\d)", raw)
    return int(m.group(1)) + int(m.group(2)) / 10 if m else None


def cmd_list(g):
    db = g.pv_db()
    have = charts(g)
    for pv in sorted(db):
        name = db[pv].get("song_name_en") or db[pv].get("song_name", "")
        lv = " ".join(f"{d[:2].upper()}{level(db[pv], d)}" for d in DIFFS if (pv, d) in have and level(db[pv], d))
        print(f"pv_{pv:03d}  {db[pv].get('bpm', '?'):>4} BPM  {name[:40]:40s} {lv}")


def cmd_dump(g, pv, difficulty):
    have = charts(g)
    if (pv, difficulty) not in have:
        sys.exit(f"No existe pv_{pv:03d}_{difficulty}.dsc")
    c, n = have[(pv, difficulty)]
    sig, events = gamedata.decode_dsc(c.read(n))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"pv_{pv:03d}_{difficulty}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {n}  signature 0x{sig:08X}\n")
        f.write(gamedata.dsc_text(events) + "\n")
    targets = sum(1 for _t, name, _p in events if name == "TARGET")
    print(f"{len(events)} comandos, {targets} TARGET -> {path}")


def chart_notes(events):
    """Targets with hit time (s), in beats, and the BPM of the chart."""
    bpm, fly, notes = None, None, []
    for t, name, p in events:
        if name == "BAR_TIME_SET":
            bpm = p[0]
            fly = 60.0 / p[0] * (p[1] + 1)
        elif name == "TARGET_FLYING_TIME":
            fly = p[0] / 1000
        elif name == "TARGET" and bpm:
            notes.append({"t": t + fly, "type": p[0], "x": p[1] / 250, "y": p[2] / 250, "angle": p[3] / 1000,
                          "dist": p[4] / 250, "amp": p[5], "freq": p[6], "fly": fly, "bpm": bpm})
    return bpm, notes


def shape_name(pts):
    """Classify a multi-note: row, column, diagonal, triangle, square/rectangle, other."""
    xs = sorted(p["x"] for p in pts)
    ys = sorted(p["y"] for p in pts)
    if len(pts) == 2:
        dx, dy = abs(pts[0]["x"] - pts[1]["x"]), abs(pts[0]["y"] - pts[1]["y"])
        return "fila" if dy < 20 else "columna" if dx < 20 else "diagonal"
    distinct_y = len({round(y / 20) for y in ys})
    distinct_x = len({round(x / 20) for x in xs})
    if len(pts) == 3:
        return "triángulo" if distinct_y == 2 and distinct_x >= 2 else "fila" if distinct_y == 1 else "otra"
    if len(pts) == 4:
        return "cuadrado" if distinct_x == 2 and distinct_y == 2 else "rombo" if distinct_x == 3 and distinct_y == 3 \
            else "fila" if distinct_y == 1 else "otra"
    return "otra"


def summary(values, digits=1):
    if not values:
        return None
    values = sorted(values)
    q = lambda f: values[min(len(values) - 1, int(f * len(values)))]  # noqa: E731
    return {"n": len(values), "media": round(statistics.mean(values), digits), "p10": round(q(0.1), digits),
            "mediana": round(q(0.5), digits), "p90": round(q(0.9), digits)}


def cmd_stats(g):
    db = g.pv_db()
    have = charts(g)
    per = {d: collections.defaultdict(list) for d in DIFFS}
    counters = {d: collections.defaultdict(collections.Counter) for d in DIFFS}
    for (pv, d), (c, n) in sorted(have.items()):
        try:
            _sig, events = gamedata.decode_dsc(c.read(n))
        except ValueError:
            counters[d]["errores"]["dsc ilegible"] += 1
            continue
        bpm, notes = chart_notes(events)
        if not notes:
            continue
        S, C = per[d], counters[d]
        beat = 60.0 / bpm
        S["vuelo_en_pulsos"].append(notes[0]["fly"] / beat)
        S["vuelo_s"].append(notes[0]["fly"])
        lv = level(db.get(pv, {}), d)
        groups = collections.OrderedDict()
        for note in notes:
            groups.setdefault(round(note["t"], 4), []).append(note)
        times = list(groups)
        span = times[-1] - times[0] if len(times) > 1 else 1
        presses = sum(len(v) for v in groups.values() if v[0]["type"] not in (15, 16))
        S["golpes_por_segundo"].append(presses / span)
        S["golpes_por_pulso"].append(presses / (span / beat))
        if lv:
            S["nivel_vs_gps"].append((lv, round(presses / span, 3)))
        # grid position of every group, in fractions of a beat
        first = times[0]
        for t in times:
            frac = ((t - first) / beat) % 1
            for name, at in (("pulso", 0), ("corchea", 0.5), ("semicorchea", 0.25), ("semicorchea", 0.75),
                             ("tresillo", 1 / 3), ("tresillo", 2 / 3)):
                if min(abs(frac - at), 1 - abs(frac - at)) < 0.02:
                    C["rejilla"][name] += 1
                    break
            else:
                C["rejilla"]["otra"] += 1
        prev = None
        for t, grp in groups.items():
            kinds = {n_["type"] for n_ in grp}
            if kinds & {15, 16}:
                C["tipos"]["cadena (eslabón)"] += len(grp)
                continue
            C["simultáneas"][len(grp)] += 1
            for n_ in grp:
                C["tipos"][SLIDES.get(n_["type"], "hold" if 4 <= n_["type"] < 8 else "botón" if n_["type"] < 4
                                      else f"tipo {n_['type']}")] += 1
                if n_["type"] < 4:
                    C["botón"]["△○×□"[n_["type"]]] += 1
            if len(grp) == 1:
                n_ = grp[0]
                S["distancia_simple"].append(n_["dist"])
                C["amplitud_simple"][n_["amp"]] += 1
                C["frecuencia_simple"][n_["freq"]] += 1
                if prev is not None:
                    gap = (t - prev[0]) / beat
                    step = math.hypot(n_["x"] - prev[1], n_["y"] - prev[2])
                    key = "≤1/4" if gap <= 0.26 else "1/2" if gap <= 0.51 else "1" if gap <= 1.01 else ">1"
                    S[f"paso_px_gap_{key}"].append(step)
                    if gap <= 0.51:
                        S["cambio_ángulo_en_ráfaga"].append(abs((n_["angle"] - prev[3] + 180) % 360 - 180))
                prev = (t, n_["x"], n_["y"], n_["angle"])
            else:
                C["forma"][f"{len(grp)}: {shape_name(grp)}"] += 1
                cx = sum(p["x"] for p in grp) / len(grp)
                cy = sum(p["y"] for p in grp) / len(grp)
                for p in grp:
                    r = math.hypot(p["x"] - cx, p["y"] - cy)
                    S[f"radio_multi_{len(grp)}"].append(r)
                    radial = math.degrees(math.atan2(p["x"] - cx, -(p["y"] - cy))) % 360
                    S["desvío_ángulo_vs_radial"].append(abs((p["angle"] - radial + 180) % 360 - 180))
                    S["distancia_multi"].append(p["dist"])
                    C["frecuencia_multi"][p["freq"]] += 1
                angles = [p["angle"] for p in grp]
                C["ángulos_multi"]["todas iguales" if max(angles) - min(angles) < 1 else "distintos"] += 1
                S["separación_x_multi"].append(max(p["x"] for p in grp) - min(p["x"] for p in grp))
                prev = (t, cx, cy, grp[0]["angle"])
        # chain slides: pieces per chain and spacing
        chain, last = [], None
        for note in notes:
            if note["type"] in (15, 16):
                if chain and (note["type"] != chain[-1]["type"] or note["t"] - chain[-1]["t"] > beat):
                    S["eslabones_por_cadena"].append(len(chain))
                    chain = []
                if chain:
                    S["eslabón_pulsos"].append((note["t"] - chain[-1]["t"]) / beat)
                    S["eslabón_px"].append(abs(note["x"] - chain[-1]["x"]))
                chain.append(note)
        if chain:
            S["eslabones_por_cadena"].append(len(chain))
        C["charts"]["total"] += 1

    report = {}
    for d in DIFFS:
        S, C = per[d], counters[d]
        if not C["charts"]["total"]:
            continue
        r = {k: summary(v) for k, v in S.items() if k != "nivel_vs_gps"}
        pairs = S["nivel_vs_gps"]
        if len(pairs) > 2:
            mx = statistics.mean(p[1] for p in pairs)
            my = statistics.mean(p[0] for p in pairs)
            slope = sum((p[1] - mx) * (p[0] - my) for p in pairs) / sum((p[1] - mx) ** 2 for p in pairs)
            r["nivel = a + b·golpes/s"] = {"a": round(my - slope * mx, 2), "b": round(slope, 2), "n": len(pairs)}
        for k, counter in C.items():
            r[k] = dict(counter.most_common(12))
        report[d] = r

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "stats.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    for d, r in report.items():
        print(f"\n=== {d} ({r['charts']['total']} charts)")
        for k, v in r.items():
            if k != "charts":
                print(f"  {k}: {v}")
    print(f"\nGuardado en {path}")


def chart_metrics(events):
    """Key per-chart numbers used to compare generated charts with official ones."""
    bpm, notes = chart_notes(events)
    if not notes:
        return None
    beat = 60.0 / bpm
    groups = collections.OrderedDict()
    for note in notes:
        groups.setdefault(round(note["t"], 4), []).append(note)
    times = list(groups)
    minutes = max(0.5, (times[-1] - times[0]) / 60)
    singles = [g_[0] for g_ in groups.values() if len(g_) == 1 and g_[0]["type"] < 8]
    steps = []
    for (t0, g0), (t1, g1) in zip(list(groups.items()), list(groups.items())[1:]):
        if len(g0) == len(g1) == 1 and abs((t1 - t0) / beat - 1) < 0.02:
            steps.append(math.hypot(g1[0]["x"] - g0[0]["x"], g1[0]["y"] - g0[0]["y"]))
    types = collections.Counter(n["type"] for n in notes)
    presses = sum(len(g_) for g_ in groups.values() if g_[0]["type"] not in (15, 16))
    return {
        "golpes/pulso": presses / ((times[-1] - times[0]) / beat),
        "paso 1 pulso px": statistics.median(steps) if steps else 0,
        "múltiples/min": sum(1 for g_ in groups.values() if len(g_) > 1) / minutes,
        "holds/min": sum(types[t] for t in range(4, 8)) / minutes,
        "desliz/min": (types[12] + types[13]) / minutes,
        "cadenas/min": sum(1 for a_, b_ in zip(notes, notes[1:]) if b_["type"] in (15, 16)
                           and a_["type"] != b_["type"]) / minutes,
        "% ○": 100 * types[1] / max(1, sum(types[t] for t in range(4))),
        "distancia simple": statistics.median([n["dist"] for n in singles]) if singles else 0,
    }


def cmd_compare(g):
    """Official charts vs the charts generated for the songs in mods/ (medians per difficulty)."""
    import glob
    from divamgr import modloader

    official = collections.defaultdict(list)
    for (pv, d), (c, n) in charts(g).items():
        try:
            m = chart_metrics(gamedata.decode_dsc(c.read(n))[1])
        except ValueError:
            continue
        if m:
            official[d].append(m)
    ours = collections.defaultdict(list)
    for path in glob.glob(os.path.join(modloader.mods_dir(paths.find_game()), "DivaManager_*", "rom", "script",
                                       "*.dsc")):
        m_ = SCRIPT_RE.search(path.replace("\\", "/"))
        with open(path, "rb") as f:
            m = chart_metrics(gamedata.decode_dsc(f.read())[1])
        if m_ and m:
            ours[m_.group(2)].append(m)
    for d in DIFFS:
        if not official[d] or not ours[d]:
            continue
        print(f"\n=== {d}  (oficiales {len(official[d])}, generados {len(ours[d])})")
        for key in official[d][0]:
            a = statistics.median(m[key] for m in official[d])
            b = statistics.median(m[key] for m in ours[d])
            print(f"  {key:18s} oficial {a:8.2f}   generado {b:8.2f}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("list", "dump", "stats", "compare"):
        sys.exit(__doc__)
    g = open_game()
    try:
        if sys.argv[1] == "list":
            cmd_list(g)
        elif sys.argv[1] == "dump":
            cmd_dump(g, int(sys.argv[2]), sys.argv[3])
        elif sys.argv[1] == "compare":
            cmd_compare(g)
        else:
            cmd_stats(g)
    finally:
        g.close()


if __name__ == "__main__":
    main()
