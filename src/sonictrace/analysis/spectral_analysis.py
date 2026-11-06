"""Module B (frequency domain): STFT, spectral descriptors, mel/MFCC, long-term spectrum and band-limit detection.

Mathematics (see docs/mathematics.md for the full derivation):

* STFT  X[k, m] = sum_n x[n + mH] w[n] e^{-j 2 pi k n / N}, Hann window w, hop H = N/4.
* centroid   c_m  = sum_k f_k P[k,m] / sum_k P[k,m]
* bandwidth  b_m  = sqrt( sum_k (f_k - c_m)^2 P[k,m] / sum_k P[k,m] )
* rolloff    r_m  = min f such that sum_{f_k <= f} P >= 0.85 sum_k P
* flatness   F_m  = exp(mean_k ln P) / mean_k P        (Wiener entropy; 1 = white noise)
* MFCC       c    = DCT-II( ln( M P ) ), M = triangular mel filterbank (HTK mel scale)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.fft import dct
from scipy.ndimage import uniform_filter1d
from scipy.signal import get_window, welch

from .signal_features import frame_view

_BATCH = 2048


@dataclass
class Spectrogram:
    freqs: np.ndarray
    times: np.ndarray
    mag: np.ndarray  # float32, shape (bins, frames)
    n_fft: int
    hop: int
    sr: int


@dataclass
class SpectralFeatures:
    centroid: np.ndarray
    bandwidth: np.ndarray
    rolloff: np.ndarray
    flatness: np.ndarray
    flux: np.ndarray
    log_mel: np.ndarray  # (n_mels, frames), dB
    mfcc: np.ndarray  # (n_mfcc, frames)


def compute_stft(x: np.ndarray, sr: int, n_fft: int, hop: int) -> Spectrogram:
    frames = frame_view(x, n_fft, hop)
    win = get_window("hann", n_fft, fftbins=True)
    mag = np.empty((n_fft // 2 + 1, frames.shape[0]), dtype=np.float32)
    for s in range(0, frames.shape[0], _BATCH):
        block = frames[s : s + _BATCH] * win
        mag[:, s : s + block.shape[0]] = np.abs(np.fft.rfft(block, axis=1)).T
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    times = (np.arange(frames.shape[0]) * hop + n_fft / 2.0) / sr
    return Spectrogram(freqs, times, mag, n_fft, hop, sr)


def hz_to_mel(f: np.ndarray | float) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def mel_to_hz(m: np.ndarray | float) -> np.ndarray:
    return 700.0 * (10.0 ** (np.asarray(m) / 2595.0) - 1.0)


def mel_filterbank(sr: int, n_fft: int, n_mels: int = 40, fmin: float = 0.0, fmax: float | None = None) -> np.ndarray:
    fmax = fmax or sr / 2.0
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    edges = mel_to_hz(np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), n_mels + 2))
    fb = np.zeros((n_mels, len(freqs)))
    for i in range(n_mels):
        lo, ce, hi = edges[i], edges[i + 1], edges[i + 2]
        up = (freqs - lo) / max(ce - lo, 1e-9)
        down = (hi - freqs) / max(hi - ce, 1e-9)
        fb[i] = np.maximum(0.0, np.minimum(up, down))
    # Slaney-style area normalisation keeps band energies comparable across bands
    fb *= (2.0 / np.maximum(edges[2:] - edges[:-2], 1e-9))[:, None]
    return fb


def compute_spectral_features(spec: Spectrogram, n_mels: int = 40, n_mfcc: int = 13) -> SpectralFeatures:
    f = spec.freqs.astype(np.float64)
    n = spec.mag.shape[1]
    out = {k: np.empty(n) for k in ("centroid", "bandwidth", "rolloff", "flatness", "flux")}
    log_mel = np.empty((n_mels, n))
    fb = mel_filterbank(spec.sr, spec.n_fft, n_mels)
    prev = None
    eps = 1e-20
    for s in range(0, n, _BATCH):
        m = spec.mag[:, s : s + _BATCH].astype(np.float64)
        p = m * m
        tot = p.sum(axis=0) + eps
        c = (f[:, None] * p).sum(axis=0) / tot
        out["centroid"][s : s + m.shape[1]] = c
        out["bandwidth"][s : s + m.shape[1]] = np.sqrt((((f[:, None] - c[None, :]) ** 2) * p).sum(axis=0) / tot)
        cum = np.cumsum(p, axis=0)
        idx = np.argmax(cum >= 0.85 * cum[-1][None, :], axis=0)
        out["rolloff"][s : s + m.shape[1]] = f[idx]
        out["flatness"][s : s + m.shape[1]] = np.exp(np.mean(np.log(p + eps), axis=0)) / (np.mean(p, axis=0) + eps)
        norm = m / (np.sqrt((m * m).sum(axis=0)) + 1e-12)
        if prev is not None:
            norm_full = np.concatenate([prev[:, None], norm], axis=1)
        else:
            norm_full = np.concatenate([norm[:, :1], norm], axis=1)
        diff = np.maximum(np.diff(norm_full, axis=1), 0.0)
        out["flux"][s : s + m.shape[1]] = np.sqrt((diff * diff).sum(axis=0))
        prev = norm[:, -1]
        log_mel[:, s : s + m.shape[1]] = 10.0 * np.log10(fb @ p + 1e-12)
    mfcc = dct(log_mel, type=2, axis=0, norm="ortho")[:n_mfcc]
    return SpectralFeatures(out["centroid"], out["bandwidth"], out["rolloff"], out["flatness"], out["flux"], log_mel, mfcc)


def compute_ltas(x: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Long-term average spectrum (Welch PSD, Hann, 50 % overlap)."""
    nper = 8192 if sr >= 32000 else 4096
    nper = min(nper, max(256, 1 << int(np.floor(np.log2(max(len(x), 256))))))
    f, p = welch(x, fs=sr, window="hann", nperseg=nper, noverlap=nper // 2, detrend=False, scaling="density")
    return f, p


BANDS = [(0, 250), (250, 500), (500, 2000), (2000, 4000), (4000, 8000), (8000, 16000), (16000, 1e9)]


def band_energy_distribution(f: np.ndarray, psd: np.ndarray) -> list[dict]:
    total = float(np.sum(psd)) + 1e-30
    out = []
    for lo, hi in BANDS:
        m = (f >= lo) & (f < hi)
        if not m.any():
            continue
        out.append({"band_hz": [lo, None if hi >= 1e9 else hi], "energy_percent": 100.0 * float(np.sum(psd[m])) / total})
    return out


@dataclass
class BandLimit:
    found: bool
    cutoff_hz: float | None
    depth_db: float | None
    transition_hz: float | None
    floor_db: float | None
    pass_db: float | None
    nyquist_hz: float
    steep: bool
    reason: str

    @property
    def cutoff_ratio(self) -> float | None:
        return None if self.cutoff_hz is None else self.cutoff_hz / self.nyquist_hz

    def to_dict(self) -> dict:
        return {
            "found": self.found, "cutoff_hz": self.cutoff_hz, "cutoff_to_nyquist": self.cutoff_ratio,
            "depth_db": self.depth_db, "transition_hz": self.transition_hz, "stopband_floor_db": self.floor_db,
            "passband_level_db": self.pass_db, "nyquist_hz": self.nyquist_hz, "steep": self.steep, "reason": self.reason,
        }


def detect_bandlimit(f: np.ndarray, psd: np.ndarray, sr: int, margin_db: float = 15.0,
                     min_depth_db: float = 25.0, max_transition_frac: float = 0.30) -> BandLimit:
    """Find the highest frequency with real content and characterise the drop above it.

    The stopband reference is the median level just below Nyquist. The cutoff is the
    highest frequency whose smoothed level exceeds that reference by ``margin_db``. The
    drop is called *steep* when its depth is at least ``min_depth_db`` and the 90 %->10 %
    transition is narrower than ``max_transition_frac`` of the cutoff frequency - the
    signature of a digital low-pass (codec or resampler) rather than an acoustic roll-off.
    """
    nyq = sr / 2.0
    db = 10.0 * np.log10(psd + 1e-30)
    df = f[1] - f[0]
    db_s = uniform_filter1d(db, size=max(1, int(round(150.0 / df))), mode="nearest")
    top = (f >= 0.965 * nyq) & (f <= 0.995 * nyq)
    if top.sum() < 2:
        top = f >= 0.95 * nyq
    floor = float(np.median(db_s[top]))
    # below ~1.5 kHz a "cutoff" is a property of the content (e.g. a lone tone), not of a filter
    cand = np.flatnonzero((db_s >= floor + margin_db) & (f >= 1500.0))
    if cand.size == 0:
        return BandLimit(False, None, None, None, floor, None, nyq, False, "no broadband content rises above the near-Nyquist floor")
    f_edge = float(f[cand[-1]])  # where content finally meets the floor (stopband edge)
    if f_edge >= 0.97 * nyq:
        return BandLimit(False, f_edge, None, None, floor, None, nyq, False, "content extends to the Nyquist frequency")
    pb = (f >= max(1000.0, 0.5 * f_edge)) & (f <= f_edge)
    pass_db = float(np.percentile(db_s[pb], 90)) if pb.sum() >= 2 else float(db_s[cand[-1]])
    depth = pass_db - floor
    # the reported cutoff is the -6 dB point below the passband level: filter design places the
    # nominal edge (and therefore a source rate's Nyquist frequency) there, not at the stopband edge
    mid_idx = np.flatnonzero((db_s >= pass_db - 6.0) & (f <= f_edge))
    fc = float(f[mid_idx[-1]]) if mid_idx.size else f_edge
    hi_idx = np.flatnonzero((db_s >= floor + 0.9 * depth) & (f <= fc))
    f_hi = float(f[hi_idx[-1]]) if hi_idx.size else fc
    lo_idx = np.flatnonzero((db_s <= floor + 0.1 * depth) & (f >= fc))
    f_lo = float(f[lo_idx[0]]) if lo_idx.size else nyq
    transition = max(f_lo - f_hi, float(df))
    steep = depth >= min_depth_db and transition <= max(600.0, max_transition_frac * fc)
    reason = "steep band limit" if steep else "gradual roll-off or shallow drop"
    return BandLimit(True, fc, depth, transition, floor, pass_db, nyq, steep, reason)


STANDARD_RATES = [8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 88200, 96000]


def candidate_source_rates(cutoff_hz: float, sr: int) -> list[int]:
    """Standard sample rates below ``sr`` whose Nyquist frequency is consistent with a cutoff.

    Anti-alias/anti-imaging filters place the passband edge at roughly 0.80-1.0 of the
    lower rate's Nyquist frequency, so a cutoff ``fc`` (-6 dB point) is consistent with a
    source rate ``r`` when 0.80 <= fc / (r/2) <= 1.05.
    """
    return [r for r in STANDARD_RATES if r < sr and 0.80 <= cutoff_hz / (r / 2.0) <= 1.05]
