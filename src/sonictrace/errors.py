"""Exception hierarchy.

Every error carries a message written for the person running the tool. The CLI maps
each class to a distinct exit code so that scripted pipelines can react to failures.
"""


class SonicTraceError(Exception):
    """Base class for all expected (user-facing) failures."""

    exit_code = 2


class InputValidationError(SonicTraceError):
    """The input path is missing, unreadable or not a regular file."""

    exit_code = 2


class UnsupportedFormatError(SonicTraceError):
    """The container or codec is not supported in the current environment."""

    exit_code = 3


class MalformedFileError(SonicTraceError):
    """The file claims to be a supported format but cannot be parsed or decoded."""

    exit_code = 4


class ResourceLimitError(SonicTraceError):
    """The input exceeds a configured resource limit (size, duration, channels)."""

    exit_code = 5


class DependencyUnavailableError(SonicTraceError):
    """An optional external tool (FFmpeg/FFprobe) is required but not installed."""

    exit_code = 6
