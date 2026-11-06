"""Controlled transformations applied to 16-bit 'original recordings'.

Every function takes int16 samples, returns int16 samples plus a log entry that records
exactly what was done and where (in the *output* timeline). Operations act on the
quantised file, as an editor working on an existing recording would.
"""

from __future__ import annotations

import tempfile
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from ..utils.tools import find_tool, run_tool


def _requant(x: np.ndarray) -> np.ndarray:
    """Round to int16 without dither (editor working in fixed point / exporting undithered)."""
    return np.clip(np.round(x), -32768, 32767).astype(np.int16)


def edit_position(rng: np.random.Generator, n: int, sr: int, margin_s: float = 1.0) -> int:
    return int(rng.uniform(margin_s, n / sr - margin_s - 0.8) * sr)


def cut(a: np.ndarray, sr: int, rng: np.random.Generator, crossfade_ms: float = 0.0) -> tuple[np.ndarray, dict]:
    p = edit_position(rng, len(a), sr)
    L = int(rng.uniform(0.15, 0.6) * sr)
    x = a.astype(np.float64)
    if crossfade_ms > 0:
        c = int(crossfade_ms * 1e-3 * sr)
        w = np.sin(np.linspace(0, np.pi / 2, c)) ** 2
        mixed = x[p - c : p] * (1 - w) + x[p + L - c : p + L] * w
        y = np.concatenate([x[: p - c], mixed, x[p + L :]])
        t = (p - c / 2) / sr
    else:
        y = np.concatenate([x[:p], x[p + L :]])
        t = p / sr
    return _requant(y), {"step": "cut", "removed_from_s": p / sr, "removed_length_s": L / sr,
                         "crossfade_ms": crossfade_ms, "edit_times_s": [t]}


def insert_silence(a: np.ndarray, sr: int, rng: np.random.Generator) -> tuple[np.ndarray, dict]:
    p = edit_position(rng, len(a), sr)
    L = int(rng.uniform(0.25, 0.8) * sr)
    y = np.concatenate([a[:p], np.zeros(L, dtype=np.int16), a[p:]])
    return y, {"step": "insert_digital_silence", "at_s": p / sr, "length_s": L / sr, "edit_times_s": [p / sr, (p + L) / sr]}


def gain_step(a: np.ndarray, sr: int, rng: np.random.Generator) -> tuple[np.ndarray, dict]:
    p = edit_position(rng, len(a), sr)
    L = int(rng.uniform(0.8, 1.6) * sr)
    L = min(L, len(a) - p - int(0.5 * sr))
    g_db = float(rng.choice([6.0, 4.0, -4.4, -6.0]))
    x = a.astype(np.float64)
    x[p : p + L] *= 10 ** (g_db / 20)
    return _requant(x), {"step": "gain_step", "from_s": p / sr, "to_s": (p + L) / sr, "gain_db": g_db,
                         "edit_times_s": [p / sr, (p + L) / sr]}


def copy_overwrite(a: np.ndarray, sr: int, rng: np.random.Generator) -> tuple[np.ndarray, dict]:
    n = len(a)
    L = int(rng.uniform(0.4, 0.8) * sr)
    src = int(rng.uniform(0.5, n / sr / 2 - 0.9) * sr)
    dst = int(rng.uniform(n / sr / 2 + 0.2, n / sr - 1.0) * sr)
    dst = min(dst, n - L - int(0.3 * sr))
    y = a.copy()
    y[dst : dst + L] = a[src : src + L]
    return y, {"step": "copy_overwrite", "source_s": src / sr, "dest_s": dst / sr, "length_s": L / sr,
               "edit_times_s": [dst / sr, (dst + L) / sr]}


def add_noise(a: np.ndarray, sr: int, rng: np.random.Generator, level_dbfs: float = -45.0) -> tuple[np.ndarray, dict]:
    from .sources import pink_noise

    noise = pink_noise(rng, len(a)) * 32767 * 10 ** (level_dbfs / 20)
    return _requant(a.astype(np.float64) + noise), {"step": "add_background_noise", "level_dbfs": level_dbfs,
                                                     "scope": "whole file", "edit_times_s": []}


