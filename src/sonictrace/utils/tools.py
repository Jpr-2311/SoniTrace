"""Discovery and invocation of optional external tools (FFmpeg / FFprobe).

External tools are always called with an argument list (never through a shell), with a
timeout, and only ever *read* the evidence file.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from functools import lru_cache

from ..errors import DependencyUnavailableError, SonicTraceError


@lru_cache(maxsize=None)
def find_tool(name: str) -> str | None:
    return shutil.which(name)


@lru_cache(maxsize=None)
def tool_version(name: str) -> str | None:
    exe = find_tool(name)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or out.stderr).decode("utf-8", "replace").splitlines()
    return text[0].strip() if text else None


def run_tool(args: list[str], timeout: float = 300.0) -> subprocess.CompletedProcess:
    """Run an external tool; raise DependencyUnavailableError if it is not installed."""
    exe = find_tool(args[0])
    if exe is None:
        raise DependencyUnavailableError(
            f"'{args[0]}' was not found on PATH. Install FFmpeg to enable this feature."
        )
    try:
        return subprocess.run([exe, *args[1:]], capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SonicTraceError(f"{args[0]} timed out after {timeout:.0f} s") from exc
    except OSError as exc:
        raise SonicTraceError(f"Could not execute {args[0]}: {exc}") from exc


def environment_report() -> dict:
    """Versions of every component that can influence analysis results."""
    import matplotlib
    import numpy
    import scipy
    import sklearn
    import soundfile

    from .. import METHODOLOGY_VERSION, __version__

    return {
        "sonictrace": __version__,
        "methodology_version": METHODOLOGY_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
        "soundfile": soundfile.__version__,
        "libsndfile": getattr(soundfile, "__libsndfile_version__", "unknown"),
        "matplotlib": matplotlib.__version__,
        "ffmpeg": tool_version("ffmpeg"),
        "ffprobe": tool_version("ffprobe"),
    }
