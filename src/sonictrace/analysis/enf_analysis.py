"""C7: electric network frequency (ENF) presence and phase continuity.

Mains hum (50 or 60 Hz) picked up by a recorder is a narrow-band sinusoid whose phase
evolves continuously. Removing or inserting N samples at an edit point shifts the hum
phase after the edit by 2*pi*f0*N/fs (mod 2*pi). Following Rodriguez, Apolinario and
Biscainho ("Audio authenticity: detecting ENF discontinuity with high precision phase
analysis", IEEE Trans. Information Forensics and Security 5(3), 2010), we estimate the
hum phase in short frames and look for steps in the phase track.

Implementation: downsample to 1 kHz, zero-phase band-pass f0 +/- 2 Hz, estimate phase
per 10-cycle frame (hop = 1 cycle) by projection on exp(-j 2 pi f0 t) with an absolute
time reference, unwrap, and compare medians of the phase track before/after each frame.
"""

from __future__ import annotations

from math import gcd

import numpy as np
from scipy.signal import butter, resample_poly, sosfiltfilt, welch

from ..evidence.evidence_model import Category, EvidenceRegistry, Localization, Severity, TestResult
from .context import AnalysisContext
from .stats import local_maxima, robust_z

FS_ENF = 1000


def detect_enf(x: np.ndarray, sr: int) -> tuple[float | None, dict, np.ndarray | None]:
    g = gcd(int(sr), FS_ENF)
    y = resample_poly(x, FS_ENF // g, int(sr) // g)
    if len(y) < 2 * FS_ENF:
        return None, {"reason": "shorter than 2 s"}, None
    f, p = welch(y, fs=FS_ENF, nperseg=min(len(y), 4096))
    best, info = None, {}
    for f0 in (50.0, 60.0):
        peak = (f > f0 - 0.75) & (f < f0 + 0.75)
        ref = (f > f0 - 8) & (f < f0 + 8) & ~((f > f0 - 2) & (f < f0 + 2))
        prom = float(10 * np.log10(p[peak].max() / (np.median(p[ref]) + 1e-30) + 1e-30))
        info[f"prominence_{int(f0)}hz_db"] = prom
        if best is None or prom > info[f"prominence_{int(best)}hz_db"]:
            best = f0
    return best, info, y


def run_enf_phase(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    test = TestResult("C7", "ENF (mains hum) phase continuity", "C: splicing", "enf",
                      score_name="max robust z of hum phase step", threshold=cfg.enf_jump_z)
    f0, info, y = detect_enf(ctx.x, ctx.sr)
    test.measurements = dict(info)
    if f0 is None or y is None or info.get(f"prominence_{int(f0)}hz_db", 0.0) < cfg.enf_prominence_db:
        test.status = "not_applicable"
        test.summary = "No mains-hum component prominent enough for phase analysis (most recordings on battery devices have none)."
        test.limitations.append("Absence of ENF says nothing about authenticity.")
        return test
    test.measurements["enf_nominal_hz"] = f0
    sos = butter(4, [f0 - 2.0, f0 + 2.0], btype="bandpass", fs=FS_ENF, output="sos")
    h = sosfiltfilt(sos, y)
    period = FS_ENF / f0
    frame = int(round(10 * period))
    hop = int(round(period))
    t_abs = np.arange(len(h)) / FS_ENF
    ref = np.exp(-2j * np.pi * f0 * t_abs)
    win = np.hanning(frame)
    starts = np.arange(0, len(h) - frame, hop)
    ph = np.array([np.angle(np.sum(win * h[s : s + frame] * ref[s : s + frame])) for s in starts])
    amp = np.array([np.abs(np.sum(win * h[s : s + frame])) for s in starts])
    ph = np.unwrap(ph)
    W = 10
    edge = int(0.3 * FS_ENF / hop)
    if len(ph) < 2 * W + 2 * edge + 2:
        test.status = "not_applicable"
        test.summary = "Recording too short for ENF phase tracking."
        return test
    d = np.full(len(ph), np.nan)
    for k in range(W, len(ph) - W):
        d[k] = np.median(ph[k : k + W]) - np.median(ph[k - W : k])
    d[:edge] = np.nan
    d[-edge:] = np.nan
    valid = np.isfinite(d)
    drift = np.nanmedian(d)
    dd = np.where(valid, np.abs(d - drift), 0.0)
    z = robust_z(np.where(valid, dd, np.nan))
    z = np.where(valid, z, 0.0)
    test.score = float(np.max(z))
    test.measurements.update({"phase_frames": len(ph), "phase_step_median_rad": float(np.nanmedian(np.abs(d - drift)))})
    t_frame = (starts + frame / 2) / FS_ENF
    for p in local_maxima(z, radius=2 * W):
        if z[p] < cfg.enf_jump_z or dd[p] < cfg.enf_phase_jump_rad:
            continue
        t = float(t_frame[p])
        f = reg.add_finding(
            "ENF", test_id=test.test_id, module=test.module, method="frame-wise hum phase tracking (absolute time reference)",
            family="enf", category=Category.OBSERVED, severity=Severity.MEDIUM,
            title=f"Mains-hum phase jumps by {dd[p]:.2f} rad near {t:.2f} s",
            description=(f"The {f0:.0f} Hz hum phase changes by {dd[p]:.2f} rad ({np.degrees(dd[p]):.0f} deg) around {t:.2f} s, "
                         "while it evolves smoothly elsewhere. Removing or inserting samples breaks hum phase continuity."),
            localization=Localization.POINT, time_start=max(0.0, t - 0.15), time_end=t + 0.15,
            measurements={"phase_step_rad": dd[p], "robust_z": z[p], "hum_amplitude": float(amp[p])},
            baseline={"phase_step_threshold_rad": cfg.enf_phase_jump_rad, "z_threshold": cfg.enf_jump_z},
            alternative_explanations=["Removal or insertion of samples (edit)", "Change of the electrical environment (another power circuit)",
                                      "Strong interference near the hum frequency"],
            limitations=["Edits that remove an exact multiple of the hum period leave no phase step.",
                         "Time resolution about +/- 0.2 s because of the narrow band-pass filter."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(test.finding_ids)
    test.summary = (f"{f0:.0f} Hz hum present; {len(test.finding_ids)} phase discontinuity(ies)." if test.detected
                    else f"{f0:.0f} Hz hum present; phase evolves continuously.")
    return test
