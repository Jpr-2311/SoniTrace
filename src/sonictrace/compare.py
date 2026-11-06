"""Controlled reference comparison: questioned file vs. a known reference (``sonictrace compare``).

Block alignment: the questioned file is cut into 0.25 s blocks; each block is located in
the reference by normalised cross-correlation within +/- 2 s. In an unedited copy the
alignment offset is constant. A step in the offset between consecutive well-matched
blocks means material was removed (offset increases) or inserted (offset decreases) at
that point; blocks that match nothing contain material absent from the reference.
"""

from __future__ import annotations

from math import gcd
from pathlib import Path

import numpy as np
from scipy.signal import correlate, resample_poly

from .analysis.spectral_analysis import compute_ltas, detect_bandlimit
from .config import AnalysisConfig
from .evidence.evidence_model import _clean
from .utils.audio_loader import load_audio
from .utils.hashing import sha256_file
from .utils.validation import sniff_file, validate_input_file


def _best_match(ref: np.ndarray, seg: np.ndarray, lo: int) -> tuple[float, int]:
    L = len(seg)
    if len(ref) < L or L < 64:
        return 0.0, lo
    s = seg - seg.mean()
    se = np.sqrt(np.sum(s * s))
    if se < 1e-12:
        return float("nan"), lo
    num = correlate(ref, s, mode="valid", method="fft")
    cs = np.concatenate(([0.0], np.cumsum(ref)))
    cs2 = np.concatenate(([0.0], np.cumsum(ref * ref)))
    sums = cs[L:] - cs[:-L]
    en = np.maximum(cs2[L:] - cs2[:-L] - sums * sums / L, 1e-20)
    ncc = num / (np.sqrt(en) * se)
    k = int(np.argmax(ncc))
    return float(ncc[k]), lo + k


def compare_files(reference: str | Path, questioned: str | Path, config: AnalysisConfig | None = None,
                  block_s: float = 0.25, max_shift_s: float = 2.0) -> tuple[dict, np.ndarray, np.ndarray, int]:
    cfg = config or AnalysisConfig()
    pr = validate_input_file(reference, cfg.max_file_bytes)
    pq = validate_input_file(questioned, cfg.max_file_bytes)
    hr, hq = sha256_file(pr), sha256_file(pq)
    ar = load_audio(pr, sniff_file(pr), cfg.max_duration_s, cfg.max_channels)
    aq = load_audio(pq, sniff_file(pq), cfg.max_duration_s, cfg.max_channels)
    sr = ar.sample_rate
    a, b = ar.mono, aq.mono
    notes = []
    if aq.sample_rate != sr:
        g = gcd(sr, aq.sample_rate)
        b = resample_poly(b, sr // g, aq.sample_rate // g)
        notes.append(f"Questioned file ({aq.sample_rate} Hz) was resampled to the reference rate ({sr} Hz) for alignment only. "
                     "A different sample rate is not by itself evidence of manipulation.")
    blk = int(block_s * sr)
    shift = int(max_shift_s * sr)
    blocks = []
    for s in range(0, max(1, len(b) - blk + 1), blk):
        seg = b[s : s + blk]
        lo = max(0, s - shift)
        hi = min(len(a), s + blk + shift)
        ncc, pos = _best_match(a[lo:hi], seg, lo)
        rms_q = float(np.sqrt(np.mean(seg * seg)))
        ref_seg = a[pos : pos + blk]
        rms_r = float(np.sqrt(np.mean(ref_seg * ref_seg))) if len(ref_seg) else 0.0
        gain = 20 * np.log10(rms_q / rms_r) if rms_q > 0 and rms_r > 0 else None
        blocks.append({"time_s": s / sr, "ncc": 0.0 if ncc != ncc else ncc, "silent": ncc != ncc,
                       "offset_samples": pos - s, "offset_s": (pos - s) / sr, "gain_db": gain})
    good = [b_ for b_ in blocks if b_["ncc"] >= 0.9]
    findings = []
    for prev, cur in zip(good, good[1:]):
        d = cur["offset_samples"] - prev["offset_samples"]
        if abs(d) > 2:
            kind = "removed from" if d > 0 else "inserted into"
            findings.append({"type": "alignment_step", "time_s": cur["time_s"], "between_s": [prev["time_s"], cur["time_s"]],
                             "offset_change_samples": d, "offset_change_s": d / sr,
                             "statement": f"About {abs(d) / sr:.3f} s of material was {kind} the questioned file between "
                                          f"{prev['time_s']:.2f} s and {cur['time_s'] + block_s:.2f} s (alignment offset step)."})
    for bl in blocks:
        if bl["silent"]:
            findings.append({"type": "silent_block", "time_s": bl["time_s"],
                             "statement": f"Block at {bl['time_s']:.2f} s is digital silence; it cannot be matched to the reference."})
        elif bl["ncc"] < 0.5:
            findings.append({"type": "unmatched_block", "time_s": bl["time_s"], "ncc": bl["ncc"],
                             "statement": f"Block at {bl['time_s']:.2f} s has no counterpart in the reference within +/-{max_shift_s:.0f} s (NCC {bl['ncc']:.2f})."})
    gains = np.array([b_["gain_db"] for b_ in good if b_["gain_db"] is not None])
    if gains.size:
        med = float(np.median(gains))
        for bl in good:
            if bl["gain_db"] is not None and abs(bl["gain_db"] - med) > 1.0:
                findings.append({"type": "gain_change", "time_s": bl["time_s"], "gain_db": bl["gain_db"] - med,
                                 "statement": f"Block at {bl['time_s']:.2f} s is {bl['gain_db'] - med:+.1f} dB relative to the typical level ratio."})
    fr, prr = compute_ltas(a, sr)
    fq, pqq = compute_ltas(b, sr)
    bl_r, bl_q = detect_bandlimit(fr, prr, sr), detect_bandlimit(fq, pqq, sr)
    aligned = [b_ for b_ in good]
    result = {
        "report_type": "sonictrace.comparison",
        "reference": {"path": str(pr), "sha256": hr, **ar.describe()},
        "questioned": {"path": str(pq), "sha256": hq, **aq.describe()},
        "identical_files": hr == hq,
        "notes": notes,
        "global_offset_s": float(np.median([b_["offset_s"] for b_ in aligned])) if aligned else None,
        "matched_block_fraction": len(good) / max(1, len(blocks)),
        "bandwidth": {"reference": bl_r.to_dict(), "questioned": bl_q.to_dict()},
        "findings": findings,
        "blocks": blocks,
        "limitations": ["Assumes the reference is the original or a faithful copy.",
                        "Heavy processing (lossy coding at low bitrate, time-stretching) lowers block NCC and can hide alignment steps.",
                        f"Insertions/removals shorter than ~2 samples or longer than +/-{max_shift_s:.0f} s are not resolved."],
    }
    if bl_q.found and bl_q.steep and (not bl_r.steep or (bl_r.cutoff_hz and bl_q.cutoff_hz < 0.9 * bl_r.cutoff_hz)):
        findings.append({"type": "bandwidth_reduction", "statement": f"The questioned file is band-limited at {bl_q.cutoff_hz:.0f} Hz; "
                                                                     "the reference is not: consistent with lossy coding or resampling of the questioned copy."})
    return _clean(result), a, b, sr
