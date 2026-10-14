"""Turns an Analysis into DIVA charts.

Note timing comes from onsets on the beat grid, buttons from the spectral band that hit, holds from
sustained sounds, multi-notes from full-band accents and slides from bright hits. Amounts, spacing and
layouts follow statistics measured on the game's own charts with dev/decompile.py and
dev/multi_patterns.py (aggregate numbers only):
  * flight time = 4 beats; consecutive notes 192 px apart per beat (48 px for 16ths)
  * single notes fly 1200 px with a 500 amplitude wave; multi-notes fly 880 px straight in (no wave)
  * multi-note templates: 4 = wide rectangle around the screen centre with corners coming in diagonally,
    3 = large triangle (apex up or down), 2 = row (from above/below) or compact vertical pair
  * chain slides: a piece every 1/8 beat, 36 px apart
"""
import itertools
import math
from dataclasses import dataclass, field

import numpy as np

from . import dsc
from .dsc import CIRCLE, CROSS, HOLD, SQUARE, TRIANGLE

SLIDE_L, SLIDE_R, CHAIN_L, CHAIN_R = 12, 13, 15, 16
LEVEL_WEIGHT = np.array([1.3, 1.0, 0.72, 0.35])  # bar, beat, eighth, sixteenth
X_MIN, X_MAX, Y_MIN, Y_MAX = 200, 1720, 210, 870
PX_PER_BEAT = 192
SINGLE_DISTANCE_PX = 1212
MULTI_DISTANCE_PX = 880
CHAIN_STEP_BEATS = 0.125
CHAIN_STEP_PX = 36


@dataclass
class DiffSpec:
    levels: tuple            # allowed grid levels
    presses_per_beat: float  # official average for the difficulty
    min_gap: float           # minimum spacing in beats
    max_run: int             # max consecutive notes at min_gap
    keep_rare: float         # chance that a □/△ stays (else × / ○); easy and normal use few of them
    holds_per_min: float
    multi_per_min: float
    multi_sizes: dict        # {buttons: share}
    pair_column_share: float  # share of 2-button multi-notes that are compact vertical pairs
    slides_per_min: float
    chains_per_min: float
    stars: tuple             # level = a + b * presses/s, clamped to [lo, hi]
    band_buttons: tuple = (CROSS, CIRCLE, SQUARE, TRIANGLE)  # button for low, low-mid, high-mid, high


# official easy charts are about 3/4 ○ and 1/4 ×; normal about half ○, half ×
EASY_BUTTONS = (CIRCLE, CROSS, CIRCLE, CIRCLE)
NORMAL_BUTTONS = (CIRCLE, CROSS, SQUARE, TRIANGLE)

# Values tuned with `dev/decompile.py compare` against the medians of the official charts.
# Normal/hard/extreme keep a few slides on purpose (official ones have none there).
DIFFS = {
    "easy": DiffSpec((0, 1, 2), 0.62, 0.5, 2, 0.08, 0, 0, {}, 0, 0, 0, (-0.6, 1.87, 1.0, 3.5), EASY_BUTTONS),
    "normal": DiffSpec((0, 1, 2), 0.79, 0.5, 3, 0.3, 2.1, 1.0, {2: 0.62, 3: 0.01, 4: 0.37}, 0, 0.5, 0,
                       (1.96, 1.16, 3.0, 5.5), NORMAL_BUTTONS),
    "hard": DiffSpec((0, 1, 2, 3), 0.92, 0.25, 3, 1.0, 7.8, 1.9, {2: 0.73, 3: 0.02, 4: 0.25}, 0, 1.5, 0.4,
                     (3.18, 1.03, 5.0, 8.0)),
    "extreme": DiffSpec((0, 1, 2, 3), 1.05, 0.25, 4, 1.0, 19, 10, {2: 0.86, 3: 0.06, 4: 0.08}, 0.6, 3, 1,
                        (4.8, 0.92, 6.5, 10.0)),
    "extra": DiffSpec((0, 1, 2, 3), 1.19, 0.25, 5, 1.0, 19, 19, {2: 0.88, 3: 0.03, 4: 0.09}, 0.55, 21, 5,
                      (5.06, 0.94, 7.0, 10.0)),
}

