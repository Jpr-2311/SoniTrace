import json

from sonictrace.engine import ForensicEngine
from sonictrace.reporting.html_report import write_html_report
from sonictrace.reporting.json_report import write_json_report
from sonictrace.reporting.visualizations import make_all
from sonictrace.utils.hashing import sha256_file

SECTIONS = ["1. Investigation summary", "2. File identity and SHA-256", "3. File metadata", "4. Audio characteristics",
            "5. Individual forensic tests", "6. Detected anomalies", "7. Suspicious timestamps", "8. Evidence correlation",
            "9. False-positive considerations", "10. Methodology limitations", "11. Final evidence-based assessment"]


def test_json_and_html_reports(silence_inserted, tmp_path):
    path, _ = silence_inserted
    res = ForensicEngine().analyze(path, keep_context=True)
    rep = res.to_dict()
    jp = write_json_report(rep, tmp_path / "r.json")
    loaded = json.loads(jp.read_text(encoding="utf-8"))
    assert loaded["file_identity"]["sha256"] == sha256_file(path)
    assert loaded["integrity"]["unchanged"] is True
    assert {"observed", "statistical"} <= {f["category"] for f in loaded["findings"]}
    figs = make_all(res.context, rep, tmp_path / "figs", "x")
    assert len(figs) == 6 and all(p.stat().st_size > 1000 for p in figs.values())
    hp = write_html_report(rep, tmp_path / "r.html", figs)
    html = hp.read_text(encoding="utf-8")
    for s in SECTIONS:
        assert s in html
    assert "data:image/png;base64" in html and rep["file_identity"]["sha256"] in html


def test_analysis_is_deterministic(tonal_clean):
    a = ForensicEngine().analyze(tonal_clean).to_dict()
    b = ForensicEngine().analyze(tonal_clean).to_dict()
    strip = lambda d: [(f["finding_id"], f["title"]) for f in d["findings"]]  # noqa: E731
    assert strip(a) == strip(b)
    assert a["assessment"] == b["assessment"]
