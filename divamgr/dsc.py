"""Writer for Future Tone style DSC chart scripts (the format Mega Mix+ reads).

Opcode ids and parameter counts follow the FT table of Open PD Script Editor (opcode_db/db.json).
File layout: int32 LE signature, then (opcode, params...) int32 LE words.
TIME is in 1/100000 s. TARGET positions use a 480000 x 270000 space (1920x1080 * 250),
angles are millidegrees with 0 = note flying in from above.
"""
import struct

SIGNATURE = 0x15122517  # script_format used by MM+ song mods (pv_db difficulty.*.script_format)

OPCODES = {
    "END": (0, 0),
    "TIME": (1, 1),
    "TARGET": (6, 7),
    "MUSIC_PLAY": (25, 0),
    "BAR_TIME_SET": (28, 2),
    "PV_END": (32, 0),
    "TARGET_FLYING_TIME": (58, 1),
    "MOVIE_PLAY": (67, 1),
    "MOVIE_DISP": (68, 1),
}

TRIANGLE, CIRCLE, CROSS, SQUARE = 0, 1, 2, 3
HOLD = 4  # add to a button to get its hold variant
POS_SCALE = 250  # 1920x1080 pixel -> DSC units


def seconds_to_time(t):
    return int(round(t * 100000))


class Script:
    def __init__(self):
        self._events = []  # (time_units, seq, opcode_name, params)

    def add(self, t_seconds, name, *params):
        _op, n = OPCODES[name]
        if len(params) != n:
            raise ValueError(f"{name} espera {n} parámetros, recibió {len(params)}")
        self._events.append((max(0, seconds_to_time(t_seconds)), len(self._events), name, [int(p) for p in params]))

    def target(self, t_seconds, note_type, x_px, y_px, angle_deg, distance_px=1200, amplitude=500, frequency=2):
        self.add(t_seconds, "TARGET", note_type, round(x_px * POS_SCALE), round(y_px * POS_SCALE),
                 round(angle_deg * 1000) % 360000, round(distance_px * POS_SCALE), amplitude, frequency)

    def to_bytes(self):
        out = [struct.pack("<i", SIGNATURE)]
        cur = None
        for t, _seq, name, params in sorted(self._events, key=lambda e: (e[0], e[1])):
            if t != cur:
                out.append(struct.pack("<2i", OPCODES["TIME"][0], t))
                cur = t
            op, _n = OPCODES[name]
            out.append(struct.pack(f"<{1 + len(params)}i", op, *params))
        out.append(struct.pack("<i", OPCODES["END"][0]))
        return b"".join(out)

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self.to_bytes())


def read_targets(path, full=False):
    """Parse a DSC written by this module; returns [(hit_time_s, type, x_px, y_px)] for previews/tests.
    Hit time is relative to MUSIC_PLAY."""
    by_id = {op: (name, n) for name, (op, n) in OPCODES.items()}
    with open(path, "rb") as f:
        data = f.read()
    words = struct.unpack(f"<{len(data) // 4}i", data[: len(data) // 4 * 4])
    i, t, fly, music, res = 1, 0.0, 0.0, 0.0, []
    while i < len(words):
        name, n = by_id[words[i]]
        p = words[i + 1:i + 1 + n]
        if name == "TIME":
            t = p[0] / 100000
        elif name == "TARGET_FLYING_TIME":
            fly = p[0] / 1000
        elif name == "MUSIC_PLAY":
            music = t
        elif name == "TARGET":
            entry = (t + fly, p[0], p[1] / POS_SCALE, p[2] / POS_SCALE)
            if full:  # + approach angle (degrees), distance (px), amplitude, frequency
                entry += (p[3] / 1000, p[4] / POS_SCALE, p[5], p[6])
            res.append(entry)
        elif name == "END":
            break
        i += 1 + n
    return [(h - music, *rest) for h, *rest in res]
