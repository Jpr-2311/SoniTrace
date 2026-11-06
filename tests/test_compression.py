"""D4 transcoding cross-check, including the v1.2 fallback for FFmpeg-written MP3s (no low-pass in the tag)."""

from pathlib import Path

import pytest

from conftest import make_signal, needs_ffmpeg, write_wav
from sonictrace.analysis.codec_models import expected_lame_cutoff
from sonictrace.engine import ForensicEngine
from sonictrace.utils.tools import run_tool


def test_model_covers_only_measured_steep_configurations():
    assert expected_lame_cutoff(44100, 1, 64) == pytest.approx(16505, abs=5)
    assert expected_lame_cutoff(44100, 2, 128) == pytest.approx(16532, abs=5)
    assert expected_lame_cutoff(48000, 2, 192) == pytest.approx(18779, abs=5)
    assert expected_lame_cutoff(44100, 2, 64) is None  # measured drop not steep -> unusable
    assert expected_lame_cutoff(32000, 2, 128) is None  # sample rate never measured
    assert expected_lame_cutoff(44100, 2, 144) is None  # not a measured bitrate


def _mp3(src: Path, dst: Path, kbps: int) -> Path:
    r = run_tool(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-codec:a", "libmp3lame", "-b:a", f"{kbps}k", str(dst)])
    assert r.returncode == 0, r.stderr
    return dst


def _d4(path: Path):
    res = ForensicEngine().analyze(path, run_statistics=False)
    return next(t for t in res.tests if t.test_id == "D4"), res


@pytest.fixture(scope="module")
def speech_wav(tmp_path_factory) -> Path:
    return write_wav(tmp_path_factory.mktemp("d4") / "speech.wav", make_signal("speech", env="room", seed=41, duration=5.0))


@needs_ffmpeg
def test_single_encodes_are_consistent(speech_wav, tmp_path):
    for kbps in (64, 192):
        d4, _ = _d4(_mp3(speech_wav, tmp_path / f"single_{kbps}.mp3", kbps))
        assert d4.measurements["encoder_lowpass_hz"] is None  # FFmpeg writes 0
        assert d4.measurements["expected_cutoff_source"] == "measured_libmp3lame_model"
        assert not d4.detected, d4.summary


@needs_ffmpeg
def test_transcoded_mp3_is_flagged(speech_wav, tmp_path):
    first = _mp3(speech_wav, tmp_path / "gen1.mp3", 64)
    decoded = tmp_path / "gen1.wav"
    assert run_tool(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(first), "-c:a", "pcm_s16le", str(decoded)]).returncode == 0
    d4, res = _d4(_mp3(decoded, tmp_path / "gen2_192.mp3", 192))
    assert d4.detected
    f = next(f for f in res.findings if f.test_id == "D4" and f.title.startswith("Audio bandwidth"))
    assert f.measurements["measured_cutoff_hz"] < 0.85 * f.measurements["expected_cutoff_hz"]
    assert f.severity.value == "low"  # model-based expectation, not a recorded tag value
    assert any(g.topic == "transcoding" and g.status == "indicated" for g in res.global_assessments)
