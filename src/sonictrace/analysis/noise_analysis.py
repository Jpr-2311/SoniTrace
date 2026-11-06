"""Noise-floor estimation and background-consistency analysis.

The background noise of a recording is set by the room, the microphone and the
pre-amplifier. Within one continuous take it changes slowly. A splice that joins
material recorded under different conditions therefore often shows a *step* in the
noise floor even when the foreground content (speech) hides the edit.

Estimator: minimum statistics. In blocks of ``noise_block_s`` the 10th percentile of
short-frame RMS levels approximates the level of the quietest frames (pauses), which
are dominated by background noise (cf. R. Martin, "Noise power spectral density
estimation based on optimal smoothing and minimum statistics", IEEE Trans. Speech and
Audio Processing 9(5), 2001). A per-mel-band percentile gives the noise *spectrum*.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..evidence.evidence_model import Category, EvidenceRegistry, Localization, Severity, TestResult
from .context import AnalysisContext
from .stats import local_maxima, robust_z


@dataclass
class NoiseProfile:
    block_times: np.ndarray  # block centres (s)
    level_db: np.ndarray  # per-block noise-floor estimate
    mel_profile_db: np.ndarray  # (n_blocks, n_mels)
    global_floor_db: float
    active_level_db: float
    snr_estimate_db: float


def estimate_noise_profile(ctx: AnalysisContext) -> NoiseProfile:
    cfg = ctx.config
    ff = ctx.frames
    frames_per_block = max(2, int(round(cfg.noise_block_s * ctx.sr / ctx.hop)))
    n_blocks = max(1, len(ff.rms_db) // frames_per_block)
    levels, profiles, times = [], [], []
    lm = ctx.spectral.log_mel
    for b in range(n_blocks):
        sl = slice(b * frames_per_block, (b + 1) * frames_per_block)
        levels.append(np.percentile(ff.rms_db[sl], cfg.noise_percentile))
        profiles.append(np.percentile(lm[:, sl], cfg.noise_percentile, axis=1))
        times.append(float(np.mean(ff.times[sl])))
    level = np.array(levels)
    active = ff.rms_db[ff.rms_db > -110.0]
    gfloor = float(np.median(level))
    act = float(np.percentile(active, 90)) if active.size else gfloor
    return NoiseProfile(np.array(times), level, np.array(profiles), gfloor, act, act - gfloor)


def run_noise_consistency(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    test = TestResult("C4", "Background noise-floor consistency", "C: splicing", "noise",
                      score_name="max robust z of noise-floor step", threshold=cfg.noise_shift_z)
    prof = estimate_noise_profile(ctx)
    ctx.cache["noise_profile"] = prof
    k = cfg.noise_context_blocks
    n = len(prof.level_db)
    test.measurements = {
        "global_noise_floor_db": prof.global_floor_db,
        "active_level_p90_db": prof.active_level_db,
        "snr_estimate_db": prof.snr_estimate_db,
        "blocks": n,
        "block_seconds": cfg.noise_block_s,
    }
    if n < 2 * k + 1:
        test.status = "not_applicable"
        test.summary = f"Recording too short for a {k}-block context on each side of a boundary."
        return test
    # ignore blocks that are digital silence: their 'noise floor' is the numeric floor, handled by C5
    valid = prof.level_db > -140.0
    lvl = np.where(valid, prof.level_db, np.nan)
    steps, shapes, idx = [], [], []
    for b in range(k, n - k + 1):
        left, right = lvl[b - k : b], lvl[b : b + k]
        if np.isnan(left).sum() > k // 2 or np.isnan(right).sum() > k // 2:
            continue
        dl = float(np.nanmedian(right) - np.nanmedian(left))
        pl = np.median(prof.mel_profile_db[b - k : b], axis=0)
        pr = np.median(prof.mel_profile_db[b : b + k], axis=0)
        shape = (pr - pr.mean()) - (pl - pl.mean())
        steps.append(dl)
        shapes.append(float(np.sqrt(np.mean(shape * shape))))
        idx.append(b)
    if not idx:
        test.status = "not_applicable"
        test.summary = "No boundary had enough non-silent context."
        return test
    steps_a, shapes_a, idx_a = np.array(steps), np.array(shapes), np.array(idx)
    z_step = robust_z(np.abs(steps_a))
    z_shape = robust_z(shapes_a)
    z = np.maximum(z_step, z_shape)
    test.score = float(np.max(z))
    peaks = local_maxima(z, radius=k)
    block_edges = prof.block_times - cfg.noise_block_s / 2.0
    for p in peaks:
        big_step = abs(steps_a[p]) >= cfg.noise_shift_db
        big_shape = shapes_a[p] >= cfg.noise_shape_db
        if z[p] < cfg.noise_shift_z or not (big_step or big_shape):
            continue
        t = float(block_edges[idx_a[p]])
        f = reg.add_finding(
            "NOI", test_id=test.test_id, module=test.module, method="minimum-statistics noise floor, left/right context comparison",
            family="noise", category=Category.STATISTICAL,
            severity=Severity.MEDIUM if (big_step and big_shape) or abs(steps_a[p]) >= 2 * cfg.noise_shift_db else Severity.LOW,
            title=f"Background noise changes abruptly near {t:.2f} s",
            description=(f"The estimated background level changes by {steps_a[p]:+.1f} dB and the noise spectrum shape by "
                         f"{shapes_a[p]:.1f} dB RMS between the {k * cfg.noise_block_s:.2f} s before and after this point."),
            localization=Localization.POINT, time_start=max(0.0, t - cfg.noise_block_s), time_end=t + cfg.noise_block_s,
            measurements={"level_step_db": steps_a[p], "spectral_shape_change_db": shapes_a[p], "robust_z": z[p]},
            baseline={"level_step_threshold_db": cfg.noise_shift_db, "shape_threshold_db": cfg.noise_shape_db, "z_threshold": cfg.noise_shift_z},
            alternative_explanations=[
                "A real change in the acoustic environment (door, HVAC, traffic, movement of the recorder)",
                "Automatic gain control or noise suppression adapting in the recording device",
                "Continuous speech/music without pauses on one side, which biases the minimum-statistics estimate upward",
                "Joining material recorded under different conditions (splice)",
            ],
            limitations=["Time resolution is limited to the block size.", "Needs pauses or quiet passages to observe the background."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(test.finding_ids)
    test.summary = (f"{len(test.finding_ids)} abrupt background change(s) found." if test.detected
                    else "No abrupt change of background level or spectrum above threshold.")
    return test
