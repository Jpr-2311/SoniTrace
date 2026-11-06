"""Robust statistics helpers shared by the detectors."""

from __future__ import annotations

import numpy as np

MAD_TO_SIGMA = 1.4826  # consistency constant for Gaussian data


def mad(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return 0.0
    return float(np.median(np.abs(x - np.median(x))))


def robust_z(x: np.ndarray, floor: float = 1e-9) -> np.ndarray:
    """Modified z-score (Iglewicz & Hoaglin, 1993): (x - median) / (1.4826 * MAD)."""
    x = np.asarray(x, dtype=np.float64)
    finite = x[np.isfinite(x)]
    if finite.size == 0:
        return np.zeros_like(x)
    med = np.median(finite)
    scale = MAD_TO_SIGMA * mad(finite)
    if scale < floor:
        # degenerate (constant) baseline: fall back to the mean absolute deviation
        scale = max(float(np.mean(np.abs(finite - med))) * 1.2533, floor)
    z = (x - med) / scale
    return np.where(np.isfinite(z), z, 0.0)


def local_maxima(values: np.ndarray, radius: int) -> list[int]:
    """Indices that are the maximum within +/- radius (greedy non-maximum suppression)."""
    v = np.asarray(values, dtype=np.float64)
    order = np.argsort(-v)
    taken = np.zeros(len(v), dtype=bool)
    out = []
    for i in order:
        if not np.isfinite(v[i]) or taken[i]:
            continue
        out.append(int(i))
        taken[max(0, i - radius) : i + radius + 1] = True
    return sorted(out)


def group_indices(indices: np.ndarray, gap: int) -> list[np.ndarray]:
    """Split sorted indices into groups whose members are at most ``gap`` apart."""
    idx = np.asarray(indices)
    if idx.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(idx) > gap) + 1
    return np.split(idx, breaks)
