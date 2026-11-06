import numpy as np

from conftest import SR, make_signal, write_wav
from sonictrace.engine import ForensicEngine


def _by_id(res):
    return {t.test_id: t for t in res.tests}


def test_hard_cut_in_continuous_music_is_localised(tonal_cut):
    path, t_cut = tonal_cut
    res = ForensicEngine().analyze(path, run_statistics=False)
    c1 = [f for f in res.findings if f.test_id == "C1"]
    assert any(abs(f.time_start - t_cut) < 0.01 for f in c1)


def test_clean_recording_has_no_waveform_or_silence_findings(tonal_clean):
    res = ForensicEngine().analyze(tonal_clean, run_statistics=False)
    t = _by_id(res)
    assert not t["C1"].detected and not t["C5"].detected and not t["C6"].detected
    assert res.assessment.local_edit_indicators in ("none", "weak")


def test_inserted_digital_silence_is_observed_and_corroborated(silence_inserted):
    path, t0 = silence_inserted
    res = ForensicEngine().analyze(path, run_statistics=False)
    sil = [f for f in res.findings if f.test_id == "C5" and f.localization.value == "region"]
    assert sil and abs(sil[0].time_start - t0) < 0.01
    assert sil[0].severity.value == "medium"
    assert res.assessment.local_edit_indicators in ("moderate", "strong")


def test_copy_move_duplicate_verified_by_ncc(tmp_path):
    x = make_signal("speech", seed=21, duration=5.0)
    y = x.copy()
    L = int(0.6 * SR)
    y[int(3.5 * SR) : int(3.5 * SR) + L] = x[SR : SR + L]
    res = ForensicEngine().analyze(write_wav(tmp_path / "dup.wav", y), run_statistics=False)
    dup = [f for f in res.findings if f.test_id == "C6"]
    assert dup and dup[0].measurements["ncc"] > 0.99
    # the verified pair lies inside the pasted region (pauses can split it into sub-runs)
    assert any(3.4 <= f.time_start <= 4.1 or 3.4 <= f.measurements["source_start_s"] <= 4.1 for f in dup)


def test_enf_phase_jump_at_cut(tmp_path):
    x = make_signal("speech", env="hum", seed=4, duration=6.0).astype(np.float64)
    p, L = int(3.0 * SR), int(0.2071 * SR)  # 10.355 hum periods: non-integer, phase jumps
    y = np.concatenate([x[:p], x[p + L :]]).astype(np.int16)
    res = ForensicEngine().analyze(write_wav(tmp_path / "hum_cut.wav", y), run_statistics=False)
    c7 = _by_id(res)["C7"]
    assert c7.status == "completed"
    enf = [f for f in res.findings if f.test_id == "C7"]
    assert enf and any(abs(0.5 * (f.time_start + f.time_end) - 3.0) < 0.4 for f in enf)


def test_gain_step_creates_local_histogram_comb(tmp_path):
    x = make_signal("tonal", seed=9, duration=5.0).astype(np.float64)
    x[int(1.5 * SR) : int(3.0 * SR)] *= 10 ** (6 / 20)
    y = np.clip(np.round(x), -32768, 32767).astype(np.int16)
    res = ForensicEngine().analyze(write_wav(tmp_path / "gain.wav", y), run_statistics=False)
    t = _by_id(res)
    assert t["D3"].detected
    q = [f for f in res.findings if f.test_id == "D3" and f.localization.value == "region"]
    assert q and q[0].time_start < 2.0 and q[0].time_end > 2.5
