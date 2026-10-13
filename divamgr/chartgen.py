"""Turns an Analysis into DIVA charts: note timing from onsets on the beat grid, buttons from the
spectral band that hit, holds on sustained sounds, multi-notes on full-band accents, slides (L/R
triggers) on bright hits and sweeps, positions flowing with melody brightness."""
import math
from dataclasses import dataclass, field

import numpy as np

from . import dsc
from .dsc import CIRCLE, CROSS, HOLD, SQUARE, TRIANGLE

SLIDE_L, SLIDE_R, CHAIN_L, CHAIN_R = 12, 13, 15, 16
LEVEL_WEIGHT = np.array([1.3, 1.0, 0.72, 0.5])  # bar, beat, eighth, sixteenth
X_MIN, X_MAX, Y_MIN, Y_MAX = 200, 1720, 210, 870
CHAIN_STEP_BEATS = 0.125  # one chain piece every 32nd note
CHAIN_STEP_PX = 56

# Multi-note shapes (offsets in px from the note position, y grows downwards), so the number of
# buttons can be read from the shape: 2 = row, 3 = triangle, 4 = square.
MULTI_SHAPES = {
    2: [(-80, 0), (80, 0)],
    3: [(0, -95), (-95, 70), (95, 70)],              # top, bottom-left, bottom-right
    4: [(-80, -80), (80, -80), (-80, 80), (80, 80)],  # top-left, top-right, bottom-left, bottom-right
}
# Where each button prefers to sit, like a controller's face buttons (△ up, ○ right, × down, □ left).
SLOT_PREFERENCE = {
    2: {SQUARE: 0, CROSS: 0, TRIANGLE: 1, CIRCLE: 1},
    3: {TRIANGLE: 0, SQUARE: 1, CROSS: 1, CIRCLE: 2},
    4: {SQUARE: 0, TRIANGLE: 1, CROSS: 2, CIRCLE: 3},
}


def multi_layout(buttons):
    """[(button, (dx, dy))] for a multi-note; a single button stays where it is."""
    if len(buttons) < 2:
        return [(buttons[0], (0, 0))]
    shape = MULTI_SHAPES[len(buttons)]
    preference = SLOT_PREFERENCE[len(buttons)]
    free = list(range(len(shape)))
    placed = []
    # buttons with a clear favourite slot first, then the rest fill what is left
    for button in sorted(buttons, key=lambda b: preference.get(b % 4, 9)):
        want = preference.get(button % 4, free[0])
        slot = want if want in free else free[0]
        free.remove(slot)
        placed.append((button, shape[slot]))
    return placed


@dataclass
class DiffSpec:
    levels: tuple          # allowed grid levels
    beats_per_note: float  # average spacing
    min_gap: float         # minimum spacing in beats
    buttons: tuple         # button per band: low, low-mid, high-mid, high
    hold_gap: float        # beats of free space needed after a hold
    hold_rate: float
    stars: tuple           # (base, per-nps, min, max)
    max_run: int           # max consecutive notes at min_gap
    multi_rate: float = 0.0   # share of the strongest full-band accents played as multi-notes
    max_multi: int = 1        # buttons pressed together at most
    slide_rate: float = 0.0   # share of bright (cymbal/high) hits turned into L/R slides
    chain_rate: float = 0.0   # share of bright sustained sweeps turned into chain slides


DIFFS = {
    "easy": DiffSpec((0, 1), 2.0, 1.0, (CROSS, CROSS, CIRCLE, CIRCLE), 2.0, 0.35, (1.0, 1.0, 1.0, 3.5), 2),
    "normal": DiffSpec((0, 1, 2), 1.25, 0.5, (CROSS, CIRCLE, TRIANGLE, TRIANGLE), 2.0, 0.3, (2.0, 1.0, 3.0, 5.5), 2,
                       multi_rate=0.25, max_multi=2, slide_rate=0.12),
    "hard": DiffSpec((0, 1, 2), 0.8, 0.5, (CROSS, CIRCLE, SQUARE, TRIANGLE), 1.5, 0.25, (3.0, 1.0, 5.0, 8.0), 4,
                     multi_rate=0.4, max_multi=3, slide_rate=0.2, chain_rate=0.3),
    "extreme": DiffSpec((0, 1, 2, 3), 0.52, 0.25, (CROSS, CIRCLE, SQUARE, TRIANGLE), 1.5, 0.2, (4.0, 0.9, 6.5, 10.0),
                        4, multi_rate=0.55, max_multi=4, slide_rate=0.25, chain_rate=0.45),
    "extra": DiffSpec((0, 1, 2, 3), 0.42, 0.25, (CROSS, CIRCLE, SQUARE, TRIANGLE), 1.5, 0.2, (4.5, 0.9, 7.0, 10.0),
                      6, multi_rate=0.7, max_multi=4, slide_rate=0.3, chain_rate=0.6),
}


