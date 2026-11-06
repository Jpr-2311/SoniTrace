"""Analysis configuration.

All thresholds live here so that every report can record the exact parameter set it
was produced with. Values were chosen a priori from signal-processing reasoning and
then checked on the *calibration* split of the synthetic dataset (see
``research/experiments.md``). They are not tuned on the evaluation split.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class AnalysisConfig:
    # --- framing -----------------------------------------------------------------
    frame_seconds: float = 0.046  # STFT frame ~46 ms, rounded to a power of two
    hop_divisor: int = 4  # hop = n_fft / hop_divisor

    # --- resource limits (forensic tools must fail loudly, not exhaust memory) ----
    max_file_bytes: int = 512 * 1024 * 1024
    max_duration_s: float = 600.0
    max_channels: int = 16
    duplication_max_duration_s: float = 180.0

    # --- Module C: waveform discontinuity (LPC residual impulse) -----------------
    residual_lpc_order: int = 16
    residual_block: int = 4096
    residual_neighbor_ms: float = 20.0
    residual_guard_ms: float = 0.5
    residual_peak_ratio: float = 4.0
    residual_max_findings: int = 25

    # --- Module C: short-time energy discontinuity --------------------------------
    energy_window_ms: float = 10.0
    energy_hop_ms: float = 2.5
    energy_jump_db: float = 15.0
    energy_jump_z: float = 6.0

    # --- Module C: spectral discontinuity -----------------------------------------
    spectral_jump_db: float = 12.0
    spectral_jump_z: float = 6.0

    # --- Module C: noise-floor consistency ----------------------------------------
    noise_block_s: float = 0.25
    noise_context_blocks: int = 4
    noise_percentile: float = 10.0
    noise_shift_db: float = 6.0
    noise_shape_db: float = 6.0
    noise_shift_z: float = 4.0

    # --- Module C: silence and padding --------------------------------------------
    digital_silence_min_ms: float = 10.0
    gating_pattern_min_runs: int = 5  # v1.1
    comb_global_fraction: float = 0.8  # v1.1: comb in >= 80 % of blocks = whole-file gain processing

    # --- Module C: duplicated segments (copy-move) --------------------------------
    dup_hop: int = 2048
    dup_similarity: float = 0.92
    dup_min_seconds: float = 0.15  # v1.1 (was 0.25): pauses inside copied speech split the similarity run
    dup_min_lag_seconds: float = 0.5
    dup_ncc_threshold: float = 0.98
    dup_max_candidates: int = 60  # v1.1 (was 12): vowel-like frames create many similarity runs; NCC verifies

    # --- ENF (electric network frequency) phase continuity ------------------------
    enf_prominence_db: float = 15.0
    enf_phase_jump_rad: float = 0.35
    enf_jump_z: float = 6.0

    # --- Module D: compression -----------------------------------------------------
    cutoff_margin_db: float = 15.0
    cutoff_min_depth_db: float = 25.0
    cutoff_max_transition_frac: float = 0.30
    hole_rel_db: float = 25.0
    hole_ratio_threshold: float = 0.03
    comb_block_s: float = 1.0
    comb_min_expected: float = 4.0  # v1.1 (was 8): too few populated bins in 1 s blocks of music
    comb_empty_fraction: float = 0.05
    comb_periodicity_db: float = 18.0

    # --- Module E: resampling ------------------------------------------------------
    nyquist_gap_fraction: float = 0.05  # v1.1 (was 0.10, with cutoff now at the transition midpoint)
    periodicity_peak_db: float = 20.0

    # --- Module F: statistical anomaly detection -----------------------------------
    robust_z_threshold: float = 3.5
    anomaly_window_s: float = 0.5
    isolation_forest_estimators: int = 200
    pelt_penalty_beta: float = 3.0
    ks_alpha: float = 1e-4
    ks_min_d: float = 0.6
    bic_lambda: float = 1.0

    # --- Module G: correlation -----------------------------------------------------
    correlation_tolerance_s: float = 0.08

    # --- misc ---------------------------------------------------------------------
    seed: int = 1337

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AnalysisConfig":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})