def normalize(a: np.ndarray, target_peak_dbfs: float = -1.0) -> tuple[np.ndarray, dict]:
    peak = np.max(np.abs(a.astype(np.float64)))
    g = (32767 * 10 ** (target_peak_dbfs / 20)) / max(peak, 1)
    return _requant(a.astype(np.float64) * g), {"step": "peak_normalize", "gain_db": float(20 * np.log10(g)),
                                                 "scope": "whole file", "edit_times_s": []}


def noise_gate(a: np.ndarray, sr: int, threshold_dbfs: float = -45.0, hold_ms: float = 30.0) -> tuple[np.ndarray, dict]:
    """Hard noise gate: samples in windows whose RMS is below threshold are set to zero."""
    x = a.astype(np.float64) / 32768
    w = int(hold_ms * 1e-3 * sr)
    pw = np.convolve(x * x, np.ones(w) / w, mode="same")
    closed = pw < 10 ** (threshold_dbfs / 10)
    y = a.copy()
    y[closed] = 0
    return y, {"step": "noise_gate", "threshold_dbfs": threshold_dbfs, "hold_ms": hold_ms,
               "gated_fraction": float(closed.mean()), "scope": "whole file", "edit_times_s": []}


def _ratio(sr_from: int, sr_to: int) -> tuple[int, int]:
    g = gcd(sr_from, sr_to)
    return sr_to // g, sr_from // g


def resample(a: np.ndarray, sr: int, rng: np.random.Generator, mode: str) -> tuple[np.ndarray, int, dict]:
    x = a.astype(np.float64)
    if mode == "poly_down_up":
        mid = int(rng.choice([16000, 22050]))
        up, down = _ratio(sr, mid)
        y = resample_poly(x, up, down)
        up2, down2 = _ratio(mid, sr)
        y = resample_poly(y, up2, down2)
        return _requant(y), sr, {"step": "resample", "mode": mode, "intermediate_rate": mid, "output_rate": sr,
                                 "method": "scipy.signal.resample_poly (Kaiser windowed sinc)", "edit_times_s": []}
    if mode == "linear_up":
        mid = 22050
        up, down = _ratio(sr, mid)
        y = resample_poly(x, up, down)
        t_out = np.arange(int(len(y) * sr / mid)) * (mid / sr)
        y = np.interp(t_out, np.arange(len(y)), y)
        return _requant(y), sr, {"step": "resample", "mode": mode, "intermediate_rate": mid, "output_rate": sr,
                                 "method": "resample_poly down, linear interpolation up", "edit_times_s": []}
    if mode == "to48k":
        up, down = _ratio(sr, 48000)
        return _requant(resample_poly(x, up, down)), 48000, {"step": "resample", "mode": mode, "output_rate": 48000,
                                                              "method": "scipy.signal.resample_poly", "edit_times_s": []}
    raise ValueError(mode)


def ffmpeg_available() -> bool:
    return find_tool("ffmpeg") is not None


def mp3_chain(a: np.ndarray, sr: int, bitrates: list[int], keep_mp3: Path | None = None) -> tuple[np.ndarray, dict]:
    """Encode/decode through LAME (via FFmpeg) once per bitrate; optionally keep the final MP3."""
    with tempfile.TemporaryDirectory(prefix="sonictrace_ds_") as tmp:
        cur = Path(tmp) / "g0.wav"
        sf.write(str(cur), a, sr, subtype="PCM_16")
        for i, br in enumerate(bitrates, 1):
            mp3 = Path(tmp) / f"g{i}.mp3"
            dec = Path(tmp) / f"g{i}.wav"
            r = run_tool(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(cur), "-codec:a", "libmp3lame",
                          "-b:a", f"{br}k", str(mp3)], timeout=120)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.decode("utf-8", "replace"))
            if keep_mp3 is not None and i == len(bitrates):
                keep_mp3.write_bytes(mp3.read_bytes())
                return a, {"step": "mp3_chain", "bitrates_kbps": bitrates, "encoder": "libmp3lame via FFmpeg",
                           "stored_as": "mp3", "edit_times_s": []}
            r = run_tool(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(mp3), "-c:a", "pcm_s16le", str(dec)], timeout=120)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.decode("utf-8", "replace"))
            cur = dec
        y, _ = sf.read(str(cur), dtype="int16")
    if y.ndim > 1:
        y = y[:, 0]
    return y, {"step": "mp3_chain", "bitrates_kbps": bitrates, "encoder": "libmp3lame via FFmpeg",
               "stored_as": "wav (decoded)", "edit_times_s": []}
