import json
import os

from typer.testing import CliRunner

from conftest import needs_ffmpeg
from sonictrace.cli import app
from sonictrace.utils.hashing import sha256_file

runner = CliRunner()


def test_version():
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0 and "numpy" in r.output


def test_analyze_text_and_json(tonal_clean, tmp_path):
    r = runner.invoke(app, ["analyze", str(tonal_clean)])
    assert r.exit_code == 0, r.output
    assert "Local edit indicators" in r.output and "Cannot be concluded" in r.output
    jo = tmp_path / "out.json"
    r = runner.invoke(app, ["analyze", str(tonal_clean), "--format", "json", "--json-out", str(jo)])
    assert r.exit_code == 0
    assert json.loads(jo.read_text(encoding="utf-8"))["file_identity"]["sha256"] == sha256_file(tonal_clean)


def test_metadata_inspect_report_compare(tonal_clean, tonal_cut, tmp_path):
    cut, _ = tonal_cut
    r = runner.invoke(app, ["metadata", str(tonal_clean), "--json"])
    assert r.exit_code == 0 and json.loads(r.output)["sha256"] == sha256_file(tonal_clean)
    r = runner.invoke(app, ["inspect", str(tonal_clean)])
    assert r.exit_code == 0 and "RIFF chunks" in r.output
    r = runner.invoke(app, ["report", str(cut), "--out-dir", str(tmp_path / "rep")])
    assert r.exit_code == 0 and (tmp_path / "rep" / "tonal_cut_report.html").exists()
    r = runner.invoke(app, ["compare", str(tonal_clean), str(cut), "--json"])
    assert r.exit_code == 0
    res = json.loads(r.output)
    steps = [f for f in res["findings"] if f["type"] == "alignment_step"]
    assert steps and abs(steps[0]["offset_change_s"] - 0.3) < 0.01


def test_malformed_unsupported_and_missing_inputs(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"RIFF\x10\x00\x00\x00WAVEjunkjunk")
    r = runner.invoke(app, ["analyze", str(bad)])
    assert r.exit_code == 4 and "Error" in r.output and "Traceback" not in r.output
    unk = tmp_path / "file.xyz"
    unk.write_bytes(os.urandom(4000))
    r = runner.invoke(app, ["analyze", str(unk)])
    assert r.exit_code == 3 and "Unsupported" in r.output
    r = runner.invoke(app, ["analyze", str(tmp_path / "missing.wav")])
    assert r.exit_code == 2 and "not found" in r.output
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    assert runner.invoke(app, ["analyze", str(empty)]).exit_code == 4


def test_resource_limit(tonal_clean):
    r = runner.invoke(app, ["analyze", str(tonal_clean), "--max-duration", "1"])
    assert r.exit_code == 5 and "exceeds" in r.output


def test_dataset_generate_and_benchmark(tmp_path):
    ds = tmp_path / "ds"
    r = runner.invoke(app, ["dataset", "generate", "--out", str(ds), "--sources", "2", "--controls", "1",
                            "--duration", "3", "--no-mp3"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["benchmark", "--dataset", str(ds), "--split", "evaluation", "--out", str(tmp_path / "b")])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "b" / "benchmark_evaluation.md").exists()


@needs_ffmpeg
def test_mp3_input_via_ffmpeg(tonal_clean, tmp_path):
    from sonictrace.utils.tools import run_tool

    m = tmp_path / "x.mp3"
    run_tool(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(tonal_clean), "-b:a", "48k", str(m)])
    r = runner.invoke(app, ["analyze", str(m), "--format", "json"])
    assert r.exit_code == 0
    rep = json.loads(r.output)
    assert rep["audio"]["decoded_via"] == "ffmpeg"
    assert any(g["topic"] == "lossy_coding" and g["status"] == "established" for g in rep["global_assessments"])
