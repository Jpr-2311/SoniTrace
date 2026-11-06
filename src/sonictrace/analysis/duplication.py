"""C6: duplicated-segment (copy-move) detection.

Stage 1 (candidate generation): cosine self-similarity of mean-removed log-mel frames.
A segment copied from elsewhere in the same recording appears as a run of very high
similarity along an off-diagonal of the self-similarity matrix.

Stage 2 (verification): normalised cross-correlation (NCC) of the raw waveforms,
searched over a +/- one-hop alignment window. Independent acoustic events - even the
same word spoken twice - do not reproduce the waveform sample by sample, so an NCC
close to 1 is direct evidence that one stretch of samples is a copy of the other.
Only verified pairs become findings.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import correlate

from ..evidence.evidence_model import Category, EvidenceRegistry, Localization, Severity, TestResult
from .context import AnalysisContext


def _ncc_best(x: np.ndarray, a0: int, b0: int, length: int, search: int) -> tuple[float, int]:
    seg = x[a0 : a0 + length]
    lo = max(0, b0 - search)
    hi = min(len(x), b0 + length + search)
    ref = x[lo:hi]
    if len(seg) < 32 or len(ref) < len(seg):
        return 0.0, b0
    seg = seg - seg.mean()
    num = correlate(ref, seg, mode="valid", method="fft")
    cs = np.concatenate(([0.0], np.cumsum(ref)))
    cs2 = np.concatenate(([0.0], np.cumsum(ref * ref)))
    L = len(seg)
    sums = cs[L:] - cs[:-L]
    energy = np.maximum(cs2[L:] - cs2[:-L] - sums * sums / L, 1e-20)
    ncc = num / (np.sqrt(energy) * np.sqrt(np.sum(seg * seg)) + 1e-20)
    k = int(np.argmax(ncc))
    return float(ncc[k]), lo + k


def run_duplication(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    sr = ctx.sr
    test = TestResult("C6", "Duplicated segment (copy-move) detection", "C: splicing", "duplication",
                      score_name="best verified waveform NCC", threshold=cfg.dup_ncc_threshold)
    if ctx.duration > cfg.duplication_max_duration_s:
        test.status = "not_applicable"
        test.summary = f"Skipped: duration exceeds {cfg.duplication_max_duration_s:.0f} s (quadratic self-similarity cost)."
        return test
    # v1.1: full STFT hop for short files (frame-grid misalignment of copies at a 46 ms hop
    # lowered their similarity below threshold); decimate only for long files (memory).
    step = 1 if ctx.duration <= 30.0 else max(1, cfg.dup_hop // ctx.hop)
    lm = ctx.spectral.log_mel[:, ::step]
    level = ctx.frames.rms_db[::step][: lm.shape[1]]
    lm = lm[:, : len(level)]
    hop_s = ctx.hop * step / sr
    # v1.1: "active" relative to the frame-level distribution; the v1.0 rule (noise floor + 15 dB)
    # marked every frame of continuous music inactive because its minimum-statistics floor is the music itself.
    active = level > max(-90.0, min(float(np.percentile(level, 10)) + 6.0, float(np.median(level))))
    z = lm - lm.mean(axis=0, keepdims=True)
    z /= np.linalg.norm(z, axis=0, keepdims=True) + 1e-12
    z[:, ~active] = 0.0
    n = z.shape[1]
    min_len = max(2, int(round(cfg.dup_min_seconds / hop_s)))
    min_lag = max(min_len, int(round(cfg.dup_min_lag_seconds / hop_s)))
    test.measurements = {"frames": n, "frame_hop_s": hop_s, "active_frames": int(active.sum())}
    if n < min_lag + min_len:
        test.status = "not_applicable"
        test.summary = "Recording too short for duplicate search."
        return test
    sim = z.T @ z
    cands = []
    for lag in range(min_lag, n):
        d = np.diagonal(sim, offset=lag)
        good = d >= cfg.dup_similarity
        if good.sum() < min_len:
            continue
        m = np.concatenate(([False], good, [False])).astype(np.int8)
        dd = np.diff(m)
        for s, e in zip(np.flatnonzero(dd == 1), np.flatnonzero(dd == -1)):
            if e - s >= min_len:
                # rank by excess similarity x length: exact copies (~0.999) outrank long runs of
                # merely similar frames (repeated vowels/notes ~0.93-0.96)
                cands.append(((float(d[s:e].mean()) - cfg.dup_similarity) * (e - s), int(s), int(e), lag))
    cands.sort(reverse=True)
    test.measurements["similarity_candidates"] = len(cands)
    best = 0.0
    verified = []
    for _, s, e, lag in cands[: cfg.dup_max_candidates]:
        a0 = s * ctx.hop * step
        b0 = (s + lag) * ctx.hop * step
        length = (e - s) * ctx.hop * step
        ncc, b_best = _ncc_best(ctx.x, a0, b0, length, search=ctx.hop * step)
        best = max(best, ncc)
        if ncc >= cfg.dup_ncc_threshold:
            verified.append((ncc, a0, b_best, length))
    test.score = best
    # keep non-overlapping pairs only
    kept: list[tuple[float, int, int, int]] = []
    for v in sorted(verified, reverse=True):
        if all(abs(v[1] - k[1]) > v[3] // 2 or abs(v[2] - k[2]) > v[3] // 2 for k in kept):
            kept.append(v)
    for ncc, a0, b0, length in kept:
        f = reg.add_finding(
            "DUP", test_id=test.test_id, module=test.module, method="log-mel self-similarity + waveform NCC verification",
            family="duplication", category=Category.OBSERVED, severity=Severity.HIGH if ncc >= 0.999 else Severity.MEDIUM,
            title=f"Segment at {b0 / sr:.2f}-{(b0 + length) / sr:.2f} s duplicates {a0 / sr:.2f}-{(a0 + length) / sr:.2f} s",
            description=(f"{length / sr:.2f} s of waveform at {b0 / sr:.3f} s matches the waveform at {a0 / sr:.3f} s with a "
                         f"normalised cross-correlation of {ncc:.5f}. Independently produced sounds do not repeat sample by sample."),
            localization=Localization.REGION, time_start=b0 / sr, time_end=(b0 + length) / sr,
            sample_start=int(b0), sample_end=int(b0 + length),
            measurements={"ncc": ncc, "source_start_s": a0 / sr, "copy_start_s": b0 / sr, "length_s": length / sr},
            baseline={"ncc_threshold": cfg.dup_ncc_threshold, "similarity_threshold": cfg.dup_similarity},
            alternative_explanations=["Copy-paste editing (copy-move)", "Loop-based music production or sampled/repeated material",
                                      "Synthetic or machine-generated signals with exact periodicity",
                                      "Playback of the same recording twice within the scene"],
            limitations=["Copies that were re-filtered, time-stretched or mixed with other sound may fall below the NCC threshold."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(test.finding_ids)
    test.summary = (f"{len(kept)} verified duplicated segment pair(s)." if kept
                    else f"No duplicated segments verified ({len(cands)} similarity candidate(s) rejected by NCC).")
    return test
