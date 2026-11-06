"""Shared fixtures: small, deterministic synthetic evidence files."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from sonictrace.dataset.sources import quantize16, render_environment, render_source
from sonictrace.utils.tools import find_tool

SR = 44100
HAS_FFMPEG = find_tool("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg not installed")


def make_signal(kind: str = "tonal", env: str = "room", seed: int = 7, duration: float = 4.0, sr: int = SR) -> np.ndarray:
    n = int(sr * duration)
    src = render_source(kind, [seed, 1], sr, duration)
    bg = render_environment(env, [seed, 2], sr, n)
    return quantize16(src + bg, np.random.default_rng([seed, 3]))


def write_wav(path: Path, data: np.ndarray, sr: int = SR) -> Path:
    sf.write(str(path), data, sr, subtype="PCM_16")
    return path


def riff_bytes(chunks: list[tuple[bytes, bytes]], riff_size: int | None = None) -> bytes:
    body = b"WAVE"
    for cid, payload in chunks:
        body += cid + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) % 2 else b"")
    size = len(body) if riff_size is None else riff_size
    return b"RIFF" + struct.pack("<I", size) + body


def fmt_payload(ch: int = 1, sr: int = 8000, bits: int = 16, tag: int = 1) -> bytes:
    ba = ch * bits // 8
    return struct.pack("<HHIIHH", tag, ch, sr, sr * ba, ba, bits)


@pytest.fixture
def tonal_clean(tmp_path: Path) -> Path:
    return write_wav(tmp_path / "tonal_clean.wav", make_signal("tonal"))


@pytest.fixture
def speech_clean(tmp_path: Path) -> Path:
    return write_wav(tmp_path / "speech_clean.wav", make_signal("speech", seed=11))


@pytest.fixture
def tonal_cut(tmp_path: Path) -> tuple[Path, float]:
    x = make_signal("tonal").astype(np.float64)
    p, L = int(1.7 * SR), int(0.3 * SR)
    y = np.concatenate([x[:p], x[p + L :]]).astype(np.int16)
    return write_wav(tmp_path / "tonal_cut.wav", y), p / SR


@pytest.fixture
def silence_inserted(tmp_path: Path) -> tuple[Path, float]:
    x = make_signal("speech", env="street", seed=5)
    p = int(2.0 * SR)
    y = np.concatenate([x[:p], np.zeros(int(0.4 * SR), dtype=np.int16), x[p:]])
    return write_wav(tmp_path / "silence.wav", y), p / SR
