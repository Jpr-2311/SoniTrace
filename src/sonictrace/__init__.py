"""SonicTrace: an explainable digital audio forensics and manipulation analysis engine.

SonicTrace does not classify recordings as "real" or "fake". It runs independent
forensic tests, records what each test measured, correlates the observations and
states explicitly what can and cannot be concluded from them.
"""

__version__ = "0.1.0"

# Bumped whenever detection rules or thresholds change, so that reports and
# benchmark results can always be tied to the exact methodology that produced them.
METHODOLOGY_VERSION = "1.2"

__all__ = ["__version__", "METHODOLOGY_VERSION"]
