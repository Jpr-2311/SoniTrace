"""Shared analysis context: every representation is computed once and reused by all detectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..config import AnalysisConfig
from ..parsers.common import StructureReport
from ..utils.audio_loader import LoadedAudio
from .signal_features import FrameFeatures, compute_frame_features
from .spectral_analysis import (
    BandLimit,
    SpectralFeatures,
    Spectrogram,
    compute_ltas,
    compute_spectral_features,
    compute_stft,
    detect_bandlimit,
)


@dataclass
class AnalysisContext:
    path: Path
    audio: LoadedAudio
    x: np.ndarray
    sr: int
    n_fft: int
    hop: int
    frames: FrameFeatures
    spec: Spectrogram
    spectral: SpectralFeatures
    ltas_freqs: np.ndarray
    ltas_psd: np.ndarray
    bandlimit: BandLimit
    config: AnalysisConfig
    structure: StructureReport | None = None
    metadata: dict | None = None
    cache: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return len(self.x) / float(self.sr)

    @property
    def lsb(self) -> float:
        """Amplitude of one quantisation step for integer PCM (fallback: 16-bit equivalent)."""
        bits = self.audio.bit_depth if self.audio.is_integer_pcm and self.audio.bit_depth else 16
        return 1.0 / 2 ** (bits - 1)


def choose_fft_size(sr: int, frame_seconds: float) -> int:
    n = 2 ** int(round(np.log2(max(frame_seconds * sr, 64))))
    return int(min(max(n, 256), 8192))


def build_context(path: Path, audio: LoadedAudio, config: AnalysisConfig,
                  structure: StructureReport | None = None, metadata: dict | None = None) -> AnalysisContext:
    x = audio.mono
    sr = audio.sample_rate
    n_fft = choose_fft_size(sr, config.frame_seconds)
    hop = n_fft // config.hop_divisor
    frames = compute_frame_features(x, sr, n_fft, hop)
    spec = compute_stft(x, sr, n_fft, hop)
    spectral = compute_spectral_features(spec)
    lf, lp = compute_ltas(x, sr)
    bl = detect_bandlimit(lf, lp, sr, config.cutoff_margin_db, config.cutoff_min_depth_db, config.cutoff_max_transition_frac)
    return AnalysisContext(path, audio, x, sr, n_fft, hop, frames, spec, spectral, lf, lp, bl, config, structure, metadata)
