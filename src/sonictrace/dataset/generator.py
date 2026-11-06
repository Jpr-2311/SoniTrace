"""Deterministic generation of the SonicTrace synthetic forensic dataset.

Design
------
* Each *source* is an independent synthetic recording (own seed, type, environment).
* Sources are assigned to exactly one split (calibration or evaluation), and every
  condition derived from a source stays in that split - no source material leaks
  across splits.
* Every condition is produced from the source's 16-bit "original recording", so the
  manipulated files differ from their original only by the logged transformation.
* All randomness comes from ``numpy.random.default_rng([seed, split, source, purpose])``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from .. import __version__
from ..utils.hashing import sha256_file
from ..utils.tools import tool_version
from . import transformations as T
from .manifest import Manifest, SampleRecord
from .sources import ENVIRONMENTS, quantize16, render_environment, render_source

SPLITS = {"calibration": 0, "evaluation": 1}
EDIT_CONDITIONS = {"cut_hard", "cut_crossfade", "insert_silence", "gain_step", "copy_overwrite", "noise_env_splice"}


def _labels(condition: str, log: list[dict]) -> dict:
    compressed = condition.startswith("mp3")
    resampled = condition.startswith("resample")
    legit = {"added_noise": ["background_noise_added"], "legit_normalize": ["peak_normalization"],
             "legit_noise_gate": ["noise_gate"], "legit_loop": ["loop_based_content"]}.get(condition, [])
    if compressed:
        legit = legit + ["lossy_compression"]
    return {
        "edited": condition in EDIT_CONDITIONS,
        "edit_type": condition if condition in EDIT_CONDITIONS else None,
        "compressed": compressed,
        "compression_generations": next((len(e["bitrates_kbps"]) for e in log if e["step"] == "mp3_chain"), 0),
        "resampled": resampled,
        "gain_edit": condition == "gain_step",
        "duplication": condition == "copy_overwrite",
        "legit_processing": legit,
    }


def generate_dataset(out_dir: str | Path, seed: int = 1337, sources_per_split: int = 4, controls_per_split: int = 4,
                     duration: float = 6.0, sr: int = 44100, include_mp3: bool = True,
                     progress: Callable[[str], None] | None = None) -> Manifest:
    root = Path(out_dir)
    (root / "audio").mkdir(parents=True, exist_ok=True)
    mp3_ok = include_mp3 and T.ffmpeg_available()
    manifest = Manifest(
        name="sonictrace-synthetic", version="1.0", seed=seed,
        created_with={"sonictrace": __version__, "ffmpeg": tool_version("ffmpeg") if mp3_ok else None},
        parameters={"sources_per_split": sources_per_split, "controls_per_split": controls_per_split,
                    "duration_s": duration, "sample_rate": sr, "mp3_conditions": mp3_ok},
    )

    def emit(split: str, sid: str, kind: str, env: str, cond: str, data: np.ndarray, rate: int, log: list[dict],
             ext: str = "wav", mp3_from: np.ndarray | None = None) -> None:
        name = f"{sid}__{cond}.{ext}"
        path = root / "audio" / name
        if ext == "wav":
            sf.write(str(path), data, rate, subtype="PCM_16")
        else:
            log.append(T.mp3_chain(mp3_from, rate, [64, 192], keep_mp3=path)[1])
        times = [t for e in log for t in e.get("edit_times_s", [])]
        dur = len(data) / rate if ext == "wav" else len(mp3_from) / rate
        rec = SampleRecord(f"{sid}__{cond}", f"audio/{name}", split, sid, kind, env, cond, rate, dur,
                           _labels(cond, log), times, log, sha256_file(path))
        manifest.samples.append(rec)
        if progress:
            progress(rec.sample_id)

    for split, si in SPLITS.items():
        for k in range(sources_per_split):
            kind = "speech" if k % 2 == 0 else "tonal"
            env = ENVIRONMENTS[k % len(ENVIRONMENTS)]
            sid = f"{split[:3]}_src{k:02d}"
            base_seed = [seed, si, k]
            n = int(sr * duration)
            src = render_source(kind, base_seed + [1], sr, duration)
            bg = render_environment(env, base_seed + [2], sr, n)
            orig = quantize16(src + bg, np.random.default_rng(base_seed + [3]))
            rng = lambda purpose: np.random.default_rng(base_seed + [100 + purpose])  # noqa: E731
            src_log = [{"step": "synthesize", "source_type": kind, "environment": env, "seed": base_seed,
                        "sample_rate": sr, "duration_s": duration, "quantization": "16-bit TPDF dither"}]
            emit(split, sid, kind, env, "clean", orig, sr, list(src_log))
            y, lg = T.add_noise(orig, sr, rng(1)); emit(split, sid, kind, env, "added_noise", y, sr, src_log + [lg])
            y, lg = T.cut(orig, sr, rng(2)); emit(split, sid, kind, env, "cut_hard", y, sr, src_log + [lg])
            y, lg = T.cut(orig, sr, rng(3), crossfade_ms=10.0); emit(split, sid, kind, env, "cut_crossfade", y, sr, src_log + [lg])
            y, lg = T.insert_silence(orig, sr, rng(4)); emit(split, sid, kind, env, "insert_silence", y, sr, src_log + [lg])
            y, lg = T.gain_step(orig, sr, rng(5)); emit(split, sid, kind, env, "gain_step", y, sr, src_log + [lg])
            y, lg = T.copy_overwrite(orig, sr, rng(6)); emit(split, sid, kind, env, "copy_overwrite", y, sr, src_log + [lg])
            # environment splice: same foreground, background switches at the edit point
            env_b = ENVIRONMENTS[(k + 1 + int(rng(7).integers(0, len(ENVIRONMENTS) - 1))) % len(ENVIRONMENTS)]
            if env_b == env:
                env_b = ENVIRONMENTS[(ENVIRONMENTS.index(env) + 1) % len(ENVIRONMENTS)]
            bg_b = render_environment(env_b, base_seed + [8], sr, n)
            p = T.edit_position(rng(9), n, sr)
            mixed = np.concatenate([src[:p] + bg[:p], src[p:] + bg_b[p:]])
            y = quantize16(mixed, np.random.default_rng(base_seed + [3]))
            emit(split, sid, kind, env, "noise_env_splice", y, sr, src_log + [
                {"step": "environment_splice", "environment_before": env, "environment_after": env_b, "at_s": p / sr, "edit_times_s": [p / sr]}])
            for mode, cond in (("poly_down_up", "resample_poly"), ("linear_up", "resample_linear"), ("to48k", "resample_48k")):
                y, rate, lg = T.resample(orig, sr, rng(10), mode)
                emit(split, sid, kind, env, cond, y, rate, src_log + [lg])
            if mp3_ok:
                # mono sources: 64 kbit/s mono gets the per-channel budget (and LAME low-pass) of 128 kbit/s stereo
                y, lg = T.mp3_chain(orig, sr, [64]); emit(split, sid, kind, env, "mp3_1gen", y, sr, src_log + [lg])
                y, lg = T.mp3_chain(orig, sr, [64, 96]); emit(split, sid, kind, env, "mp3_2gen", y, sr, src_log + [lg])
                emit(split, sid, kind, env, "mp3_transcoded", orig, sr, list(src_log), ext="mp3", mp3_from=orig)
            y, lg = T.normalize(orig); emit(split, sid, kind, env, "legit_normalize", y, sr, src_log + [lg])
            y, lg = T.noise_gate(orig, sr); emit(split, sid, kind, env, "legit_noise_gate", y, sr, src_log + [lg])
            if kind == "tonal":
                bar = src[: int(1.5 * sr)]
                looped = np.tile(bar, int(np.ceil(n / len(bar))))[:n]
                y = quantize16(looped + bg, np.random.default_rng(base_seed + [3]))
                emit(split, sid, kind, env, "legit_loop", y, sr, src_log + [{"step": "loop_content", "bar_s": 1.5, "edit_times_s": []}])

        for c in range(controls_per_split):
            kind = "speech" if c % 2 == 0 else "tonal"
            env = ENVIRONMENTS[(c + 1) % len(ENVIRONMENTS)]
            sid = f"{split[:3]}_ctl{c:02d}"
            base_seed = [seed, si, 500 + c]
            rate = 48000 if c % 4 == 3 else sr
            n = int(rate * duration)
            src = render_source(kind, base_seed + [1], rate, duration)
            if c % 4 == 2:
                src = src * 10 ** (-14 / 20)  # quiet recording
            bg = render_environment(env, base_seed + [2], rate, n)
            y = quantize16(src + bg, np.random.default_rng(base_seed + [3]))
            emit(split, sid, kind, env, "control", y, rate, [{"step": "synthesize", "source_type": kind, "environment": env,
                                                             "seed": base_seed, "sample_rate": rate, "duration_s": duration,
                                                             "quantization": "16-bit TPDF dither", "role": "unmodified control"}])
    manifest.write(root)
    return manifest
