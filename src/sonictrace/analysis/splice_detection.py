"""Module C: splice / discontinuity investigation.

C1  Waveform discontinuity - impulses in the linear-prediction residual.
C2  Short-time energy discontinuity.
C3  Spectral discontinuity (log-spectral distance between non-overlapping frames).
C5  Digital silence and padding (runs of exactly-zero samples).

C4 (noise floor) lives in ``noise_analysis``, C6 (duplication) in ``duplication`` and
C7 (ENF phase) in ``enf_analysis``.

Principle of C1: a short-term linear predictor of order p,
    x_hat[n] = sum_{k=1..p} a_k x[n-k],
whitens a locally stationary signal, so the residual e[n] = x[n] - x_hat[n] looks like
low-level noise. A hard edit joins two waveforms whose values and slopes do not
continue each other; the predictor fails for a few samples and e[n] shows an isolated
impulse much larger than every residual value in its neighbourhood. Comparing against
the neighbourhood *maximum* (not the RMS) keeps periodic residual peaks - e.g. glottal
pulses in real speech - from being reported as discontinuities.
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import LinAlgError, solve_toeplitz
from scipy.ndimage import maximum_filter1d
from scipy.signal import lfilter

from ..evidence.evidence_model import Category, EvidenceRegistry, Localization, Severity, TestResult
from .context import AnalysisContext
from .signal_features import runs_of_true, to_db
from .stats import group_indices, local_maxima, robust_z


# ----------------------------------------------------------------------------- C1
def lpc_residual(x: np.ndarray, order: int = 16, block: int = 4096) -> np.ndarray:
    """Blockwise autocorrelation-method LPC residual (coefficients re-estimated per block)."""
    n = len(x)
    e = np.zeros(n)
    win_len = 2 * block
    window = np.hanning(win_len)
    nfft = 1 << int(np.ceil(np.log2(2 * win_len)))
    for start in range(0, n, block):
        end = min(n, start + block)
        a0 = max(0, start - block // 2)
        est = x[a0 : a0 + win_len]
        est = est * window[: len(est)]
        spec = np.fft.rfft(est, nfft)
        r = np.fft.irfft(spec * np.conj(spec), nfft)[: order + 1]
        seg_start = max(0, start - order)
        seg = x[seg_start:end]
        if r[0] <= 1e-18:
            e[start:end] = x[start:end]
            continue
        r = r.copy()
        r[0] *= 1.0 + 1e-6  # white-noise correction (regularisation)
        try:
            a = solve_toeplitz(r[:order], r[1 : order + 1])
        except (LinAlgError, ValueError):
            a = np.zeros(order)
        res = lfilter(np.concatenate(([1.0], -a)), [1.0], seg)
        e[start:end] = res[start - seg_start :]
    return e


def _side_max(a: np.ndarray, near: int, far: int) -> tuple[np.ndarray, np.ndarray]:
    """Max of a over [n-far, n-near] (left) and [n+near, n+far] (right)."""
    size = far - near + 1
    m = maximum_filter1d(a, size=size, mode="constant", cval=0.0)
    shift = (far + near) // 2
    left = np.zeros_like(a)
    right = np.zeros_like(a)
    left[shift:] = m[:-shift] if shift else m
    right[:-shift] = m[shift:] if shift else m
    return left, right


def run_waveform_discontinuity(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    sr = ctx.sr
    test = TestResult("C1", "Waveform discontinuity (LPC residual impulses)", "C: splicing", "waveform",
                      score_name="max residual impulse / neighbourhood max", threshold=cfg.residual_peak_ratio)
    e = lpc_residual(ctx.x, cfg.residual_lpc_order, cfg.residual_block)
    ae = np.abs(e)
    ctx.cache["lpc_residual"] = e
    near = max(1, int(round(cfg.residual_guard_ms * 1e-3 * sr)))
    far = max(near + 2, int(round(cfg.residual_neighbor_ms * 1e-3 * sr)))
    left, right = _side_max(ae, near, far)
    neigh = np.maximum(left, right)
    abs_floor = 2.0 * ctx.lsb
    ratio = ae / np.maximum(neigh, abs_floor)
    edge = far + cfg.residual_lpc_order
    ratio[:edge] = 0.0
    ratio[-edge:] = 0.0
    test.score = float(ratio.max()) if ratio.size else 0.0
    cand = np.flatnonzero(ratio >= cfg.residual_peak_ratio)
    groups = group_indices(cand, gap=near * 4)
    events = []
    for g in groups:
        i = int(g[np.argmax(ratio[g])])
        events.append((ratio[i], i))
    events.sort(reverse=True)
    test.measurements = {"candidates": len(events), "residual_rms": float(np.sqrt(np.mean(e * e))),
                         "neighbourhood_ms": cfg.residual_neighbor_ms, "lpc_order": cfg.residual_lpc_order}
    for r, i in events[: cfg.residual_max_findings]:
        jump = float(abs(ctx.x[i] - ctx.x[i - 1]))
        f = reg.add_finding(
            "SPL", test_id=test.test_id, module=test.module, method="LPC residual impulse vs. neighbourhood maximum",
            family="waveform", category=Category.OBSERVED,
            severity=Severity.MEDIUM if r >= 2 * cfg.residual_peak_ratio else Severity.LOW,
            title=f"Isolated waveform discontinuity at {i / sr:.4f} s",
            description=(f"The prediction residual at sample {i} is {r:.1f}x larger than any residual value within "
                         f"{cfg.residual_neighbor_ms:.0f} ms on either side; the waveform does not continue smoothly."),
            localization=Localization.POINT, time_start=i / sr, time_end=i / sr, sample_start=i, sample_end=i,
            measurements={"impulse_ratio": r, "residual_value": float(e[i]), "sample_step": jump,
                          "sample_step_dbfs": float(to_db(np.array([jump]))[0])},
            baseline={"ratio_threshold": cfg.residual_peak_ratio, "neighbourhood_ms": cfg.residual_neighbor_ms,
                      "guard_ms": cfg.residual_guard_ms},
            alternative_explanations=[
                "Click, pop, plosive or percussive onset in the original sound",
                "Digital dropout, buffer underrun or bit error in the recording chain",
                "Clipping onset",
                "A hard edit point (cut, insertion or gain step without crossfade)",
            ],
            limitations=["Edits made at zero crossings with matching slope, or with crossfades, produce no impulse."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(test.finding_ids)
    test.summary = (f"{len(events)} isolated residual impulse(s); {len(test.finding_ids)} reported." if events
                    else "No isolated waveform discontinuity above threshold.")
    if len(events) > cfg.residual_max_findings:
        test.limitations.append(f"Only the {cfg.residual_max_findings} strongest of {len(events)} candidates are reported.")
    return test


# ----------------------------------------------------------------------------- C2
def short_time_level(x: np.ndarray, sr: int, win_ms: float, hop_ms: float) -> tuple[np.ndarray, np.ndarray, int, int]:
    win = max(8, int(round(win_ms * 1e-3 * sr)))
    hop = max(1, int(round(hop_ms * 1e-3 * sr)))
    cs = np.concatenate(([0.0], np.cumsum(x * x)))
    starts = np.arange(0, max(1, len(x) - win + 1), hop)
    energy = np.maximum(cs[starts + win] - cs[starts], 0.0) / win
    return starts, to_db(energy, power=True, floor=-120.0), win, hop


def run_energy_discontinuity(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    sr = ctx.sr
    test = TestResult("C2", "Short-time energy discontinuity", "C: splicing", "short_time",
                      score_name="max robust z of level step", threshold=cfg.energy_jump_z)
    starts, lvl, win, hop = short_time_level(ctx.x, sr, cfg.energy_window_ms, cfg.energy_hop_ms)
    lag = max(1, win // hop)
    if len(lvl) <= 2 * lag + 2:
        test.status = "not_applicable"
        test.summary = "Recording too short."
        return test
    # d[t] compares the window ending at the boundary with the window starting there
    d = lvl[lag:] - lvl[:-lag]
    boundary = starts[lag:]
    z = robust_z(np.abs(d))
    test.score = float(np.max(z))
    peaks = [p for p in local_maxima(np.abs(d), radius=2 * lag) if abs(d[p]) >= cfg.energy_jump_db and z[p] >= cfg.energy_jump_z]
    test.measurements = {"window_ms": cfg.energy_window_ms, "median_abs_step_db": float(np.median(np.abs(d))), "candidates": len(peaks)}
    for p in peaks[:40]:
        t = boundary[p] / sr
        f = reg.add_finding(
            "SPL", test_id=test.test_id, module=test.module, method="10 ms level before vs. after boundary",
            family="short_time", category=Category.STATISTICAL,
            severity=Severity.LOW,
            title=f"Abrupt level change of {d[p]:+.1f} dB at {t:.3f} s",
            description=f"Signal level changes by {d[p]:+.1f} dB within {cfg.energy_window_ms:.0f} ms (robust z = {z[p]:.1f}).",
            localization=Localization.POINT, time_start=t, time_end=t, sample_start=int(boundary[p]), sample_end=int(boundary[p]),
            measurements={"level_step_db": d[p], "robust_z": z[p], "level_before_db": lvl[p], "level_after_db": lvl[p + lag]},
            baseline={"step_threshold_db": cfg.energy_jump_db, "z_threshold": cfg.energy_jump_z},
            alternative_explanations=["Natural onset/offset of speech, notes or percussive sounds", "Noise gate or recorder muting",
                                      "Inserted or removed segment"],
            limitations=["Ordinary speech onsets after pauses produce large level steps; on its own this is weak evidence."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(test.finding_ids)
    test.summary = f"{len(peaks)} abrupt level change(s) above threshold." if peaks else "No abrupt level change above threshold."
    return test


# ----------------------------------------------------------------------------- C3
def run_spectral_discontinuity(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    spec = ctx.spec
    test = TestResult("C3", "Spectral discontinuity (log-spectral distance)", "C: splicing", "short_time",
                      score_name="max robust z of log-spectral distance", threshold=cfg.spectral_jump_z)
    lag = ctx.config.hop_divisor  # frames that no longer overlap
    if spec.mag.shape[1] <= 2 * lag + 2:
        test.status = "not_applicable"
        test.summary = "Recording too short."
        return test
    hi = ctx.bandlimit.cutoff_hz if ctx.bandlimit.found and ctx.bandlimit.steep else 0.9 * ctx.sr / 2
    band = (spec.freqs >= 100.0) & (spec.freqs <= min(hi, 16000.0))
    logm = 20.0 * np.log10(spec.mag[band].astype(np.float64) + 1e-9)
    # frames quieter than the noise floor carry no spectral information
    lsd = np.sqrt(np.mean((logm[:, lag:] - logm[:, :-lag]) ** 2, axis=0))
    z = robust_z(lsd)
    test.score = float(np.max(z))
    peaks = [p for p in local_maxima(lsd, radius=2 * lag) if lsd[p] >= cfg.spectral_jump_db and z[p] >= cfg.spectral_jump_z]
    t_bound = (np.arange(len(lsd)) + lag) * spec.hop / ctx.sr
    test.measurements = {"median_lsd_db": float(np.median(lsd)), "candidates": len(peaks)}
    for p in peaks[:40]:
        t = float(t_bound[p])
        f = reg.add_finding(
            "SPL", test_id=test.test_id, module=test.module, method="log-spectral distance between non-overlapping STFT frames",
            family="short_time", category=Category.STATISTICAL, severity=Severity.LOW,
            title=f"Abrupt spectral change at {t:.3f} s",
            description=f"Log-spectral distance {lsd[p]:.1f} dB between adjacent non-overlapping frames (robust z = {z[p]:.1f}).",
            localization=Localization.POINT, time_start=t, time_end=t,
            measurements={"log_spectral_distance_db": lsd[p], "robust_z": z[p]},
            baseline={"lsd_threshold_db": cfg.spectral_jump_db, "z_threshold": cfg.spectral_jump_z},
            alternative_explanations=["Phoneme or note transition", "Onset of a new sound source", "Edit point"],
            limitations=["Frame resolution is n_fft/4 samples; content changes are common in speech and music."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(test.finding_ids)
    test.summary = f"{len(peaks)} abrupt spectral change(s)." if peaks else "No abrupt spectral change above threshold."
    return test


# ----------------------------------------------------------------------------- C5
def run_digital_silence(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    sr = ctx.sr
    test = TestResult("C5", "Digital silence and padding", "C: splicing", "silence",
                      score_name="longest interior exact-zero run (ms)", threshold=cfg.digital_silence_min_ms)
    zero = np.all(ctx.audio.samples == 0.0, axis=1)
    min_len = max(1, int(round(cfg.digital_silence_min_ms * 1e-3 * sr)))
    runs = [(s, e) for s, e in runs_of_true(zero) if e - s >= min_len]
    n = len(zero)
    lead = runs[0][1] if runs and runs[0][0] == 0 else 0
    trail = n - runs[-1][0] if runs and runs[-1][1] == n else 0
    interior = [(s, e) for s, e in runs if s > 0 and e < n]
    test.measurements = {
        "leading_zero_samples": lead, "trailing_zero_samples": trail,
        "leading_zero_ms": 1e3 * lead / sr, "trailing_zero_ms": 1e3 * trail / sr,
        "interior_runs": len(interior), "total_zero_samples": int(zero.sum()),
    }
    test.score = max([1e3 * (e - s) / sr for s, e in interior], default=0.0)
    ff = ctx.frames
    # v1.1: many short zero runs spread over the file are the signature of a noise gate / silence
    # suppression, not of individual insertions (benchmark v1.0: 3/4 gated controls flagged MEDIUM).
    gating = len(interior) >= cfg.gating_pattern_min_runs
    test.measurements["systematic_gating_pattern"] = gating
    if gating:
        f = reg.add_finding(
            "SIL", test_id=test.test_id, module=test.module, method="exact-zero run pattern analysis", family="processing",
            category=Category.OBSERVED, severity=Severity.LOW,
            title=f"{len(interior)} digital-silence runs: systematic gating pattern",
            description=(f"{len(interior)} separate runs of exact zeros occur across the recording. Such a pattern is produced by "
                         "a noise gate or silence suppression applied to the whole recording; individual runs are therefore "
                         "reported at low severity."),
            localization=Localization.GLOBAL, measurements={"runs": len(interior), "total_zero_samples": int(zero.sum())},
            baseline={"min_runs_for_pattern": cfg.gating_pattern_min_runs},
            alternative_explanations=["Noise gate / VAD-based silence suppression", "Repeated manual muting or insertion of silence"],
            limitations=["Repeated deliberate insertions of digital silence would also match this pattern."],
        )
        test.finding_ids.append(f.finding_id)
    for s, e in interior:
        t0, t1 = s / sr, e / sr
        around = ((ff.times > t0 - 0.5) & (ff.times < t0 - 0.02)) | ((ff.times > t1 + 0.02) & (ff.times < t1 + 0.5))
        bg = ff.rms_db[around]
        bg = bg[bg > -140.0]
        bg_floor = float(np.percentile(bg, 10)) if bg.size else None
        noisy_context = bg_floor is not None and bg_floor > -100.0
        f = reg.add_finding(
            "SIL", test_id=test.test_id, module=test.module, method="exact-zero sample run detection", family="silence",
            category=Category.OBSERVED, severity=Severity.MEDIUM if (noisy_context and not gating) else Severity.LOW,
            title=f"Digital silence of {1e3 * (e - s) / sr:.0f} ms at {t0:.3f}-{t1:.3f} s",
            description=(f"{e - s} consecutive samples are exactly zero in every channel"
                         + (f", while the surrounding background noise is about {bg_floor:.0f} dBFS. A continuous acoustic "
                            "recording would contain that background noise during pauses." if noisy_context else ".")),
            localization=Localization.REGION, time_start=t0, time_end=t1, sample_start=int(s), sample_end=int(e),
            measurements={"run_samples": e - s, "run_ms": 1e3 * (e - s) / sr, "surrounding_noise_floor_db": bg_floor},
            baseline={"minimum_run_ms": cfg.digital_silence_min_ms, "noisy_context_threshold_db": -100.0},
            alternative_explanations=["Inserted silence (editing)", "Noise gate or 'silence removal' processing",
                                      "Recorder muting or pause function", "Dropout in the recording chain"],
            limitations=["Dithered or noise-filled insertions are not exact zeros and are not detected by this test."],
        )
        test.finding_ids.append(f.finding_id)
    if lead >= min_len or trail >= min_len:
        f = reg.add_finding(
            "SIL", test_id=test.test_id, module=test.module, method="exact-zero sample run detection", family="silence",
            category=Category.OBSERVED, severity=Severity.INFO, title="Leading/trailing digital silence (padding)",
            description=f"{lead} leading and {trail} trailing samples are exactly zero.",
            localization=Localization.GLOBAL, measurements={"leading_samples": lead, "trailing_samples": trail},
            alternative_explanations=["Codec priming/padding", "Editor fade or trimming", "Recorder start-up behaviour"],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(interior)
    test.summary = (f"{len(interior)} interior digital-silence run(s) >= {cfg.digital_silence_min_ms:.0f} ms." if interior
                    else "No interior digital silence.")
    return test