@dataclass
class Note:
    t: float
    beat: float
    button: int
    hold: bool = False
    x: float = 960.0
    y: float = 540.0
    angle: float = 0.0
    freq: int = 2
    extra: list = field(default_factory=list)  # more buttons pressed at the same time
    slide: int = 0                              # 0, SLIDE_L/R or CHAIN_L/R
    chain_pieces: int = 0

    @property
    def type(self):
        if self.slide:
            return self.slide
        return self.button + (HOLD if self.hold else 0)


def select_times(a, spec, density, rng):
    step = 4  # grid points per beat
    min_gap = max(1, int(round(spec.min_gap * step)))
    usable = np.isin(a.grid_level, spec.levels) & a.active & (a.grid > 0.3) & (a.grid < a.duration - 0.6)
    score = (0.15 + a.strength) * LEVEL_WEIGHT[a.grid_level] * (0.55 + 0.9 * a.energy)
    if spec.min_gap >= 1.0:
        score = score + 0.25 * (a.grid_level <= 1)  # keep a steady pulse on easy charts
    score = score * (1.0 + 0.05 * rng.standard_normal(len(score)))
    score[~usable] = -1
    score[(a.strength < 0.08) & (a.grid_level >= 2)] = -1

    active_beats = a.active.sum() / step
    target = int(active_beats / spec.beats_per_note * density)
    taken = np.zeros(len(score), bool)
    count = 0
    for g in np.argsort(-score):
        if count >= target or score[g] <= 0:
            break
        lo, hi = max(0, g - min_gap + 1), g + min_gap
        if taken[lo:hi].any():
            continue
        # limit dense runs
        if min_gap <= 2:
            run = 0
            k = g - min_gap
            while k >= 0 and taken[k]:
                run += 1
                k -= min_gap
            k = g + min_gap
            while k < len(taken) and taken[k]:
                run += 1
                k += min_gap
            if run >= spec.max_run:
                continue
        taken[g] = True
        count += 1

    # fill long silent stretches while the music is still playing
    max_hole = int(step * max(4, spec.beats_per_note * 3))
    filled = True
    while filled:
        filled = False
        idx = list(np.flatnonzero(taken))
        for p, q in zip(idx, idx[1:]):
            if q - p > max_hole:
                seg = np.arange(p + min_gap, q - min_gap + 1)
                seg = seg[(a.grid_level[seg] <= 1) & a.active[seg]]
                if len(seg):
                    taken[seg[np.argmax(score[seg])]] = True
                    filled = True
    return np.flatnonzero(taken)


def assign_buttons(a, spec, idx, rng):
    # rank each band among the chart's notes: a note's button is the band that is unusually
    # strong for that moment, so hats everywhere do not turn every note into the same button
    raw = a.bands[idx]
    ranks = np.argsort(np.argsort(raw, axis=0), axis=0) / max(1, len(idx) - 1)
    notes = []
    prev_raw, prev_btn, same_count = None, None, 0
    for j, g in enumerate(idx):
        vec = ranks[j] + 0.15 * raw[j] / (raw[j].max() + 1e-9)
        order = np.argsort(-vec)
        btn = spec.buttons[order[0]]
        n = Note(t=float(a.grid[g]), beat=float(a.grid_beat[g]), button=btn)
        if notes:
            gap = n.beat - notes[-1].beat
            sim = float(raw[j] @ prev_raw / (np.linalg.norm(raw[j]) * np.linalg.norm(prev_raw) + 1e-9))
            if gap <= 0.26 or (gap <= 0.51 and sim > 0.9):
                btn = prev_btn  # fast streams share a button, like official charts
            elif btn == prev_btn and same_count >= 4 and gap >= 1.0:
                for b in order[1:]:
                    if spec.buttons[b] != prev_btn:
                        btn = spec.buttons[b]
                        break
            n.button = btn
        same_count = same_count + 1 if btn == prev_btn else 1
        prev_raw, prev_btn = raw[j], btn
        notes.append(n)
    return notes, ranks


