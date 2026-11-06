"""Read-only audio decoding.

WAV, FLAC, Ogg and AIFF are decoded natively through libsndfile. MP3, AAC and MP4
audio are decoded by FFmpeg into a private temporary directory (removed afterwards);
the evidence file itself is only ever opened for reading.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from ..errors import DependencyUnavailableError, MalformedFileError, ResourceLimitError, UnsupportedFormatError
from .tools import find_tool, run_tool

NATIVE_CONTAINERS = {"wav", "flac", "ogg", "aiff"}
FFMPEG_CONTAINERS = {"mp3", "mp4", "aac_adts"}

SUBTYPE_BITS = {
    "PCM_S8": 8,
    "PCM_U8": 8,
    "PCM_16": 16,
    "PCM_24": 24,
    "PCM_32": 32,
    "FLOAT": 32,
    "DOUBLE": 64,
    "ULAW": 8,
    "ALAW": 8,
}
INTEGER_PCM = {"PCM_S8", "PCM_U8", "PCM_16", "PCM_24", "PCM_32"}


@dataclass
class LoadedAudio:
    samples: np.ndarray  # float64, shape (frames, channels), nominal range [-1, 1]
    sample_rate: int
    subtype: str
    bit_depth: int | None
    is_integer_pcm: bool
    decoded_via: str
    lossy_decoded: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def channels(self) -> int:
        return int(self.samples.shape[1])

    @property
    def n_frames(self) -> int:
        return int(self.samples.shape[0])

    @property
    def duration(self) -> float:
        return self.n_frames / float(self.sample_rate)

    @property
    def mono(self) -> np.ndarray:
        if self.channels == 1:
            return self.samples[:, 0]
        return self.samples.mean(axis=1)

    def describe(self) -> dict:
        return {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "frames": self.n_frames,
            "duration_s": round(self.duration, 6),
            "subtype": self.subtype,
            "bit_depth": self.bit_depth,
            "integer_pcm": self.is_integer_pcm,
            "decoded_via": self.decoded_via,
            "lossy_decoded": self.lossy_decoded,
            "warnings": list(self.warnings),
        }


def _check_limits(frames: int, sr: int, channels: int, max_duration: float, max_channels: int) -> None:
    if sr <= 0:
        raise MalformedFileError(f"Invalid sample rate declared: {sr}")
    if channels <= 0:
        raise MalformedFileError(f"Invalid channel count declared: {channels}")
    if channels > max_channels:
        raise ResourceLimitError(f"{channels} channels exceeds the limit of {max_channels}.")
    if frames / sr > max_duration:
        raise ResourceLimitError(
            f"Audio duration {frames / sr:.1f} s exceeds the configured limit of "
            f"{max_duration:.0f} s. Raise --max-duration to analyse it."
        )


def _finalise(data: np.ndarray, audio: LoadedAudio) -> LoadedAudio:
    if data.shape[0] == 0:
        raise MalformedFileError("The file decodes to zero audio samples.")
    bad = ~np.isfinite(data)
    if bad.any():
        audio.warnings.append(f"{int(bad.sum())} non-finite sample values (NaN/Inf) replaced by 0.")
        data = np.where(bad, 0.0, data)
    audio.samples = np.ascontiguousarray(data, dtype=np.float64)
    return audio


def _load_native(path: Path, max_duration: float, max_channels: int) -> LoadedAudio:
    try:
        info = sf.info(str(path))
    except Exception as exc:  # libsndfile raises LibsndfileError / RuntimeError
        raise MalformedFileError(f"libsndfile could not open the file: {exc}") from exc
    _check_limits(info.frames, info.samplerate, info.channels, max_duration, max_channels)
    try:
        data, sr = sf.read(str(path), dtype="float64", always_2d=True)
    except Exception as exc:
        raise MalformedFileError(f"libsndfile could not decode the audio data: {exc}") from exc
    subtype = info.subtype
    lossy = subtype in {"VORBIS", "OPUS", "MPEG_LAYER_III", "MPEG_LAYER_II", "MPEG_LAYER_I"}
    audio = LoadedAudio(
        samples=data,
        sample_rate=int(sr),
        subtype=subtype,
        bit_depth=SUBTYPE_BITS.get(subtype),
        is_integer_pcm=subtype in INTEGER_PCM,
        decoded_via="libsndfile",
        lossy_decoded=lossy,
    )
    return _finalise(data, audio)


def _load_ffmpeg(path: Path, max_duration: float, max_channels: int) -> LoadedAudio:
    if find_tool("ffmpeg") is None:
        raise DependencyUnavailableError(
            "Decoding this format requires FFmpeg, which was not found on PATH. "
            "WAV, FLAC and Ogg files can be analysed without FFmpeg."
        )
    with tempfile.TemporaryDirectory(prefix="sonictrace_") as tmp:
        out = Path(tmp) / "decoded.wav"
        res = run_tool(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0",
                "-t", f"{max_duration + 1.0:.3f}", "-c:a", "pcm_f32le", "-f", "wav", str(out),
            ],
            timeout=900,
        )
        if res.returncode != 0 or not out.exists() or out.stat().st_size <= 44:
            msg = res.stderr.decode("utf-8", "replace").strip().splitlines()
            raise MalformedFileError(f"FFmpeg could not decode the file: {msg[-1] if msg else 'no output'}")
        data, sr = sf.read(str(out), dtype="float64", always_2d=True)
    _check_limits(data.shape[0], int(sr), data.shape[1], max_duration, max_channels)
    audio = LoadedAudio(
        samples=data,
        sample_rate=int(sr),
        subtype="FLOAT (decoded by FFmpeg)",
        bit_depth=None,
        is_integer_pcm=False,
        decoded_via="ffmpeg",
        lossy_decoded=True,
    )
    audio.warnings.append(
        "Decoded by FFmpeg: decoder output reflects FFmpeg's decoder (including any gapless "
        "trimming of encoder delay), not the raw bitstream."
    )
    return _finalise(data, audio)


def load_audio(path: str | Path, container: str, max_duration: float = 600.0, max_channels: int = 16) -> LoadedAudio:
    """Decode ``path`` (read-only) according to its sniffed container."""
    p = Path(path)
    if container in NATIVE_CONTAINERS:
        try:
            return _load_native(p, max_duration, max_channels)
        except MalformedFileError:
            if container != "wav" and find_tool("ffmpeg"):
                return _load_ffmpeg(p, max_duration, max_channels)
            raise
    if container in FFMPEG_CONTAINERS:
        return _load_ffmpeg(p, max_duration, max_channels)
    raise UnsupportedFormatError(
        f"Unsupported or unrecognised format (content sniffed as '{container}'). Supported: "
        "WAV natively; FLAC/Ogg/AIFF via libsndfile; MP3/AAC/M4A via FFmpeg."
    )
