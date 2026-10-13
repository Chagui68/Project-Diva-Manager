"""Synthetic test song: kick/snare/hats at a known BPM plus a melody with long (hold) and short notes."""
import numpy as np
import soundfile as sf

SR = 44100


def make_song(path, bpm=128.0, duration=70.0, seed=1):
    beat = 60 / bpm
    y = np.zeros(int(SR * duration))
    rng = np.random.default_rng(seed)

    def add(start, sig):
        i = int(start * SR)
        y[i:i + len(sig)] += sig[: len(y) - i]

    kt = np.arange(int(0.25 * SR)) / SR
    kick = np.sin(2 * np.pi * (50 + 120 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 12)
    snare = rng.standard_normal(int(0.2 * SR)) * np.exp(-np.arange(int(0.2 * SR)) / SR * 25) * 0.5
    hat = rng.standard_normal(int(0.05 * SR)) * np.exp(-np.arange(int(0.05 * SR)) / SR * 80) * 0.25
    hat = np.diff(hat, prepend=0)
    melody = [60, 62, 64, 67, 69, 67, 64, 62]
    beats = int(duration / beat)
    for b in range(4, beats - 2):
        tb = b * beat
        add(tb, kick if b % 2 == 0 else snare)
        if b % 2 == 1:
            add(tb, kick * 0.3)
        add(tb, hat)
        add(tb + beat / 2, hat)
        if 20 <= b < 40:
            add(tb + beat / 4, hat * 0.8)
            add(tb + 3 * beat / 4, hat * 0.8)
        if b % 4 == 0:
            f = 440 * 2 ** ((melody[(b // 4) % 8] - 69) / 12)
            n = int(beat * (3.5 if b % 8 == 0 else 1.0) * SR)
            tt = np.arange(n) / SR
            add(tb, 0.3 * np.sin(2 * np.pi * f * tt) * np.minimum(1, tt * 50) * np.exp(-tt * 0.3))
    y = y / np.abs(y).max() * 0.8
    sf.write(path, np.stack([y, y], 1), SR)
    return path