def assign_holds(a, spec, idx, notes, rng):
    """Sustained tones become holds. On easy/normal nothing else may come during the hold; on
    hard/extreme other buttons may be pressed meanwhile, but not the held one."""
    others_ok = spec.min_gap < 1.0 and spec.hold_gap < 2.0
    for i, (g, n) in enumerate(zip(idx, notes)):
        nxt = notes[i + 1].beat - n.beat if i + 1 < len(notes) else 99
        same = next((m.beat - n.beat for m in notes[i + 1:] if m.button == n.button), 99)
        room = (same >= spec.hold_gap and nxt >= 0.5) if others_ok else nxt >= spec.hold_gap
        s = a.sustain[g]
        if room and s > 0.75 and rng.random() < spec.hold_rate + 1.5 * (s - 0.75):
            n.hold = True


def _isolated(notes, i, beats):
    prev_gap = notes[i].beat - notes[i - 1].beat if i else 99
    next_gap = notes[i + 1].beat - notes[i].beat if i + 1 < len(notes) else 99
    return prev_gap >= beats and next_gap >= beats


def assign_specials(a, spec, idx, notes, ranks, rng):
    """Multi-notes on accents where every band hits at once (crash + kick + chord), slides on bright
    off-pulse hits, chain slides on bright sustained sweeps. Direction follows the melody."""
    if not len(notes):
        return
    breadth = ranks.min(axis=1)                      # high when all bands are strong together
    accent = np.array([a.strength[g] for g in idx]) * (0.5 + breadth)
    accent_cut, accent_3, accent_4 = np.percentile(accent, [88, 95, 98.5])
    bright = ranks[:, 3] - ranks[:, :2].mean(axis=1)  # high band stands out over bass/low-mid
    pitch_slope = np.gradient(a.pitch)
    dropped = set()  # notes swallowed by a chain slide on dense charts

    for i, (g, n) in enumerate(zip(idx, notes)):
        if n.hold or i in dropped:
            continue
        # multi-notes: 2..max_multi buttons together, more for stronger and wider accents
        if (spec.max_multi > 1 and accent[i] >= accent_cut and _isolated(notes, i, 0.5)
                and rng.random() < spec.multi_rate):
            count = 2 + (accent[i] >= accent_3) + (accent[i] >= accent_4)  # 3 and 4 only on the biggest hits
            count = min(spec.max_multi, count)
            others = [b for b in (TRIANGLE, CIRCLE, CROSS, SQUARE) if b != n.button]
            rng.shuffle(others)
            n.extra = others[:count - 1]
            continue
        if spec.slide_rate <= 0 or bright[i] < 0.35 or not _isolated(notes, i, 0.5):
            continue
        direction = 1 if pitch_slope[min(g, len(pitch_slope) - 1)] >= 0 else -1  # rising -> right
        next_gap = notes[i + 1].beat - n.beat if i + 1 < len(notes) else 99
        sweep = a.sustain[g] > 0.5 or bright[i] > 0.6  # ringing cymbal/synth after the hit
        if spec.chain_rate > 0 and sweep and next_gap >= 1.0 and rng.random() < spec.chain_rate:
            length = min(next_gap - 0.5, 2.0)
            n.slide = CHAIN_R if direction > 0 else CHAIN_L
            n.chain_pieces = max(4, int(length / CHAIN_STEP_BEATS))
        elif (spec.max_run >= 4 and spec.chain_rate > 0 and bright[i] > 0.55 and a.sustain[g] > 0.3
              and next_gap >= 0.5 and rng.random() < spec.chain_rate * 0.6):
            # dense chart: the chain takes the next beat, the notes inside it are removed
            n.slide = CHAIN_R if direction > 0 else CHAIN_L
            n.chain_pieces = 6
            k = i + 1
            while k < len(notes) and notes[k].beat - n.beat <= 1.0:
                dropped.add(k)
                k += 1
        elif rng.random() < spec.slide_rate:
            n.slide = SLIDE_R if direction > 0 else SLIDE_L
    if dropped:
        notes[:] = [n for k, n in enumerate(notes) if k not in dropped]