# Multi-note templates: (dx, dy, approach angle in degrees, 0 = from above, clockwise)
RECT_4 = [(-720, -240, 315), (720, -240, 45), (-720, 240, 225), (720, 240, 135)]
TRIANGLE_UP = [(0, -384, 0), (-480, 192, 225), (480, 192, 135)]
TRIANGLE_DOWN = [(0, 384, 180), (-480, -192, 315), (480, -192, 45)]
# where each button "points" on a controller: △ up, ○ right, × down, □ left
BUTTON_DIRECTION = {TRIANGLE: (0, -1), CIRCLE: (1, 0), CROSS: (0, 1), SQUARE: (-1, 0)}


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
    extra: list = field(default_factory=list)   # more buttons pressed at the same time
    multi: list = field(default_factory=list)   # [(button, x, y, angle)] once positioned
    slide: int = 0                               # 0, SLIDE_L/R or CHAIN_L/R
    chain_pieces: int = 0

    @property
    def type(self):
        if self.slide:
            return self.slide
        return self.button + (HOLD if self.hold else 0)


def minutes(a):
    return max(0.5, a.active.sum() / 4 * 60.0 / a.bpm / 60.0)


def select_times(a, spec, density, rng):
    step = 4  # grid points per beat
    min_gap = max(1, int(round(spec.min_gap * step)))
    usable = np.isin(a.grid_level, spec.levels) & a.active & (a.grid > 0.3) & (a.grid < a.duration - 0.6)
    score = (0.15 + a.strength) * LEVEL_WEIGHT[a.grid_level] * (0.55 + 0.9 * a.energy)
    score = score + 0.2 * (a.grid_level <= 1) * (spec.presses_per_beat <= 0.8)  # steady pulse on easy charts
    score = score * (1.0 + 0.05 * rng.standard_normal(len(score)))
    score[~usable] = -1
    score[(a.strength < 0.08) & (a.grid_level >= 2)] = -1

    active_beats = a.active.sum() / step
    target = int(active_beats * spec.presses_per_beat * density)
    taken = np.zeros(len(score), bool)
    count = 0
    for g in np.argsort(-score):
        if count >= target or score[g] <= 0:
            break
        lo, hi = max(0, g - min_gap + 1), g + min_gap
        if taken[lo:hi].any():
            continue
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
    max_hole = int(step * 4)
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
    # strong for that moment (spec.band_buttons maps low, low-mid, high-mid, high)
    raw = a.bands[idx]
    ranks = np.argsort(np.argsort(raw, axis=0), axis=0) / max(1, len(idx) - 1)
    band_button = spec.band_buttons
    notes = []
    prev_raw, prev_btn, same_count = None, None, 0
    for j, g in enumerate(idx):
        vec = ranks[j] + 0.15 * raw[j] / (raw[j].max() + 1e-9)
        order = np.argsort(-vec)
        btn = band_button[order[0]]
        if btn in (SQUARE, TRIANGLE) and rng.random() > spec.keep_rare:
            btn = CROSS if btn == SQUARE else CIRCLE
        n = Note(t=float(a.grid[g]), beat=float(a.grid_beat[g]), button=btn)
        if notes:
            gap = n.beat - notes[-1].beat
            sim = float(raw[j] @ prev_raw / (np.linalg.norm(raw[j]) * np.linalg.norm(prev_raw) + 1e-9))
            if gap <= 0.26 or (gap <= 0.51 and sim > 0.9):
                btn = prev_btn  # fast streams share a button, like official charts
            elif btn == prev_btn and same_count >= 4 and gap >= 1.0:
                for b in order[1:]:
                    alt = band_button[b]
                    if alt in (SQUARE, TRIANGLE) and spec.keep_rare < 0.5:
                        alt = CROSS if alt == SQUARE else CIRCLE
                    if alt != prev_btn:
                        btn = alt
                        break
            n.button = btn
        same_count = same_count + 1 if btn == prev_btn else 1
        prev_raw, prev_btn = raw[j], btn
        notes.append(n)
    return notes, ranks


def gaps(notes, i):
    prev_gap = notes[i].beat - notes[i - 1].beat if i else 99
    next_gap = notes[i + 1].beat - notes[i].beat if i + 1 < len(notes) else 99
    return prev_gap, next_gap


def assign_holds(a, spec, idx, notes):
    """The most sustained sounds become holds (official amount per minute). Other buttons may be
    pressed during a hold on hard and above, but not the held one."""
    quota = int(round(spec.holds_per_min * minutes(a)))
    if quota <= 0:
        return
    others_ok = spec.min_gap < 0.5
    candidates = []
    for i, (g, n) in enumerate(zip(idx, notes)):
        _prev_gap, next_gap = gaps(notes, i)
        same = next((m.beat - n.beat for m in notes[i + 1:] if m.button == n.button), 99)
        room = (same >= 1.0 and next_gap >= 0.5) if others_ok else next_gap >= 1.5
        if room and a.sustain[g] > 0.3:
            candidates.append((a.sustain[g], i))
    for _s, i in sorted(candidates, reverse=True)[:quota]:
        notes[i].hold = True


