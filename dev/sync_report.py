"""Sync report for imported songs: tempo, constant-tempo fit, half-beat phase check and local drift.
Run: python dev\\sync_report.py [carpeta_mods]"""
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from divamgr import analysis, modloader, paths  # noqa: E402


def onset_curve(path):
    """Onset envelope and its time axis, as the analyzer computes them."""
    y, _ = analysis.load_mono(path)
    omel, _ = analysis.mel_spectrogram(y, analysis.ONSET_FFT)
    log = np.log1p(omel * 1000)
    flux = np.maximum(0, np.diff(log, axis=0, prepend=log[:1])).mean(1)
    t = np.arange(len(flux)) / analysis.FPS + analysis.ONSET_LATENCY
    return t, flux


def report(ogg):
    a = analysis.analyze(ogg)
    t, env = onset_curve(ogg)
    beats = a.beats[(a.beats > 5) & (a.beats < a.duration - 5)]
    period = 60 / a.bpm
    on = np.interp(beats, t, env).mean()
    half = np.interp(beats + period / 2, t, env).mean()
    # local drift: best shift (ms) of 8-beat windows against the onset envelope
    shifts = np.arange(-0.06, 0.0601, 0.002)
    drift = []
    for i in range(0, len(beats) - 8, 8):
        w = beats[i:i + 8]
        sc = [np.interp(w + s, t, env).sum() for s in shifts]
        drift.append(shifts[int(np.argmax(sc))] * 1000)
    drift = np.array(drift)
    return a, on, half, drift


def main():
    mods = sys.argv[1] if len(sys.argv) > 1 else modloader.mods_dir(paths.find_game())
    for meta_path in sorted(glob.glob(os.path.join(mods, "*", modloader.DM_META))):
        meta = json.load(open(meta_path, encoding="utf-8"))
        ogg = os.path.join(os.path.dirname(meta_path), "rom", "sound", "song", f"pv_{meta['pv_id']:03d}.ogg")
        a, on, half, drift = report(ogg)
        print(f"{meta['title'][:28]:28s} bpm {a.bpm:7.2f} constante={a.constant_tempo!s:5s} "
              f"pulso/contrapulso {on / (half + 1e-9):4.2f}  deriva ms: mediana {np.median(drift):+5.0f} "
              f"p10 {np.percentile(drift, 10):+4.0f} p90 {np.percentile(drift, 90):+4.0f}")


if __name__ == "__main__":
    main()