def assign_positions(a, notes, rng):
    x, y = 480.0, 540.0
    theta = 0.0
    curve = math.radians(8)
    recent = []
    for i, n in enumerate(notes):
        gap = n.beat - notes[i - 1].beat if i else 99
        g = int(np.searchsorted(a.grid, n.t))
        g = min(g, len(a.pitch) - 1)
        new_phrase = i == 0 or gap >= 2 or (int(n.beat) - a.downbeat_phase) % 8 == 0 and gap >= 1
        if new_phrase:
            target_y = Y_MAX - a.pitch[g] * (Y_MAX - Y_MIN)
            dx = 1.0 if x < 960 else -1.0
            if rng.random() < 0.3:
                dx = -dx
            theta = math.atan2((target_y - y) / 400.0, dx)
            curve = math.radians(rng.uniform(4, 16)) * rng.choice([-1, 1])
        step = 100 if gap <= 0.26 else 135 if gap <= 0.51 else min(380, 150 + 70 * (gap - 1))
        if i == 0:
            step = 0
        for attempt in range(8):
            th = theta + curve if attempt == 0 else theta + math.radians(45 * attempt) * (1 if attempt % 2 else -1)
            nx, ny = x + step * math.cos(th), y + step * math.sin(th)
            if nx < X_MIN or nx > X_MAX:
                th = math.pi - th
                nx = x + step * math.cos(th)
            if ny < Y_MIN or ny > Y_MAX:
                th = -th
                ny = y + step * math.sin(th)
            nx, ny = min(max(nx, X_MIN), X_MAX), min(max(ny, Y_MIN), Y_MAX)
            if all(math.hypot(nx - px, ny - py) > 110 for pt, px, py in recent if n.t - pt < 2.5) or step == 0:
                break
        theta, x, y = th, nx, ny

        # room for wide shapes: a multi-note row or a chain that runs sideways
        if n.extra:
            offsets = MULTI_SHAPES[len(n.extra) + 1]
            x = min(max(x, X_MIN - min(o[0] for o in offsets)), X_MAX - max(o[0] for o in offsets))
            y = min(max(y, Y_MIN - min(o[1] for o in offsets)), Y_MAX - max(o[1] for o in offsets))
        if n.chain_pieces:
            run = n.chain_pieces * CHAIN_STEP_PX
            x = max(x, X_MIN + run) if n.slide == CHAIN_L else min(x, X_MAX - run)
        n.x, n.y = x, y
        recent = [r for r in recent if n.t - r[0] < 2.5] + [(n.t, x, y)]
        if i and gap <= 0.51:
            n.angle = notes[i - 1].angle  # streams fly in from the same side
        else:
            n.angle = (math.degrees(math.atan2(x - 960, -(y - 540))) + rng.uniform(-25, 25)) % 360
        n.freq = 2 if i % 2 == 0 else -2


def estimate_stars(notes, a, spec):
    active_s = max(1.0, a.active.sum() / 4 * 60.0 / a.bpm)
    presses = sum(1 + len(n.extra) * 0.5 for n in notes)
    nps = presses / active_s
    base, per, lo, hi = spec.stars
    stars = base + per * nps
    return float(min(hi, max(lo, round(stars * 2) / 2)))


def generate(a, difficulty, density=1.0, seed=0):
    spec = DIFFS[difficulty]
    rng = np.random.default_rng(seed * 10 + list(DIFFS).index(difficulty))
    idx = select_times(a, spec, density, rng)
    notes, ranks = assign_buttons(a, spec, idx, rng)
    assign_holds(a, spec, idx, notes, rng)
    assign_specials(a, spec, idx, notes, ranks, rng)
    assign_positions(a, notes, rng)
    return notes, estimate_stars(notes, a, spec)


def flying_time(bpm):
    """Seconds a note takes to reach its target: one bar of the tempo folded into 90-180 BPM, so
    fast songs analysed at double tempo do not get notes flying twice as fast."""
    while bpm >= 180:
        bpm /= 2
    while bpm < 90:
        bpm *= 2
    return min(2.3, max(1.1, 240.0 / bpm))


def build_script(a, notes, has_movie, offset_ms=0.0, lead_in=None):
    """offset_ms moves every note later (+) or earlier (-) relative to the music."""
    ft = flying_time(a.bpm)
    lead = ft + 0.5 if lead_in is None else lead_in
    shift = offset_ms / 1000.0
    beat = 60.0 / a.bpm
    s = dsc.Script()
    s.add(0, "BAR_TIME_SET", int(round(a.bpm)), 3)
    s.add(0, "TARGET_FLYING_TIME", int(round(ft * 1000)))
    s.add(lead, "MUSIC_PLAY")
    if has_movie:
        s.add(lead, "MOVIE_PLAY", 1)
        s.add(lead, "MOVIE_DISP", 1)
    for n in notes:
        spawn = lead + n.t + shift - ft
        if n.chain_pieces:
            direction = 1 if n.slide == CHAIN_R else -1
            for k in range(n.chain_pieces):
                s.target(spawn + k * CHAIN_STEP_BEATS * beat, n.slide, n.x + direction * k * CHAIN_STEP_PX, n.y,
                         n.angle, frequency=n.freq)
            continue
        # multi-notes: row (2), triangle (3) or square (4) centred on the note, all from the same side
        for button, (dx, dy) in multi_layout([n.type] + list(n.extra)):
            s.target(spawn, button, n.x + dx, n.y + dy, n.angle, frequency=n.freq)
    s.add(lead + a.duration + 0.3, "PV_END")
    return s
