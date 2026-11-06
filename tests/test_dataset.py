import json

import pytest

from sonictrace.dataset.generator import generate_dataset


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    a = tmp_path_factory.mktemp("ds_a")
    b = tmp_path_factory.mktemp("ds_b")
    ma = generate_dataset(a, seed=99, sources_per_split=2, controls_per_split=2, duration=3.0, include_mp3=False)
    mb = generate_dataset(b, seed=99, sources_per_split=2, controls_per_split=2, duration=3.0, include_mp3=False)
    return a, ma, mb


def test_generation_is_bit_reproducible(small):
    _, ma, mb = small
    assert [s.sha256 for s in ma.samples] == [s.sha256 for s in mb.samples]


def test_no_source_leaks_across_splits(small):
    _, ma, _ = small
    by_split = {}
    for s in ma.samples:
        by_split.setdefault(s.split, set()).add(s.source_id)
    assert by_split["calibration"].isdisjoint(by_split["evaluation"])


def test_labels_logs_and_manifest(small):
    root, ma, _ = small
    conds = {s.condition for s in ma.samples}
    assert {"clean", "cut_hard", "insert_silence", "gain_step", "copy_overwrite", "noise_env_splice",
            "resample_poly", "legit_noise_gate", "control"} <= conds
    for s in ma.samples:
        assert s.transformation_log and s.transformation_log[0]["step"] == "synthesize"
        assert s.labels["edited"] == bool(s.edit_times_s) or s.condition in ("gain_step",)
        assert (root / s.file).exists()
    man = json.loads((root / "manifest.json").read_text())
    assert man["sample_count"] == len(ma.samples) and (root / "manifest.csv").exists()


def test_edit_labels_are_consistent(small):
    _, ma, _ = small
    for s in ma.samples:
        if s.condition in ("clean", "control", "legit_normalize", "legit_noise_gate", "added_noise"):
            assert not s.labels["edited"]
        if s.condition == "cut_hard":
            assert s.labels["edited"] and len(s.edit_times_s) == 1
