"""Module E: resampling investigation.

E1  Empty band below Nyquist: upsampling from rate r to R > r leaves no content between
    roughly r/2 and R/2, terminated by the steep edge of the anti-imaging filter.
E2  Interpolation periodicity (experimental): after rational resampling with a short
    interpolation kernel the prediction residual has periodically varying variance
    (Popescu & Farid, "Exposing digital forgeries by detecting traces of resampling",
    IEEE Trans. Signal Processing 53(2), 2005). Long windowed-sinc resamplers largely
    remove this trace; the benchmark reports how often it is observed.
E3  Sample-rate metadata consistency (container vs. decoder vs. bitstream).

A different sample rate between two files is never treated as evidence of resampling.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import welch

from ..evidence.evidence_model import Category, EvidenceRegistry, Localization, Severity, TestResult
from .context import AnalysisContext
from .spectral_analysis import candidate_source_rates


def run_nyquist_gap(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    bl = ctx.bandlimit
    test = TestResult("E1", "Empty band below Nyquist (upsampling trace)", "E: resampling", "bandwidth",
                      score_name="empty fraction of the Nyquist band", threshold=cfg.nyquist_gap_fraction)
    gap = 1.0 - (bl.cutoff_ratio or 1.0) if bl.found else 0.0
    test.score = float(gap) if bl.steep else 0.0
    rates = candidate_source_rates(bl.cutoff_hz, ctx.sr) if bl.found and bl.cutoff_hz else []
    test.measurements = {"cutoff_hz": bl.cutoff_hz, "nyquist_hz": bl.nyquist_hz, "empty_band_fraction": gap,
                         "steep": bl.steep, "consistent_source_rates": rates, "declared_sample_rate": ctx.sr}
    if bl.found and bl.steep and gap >= cfg.nyquist_gap_fraction:
        f = reg.add_finding(
            "RES", test_id=test.test_id, module=test.module, method="band-limit vs. Nyquist frequency", family="bandwidth",
            category=Category.OBSERVED, severity=Severity.MEDIUM if rates else Severity.LOW,
            title=f"{100 * gap:.0f} % of the representable band is empty",
            description=(f"The file is stored at {ctx.sr} Hz (Nyquist {bl.nyquist_hz:.0f} Hz) but carries no content above "
                         f"{bl.cutoff_hz:.0f} Hz. " + (f"This cutoff is consistent with original sample rates of {', '.join(map(str, rates))} Hz." if rates
                                                       else "The cutoff does not match a standard sample rate's Nyquist frequency.")),
            localization=Localization.GLOBAL, measurements={"empty_band_fraction": gap, "consistent_source_rates": rates},
            baseline={"min_empty_fraction": cfg.nyquist_gap_fraction},
            alternative_explanations=["Upsampling from a lower sample rate", "Lossy-codec low-pass (see D2 for codec holes)",
                                      "Low-pass filtering or a band-limited source"],
            limitations=["Downsampling leaves no such trace: a downsampled file looks like a native recording at the lower rate."],
        )
        test.finding_ids.append(f.finding_id)
        test.detected = True
        test.summary = f"Content limited to {bl.cutoff_hz:.0f} Hz of {bl.nyquist_hz:.0f} Hz; consistent source rates: {rates or 'none'}."
    else:
        test.summary = "Content uses the band up to Nyquist (no upsampling trace)." if not bl.found or not bl.steep else \
            f"Band limit at {bl.cutoff_hz:.0f} Hz leaves less than {100 * cfg.nyquist_gap_fraction:.0f} % of the band empty."
    return test


def residual_periodicity(e: np.ndarray, max_len: int = 1 << 21) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Peak-to-local-median ratio (dB) of the spectrum of the squared residual."""
    p = e[:max_len] ** 2
    p = p - p.mean()
    nper = 4096 if len(p) >= 8192 else max(256, 1 << int(np.floor(np.log2(max(len(p) // 2, 256)))))
    f, s = welch(p, fs=1.0, nperseg=nper)
    sel = f >= 0.01
    f, s = f[sel], s[sel]
    base = median_filter(s, size=65, mode="nearest") + 1e-30
    ratio_db = 10 * np.log10(s / base + 1e-30)
    k = int(np.argmax(ratio_db))
    return float(ratio_db[k]), float(f[k]), f, ratio_db


def run_interpolation_periodicity(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    test = TestResult("E2", "Interpolation periodicity in prediction residual", "E: resampling", "resampling_periodicity",
                      score_name="peak/median ratio of residual-variance spectrum (dB)", threshold=cfg.periodicity_peak_db,
                      experimental=True)
    e = ctx.cache.get("lpc_residual")
    if e is None:
        from .splice_detection import lpc_residual

        e = lpc_residual(ctx.x, cfg.residual_lpc_order, cfg.residual_block)
    peak_db, peak_f, _, _ = residual_periodicity(e)
    test.score = peak_db
    test.measurements = {"peak_ratio_db": peak_db, "peak_frequency_cycles_per_sample": peak_f,
                         "implied_period_samples": (1.0 / peak_f) if peak_f > 0 else None}
    test.limitations.append("Experimental: long windowed-sinc resamplers leave little periodic residual structure.")
    if peak_db >= cfg.periodicity_peak_db:
        f = reg.add_finding(
            "RES", test_id=test.test_id, module=test.module, method="spectrum of squared LPC residual", family="resampling_periodicity",
            category=Category.STATISTICAL, severity=Severity.LOW,
            title=f"Periodic residual structure at {peak_f:.4f} cycles/sample",
            description=(f"The variance of the prediction residual varies periodically (period {1 / peak_f:.2f} samples, "
                         f"{peak_db:.0f} dB above the local spectral median), as expected after interpolation by a short kernel."),
            localization=Localization.GLOBAL, measurements=dict(test.measurements),
            baseline={"peak_threshold_db": cfg.periodicity_peak_db},
            alternative_explanations=["Resampling with linear/short-kernel interpolation", "Strongly periodic (tonal) content",
                                      "Periodic digital interference"],
            limitations=list(test.limitations),
        )
        test.finding_ids.append(f.finding_id)
        test.detected = True
        test.summary = f"Periodic residual peak {peak_db:.0f} dB at {peak_f:.4f} cycles/sample."
    else:
        test.summary = f"No periodic residual structure above {cfg.periodicity_peak_db:.0f} dB (max {peak_db:.1f} dB)."
    return test


def run_rate_consistency(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    test = TestResult("E3", "Sample-rate metadata consistency", "E: resampling", "metadata", score_name="mismatches")
    declared = {}
    st = ctx.structure
    if st is not None:
        if st.container == "wav" and st.details.get("fmt"):
            declared["riff_fmt"] = st.details["fmt"]["sample_rate"]
        elif st.container == "mp3":
            declared["mpeg_frames"] = st.details.get("sample_rate")
        elif st.container == "flac":
            declared["flac_streaminfo"] = st.details["streaminfo"]["sample_rate"]
        elif st.container == "ogg":
            for k, v in st.details.get("streams", {}).items():
                if v.get("sample_rate"):
                    declared[f"ogg_stream_{k}"] = v["sample_rate"]
                if v.get("input_sample_rate"):
                    test.measurements["opus_input_sample_rate"] = v["input_sample_rate"]
    probe_sr = (ctx.metadata or {}).get("technical", {}).get("sample_rate")
    if probe_sr:
        declared["ffprobe"] = probe_sr
    declared["decoder"] = ctx.sr
    test.measurements["declared_rates"] = declared
    values = set(declared.values())
    test.score = float(len(values) - 1)
    if len(values) > 1:
        f = reg.add_finding(
            "RES", test_id=test.test_id, module=test.module, method="cross-check of declared sample rates", family="metadata",
            category=Category.OBSERVED, severity=Severity.MEDIUM,
            title="Declared sample rates disagree",
            description=f"Different components report different sample rates: {declared}.",
            localization=Localization.GLOBAL, measurements={"declared_rates": declared},
            alternative_explanations=["Header edited or written by non-conforming software", "Decoder resampling on output"],
        )
        test.finding_ids.append(f.finding_id)
        test.detected = True
        test.summary = f"Sample-rate mismatch: {declared}."
    else:
        test.summary = f"All sources agree on {ctx.sr} Hz. (A sample rate alone is not evidence of resampling.)"
    return test
