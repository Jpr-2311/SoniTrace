"""Module B (time domain): framing, RMS, peak, zero-crossing rate and global level statistics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.ndimage import maximum_filter1d
from scipy.signal import resample_poly

DB_FLOOR = -150.0


def to_db(power_or_amp: np.ndarray, power: bool = False, floor: float = DB_FLOOR) -> np.ndarray:
    a = np.asarray(power_or_amp, dtype=np.float64)
    with np.errstate(divide="ignore"):
        out = (10.0 if power else 20.0) * np.log10(np.maximum(a, 0.0))
    return np.maximum(out, floor)


def frame_view(x: np.ndarray, frame_length: int, hop: int) -> np.ndarray:
    """Zero-copy (n_frames, frame_length) view; the signal is zero-padded to cover its end."""
    if len(x) < frame_length:
        x = np.pad(x, (0, frame_length - len(x)))
    rem = (len(x) - frame_length) % hop
    if rem:
        x = np.pad(x, (0, hop - rem))
    return sliding_window_view(x, frame_length)[::hop]


@dataclass
class FrameFeatures:
    times: np.ndarray
    rms: np.ndarray
    rms_db: np.ndarray
    peak: np.ndarray
    zcr: np.ndarray
    frame_length: int
    hop: int


def compute_frame_features(x: np.ndarray, sr: int, frame_length: int, hop: int) -> FrameFeatures:
    n = len(x)
    n_frames = max(1, 1 + int(np.ceil(max(0, n - frame_length) / hop)))
    starts = np.arange(n_frames) * hop
    pad = int(starts[-1] + frame_length - n) if starts[-1] + frame_length > n else 0
    xp = np.pad(x, (0, pad)) if pad else x
    cs = np.concatenate(([0.0], np.cumsum(xp * xp)))
    energy = np.maximum(cs[starts + frame_length] - cs[starts], 0.0)
    rms = np.sqrt(energy / frame_length)
    signs = np.signbit(xp)
    zc = np.concatenate(([0], np.cumsum(signs[1:] != signs[:-1])))
    zcr = (zc[starts + frame_length - 1] - zc[starts]) / float(frame_length - 1)
    peaks = maximum_filter1d(np.abs(xp), size=frame_length, mode="constant", cval=0.0, origin=-(frame_length // 2))
    peak = peaks[starts]
    times = (starts + frame_length / 2.0) / sr
    return FrameFeatures(times, rms, to_db(rms), peak, zcr, frame_length, hop)


def runs_of_true(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return [start, end) index pairs of consecutive True runs."""
    m = np.concatenate(([False], np.asarray(mask, dtype=bool), [False]))
    d = np.diff(m.astype(np.int8))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts.tolist(), ends.tolist()))


def true_peak(x: np.ndarray, oversample: int = 4, chunk: int = 1 << 18) -> float:
    """Inter-sample (true) peak estimate via polyphase oversampling, processed in chunks."""
    best = 0.0
    margin = 64
    for s in range(0, len(x), chunk):
        seg = x[max(0, s - margin) : s + chunk + margin]
        if len(seg) == 0:
            continue
        best = max(best, float(np.max(np.abs(resample_poly(seg, oversample, 1)))))
    return best


def summarize_signal(samples: np.ndarray, mono: np.ndarray, sr: int, ff: FrameFeatures, bit_depth: int | None) -> dict:
    """Global level statistics used in the report's audio-characteristics section."""
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    rms = float(np.sqrt(np.mean(mono * mono))) if mono.size else 0.0
    active = ff.rms_db[ff.rms_db > -110.0]
    full_scale = 1.0 - (1.0 / 2 ** (bit_depth - 1) if bit_depth else 1e-4)
    clip_mask = np.any(np.abs(samples) >= full_scale - 1e-12, axis=1)
    clip_runs = [r for r in runs_of_true(clip_mask) if r[1] - r[0] >= 3]
    tp = true_peak(mono)
    out = {
        "peak_dbfs": float(to_db(np.array([peak]))[0]),
        "true_peak_dbfs_estimate": float(to_db(np.array([tp]))[0]),
        "rms_dbfs": float(to_db(np.array([rms]))[0]),
        "crest_factor_db": float(to_db(np.array([peak / rms]))[0]) if rms > 0 else None,
        "dc_offset_per_channel": [float(v) for v in samples.mean(axis=0)],
        "clipping_runs_3plus_samples": len(clip_runs),
        "clipped_samples": int(sum(e - s for s, e in clip_runs)),
        "frame_rms_db_p5": float(np.percentile(active, 5)) if active.size else None,
        "frame_rms_db_p50": float(np.percentile(active, 50)) if active.size else None,
        "frame_rms_db_p95": float(np.percentile(active, 95)) if active.size else None,
        "dynamic_range_db_p95_p5": float(np.percentile(active, 95) - np.percentile(active, 5)) if active.size else None,
        "zero_crossing_rate_mean": float(np.mean(ff.zcr)),
        "zero_crossing_rate_median": float(np.median(ff.zcr)),
    }
    if samples.shape[1] == 2:
        a, b = samples[:, 0], samples[:, 1]
        denom = np.sqrt(np.sum(a * a) * np.sum(b * b))
        out["inter_channel_correlation"] = float(np.sum(a * b) / denom) if denom > 0 else None
        out["channels_identical"] = bool(np.array_equal(a, b))
    return out