def assign_specials(a, spec, idx, notes, ranks, rng):
    """Multi-notes on the strongest full-band accents (bigger shapes on the biggest hits), slides on
    bright hits, chain slides on bright sustained sweeps. Slide direction follows the melody."""
    if not notes:
        return
    mins = minutes(a)
    breadth = ranks.min(axis=1)  # high when every band hits at once
    accent = np.array([a.strength[g] for g in idx]) * (0.5 + breadth)
    bright = ranks[:, 3] - ranks[:, :2].mean(axis=1)
    pitch_slope = np.gradient(a.pitch)

    # multi-notes
    quota = int(round(spec.multi_per_min * mins))
    if quota and spec.multi_sizes:
        order = [i for i in np.argsort(-accent) if not notes[i].hold and min(gaps(notes, i)) >= 0.5]
        chosen = order[:quota]
        sizes = []
        for size in (4, 3):
            sizes += [size] * int(round(quota * spec.multi_sizes.get(size, 0)))
        sizes += [2] * (len(chosen) - len(sizes))
        for i, size in zip(chosen, sizes):  # strongest accents get the biggest shapes
            if size == 4 and min(gaps(notes, i)) < 1.0:
                size = 3 if spec.multi_sizes.get(3) else 2
            others = [b for b in (TRIANGLE, CIRCLE, CROSS, SQUARE) if b != notes[i].button]
            rng.shuffle(others)
            notes[i].extra = others[:size - 1]

    # chain slides, then single slides
    dropped = set()

    def direction(i):
        return 1 if pitch_slope[min(idx[i], len(pitch_slope) - 1)] >= 0 else -1

    quota = int(round(spec.chains_per_min * mins))
    if quota:
        cands = []
        for i, g in enumerate(idx):
            if notes[i].hold or notes[i].extra or i in dropped:
                continue
            _p, next_gap = gaps(notes, i)
            if next_gap >= 1.0 or spec.max_run >= 4:
                cands.append((bright[i] + a.sustain[g], i))
        for _score, i in sorted(cands, reverse=True)[:quota]:
            if i in dropped:
                continue
            n = notes[i]
            _p, next_gap = gaps(notes, i)
            length = min(2.5, max(0.5, next_gap - 0.5)) if next_gap >= 1.0 else 1.0
            n.slide = CHAIN_R if direction(i) > 0 else CHAIN_L
            n.chain_pieces = max(4, min(21, int(length / CHAIN_STEP_BEATS)))
            k = i + 1
            while k < len(notes) and notes[k].beat - n.beat <= n.chain_pieces * CHAIN_STEP_BEATS + 0.25:
                dropped.add(k)  # the chain takes this stretch on dense charts
                k += 1

    quota = int(round(spec.slides_per_min * mins))
    if quota:
        cands = [(bright[i], i) for i in range(len(notes))
                 if not (notes[i].hold or notes[i].extra or notes[i].slide or i in dropped)
                 and min(gaps(notes, i)) >= 0.25]
        for _b, i in sorted(cands, reverse=True)[:quota]:
            notes[i].slide = SLIDE_R if direction(i) > 0 else SLIDE_L

    if dropped:
        notes[:] = [n for k, n in enumerate(notes) if k not in dropped]


def best_slots(buttons, offsets):
    """Assigns buttons to template slots so each button sits where it points on a controller."""
    best, best_score = None, -1e9
    for perm in itertools.permutations(range(len(offsets))):
        score = 0.0
        for button, slot in zip(buttons, perm):
            dx, dy = offsets[slot][0], offsets[slot][1]
            norm = math.hypot(dx, dy) or 1.0
            bx, by = BUTTON_DIRECTION[button % 4]
            score += (dx * bx + dy * by) / norm
        if score > best_score:
            best, best_score = perm, score
    return [(b, offsets[s]) for b, s in zip(buttons, best)]


def multi_template(size, spec, rng, x, y):
    """(centre_x, centre_y, [(dx, dy, angle)]) for a multi-note near the current path position."""
    if size == 4:
        return 960.0, 500.0, RECT_4
    if size == 3:
        up = rng.random() < 0.55
        cx = 720.0 if x < 960 else 1200.0
        return cx, (560.0 if up else 400.0), (TRIANGLE_UP if up else TRIANGLE_DOWN)
    if rng.random() < spec.pair_column_share:
        half = float(rng.choice([48, 96, 144], p=[0.45, 0.35, 0.2]))
        top, bottom = (45, 135) if rng.random() < 0.5 else (315, 225)
        cy = min(max(y, Y_MIN + half), Y_MAX - half)
        return x, cy, [(0, -half, top), (0, half, bottom)]
    half = float(rng.choice([240, 480, 720], p=[0.55, 0.2, 0.25]))
    left, right = (340, 20) if rng.random() < 0.5 else (200, 160)
    cx = 960.0 if half >= 720 else min(max(x, X_MIN + half), X_MAX - half)
    return cx, y, [(-half, 0, left), (half, 0, right)]


