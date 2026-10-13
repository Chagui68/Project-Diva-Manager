"""Audio analysis with numpy/scipy only: tempo, beat grid, onsets, spectral bands, sustain and energy.

(librosa is not used: its numba dependency is blocked by Windows Application Control on this PC.)
"""
from dataclasses import dataclass

import numpy as np
import soundfile as sf
from scipy import ndimage

SR = 22050
N_FFT = 2048
HOP = 256
FPS = SR / HOP
N_MELS = 64
ONSET_FFT = 1024
ONSET_LATENCY = 0.0093  # seconds (calibrated on synthetic drums) added to onset-frame times so they land on the real attack
# mel band groups used to pick buttons: low (kick/bass), low-mid, high-mid, high (hats/cymbals)
BAND_EDGES = (0, 10, 24, 42, N_MELS)


@dataclass
class Analysis:
    duration: float
    bpm: float
    beats: np.ndarray        # beat times (s), whole song
    downbeat_phase: int      # beats[i] is a bar start when i % 4 == phase
    grid: np.ndarray         # 16th-note grid times (s)
    grid_level: np.ndarray   # 0 bar, 1 beat, 2 eighth, 3 sixteenth
    grid_beat: np.ndarray    # grid position measured in beats (float)
    strength: np.ndarray     # onset strength per grid point, ~0..1
    bands: np.ndarray        # (grid, 4) normalised band onset flux
    sustain: np.ndarray      # harmonic sustain after each grid point, 0..1
    pitch: np.ndarray        # smoothed brightness/pitch 0..1 per grid point
    energy: np.ndarray       # smoothed loudness 0..1 per grid point
    active: np.ndarray       # bool, music audible
    sabi_start: float
    sabi_len: float
    constant_tempo: bool = True


def load_mono(path):
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    y = data.mean(axis=1)
    if sr != SR:
        import soxr
        y = soxr.resample(y, sr, SR)
    return np.ascontiguousarray(y, dtype=np.float32), len(data) / sr


def _mel_filterbank(n_fft=N_FFT):
    def hz2mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel2hz(m):
        return 700.0 * (10.0 ** (m / 2595.0) - 1.0)

    hz = mel2hz(np.linspace(hz2mel(30.0), hz2mel(11000.0), N_MELS + 2))
    freqs = np.fft.rfftfreq(n_fft, 1.0 / SR)
    fb = np.zeros((N_MELS, len(freqs)), np.float32)
    for i in range(N_MELS):
        lo, c, hi = hz[i], hz[i + 1], hz[i + 2]
        fb[i] = np.maximum(0.0, np.minimum((freqs - lo) / (c - lo), (hi - freqs) / (hi - c)))
    return fb, hz[1:-1]


def mel_spectrogram(y, n_fft=N_FFT):
    pad = N_FFT // 2  # same padding for every n_fft so frame f is centred on f * HOP
    yp = np.pad(y, (pad, pad), mode="reflect")
    off = pad - n_fft // 2
    n = 1 + (len(yp) - N_FFT) // HOP
    frames = np.lib.stride_tricks.as_strided(yp[off:], shape=(n, n_fft), strides=(yp.strides[0] * HOP, yp.strides[0]))
    win = np.hanning(n_fft).astype(np.float32)
    fb, centers = _mel_filterbank(n_fft)
    mel = np.empty((n, N_MELS), np.float32)
    for i in range(0, n, 1024):
        spec = np.abs(np.fft.rfft(frames[i:i + 1024] * win, axis=1)).astype(np.float32) ** 2
        mel[i:i + 1024] = spec @ fb.T
    return mel, centers


def _norm(x, lo_pct=5, hi_pct=95):
    lo, hi = np.percentile(x, lo_pct), np.percentile(x, hi_pct)
    return np.clip((x - lo) / (hi - lo + 1e-9), 0.0, 1.0)


def estimate_tempo(oenv):
    x = oenv - ndimage.uniform_filter1d(oenv, int(FPS * 2))
    n = len(x)
    f = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(np.abs(f) ** 2)[:n]
    lags = np.arange(int(FPS * 60 / 220), int(FPS * 60 / 55))
    bpms = 60.0 * FPS / lags
    prior = np.exp(-0.5 * (np.log2(bpms / 120.0) / 0.9) ** 2)
    score = ac[lags] * prior
    # reward lags whose double is also strong (metrical consistency)
    dbl = np.minimum(lags * 2, n - 1)
    score = score + 0.5 * ac[dbl] * prior
    k = int(np.argmax(score))
    lag = float(lags[k])
    if 0 < k < len(lags) - 1:
        a, b, c = score[k - 1], score[k], score[k + 1]
        den = a - 2 * b + c
        if den:
            lag += 0.5 * (a - c) / den
    return 60.0 * FPS / lag


