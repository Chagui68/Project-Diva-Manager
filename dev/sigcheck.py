"""Checks every DivaLoader signature (read from loader/src/Game.cpp) against DivaMegaMix.exe on disk.
Use after a game update. Run: python dev\\sigcheck.py [ruta\\DivaMegaMix.exe]"""
import mmap
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from divamgr import paths  # noqa: E402

BASE = 0x140000000


def sections(m):
    pe = struct.unpack_from("<I", m, 0x3C)[0]
    count = struct.unpack_from("<H", m, pe + 6)[0]
    opt = struct.unpack_from("<H", m, pe + 20)[0]
    out = []
    for i in range(count):
        o = pe + 24 + opt + i * 40
        _vsize, va, rsize, raw = struct.unpack_from("<IIII", m, o + 8)
        out.append((va, rsize, raw))
    return out


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(paths.find_game() or "", paths.GAME_EXE)
    src = open(os.path.join(ROOT, "loader", "src", "Game.cpp"), encoding="utf-8").read()
    sigs = re.findall(r'\{\s*"(\w+)",\s*(0x[0-9A-Fa-f]+),\s*"([0-9A-F? ]+)"\s*\}', src)
    with open(exe, "rb") as f:
        m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    secs = sections(m)

    def va2off(v):
        for va, rsize, raw in secs:
            if BASE + va <= v < BASE + va + rsize:
                return v - BASE - va + raw

    def off2va(o):
        for va, rsize, raw in secs:
            if raw <= o < raw + rsize:
                return BASE + va + o - raw

    bad = 0
    for name, hint, pattern in sigs:
        tokens = pattern.split()
        rx = re.compile(b"".join(b"." if t.startswith("?") else re.escape(bytes([int(t, 16)])) for t in tokens), re.S)
        o = va2off(int(hint, 16))
        if o is not None and rx.match(m, o):
            print(f"OK    {name:22s} {hint}")
            continue
        hit = rx.search(m)
        bad += 1
        print(f"MOVIDO {name:22s} {hint} -> {hex(off2va(hit.start())) if hit else 'NO ENCONTRADO'}")
    print(f"\n{len(sigs) - bad}/{len(sigs)} firmas en su sitio")


if __name__ == "__main__":
    main()
