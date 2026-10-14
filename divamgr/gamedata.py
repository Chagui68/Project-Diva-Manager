"""Read the game's own data for analysis: CRI CPK archives, Mega Mix+ file decryption, pv_db and
Future Tone DSC chart scripts. Only reads the user's local installation; nothing is redistributed.

Mega Mix+ stores every file inside its CPKs encrypted with AES-256-CBC; key and IV as published in
MikuMikuLibrary (MIT, blueskythlikesclouds). Decryption uses Windows CNG (bcrypt.dll) through ctypes.
"""
import ctypes
import os
import re
import struct
from ctypes import wintypes

AES_KEY = bytes([0xCF, 0x53, 0xBF, 0x9C, 0x37, 0x67, 0xAF, 0xB0, 0x35, 0x54, 0x4E, 0xB9, 0x96, 0xAA, 0x24, 0x39,
                 0x26, 0x5D, 0x40, 0x89, 0x7E, 0xD0, 0x1C, 0x3A, 0x6B, 0xA6, 0x5D, 0xD5, 0xFD, 0x6C, 0x19, 0xA3])
AES_IV = bytes([0xC2, 0x55, 0xFD, 0x73, 0xD8, 0x30, 0xFA, 0xEF, 0xD5, 0x32, 0x08, 0x54, 0xA2, 0x26, 0x44, 0x14])

# Future Tone DSC opcodes: id -> (name, parameter count). From Open PD Script Editor's opcode_db (FT).
FT_OPCODES = {
    0: ("END", 0), 1: ("TIME", 1), 2: ("MIKU_MOVE", 4), 3: ("MIKU_ROT", 2), 4: ("MIKU_DISP", 2),
    5: ("MIKU_SHADOW", 2), 6: ("TARGET", 7), 7: ("SET_MOTION", 4), 8: ("SET_PLAYDATA", 2), 9: ("EFFECT", 6),
    10: ("FADEIN_FIELD", 2), 11: ("EFFECT_OFF", 1), 12: ("SET_CAMERA", 6), 13: ("DATA_CAMERA", 2),
    14: ("CHANGE_FIELD", 1), 15: ("HIDE_FIELD", 1), 16: ("MOVE_FIELD", 3), 17: ("FADEOUT_FIELD", 2),
    18: ("EYE_ANIM", 3), 19: ("MOUTH_ANIM", 5), 20: ("HAND_ANIM", 5), 21: ("LOOK_ANIM", 4), 22: ("EXPRESSION", 4),
    23: ("LOOK_CAMERA", 5), 24: ("LYRIC", 2), 25: ("MUSIC_PLAY", 0), 26: ("MODE_SELECT", 2),
    27: ("EDIT_MOTION", 4), 28: ("BAR_TIME_SET", 2), 29: ("SHADOWHEIGHT", 2), 30: ("EDIT_FACE", 1),
    31: ("MOVE_CAMERA", 21), 32: ("PV_END", 0), 33: ("SHADOWPOS", 3), 34: ("EDIT_LYRIC", 2),
    35: ("EDIT_TARGET", 5), 36: ("EDIT_MOUTH", 1), 37: ("SET_CHARA", 1), 38: ("EDIT_MOVE", 7),
    39: ("EDIT_SHADOW", 1), 40: ("EDIT_EYELID", 1), 41: ("EDIT_EYE", 2), 42: ("EDIT_ITEM", 1),
    43: ("EDIT_EFFECT", 2), 44: ("EDIT_DISP", 1), 45: ("EDIT_HAND_ANIM", 2), 46: ("AIM", 3),
    47: ("HAND_ITEM", 3), 48: ("EDIT_BLUSH", 1), 49: ("NEAR_CLIP", 2), 50: ("CLOTH_WET", 2),
    51: ("LIGHT_ROT", 3), 52: ("SCENE_FADE", 6), 53: ("TONE_TRANS", 6), 54: ("SATURATE", 1),
    55: ("FADE_MODE", 1), 56: ("AUTO_BLINK", 2), 57: ("PARTS_DISP", 3), 58: ("TARGET_FLYING_TIME", 1),
    59: ("CHARA_SIZE", 2), 60: ("CHARA_HEIGHT_ADJUST", 2), 61: ("ITEM_ANIM", 4), 62: ("CHARA_POS_ADJUST", 4),
    63: ("SCENE_ROT", 1), 64: ("EDIT_MOT_SMOOTH_LEN", 2), 65: ("PV_BRANCH_MODE", 1),
    66: ("DATA_CAMERA_START", 2), 67: ("MOVIE_PLAY", 1), 68: ("MOVIE_DISP", 1), 69: ("WIND", 3),
    70: ("OSAGE_STEP", 3), 71: ("OSAGE_MV_CCL", 3), 72: ("CHARA_COLOR", 2), 73: ("SE_EFFECT", 1),
    74: ("EDIT_MOVE_XYZ", 9), 75: ("EDIT_EYELID_ANIM", 3), 76: ("EDIT_INSTRUMENT_ITEM", 2),
    77: ("EDIT_MOTION_LOOP", 4), 78: ("EDIT_EXPRESSION", 2), 79: ("EDIT_EYE_ANIM", 3), 80: ("EDIT_MOUTH_ANIM", 2),
    81: ("EDIT_CAMERA", 24), 82: ("EDIT_MODE_SELECT", 1), 83: ("PV_END_FADEOUT", 2), 84: ("TARGET_FLAG", 1),
    85: ("ITEM_ANIM_ATTACH", 3), 86: ("SHADOW_RANGE", 1), 87: ("HAND_SCALE", 3), 88: ("LIGHT_POS", 4),
    89: ("FACE_TYPE", 1), 90: ("SHADOW_CAST", 2), 91: ("EDIT_MOTION_F", 6), 92: ("FOG", 3), 93: ("BLOOM", 2),
    94: ("COLOR_COLLE", 3), 95: ("DOF", 3), 96: ("CHARA_ALPHA", 4), 97: ("AOTO_CAP", 1), 98: ("MAN_CAP", 1),
    99: ("TOON", 3), 100: ("SHIMMER", 3), 101: ("ITEM_ALPHA", 4), 102: ("MOVIE_CUT_CHG", 1),
    103: ("CHARA_LIGHT", 3), 104: ("STAGE_LIGHT", 3), 105: ("AGEAGE_CTRL", 8), 106: ("PSE", 2),
}