def track_beats(oenv, bpm, tightness=100.0):
    """Ellis-style dynamic programming beat tracker; returns frame indices."""
    period = FPS * 60.0 / bpm
    g = np.exp(-0.5 * (np.arange(-int(period), int(period) + 1) * 32.0 / period) ** 2)
    local = np.convolve(oenv / (oenv.std() + 1e-9), g, mode="same")
    n = len(local)
    cum = np.zeros(n)
    back = -np.ones(n, dtype=int)
    lo, hi = int(round(period / 2)), int(round(period * 2))
    offsets = np.arange(lo, hi + 1)
    penalty = -tightness * np.log(offsets / period) ** 2
    for t in range(n):
        prev = t - offsets
        ok = prev >= 0
        if not ok.any():
            cum[t] = local[t]
            continue
        cand = cum[prev[ok]] + penalty[ok]
        j = int(np.argmax(cand))
        cum[t] = local[t] + max(0.0, cand[j])
        back[t] = prev[ok][j] if cand[j] > 0 else -1
    tail = cum[max(0, n - int(period * 2)):]
    t = max(0, n - int(period * 2)) + int(np.argmax(tail))
    beats = []
    while t >= 0:
        beats.append(t)
        t = back[t]
    return np.array(beats[::-1], dtype=int)




