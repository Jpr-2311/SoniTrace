"""End-to-end demonstration: one unmodified and one deliberately manipulated recording.

Creates examples/demo/original.wav and examples/demo/manipulated.wav (deterministic),
then runs `sonictrace report` on both and `sonictrace compare` on the pair.

    python scripts/run_demo.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from sonictrace.dataset.sources import quantize16, render_environment, render_source

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"
SR = 44100


def build() -> dict:
    DEMO.mkdir(parents=True, exist_ok=True)
    dur = 8.0
    n = int(SR * dur)
    src = render_source("speech", [2026, 1], SR, dur)
    bg = render_environment("hum", [2026, 2], SR, n)  # mains hum makes ENF analysis applicable
    orig = quantize16(src + bg, np.random.default_rng([2026, 3]))
    x = orig.astype(np.float64)
    log = []
    # 1) hard cut: remove 0.3519 s at 2.30 s (17.6 hum periods -> hum phase jump)
    p, L = int(2.30 * SR), int(0.3519 * SR)
    x = np.concatenate([x[:p], x[p + L:]])
    log.append({"edit": "cut", "at_s": p / SR, "removed_s": L / SR})
    # 2) insert 0.40 s of digital silence at 4.10 s
    p = int(4.10 * SR)
    x = np.concatenate([x[:p], np.zeros(int(0.40 * SR)), x[p:]])
    log.append({"edit": "insert_digital_silence", "from_s": 4.10, "to_s": 4.50})
    # 3) copy 0.5 s from 1.00 s over 6.00 s (copy-move)
    a, b, L = int(1.00 * SR), int(6.00 * SR), int(0.50 * SR)
    x[b:b + L] = x[a:a + L]
    log.append({"edit": "copy_overwrite", "source_s": 1.0, "dest_s": 6.0, "length_s": 0.5})
    man = np.clip(np.round(x), -32768, 32767).astype(np.int16)
    sf.write(str(DEMO / "original.wav"), orig, SR, subtype="PCM_16")
    sf.write(str(DEMO / "manipulated.wav"), man, SR, subtype="PCM_16")
    (DEMO / "ground_truth.json").write_text(json.dumps({"original": "unmodified", "manipulated_edits": log}, indent=2))
    return {"edits": log}


def run(*args: str) -> None:
    cmd = [sys.executable, "-m", "sonictrace", *args]
    print("\n$ sonictrace " + " ".join(args), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


if __name__ == "__main__":
    gt = build()
    print("Ground truth:", json.dumps(gt, indent=2))
    run("report", str(DEMO / "original.wav"), "--out-dir", str(DEMO / "reports"))
    run("report", str(DEMO / "manipulated.wav"), "--out-dir", str(DEMO / "reports"))
    run("analyze", str(DEMO / "manipulated.wav"))
    run("compare", str(DEMO / "original.wav"), str(DEMO / "manipulated.wav"), "--out-dir", str(DEMO / "compare"))
