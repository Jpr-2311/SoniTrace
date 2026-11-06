"""Forensic engine: orchestrates Modules A-G for one evidence file.

Integrity guarantees
--------------------
* The evidence file is opened read-only, hashed (SHA-256) before analysis and hashed
  again afterwards; the report records both hashes and whether they match.
* Each test runs in isolation: a failing test is recorded with status ``error`` and
  the investigation continues, so one defective method never silently hides others.
* Analysis is deterministic: identical input + configuration => identical report
  (apart from timestamps and run time).
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import METHODOLOGY_VERSION, __version__
from .analysis.anomaly_detection import run_anomaly_suite
from .analysis.compression_analysis import run_codec_consistency, run_quantization, run_spectral_cutoff, run_spectral_holes
from .analysis.context import AnalysisContext, build_context
from .analysis.duplication import run_duplication
from .analysis.enf_analysis import run_enf_phase
from .analysis.noise_analysis import run_noise_consistency
from .analysis.resampling_analysis import run_interpolation_periodicity, run_nyquist_gap, run_rate_consistency
from .analysis.signal_features import summarize_signal
from .analysis.spectral_analysis import band_energy_distribution
from .analysis.splice_detection import (
    run_digital_silence,
    run_energy_discontinuity,
    run_spectral_discontinuity,
    run_waveform_discontinuity,
)
from .analysis.structure_tests import run_container_structure, run_declared_vs_actual
from .config import AnalysisConfig
from .evidence.assessment import Assessment, build_assessment
from .evidence.correlation import CorrelatedEvent, GlobalAssessment, assess_global, correlate_events
from .evidence.evidence_model import EvidenceRegistry, TestResult, _clean
from .parsers.codec_inspector import inspect_structure
from .parsers.common import StructureReport
from .parsers.metadata import build_metadata, probe_ffprobe
from .utils.audio_loader import load_audio
from .utils.hashing import sha256_file
from .utils.tools import environment_report
from .utils.validation import sniff_file, validate_input_file

DetectorFn = Callable[[AnalysisContext, EvidenceRegistry], TestResult]

# Order matters only for cache reuse: C1 caches the LPC residual reused by E2; C4 caches the noise
# profile reused by the signal summary and the noise-floor figure.
DETECTORS: list[tuple[str, str, str, DetectorFn]] = [
    ("C1", "Waveform discontinuity (LPC residual impulses)", "C: splicing", run_waveform_discontinuity),
    ("C2", "Short-time energy discontinuity", "C: splicing", run_energy_discontinuity),
    ("C3", "Spectral discontinuity (log-spectral distance)", "C: splicing", run_spectral_discontinuity),
    ("C4", "Background noise-floor consistency", "C: splicing", run_noise_consistency),
    ("C5", "Digital silence and padding", "C: splicing", run_digital_silence),
    ("C6", "Duplicated segment (copy-move) detection", "C: splicing", run_duplication),
    ("C7", "ENF (mains hum) phase continuity", "C: splicing", run_enf_phase),
    ("D1", "Spectral band limit (codec/resampler low-pass)", "D: compression", run_spectral_cutoff),
    ("D2", "Spectral holes (codec quantisation to zero)", "D: compression", run_spectral_holes),
    ("D3", "Quantisation: bit depth and histogram combing", "D: compression", run_quantization),
    ("D4", "Codec signature, bitrate and declared-bandwidth consistency", "D: compression", run_codec_consistency),
    ("E1", "Empty band below Nyquist (upsampling trace)", "E: resampling", run_nyquist_gap),
    ("E2", "Interpolation periodicity in prediction residual", "E: resampling", run_interpolation_periodicity),
    ("E3", "Sample-rate metadata consistency", "E: resampling", run_rate_consistency),
]


@dataclass
class AnalysisResult:
    file_identity: dict
    metadata: dict
    structure: StructureReport
    audio: dict
    signal_summary: dict
    frequency_distribution: list[dict]
    tests: list[TestResult]
    findings: list
    events: list[CorrelatedEvent]
    global_assessments: list[GlobalAssessment]
    assessment: Assessment
    integrity: dict
    environment: dict
    config: dict
    timing: dict
    context: AnalysisContext | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return _clean({
            "report_type": "sonictrace.forensic_analysis",
            "schema_version": "1.0",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "tool": {"name": "SonicTrace", "version": __version__, "methodology_version": METHODOLOGY_VERSION},
            "file_identity": self.file_identity,
            "integrity": self.integrity,
            "metadata": self.metadata,
            "structure": self.structure.to_dict(),
            "audio": self.audio,
            "signal_summary": self.signal_summary,
            "frequency_distribution": self.frequency_distribution,
            "assessment": self.assessment.to_dict(),
            "global_assessments": [g.to_dict() for g in self.global_assessments],
            "correlated_events": [e.to_dict() for e in self.events],
            "tests": [t.to_dict() for t in self.tests],
            "findings": [f.to_dict() for f in self.findings],
            "environment": self.environment,
            "config": self.config,
            "timing": self.timing,
        })


def _safe(test_id: str, name: str, module: str, fn: Callable[[], TestResult | list[TestResult]]) -> list[TestResult]:
    try:
        res = fn()
        return res if isinstance(res, list) else [res]
    except Exception as exc:  # recorded, never swallowed silently
        return [TestResult(test_id, name, module, "error", status="error",
                           summary=f"Test failed with {type(exc).__name__}: {exc}",
                           measurements={"traceback": traceback.format_exc(limit=4)})]


class ForensicEngine:
    def __init__(self, config: AnalysisConfig | None = None) -> None:
        self.config = config or AnalysisConfig()

    def analyze(self, path: str | Path, keep_context: bool = False, run_statistics: bool = True) -> AnalysisResult:
        cfg = self.config
        t0 = time.perf_counter()
        p = validate_input_file(path, cfg.max_file_bytes)
        st_before = p.stat()
        sha_before = sha256_file(p)
        container = sniff_file(p)
        reg = EvidenceRegistry()

        structure = inspect_structure(p, container)
        ffprobe = probe_ffprobe(p)
        meta = build_metadata(p, container, structure, ffprobe)
        t_struct = time.perf_counter()

        audio = load_audio(p, container, cfg.max_duration_s, cfg.max_channels)
        ctx = build_context(p, audio, cfg, structure, meta)
        t_ctx = time.perf_counter()

        reg.add_test(run_container_structure(structure, reg))
        reg.add_test(run_declared_vs_actual(structure, meta, audio, reg))
        for tid, name, module, fn in DETECTORS:
            for t in _safe(tid, name, module, lambda fn=fn: fn(ctx, reg)):
                reg.add_test(t)
        if run_statistics:
            for t in _safe("F", "Statistical anomaly suite", "F: statistics", lambda: run_anomaly_suite(ctx, reg)):
                reg.add_test(t)
        t_tests = time.perf_counter()

        events = correlate_events(reg.findings, cfg.correlation_tolerance_s)
        glob = assess_global(reg.findings, reg.tests, container, audio.lossy_decoded)
        assessment = build_assessment(reg.findings, reg.tests, events, glob)

        sha_after = sha256_file(p)
        st_after = p.stat()
        integrity = {
            "sha256_before": sha_before,
            "sha256_after": sha_after,
            "unchanged": sha_before == sha_after and st_before.st_size == st_after.st_size
                         and st_before.st_mtime_ns == st_after.st_mtime_ns,
            "access_mode": "read-only",
        }
        noise = ctx.cache.get("noise_profile")
        summary = summarize_signal(audio.samples, ctx.x, audio.sample_rate, ctx.frames, audio.bit_depth if audio.is_integer_pcm else None)
        if noise is not None:
            summary.update({"noise_floor_db": noise.global_floor_db, "snr_estimate_db": noise.snr_estimate_db})
        summary["spectral_centroid_median_hz"] = float(_median(ctx.spectral.centroid))
        summary["spectral_bandwidth_median_hz"] = float(_median(ctx.spectral.bandwidth))
        summary["spectral_rolloff85_median_hz"] = float(_median(ctx.spectral.rolloff))
        summary["spectral_flatness_median"] = float(_median(ctx.spectral.flatness))
        summary["mfcc_mean"] = [float(v) for v in ctx.spectral.mfcc.mean(axis=1)]
        summary["band_limit"] = ctx.bandlimit.to_dict()
        summary["stft"] = {"n_fft": ctx.n_fft, "hop": ctx.hop, "window": "hann", "frames": int(ctx.spec.mag.shape[1])}
        t_end = time.perf_counter()
        return AnalysisResult(
            file_identity={"file_name": p.name, "path": str(p), "size_bytes": st_before.st_size, "sha256": sha_before,
                           "container": container, "analysed_utc": datetime.now(timezone.utc).isoformat()},
            metadata=meta, structure=structure, audio=audio.describe(), signal_summary=summary,
            frequency_distribution=band_energy_distribution(ctx.ltas_freqs, ctx.ltas_psd),
            tests=reg.tests, findings=reg.findings, events=events, global_assessments=glob, assessment=assessment,
            integrity=integrity, environment=environment_report(), config=cfg.to_dict(),
            timing={"structure_s": t_struct - t0, "decode_and_features_s": t_ctx - t_struct,
                    "tests_s": t_tests - t_ctx, "total_s": t_end - t0},
            context=ctx if keep_context else None,
        )


def _median(a) -> float:
    import numpy as np

    return float(np.median(a)) if len(a) else 0.0