def fit_grid(oenv, low, bpm0, duration):
    """Beat grid for the whole song. Most songs are produced at a constant tempo, so the period and
    phase are fitted globally by folding the onset envelope over candidate periods (2 ms bins).
    The bass band decides between beat and off-beat. 16-beat windows then check the fit; if they
    disagree the grid follows their (smoothed) local shifts. Returns (beats, constant_tempo)."""
    t_axis = np.arange(len(oenv)) / FPS + ONSET_LATENCY

    def strong(env):
        thr = np.percentile(env, 80)
        sel = env > thr
        return t_axis[sel], env[sel] ** 2

    def fold(period, times, weights):
        nb = max(8, int(round(period / 0.002)))
        idx = (np.mod(times, period) / period * nb).astype(int) % nb
        h = np.bincount(idx, weights=weights, minlength=nb)
        return h + 0.6 * (np.roll(h, 1) + np.roll(h, -1)) + 0.25 * (np.roll(h, 2) + np.roll(h, -2)), nb

    times, weights = strong(oenv)

    def search(center, rel, steps):
        best = (-1.0, center, 0.0)
        for period in center * (1 + np.linspace(-rel, rel, steps)):
            h, nb = fold(period, times, weights)
            j = int(np.argmax(h))
            if h[j] > best[0]:
                best = (h[j], period, (j + 0.5) / nb * period)
        return best

    _s, period, phase = search(60.0 / bpm0, 0.04, 801)
    _s, period, phase = search(period, 2e-4, 401)

    low_times, low_weights = strong(low)
    hl, nb = fold(period, low_times, low_weights)
    j0 = int(phase / period * nb) % nb
    j1 = (j0 + nb // 2) % nb
    if hl[j1] > hl[j0] * 1.15:
        phase = (phase + period / 2) % period

    beats = np.arange(phase, duration, period)

    # check the global grid in overlapping 16-beat windows
    reach = min(0.06, period / 4)
    cand = np.arange(-reach, reach + 1e-9, 0.002)
    level = np.median(oenv) + 1e-9
    centers, shifts = [], []
    for i in range(0, max(0, len(beats) - 16), 8):
        wb = beats[i:i + 16]
        a, b = np.searchsorted(t_axis, [wb[0], wb[-1]])
        if oenv[a:b].mean() < 0.5 * level:
            continue
        sc = np.interp(wb[None, :] + cand[:, None], t_axis, oenv).sum(axis=1)
        centers.append(wb.mean())
        shifts.append(cand[int(np.argmax(sc))])
    if len(shifts) < 4:
        return beats, True
    shifts = np.array(shifts)
    if np.mean(np.abs(shifts - np.median(shifts)) <= 0.02) >= 0.8:
        return beats + float(np.median(shifts)), True
    smooth = ndimage.median_filter(shifts, size=3, mode="nearest")
    return beats + np.interp(beats, centers, smooth), False


def analyze(path, progress=lambda f, msg="": None):
    progress(0.05, "Leyendo audio")
    y, duration = load_mono(path)
    progress(0.12, "Espectrograma")
    mel, centers = mel_spectrogram(y)
    omel, _ = mel_spectrogram(y, ONSET_FFT)
    n = len(mel)

    def frame(t):
        return np.clip(np.round((np.asarray(t) - ONSET_LATENCY) * FPS).astype(int), 0, n - 1)

    progress(0.25, "Separando percusión y armonía")
    harm = ndimage.median_filter(mel, size=(31, 1))
    perc = ndimage.median_filter(mel, size=(1, 9))
    harm_mask = harm ** 2 / (perc ** 2 + harm ** 2 + 1e-12)
    oharm = ndimage.median_filter(omel, size=(31, 1))
    operc = ndimage.median_filter(omel, size=(1, 9))
    log_operc = np.log1p(omel * operc ** 2 / (operc ** 2 + oharm ** 2 + 1e-12) * 1000.0)

    progress(0.4, "Detectando ataques")
    log_omel = np.log1p(omel * 1000.0)
    flux = np.maximum(0.0, np.diff(log_omel, axis=0, prepend=log_omel[:1]))
    pflux = np.maximum(0.0, np.diff(log_operc, axis=0, prepend=log_operc[:1]))
    oenv = flux.mean(axis=1) * 0.5 + pflux.mean(axis=1) * 0.5
    oenv = np.maximum(0.0, oenv - ndimage.uniform_filter1d(oenv, int(FPS * 0.5)) * 0.8)
    band_flux = np.stack([flux[:, a:b].mean(axis=1) for a, b in zip(BAND_EDGES[:-1], BAND_EDGES[1:])], axis=1)

    rms_db = 10.0 * np.log10(mel.sum(axis=1) + 1e-10)
    active = rms_db > (np.percentile(rms_db, 98) - 38.0)
    active = ndimage.binary_closing(active, structure=np.ones(int(FPS)))
    energy_frames = _norm(ndimage.uniform_filter1d(rms_db, int(FPS * 3)), 10, 98)

    hsum = mel * harm_mask
    centroid = (hsum * np.log2(centers)[None, :]).sum(axis=1) / (hsum.sum(axis=1) + 1e-9)
    pitch_frames = _norm(ndimage.uniform_filter1d(centroid, int(FPS * 0.6)))

    progress(0.55, "Calculando tempo")
    bpm = estimate_tempo(oenv)
    while bpm < 85:
        bpm *= 2
    while bpm > 195:
        bpm /= 2
    progress(0.6, "Siguiendo el pulso")
    bf = track_beats(oenv, bpm)
    if len(bf) >= 8:
        bpm = 60.0 / (np.median(np.diff(bf)) / FPS)
    low = band_flux[:, 0]
    beats, constant = fit_grid(oenv, low, bpm, duration)
    period_s = float(np.median(np.diff(beats)))
    bpm = 60.0 / period_s

    phase_score = [low[frame(beats[p::4])].sum() + oenv[frame(beats[p::4])].sum() * 0.5 for p in range(4)]
    phase = int(np.argmax(phase_score))

    progress(0.75, "Construyendo rejilla rítmica")
    grid, level, gbeat = [], [], []
    for i in range(len(beats)):
        b0 = beats[i]
        b1 = beats[i + 1] if i + 1 < len(beats) else b0 + period_s
        for k in range(4):
            t = b0 + (b1 - b0) * k / 4
            if t >= duration:
                break
            grid.append(t)
            gbeat.append(i + k / 4)
            level.append((0 if (i - phase) % 4 == 0 else 1) if k == 0 else (2 if k == 2 else 3))
    grid, level, gbeat = np.array(grid), np.array(level), np.array(gbeat)
    gf = frame(grid)

    on_n = oenv / (np.percentile(oenv[active] if active.any() else oenv, 99) + 1e-9)
    strength = np.clip(np.array([on_n[max(0, f - 2):f + 3].max() for f in gf]), 0, 1.2)
    bn = band_flux / (np.percentile(band_flux, 98, axis=0) + 1e-9)
    bands = np.array([bn[max(0, f - 2):f + 3].max(axis=0) for f in gf])

    # sustain: does the tonal sound that starts at this point keep ringing for ~1.5 beats?
    beat_frames = int(round(period_s * FPS))
    tail_len = int(beat_frames * 1.5)
    hmel = (mel * harm_mask)[:, 8:]  # skip the lowest bands (kick/bass)
    sustain = np.zeros(len(gf))
    for i, f in enumerate(gf):
        if f < 12 or f + tail_len + 6 >= n:
            continue
        bg = hmel[f - 12:f - 2].mean(axis=0)
        head = hmel[f + 2:f + 6].mean(axis=0)
        note = np.maximum(head - bg, 0.0)
        tot = head.sum()
        if tot <= 0 or note.sum() < 0.25 * tot:
            continue
        w = note / note.sum()
        ref = float(note @ w)
        tail = (hmel[f + 6:f + 6 + tail_len] - bg[None, :]) @ w
        sustain[i] = float(np.clip(tail / ref, 0, 1).mean()) * min(1.0, note.sum() / tot / 0.5)

    progress(0.9, "Buscando el estribillo")
    sabi_len = min(30.0, max(10.0, duration * 0.25))
    best, sabi_start = -1e9, 0.0
    for t in beats[phase::4]:
        if t < duration * 0.15 or t + sabi_len > duration - 3:
            continue
        s = rms_db[frame(t):frame(t + sabi_len)].mean()
        if s > best:
            best, sabi_start = s, float(t)

    progress(1.0, "Análisis listo")
    return Analysis(duration=duration, bpm=float(bpm), beats=beats, downbeat_phase=phase, grid=grid,
                    grid_level=level, grid_beat=gbeat, strength=strength, bands=bands, sustain=sustain,
                    pitch=pitch_frames[gf], energy=energy_frames[gf], active=active[gf],
                    sabi_start=sabi_start, sabi_len=sabi_len, constant_tempo=constant)