def assign_positions(a, spec, notes, rng):
    """Notes follow curved paths 192 px apart per beat; multi-notes use the official templates and the
    path continues from their centre."""
    x, y = 480.0, 540.0
    theta = 0.0
    curve = math.radians(8)
    recent = []  # (time, x, y) of notes still on screen, excluding the previous one
    last = None
    freq = 2
    for i, n in enumerate(notes):
        gap = n.beat - notes[i - 1].beat if i else 99
        g = min(int(np.searchsorted(a.grid, n.t)), len(a.pitch) - 1)
        new_phrase = i == 0 or gap >= 2 or (int(n.beat) - a.downbeat_phase) % 8 == 0 and gap >= 1
        if new_phrase:
            target_y = Y_MAX - a.pitch[g] * (Y_MAX - Y_MIN)
            dx = 1.0 if x < 960 else -1.0
            if rng.random() < 0.3:
                dx = -dx
            theta = math.atan2((target_y - y) / 400.0, dx)
            curve = math.radians(rng.uniform(4, 16)) * rng.choice([-1, 1])
            freq = 2 if rng.random() < 0.6 else -2  # official charts: about 60 % / 40 %
        step = 0 if i == 0 else min(860.0, max(48.0, PX_PER_BEAT * gap))
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
            if step == 0 or all(math.hypot(nx - px, ny - py) > 90 for pt, px, py in recent if n.t - pt < 2.5):
                break
        theta, x, y = th, nx, ny

        if n.chain_pieces:
            run = n.chain_pieces * CHAIN_STEP_PX
            x = max(x, X_MIN + run) if n.slide == CHAIN_L else min(x, X_MAX - run)
        if n.extra:
            cx, cy, template = multi_template(1 + len(n.extra), spec, rng, x, y)
            placed = best_slots([n.type] + list(n.extra), template)
            n.multi = [(b, cx + dx, cy + dy, ang) for b, (dx, dy, ang) in placed]
            x, y = cx, cy
        n.x, n.y = x, y
        if last is not None:
            recent = [r for r in recent if n.t - r[0] < 2.5] + [last]
        last = (n.t, x, y)
        if i and gap <= 0.51:
            n.angle = (notes[i - 1].angle + rng.uniform(-2, 2)) % 360  # streams fly in from the same side
        else:
            n.angle = (math.degrees(math.atan2(x - 960, -(y - 540))) + rng.uniform(-25, 25)) % 360
        n.freq = freq



def estimate_stars(notes, a, spec):
    """Official charts: level ≈ a + b · presses per second (fitted per difficulty)."""
    active_s = max(1.0, a.active.sum() / 4 * 60.0 / a.bpm)
    presses = sum(1 + len(n.extra) for n in notes if not n.chain_pieces) + sum(1 for n in notes if n.chain_pieces)
    base, per, lo, hi = spec.stars
    stars = base + per * presses / active_s
    return float(min(hi, max(lo, round(stars * 2) / 2)))


def generate(a, difficulty, density=1.0, seed=0):
    spec = DIFFS[difficulty]
    rng = np.random.default_rng(seed * 10 + list(DIFFS).index(difficulty))
    idx = select_times(a, spec, density, rng)
    notes, ranks = assign_buttons(a, spec, idx, rng)
    assign_holds(a, spec, idx, notes)
    assign_specials(a, spec, idx, notes, ranks, rng)
    assign_positions(a, spec, notes, rng)
    return notes, estimate_stars(notes, a, spec)


def flying_time(bpm):
    """Official charts always fly 4 beats; the tempo is folded into 120-240 BPM first so that songs
    analysed at half tempo do not get very slow notes."""
    while bpm >= 240:
        bpm /= 2
    while bpm < 120:
        bpm *= 2
    return min(2.0, max(1.0, 240.0 / bpm))


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
                         n.angle, distance_px=SINGLE_DISTANCE_PX, frequency=n.freq)
        elif n.multi:
            # each note comes straight in from outside its corner: the incoming notes form a bigger
            # copy of the shape that closes onto the targets
            for button, x, y, angle in n.multi:
                s.target(spawn, button, x, y, angle, distance_px=MULTI_DISTANCE_PX, frequency=0)
        else:
            s.target(spawn, n.type, n.x, n.y, n.angle, distance_px=SINGLE_DISTANCE_PX, frequency=n.freq)
    s.add(lead + a.duration + 0.3, "PV_END")
    return s