# ---- AES-256-CBC through Windows CNG ---------------------------------------------------------------
class _Aes:
    def __init__(self, key):
        self.bcrypt = ctypes.WinDLL("bcrypt")
        self.alg = wintypes.HANDLE()
        self.key = wintypes.HANDLE()
        self._check(self.bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(self.alg), "AES", None, 0))
        mode = ctypes.create_unicode_buffer("ChainingModeCBC")
        self._check(self.bcrypt.BCryptSetProperty(self.alg, "ChainingMode", mode, ctypes.sizeof(mode), 0))
        self._check(self.bcrypt.BCryptGenerateSymmetricKey(self.alg, ctypes.byref(self.key), None, 0,
                                                           key, len(key), 0))

    @staticmethod
    def _check(status):
        if status != 0:
            raise OSError(f"BCrypt error 0x{status & 0xFFFFFFFF:08X}")

    def decrypt(self, data, iv):
        data = data[: len(data) // 16 * 16]
        out = ctypes.create_string_buffer(len(data))
        iv_buf = ctypes.create_string_buffer(iv, len(iv))
        written = wintypes.ULONG()
        self._check(self.bcrypt.BCryptDecrypt(self.key, data, len(data), None, iv_buf, len(iv), out, len(data),
                                              ctypes.byref(written), 0))
        plain = out.raw[: written.value]
        pad = plain[-1] if plain else 0
        if 1 <= pad <= 16 and plain.endswith(bytes([pad]) * pad):
            plain = plain[:-pad]
        return plain


_aes = None


def decrypt(data):
    global _aes
    if _aes is None:
        _aes = _Aes(AES_KEY)
    return _aes.decrypt(data, AES_IV)


# ---- CRI CPK -----------------------------------------------------------------------------------------
def _decrypt_utf(b):
    if b[:4] == b"@UTF":
        return b
    out = bytearray(b)
    m = 0x655F
    for i in range(len(out)):
        out[i] ^= m & 0xFF
        m = (m * 0x4115) & 0xFFFFFFFF
    return bytes(out)


def _parse_utf(b):
    b = _decrypt_utf(b)
    _size, rows_off, str_off, data_off, _name, ncol, rowlen, nrows = struct.unpack(">IIIIIHHI", b[4:32])
    base = 8

    def string(o):
        st = base + str_off + o
        return b[st:b.index(b"\0", st)].decode("utf-8", "replace")

    fixed = {0: ">B", 1: ">b", 2: ">H", 3: ">h", 4: ">I", 5: ">i", 6: ">Q", 7: ">q", 8: ">f", 9: ">d"}

    def value(t, p):
        if t in fixed:
            f = fixed[t]
            return struct.unpack_from(f, b, p)[0], p + struct.calcsize(f)
        if t == 0xA:
            return string(struct.unpack_from(">I", b, p)[0]), p + 4
        if t == 0xB:
            o, n = struct.unpack_from(">II", b, p)
            return b[base + data_off + o: base + data_off + o + n], p + 8
        raise ValueError(f"UTF type {t}")

    p, cols = 32, []
    for _ in range(ncol):
        flags = b[p]
        name = string(struct.unpack_from(">I", b, p + 1)[0])
        p += 5
        storage, kind = flags & 0xF0, flags & 0x0F
        const = None
        if storage in (0x30, 0x70):
            const, p = value(kind, p)
        cols.append((name, storage, kind, const))
    rows = []
    for r in range(nrows):
        p, row = base + rows_off + r * rowlen, {}
        for name, storage, kind, const in cols:
            if storage == 0x50:
                row[name], p = value(kind, p)
            else:
                row[name] = const
        rows.append(row)
    return rows


def _crilayla(src):
    usize, hoff = struct.unpack("<II", src[8:16])
    res = bytearray(usize + 0x100)
    res[0:0x100] = src[hoff + 0x10:hoff + 0x110]
    state = {"off": len(src) - 0x100 - 1, "pool": 0, "left": 0}

    def bits(n):
        out = got = 0
        while got < n:
            if state["left"] == 0:
                state["pool"], state["left"] = src[state["off"]], 8
                state["off"] -= 1
            k = min(state["left"], n - got)
            out = (out << k) | ((state["pool"] >> (state["left"] - k)) & ((1 << k) - 1))
            state["left"] -= k
            got += k
        return out

    end, done, vle = 0x100 + usize - 1, 0, (2, 3, 5, 8)
    while done < usize:
        if bits(1):
            back, length = end - done + bits(13) + 3, 3
            for level in range(4):
                v = bits(vle[level])
                length += v
                if v != (1 << vle[level]) - 1:
                    break
            else:
                while True:
                    v = bits(8)
                    length += v
                    if v != 255:
                        break
            for _ in range(length):
                res[end - done] = res[back]
                back -= 1
                done += 1
        else:
            res[end - done] = bits(8)
            done += 1
    return bytes(res)


class Cpk:
    """Read-only CPK archive; read(name) returns the decrypted file."""

    def __init__(self, path):
        self.path = path
        self.file = open(path, "rb")
        head = self.file.read(16)
        if head[:4] != b"CPK ":
            raise ValueError(f"{path} no es un CPK")
        header = _parse_utf(self.file.read(struct.unpack("<Q", head[8:16])[0]))[0]
        toc_offset, content_offset = header["TocOffset"], header["ContentOffset"]
        align = header.get("Align") or 1
        self.file.seek(toc_offset)
        head = self.file.read(16)
        rows = _parse_utf(self.file.read(struct.unpack("<Q", head[8:16])[0]))
        base = content_offset if content_offset < toc_offset else toc_offset
        self.entries = {}
        for row in rows:
            name = f"{row.get('DirName') or ''}/{row['FileName']}".lstrip("/")
            pos = base + row["FileOffset"]
            pos = (pos + align - 1) // align * align
            self.entries[name] = (pos, row["FileSize"])

    def names(self, pattern=None):
        rx = re.compile(pattern) if pattern else None
        return [n for n in self.entries if rx is None or rx.search(n)]

    def read(self, name, raw=False):
        pos, size = self.entries[name]
        self.file.seek(pos)
        data = self.file.read(size)
        if data[:8] == b"CRILAYLA":
            data = _crilayla(data)
        return data if raw else decrypt(data)

    def close(self):
        self.file.close()


class Game:
    """All CPKs of an installation, searched in order (later archives override earlier ones)."""

    ARCHIVES = ("diva_main.cpk", "diva_main_region.cpk", "diva_dlc00.cpk", "diva_dlc00_region.cpk")

    def __init__(self, game_dir):
        self.cpks = [Cpk(os.path.join(game_dir, n)) for n in self.ARCHIVES if os.path.isfile(os.path.join(game_dir, n))]

    def find(self, pattern):
        """[(cpk, name)] of files whose path matches the regex."""
        rx = re.compile(pattern)
        return [(c, n) for c in self.cpks for n in c.entries if rx.search(n)]

    def read(self, name_suffix):
        """Decrypted file whose path ends with name_suffix (last archive wins)."""
        hits = [(c, n) for c in self.cpks for n in c.entries if n.endswith(name_suffix)]
        if not hits:
            raise FileNotFoundError(name_suffix)
        c, n = hits[-1]
        return c.read(n)

    def pv_db(self):
        """Merged pv_db: {pv_id: {key: value}} from the base game and DLC databases."""
        db = {}
        for c, n in self.find(r"(^|/)rom/(mdata_)?pv_db\.txt$"):
            for line in c.read(n).decode("utf-8", "replace").splitlines():
                m = re.match(r"pv_(\d+)\.([^=]+)=(.*)", line.strip())
                if m:
                    db.setdefault(int(m.group(1)), {})[m.group(2)] = m.group(3)
        return db

    def close(self):
        for c in self.cpks:
            c.close()


# ---- DSC ---------------------------------------------------------------------------------------------
def decode_dsc(data):
    """[(time_s, name, params)] for an FT-format DSC (int32 LE signature + opcodes)."""
    words = struct.unpack(f"<{len(data) // 4}i", data[: len(data) // 4 * 4])
    out, t, i = [], 0.0, 1
    while i < len(words):
        op = words[i]
        if op not in FT_OPCODES:
            raise ValueError(f"opcode desconocido {op} en la palabra {i}")
        name, n = FT_OPCODES[op]
        params = list(words[i + 1:i + 1 + n])
        if name == "TIME":
            t = params[0] / 100000
        out.append((t, name, params))
        if name == "END":
            break
        i += 1 + n
    return words[0], out


def dsc_text(events):
    """Plain-text listing like the community script editors: TIME(...); TARGET(...); ..."""
    return "\n".join(f"{name}({', '.join(map(str, params))});" for _t, name, params in events)
