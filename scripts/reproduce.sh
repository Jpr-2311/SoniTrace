#!/usr/bin/env sh
# Reproduce every SonicTrace experiment (Linux/macOS). Run from the repository root.
set -e
python -m pip install -e ".[dev]"
python -m pytest
sonictrace dataset generate --out datasets/sonictrace_v1 --seed 1337
sonictrace benchmark --dataset datasets/sonictrace_v1 --split calibration --out output/benchmark_v1.2
sonictrace benchmark --dataset datasets/sonictrace_v1 --split evaluation --out output/benchmark_v1.2
python scripts/verify_lame_lowpass.py
python scripts/run_demo.py
