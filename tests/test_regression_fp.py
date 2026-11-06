"""Regression tests for the false-positive cases investigated in research/false_positive_analysis.md."""

import os

import numpy as np

from conftest import SR, make_signal, write_wav
from sonictrace.dataset import transformations as T
from sonictrace.engine import ForensicEngine
from sonictrace.utils.hashing import sha256_file


def tid(res):
    return {t.test_id: t for t in res.tests}


def test_fp1_noise_gate_is_reported_as_gating_pattern_not_insertions(tmp_path):
    x = make_signal("speech", env="room", seed=31, duration=6.0)
    y, _ = T.noise_gate(x, SR)
    res = ForensicEngine().analyze(write_wav(tmp_path / "gate.wav", y), run_statistics=False)
    t = tid(res)
    if t["C5"].measurements["interior_runs"] >= 5:
        assert t["C5"].measurements["systematic_gating_pattern"]
        runs = [f for f in res.findings if f.test_id == "C5" and f.localization.value == "region"]
        assert all(f.severity.value == "low" for f in runs)


def test_fp2_whole_file_normalisation_is_processing_not_local_gain_edit(tmp_path):
    x = make_signal("tonal", seed=32, duration=5.0)
    y, _ = T.normalize(x)
    res = ForensicEngine().analyze(write_wav(tmp_path / "norm.wav", y), run_statistics=False)
    t = tid(res)
    assert t["D3"].measurements["whole_file_gain_processing"]
    assert not t["D3"].detected
    assert any(g.topic == "whole_file_gain_change" for g in res.global_assessments)


def test_fp3_natural_onsets_alone_do_not_create_events(speech_clean):
    res = ForensicEngine().analyze(speech_clean)
    t = tid(res)
    assert t["C2"].detected  # onsets are still measured and reported ...
    assert all(e.independent_families for e in res.events)  # ... but never form an event on their own
    assert not any(set(e.families) <= {"short_time", "statistical"} for e in res.events)


def test_fp4_loop_based_content_duplication_lists_loop_explanation(tmp_path):
    from sonictrace.dataset.sources import quantize16, render_environment, render_source

    src = render_source("tonal", [77, 1], SR, 6.0)
    bar = src[: int(1.5 * SR)]
    looped = np.tile(bar, 4)[: 6 * SR]
    y = quantize16(looped + render_environment("quiet", [77, 2], SR, 6 * SR), np.random.default_rng(1))
    res = ForensicEngine().analyze(write_wav(tmp_path / "loop.wav", y), run_statistics=False)
    dup = [f for f in res.findings if f.test_id == "C6"]
    assert dup, "exact loops are real duplicates and must be reported as observed fact"
    assert any("Loop-based" in a for a in dup[0].alternative_explanations)


def test_evidence_file_is_never_modified(tonal_clean):
    before = (sha256_file(tonal_clean), os.stat(tonal_clean).st_mtime_ns)
    res = ForensicEngine().analyze(tonal_clean)
    assert res.integrity["unchanged"]
    assert (sha256_file(tonal_clean), os.stat(tonal_clean).st_mtime_ns) == before
