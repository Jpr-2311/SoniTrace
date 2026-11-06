"""Cryptographic hashing of evidence files (streamed, read-only)."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1 << 20


def sha256_file(path: str | Path) -> str:
    """Return the hex SHA-256 digest of a file, reading it in 1 MiB chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of an in-memory byte string."""
    return hashlib.sha256(data).hexdigest()
