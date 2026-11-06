"""Synthetic source recordings and acoustic environments.

Sources are synthesised, not recorded, so that ground truth is exact and the dataset
can be regenerated bit-for-bit from a seed. They are designed to avoid two artefacts
that would make detection trivially easy or trivially hard:

* no exact periodicity (pitch jitter, vibrato, random phases), so that waveform-level
  duplicate detection is not triggered by the synthesis itself;
* broadband background (white "self-noise" floor plus environment noise up to
  Nyquist), so that band-limiting by codecs or resamplers is observable, as it is in
  real microphone recordings.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter, sosfilt

VOWELS = {  # (F1, F2, F3) in Hz, Peterson & Barney (1952) adult male averages
    "a": (730, 1090, 2440),
    "e": (530, 1840, 2480),
    "i": (270, 2290, 3010),
    "o": (570, 840, 2410),
    "u": (300, 870, 2240),
}
ENVIRONMENTS = ["room", "hum", "street", "quiet"]
WHITE_FLOOR_DBFS = -68.0


def db_to_amp(db: float) -> float:
    return 10.0 ** (db / 20.0)


def _scale_rms(x: np.ndarray, rms_dbfs: float) -> np.ndarray:
    r = np.sqrt(np.mean(x * x))
    return x if r == 0 else x * (db_to_amp(rms_dbfs) / r)


def _resonator(f: float, bw: float, sr: int) -> tuple[np.ndarray, np.ndarray]:
    r = np.exp(-np.pi * bw / sr)
    theta = 2 * np.pi * f / sr
    a = np.array([1.0, -2 * r * np.cos(theta), r * r])
    return np.array([1.0 - r]), a


def _envelope(n: int, sr: int, attack_s: float, release_s: float) -> np.ndarray:
    env = np.ones(n)
    na, nr = min(n // 2, int(attack_s * sr)), min(n // 2, int(release_s * sr))
    if na:
        env[:na] = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, na))
    if nr:
        env[-nr:] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, nr))
    return env


def synth_speech(rng: np.random.Generator, sr: int, duration: float) -> np.ndarray:
    """Formant-synthesised speech-like signal: syllables, pauses, intonation, fricatives."""
    n = int(sr * duration)
    out = np.zeros(n)
    base = rng.uniform(95, 210)
    t = np.arange(n) / sr
    walk = np.cumsum(rng.normal(0, 1, n // 256 + 2))
    walk = np.interp(np.arange(n), np.arange(len(walk)) * 256, walk / (np.std(walk) + 1e-9))
    f0 = base * (1 + 0.08 * np.sin(2 * np.pi * rng.uniform(0.2, 0.5) * t + rng.uniform(0, 6.28)) + 0.03 * walk)
    f0 *= 1 + 0.004 * rng.normal(0, 1, n)  # jitter
    phase = 2 * np.pi * np.cumsum(f0) / sr
    K = int(5000 / (base * 1.25))
    tilt = rng.uniform(0.9, 1.3)
    source = np.zeros(n)
    for k in range(1, K + 1):
        source += np.sin(k * phase + rng.uniform(0, 6.28)) / k**tilt
    pos = int(rng.uniform(0.1, 0.3) * sr)
    vowels = list(VOWELS)
    while pos < n - int(0.1 * sr):
        L = int(rng.uniform(0.12, 0.28) * sr)
        end = min(n, pos + L)
        v = VOWELS[vowels[rng.integers(len(vowels))]]
        seg = source[pos:end].copy()
        for fi, bw in zip(v, (80, 100, 130)):
            b, a = _resonator(fi * rng.uniform(0.95, 1.05), bw, sr)
            seg = lfilter(b, a, seg)
        seg *= _envelope(len(seg), sr, rng.uniform(0.02, 0.04), rng.uniform(0.04, 0.07)) * rng.uniform(0.6, 1.0)
        out[pos:end] += seg
        if rng.random() < 0.4 and pos > int(0.1 * sr):
            fl = int(rng.uniform(0.04, 0.09) * sr)
            fs0 = max(0, pos - fl)
            sos = butter(4, rng.uniform(2500, 5000), btype="highpass", fs=sr, output="sos")
            burst = sosfilt(sos, rng.normal(0, 1, pos - fs0)) * np.hanning(pos - fs0)
            out[fs0:pos] += burst * 0.25 * np.sqrt(np.mean(seg * seg)) / (np.sqrt(np.mean(burst * burst)) + 1e-12)
        gap = rng.uniform(0.35, 0.7) if rng.random() < 0.15 else rng.uniform(0.04, 0.25)
        pos = end + int(gap * sr)
    return _scale_rms(out, -26.0)


def synth_tonal(rng: np.random.Generator, sr: int, duration: float) -> np.ndarray:
    """Music-like signal: random melody of harmonic notes with vibrato and ADSR envelopes."""
    n = int(sr * duration)
    out = np.zeros(n)
    scale = np.array([0, 2, 4, 5, 7, 9, 11])
    pos = int(0.05 * sr)
    while pos < n - int(0.1 * sr):
        L = int(rng.uniform(0.15, 0.6) * sr)
        end = min(n, pos + L)
        midi = 55 + scale[rng.integers(7)] + 12 * rng.integers(0, 2)
        f = 440.0 * 2 ** ((midi - 69) / 12) * rng.uniform(0.997, 1.003)
        tt = np.arange(end - pos) / sr
        vib = 1 + 0.003 * np.sin(2 * np.pi * rng.uniform(4.5, 6.0) * tt + rng.uniform(0, 6.28))
        ph = 2 * np.pi * np.cumsum(f * vib) / sr
        p = rng.uniform(1.2, 2.0)
        note = np.zeros(end - pos)
        for k in range(1, min(20, int(0.45 * sr / f)) + 1):
            note += np.sin(k * ph + rng.uniform(0, 6.28)) * rng.uniform(0.7, 1.0) / k**p
        env = _envelope(len(note), sr, rng.uniform(0.005, 0.025), rng.uniform(0.05, 0.15))
        env *= np.exp(-tt * rng.uniform(0.5, 2.5))
        out[pos:end] += note * env * rng.uniform(0.6, 1.0)
        pos = end - int(rng.uniform(0.0, 0.03) * sr)
    return _scale_rms(out, -22.0)


def pink_noise(rng: np.random.Generator, n: int) -> np.ndarray:
    spec = np.fft.rfft(rng.normal(0, 1, n))
    f = np.arange(len(spec))
    spec[1:] /= np.sqrt(f[1:])
    spec[0] = 0
    x = np.fft.irfft(spec, n)
    return x / (np.std(x) + 1e-12)


def environment_noise(rng: np.random.Generator, sr: int, n: int, env: str) -> np.ndarray:
    """Background for a named environment, always including a white self-noise floor."""
    white = rng.normal(0, db_to_amp(WHITE_FLOOR_DBFS), n)
    if env == "quiet":
        return white
    if env == "room":
        return white + pink_noise(rng, n) * db_to_amp(-54.0)
    if env == "hum":
        t = np.arange(n) / sr
        drift = np.cumsum(rng.normal(0, 1, n // 4410 + 2))
        drift = np.interp(np.arange(n), np.arange(len(drift)) * 4410, 0.01 * drift)
        ph = 2 * np.pi * np.cumsum(50.0 + drift) / sr + rng.uniform(0, 6.28)
        hum = db_to_amp(-46.0) * np.sqrt(2) * np.sin(ph) + db_to_amp(-54.0) * np.sqrt(2) * np.sin(2 * ph + 1.0) \
            + db_to_amp(-58.0) * np.sqrt(2) * np.sin(3 * ph + 2.0)
        del t
        return white + hum + pink_noise(rng, n) * db_to_amp(-62.0)
    if env == "street":
        brown = np.cumsum(rng.normal(0, 1, n))
        sos = butter(2, 20, btype="highpass", fs=sr, output="sos")
        brown = sosfilt(sos, brown)
        brown = brown / (np.std(brown) + 1e-12) * db_to_amp(-46.0)
        car = sosfilt(butter(2, [200, 2000], btype="bandpass", fs=sr, output="sos"), rng.normal(0, 1, n))
        car_env = np.interp(np.arange(n), np.linspace(0, n, 6), rng.uniform(0.2, 1.0, 6))
        car = car / (np.std(car) + 1e-12) * db_to_amp(-52.0) * car_env
        return white + brown + car
    raise ValueError(f"unknown environment {env!r}")


def quantize16(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Quantise float audio to 16-bit PCM with TPDF dither (as a recorder would)."""
    d = rng.uniform(-0.5, 0.5, len(x)) + rng.uniform(-0.5, 0.5, len(x))
    return np.clip(np.round(x * 32767.0 + d), -32768, 32767).astype(np.int16)


def render_source(kind: str, seed_seq: list[int], sr: int, duration: float) -> np.ndarray:
    rng = np.random.default_rng(seed_seq)
    return synth_speech(rng, sr, duration) if kind == "speech" else synth_tonal(rng, sr, duration)


def render_environment(env: str, seed_seq: list[int], sr: int, n: int) -> np.ndarray:
    return environment_noise(np.random.default_rng(seed_seq), sr, n, env)
