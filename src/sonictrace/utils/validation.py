"""Input validation and content-based container identification (magic bytes)."""

from __future__ import annotations

from pathlib import Path

from ..errors import InputValidationError, MalformedFileError, ResourceLimitError

EXTENSION_CONTAINERS = {
    ".wav": "wav",
    ".wave": "wav",
    ".bwf": "wav",
    ".rf64": "wav",
    ".flac": "flac",
    ".ogg": "ogg",
    ".oga": "ogg",
    ".opus": "ogg",
    ".mp3": "mp3",
    ".m4a": "mp4",
    ".mp4": "mp4",
    ".aac": "aac_adts",
    ".aif": "aiff",
    ".aiff": "aiff",
}

CONTAINER_NAMES = {
    "wav": "RIFF/WAVE (or RF64)",
    "flac": "FLAC",
    "ogg": "Ogg",
    "mp3": "MPEG audio (MP3)",
    "mp4": "ISO base media (MP4/M4A)",
    "aac_adts": "AAC (ADTS stream)",
    "aiff": "AIFF/AIFC",
    "unknown": "unrecognised",
}


def syncsafe(b: bytes) -> int:
    """Decode a 28-bit ID3v2 'syncsafe' integer."""
    return (b[0] & 0x7F) << 21 | (b[1] & 0x7F) << 14 | (b[2] & 0x7F) << 7 | (b[3] & 0x7F)


def _is_mpeg_audio_header(b: bytes) -> bool:
    if len(b) < 4 or b[0] != 0xFF or (b[1] & 0xE0) != 0xE0:
        return False
    version = (b[1] >> 3) & 3
    layer = (b[1] >> 1) & 3
    bitrate = (b[2] >> 4) & 0xF
    srate = (b[2] >> 2) & 3
    return version != 1 and layer != 0 and bitrate not in (0, 15) and srate != 3


def sniff_container(head: bytes) -> str:
    """Identify a container from its first bytes (no ID3 handling)."""
    if len(head) >= 12 and head[:4] in (b"RIFF", b"RF64") and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"OggS":
        return "ogg"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "mp4"
    if len(head) >= 12 and head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        return "aiff"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xF6) == 0xF0:
        return "aac_adts"
    if _is_mpeg_audio_header(head[:4]):
        return "mp3"
    return "unknown"


def sniff_file(path: str | Path) -> str:
    """Identify a file's container, skipping a leading ID3v2 tag if present."""
    with open(path, "rb") as handle:
        head = handle.read(65536)
    if head[:3] == b"ID3" and len(head) >= 10:
        offset = 10 + syncsafe(head[6:10])
        with open(path, "rb") as handle:
            handle.seek(offset)
            after = handle.read(8192)
        kind = sniff_container(after)
        if kind != "unknown":
            return kind
        # tolerate a few junk/padding bytes between the tag and the first frame
        for i in range(min(len(after) - 4, 4096)):
            if _is_mpeg_audio_header(after[i : i + 4]):
                return "mp3"
        return "unknown"
    return sniff_container(head)


def validate_input_file(path: str | Path, max_bytes: int) -> Path:
    """Check that ``path`` is an existing, readable, non-empty regular file within limits."""
    p = Path(path)
    if not p.exists():
        raise InputValidationError(f"Input file not found: {p}")
    if p.is_dir():
        raise InputValidationError(f"Input path is a directory, not a file: {p}")
    if not p.is_file():
        raise InputValidationError(f"Input path is not a regular file: {p}")
    size = p.stat().st_size
    if size == 0:
        raise MalformedFileError(f"Input file is empty (0 bytes): {p}")
    if size > max_bytes:
        raise ResourceLimitError(
            f"Input file is {size / 2**20:.1f} MiB, above the configured limit of "
            f"{max_bytes / 2**20:.0f} MiB. Raise --max-mib to analyse it."
        )
    try:
        with open(p, "rb") as handle:
            handle.read(1)
    except OSError as exc:
        raise InputValidationError(f"Input file cannot be read: {exc}") from exc
    return p.resolve()
