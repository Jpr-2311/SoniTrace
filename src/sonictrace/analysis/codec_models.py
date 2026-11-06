"""Empirical encoder low-pass model for the D4 transcoding cross-check.

FFmpeg's MP3 muxer writes the LAME-style Info tag with an encoder string such as
"Lavc61.3." and a low-pass byte of 0, so the low-pass that libmp3lame actually applied is
not recorded in the file. D4 then falls back to this model.

The values are *measured*, not taken from encoder documentation:
``scripts/verify_lame_lowpass.py`` encodes broadband noise with libmp3lame (via FFmpeg) at
every MPEG-1 Layer III CBR bitrate, mono and stereo, at 44.1 and 48 kHz, decodes it and
measures the -6 dB band limit with SonicTrace's own detector
(``research/lame_lowpass_verification.md``). Entries whose measured drop was not steep are
not used: outside the measured, steep configurations the model returns ``None`` and D4
reports that it cannot check the file.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

MODEL_SOURCE = "measured libmp3lame CBR low-pass (scripts/verify_lame_lowpass.py)"
LAME_LIKE_ENCODERS = ("LAME", "Lavc", "Lavf")  # libmp3lame directly, or via FFmpeg's muxer


@lru_cache(maxsize=1)
def _model() -> dict[tuple[int, int, int], float]:
    raw = json.loads(resources.files("sonictrace").joinpath("data/lame_cbr_cutoffs.json").read_text(encoding="utf-8"))
    return {(e["sample_rate"], e["channels"], e["bitrate_kbps"]): float(e["cutoff_hz"])
            for e in raw["entries"] if e["steep"] and e["cutoff_hz"]}


def expected_lame_cutoff(sample_rate: int, channels: int, bitrate_kbps: float) -> float | None:
    """Measured libmp3lame CBR cutoff (Hz) for this configuration, or None if not covered."""
    return _model().get((int(sample_rate), 1 if channels == 1 else 2, int(round(bitrate_kbps))))
