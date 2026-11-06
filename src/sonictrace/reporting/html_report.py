"""Self-contained HTML forensic report (figures embedded as base64 PNG)."""

from __future__ import annotations

import base64
import html
from pathlib import Path

CAT_BADGE = {"observed": ("OBSERVED EVIDENCE", "#1565c0"), "statistical": ("STATISTICAL ANOMALY", "#6d4c41"),
             "explanation": ("POSSIBLE EXPLANATION", "#2e7d32"), "undetermined": ("CANNOT BE ESTABLISHED", "#616161")}
SEV_COLOR = {"info": "#90a4ae", "low": "#fbc02d", "medium": "#fb8c00", "high": "#d32f2f"}
LEVEL_COLOR = {"none": "#2e7d32", "weak": "#f9a825", "moderate": "#ef6c00", "strong": "#c62828"}

CSS = """
body{font-family:Segoe UI,Helvetica,Arial,sans-serif;margin:0;background:#f5f6f8;color:#1d2330;line-height:1.45}
main{max-width:1180px;margin:0 auto;padding:24px}
h1{margin:0 0 4px}h2{border-bottom:2px solid #d0d5dd;padding-bottom:4px;margin-top:34px}
.card{background:#fff;border:1px solid #dde1e7;border-radius:8px;padding:14px 18px;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #e1e4ea;padding:5px 7px;text-align:left;vertical-align:top}
th{background:#eef1f5}.badge{display:inline-block;padding:1px 7px;border-radius:10px;color:#fff;font-size:11px;font-weight:600}
.mono{font-family:Consolas,monospace;font-size:12px;word-break:break-all}.muted{color:#5f6b7a}
img{max-width:100%;border:1px solid #dde1e7;border-radius:4px;background:#fff}
.level{font-size:20px;font-weight:700;padding:6px 14px;border-radius:6px;color:#fff;display:inline-block;margin-right:10px}
ul{margin:4px 0 4px 18px;padding:0}details summary{cursor:pointer;font-weight:600}
.banner{background:#fff8e1;border-left:5px solid #f9a825;padding:10px 14px;margin:12px 0}
"""


def _e(v) -> str:
    return html.escape("" if v is None else str(v))


def _badge(text: str, color: str) -> str:
    return f'<span class="badge" style="background:{color}">{_e(text)}</span>'


def _kv_table(d: dict, keys: list[str] | None = None) -> str:
    rows = "".join(f"<tr><th>{_e(k)}</th><td class='mono'>{_e(v)}</td></tr>" for k, v in d.items() if keys is None or k in keys)
    return f"<table>{rows}</table>"


def _img(path: Path | None, alt: str) -> str:
    if path is None or not Path(path).exists():
        return ""
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return f'<p><img alt="{_e(alt)}" src="data:image/png;base64,{data}"></p>'


def _finding_html(f: dict) -> str:
    label, color = CAT_BADGE.get(f["category"], (f["category"], "#555"))
    when = ""
    if f.get("time_start") is not None:
        when = f"{f['time_start']:.3f} s" if f["time_end"] in (None, f["time_start"]) else f"{f['time_start']:.3f}-{f['time_end']:.3f} s"
        if f.get("sample_start") is not None:
            when += f" (samples {f['sample_start']}-{f['sample_end']})"
    alt = "".join(f"<li>{_e(a)}</li>" for a in f.get("alternative_explanations", []))
    lim = "".join(f"<li>{_e(a)}</li>" for a in f.get("limitations", []))
    sup = ", ".join(_e(s) for s in f.get("supporting_evidence", []))
    return f"""<div class="card"><b>{_e(f['finding_id'])}</b> {_badge(label, color)} {_badge(f['severity'].upper(), SEV_COLOR.get(f['severity'], '#999'))}
<b>{_e(f['title'])}</b><br><span class="muted">Test {_e(f['test_id'])} &middot; {_e(f['method'])} &middot; family <i>{_e(f['family'])}</i>
{(' &middot; ' + _e(when)) if when else ''}</span>
<p>{_e(f['description'])}</p>
<table><tr><th>Observed measurements</th><td class="mono">{_e(f.get('measurements'))}</td></tr>
<tr><th>Threshold / baseline</th><td class="mono">{_e(f.get('baseline') or '-')}</td></tr>
{f"<tr><th>Supporting evidence</th><td>{sup}</td></tr>" if sup else ''}
<tr><th>Alternative explanations</th><td><ul>{alt or '<li>-</li>'}</ul></td></tr>
<tr><th>Confidence limitations</th><td><ul>{lim or '<li>-</li>'}</ul></td></tr></table></div>"""


def render_html(report: dict, figures: dict[str, Path] | None = None) -> str:
    figures = figures or {}
    a = report["assessment"]
    ident = report["file_identity"]
    findings = report["findings"]
    tests = report["tests"]
    events = report["correlated_events"]
    meta = report["metadata"]
    out = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>SonicTrace report - {_e(ident['file_name'])}</title><style>{CSS}</style></head><body><main>"]
    out.append(f"<h1>SonicTrace forensic report</h1><div class='muted'>{_e(ident['file_name'])} &middot; generated {_e(report['generated_utc'])} "
               f"&middot; SonicTrace {_e(report['tool']['version'])}, methodology {_e(report['tool']['methodology_version'])}</div>")
    out.append("<div class='banner'>This report distinguishes <b>observed technical evidence</b>, <b>statistical anomalies</b>, "
               "<b>possible explanations</b> and <b>what cannot be established</b>. Indicator levels follow explicit rules; "
               "they are not probabilities and not a verdict on authenticity.</div>")

    # 1 summary
    out.append("<h2>1. Investigation summary</h2><div class='card'>")
    out.append(f"<span class='level' style='background:{LEVEL_COLOR[a['local_edit_indicators']]}'>Local edit indicators: {_e(a['local_edit_indicators']).upper()}</span>")
    out.append(f"<span class='level' style='background:{LEVEL_COLOR[a['structural_integrity']]}'>Structural inconsistencies: {_e(a['structural_integrity']).upper()}</span>")
    out.append(f"<p>{_e(a['summary'])}</p>")
    if a["rationale"]:
        out.append("<b>Rationale</b><ul>" + "".join(f"<li>{_e(r)}</li>" for r in a["rationale"]) + "</ul>")
    out.append(f"<p class='muted'>{len(tests)} tests run, {sum(t['detected'] for t in tests)} reported observations, "
               f"{len(findings)} findings, {len(events)} correlated events.</p></div>")

    # 2 identity
    integ = report["integrity"]
    out.append("<h2>2. File identity and SHA-256</h2><div class='card'>")
    out.append(_kv_table({"File": ident["path"], "Size (bytes)": ident["size_bytes"], "SHA-256 (before analysis)": integ["sha256_before"],
                          "SHA-256 (after analysis)": integ["sha256_after"],
                          "Evidence unchanged": "YES" if integ["unchanged"] else "NO - FILE CHANGED DURING ANALYSIS",
                          "Access mode": integ["access_mode"], "Container (from content)": meta["identity"]["container_description"],
                          "Analysed (UTC)": ident["analysed_utc"]}))
    out.append("</div>")

    # 3 metadata
    out.append("<h2>3. File metadata</h2><div class='card'>")
    out.append("<b>Identity</b>" + _kv_table(meta["identity"]))
    if meta.get("technical"):
        out.append("<b>Technical (FFprobe)</b>" + _kv_table(meta["technical"]))
    out.append("<b>Tags</b>" + (_kv_table(meta["tags"]) if meta["tags"] else "<p class='muted'>No tags.</p>"))
    sigs = meta.get("software_signatures", [])
    out.append("<b>Software signatures (observed in file)</b>" + (
        "<table><tr><th>Signature</th><th>Product</th><th>Category</th></tr>" + "".join(
            f"<tr><td class='mono'>{_e(s['signature'])}</td><td>{_e(s['product'])}</td><td>{_e(s['category'])}</td></tr>" for s in sigs) + "</table>"
        if sigs else "<p class='muted'>None found.</p>"))
    st = report["structure"]
    out.append(f"<details><summary>Binary structure ({_e(st['parser'])})</summary><pre class='mono'>{_e(_pretty(st['details']))}</pre></details></div>")

    # 4 audio characteristics
    ss = report["signal_summary"]
    out.append("<h2>4. Audio characteristics</h2><div class='card'>")
    out.append(_kv_table(report["audio"]))
    out.append(_kv_table({k: v for k, v in ss.items() if k not in ("band_limit", "mfcc_mean")}))
    out.append("<b>Frequency distribution (share of long-term energy)</b><table><tr>" + "".join(
        f"<th>{_e(b['band_hz'][0])}-{_e(b['band_hz'][1] or 'Nyq')} Hz</th>" for b in report["frequency_distribution"]) + "</tr><tr>" + "".join(
        f"<td>{b['energy_percent']:.2f} %</td>" for b in report["frequency_distribution"]) + "</tr></table>")
    for k in ("waveform", "spectrogram", "frequency", "rms", "noise_floor"):
        out.append(_img(figures.get(k), k))
    out.append("</div>")

    # 5 tests
    out.append("<h2>5. Individual forensic tests</h2><div class='card'><table><tr><th>ID</th><th>Test</th><th>Module</th><th>Status</th>"
               "<th>Result</th><th>Score</th><th>Threshold</th><th>Summary</th></tr>")
    for t in tests:
        res = _badge("REPORTED", "#ef6c00") if t["detected"] else _badge("NOTHING ABOVE THRESHOLD", "#2e7d32")
        if t["status"] != "completed":
            res = _badge(t["status"].upper().replace("_", " "), "#757575")
        exp = " <i>(experimental)</i>" if t.get("experimental") else ""
        sc = f"{t['score']:.4g}" if isinstance(t["score"], (int, float)) else "-"
        th = f"{t['threshold']:.4g}" if isinstance(t["threshold"], (int, float)) else "-"
        out.append(f"<tr><td>{_e(t['test_id'])}</td><td>{_e(t['name'])}{exp}</td><td>{_e(t['module'])}</td><td>{_e(t['status'])}</td>"
                   f"<td>{res}</td><td>{sc}<br><span class='muted'>{_e(t['score_name'])}</span></td><td>{th}</td><td>{_e(t['summary'])}</td></tr>")
    out.append("</table></div>")

    # 6 anomalies (observed + statistical), 7 timestamps
    obs = [f for f in findings if f["category"] == "observed" and f["severity"] != "info"]
    stat = [f for f in findings if f["category"] == "statistical"]
    out.append("<h2>6. Detected anomalies</h2><h3>6a. Observed technical evidence</h3>")
    out.append("".join(_finding_html(f) for f in obs) or "<p class='muted'>None.</p>")
    out.append("<h3>6b. Statistical anomalies (relative to this file's own baseline; not evidence of manipulation by themselves)</h3>")
    out.append("<details><summary>" + f"{len(stat)} statistical findings</summary>" + "".join(_finding_html(f) for f in stat) + "</details>")
    info = [f for f in findings if f["severity"] == "info" and f["category"] != "statistical"]
    if info:
        out.append("<details><summary>Informational observations</summary>" + "".join(_finding_html(f) for f in info) + "</details>")

    out.append("<h2>7. Suspicious timestamps</h2><div class='card'>")
    timed = sorted([f for f in findings if f.get("time_start") is not None and f["category"] != "statistical"], key=lambda f: f["time_start"])
    if timed:
        out.append("<table><tr><th>Time</th><th>Finding</th><th>Family</th><th>Category</th><th>Severity</th><th>Title</th></tr>" + "".join(
            f"<tr><td>{f['time_start']:.3f}" + (f"-{f['time_end']:.3f}" if f["time_end"] not in (None, f["time_start"]) else "") + " s</td>"
            f"<td>{_e(f['finding_id'])}</td><td>{_e(f['family'])}</td><td>{_e(f['category'])}</td><td>{_e(f['severity'])}</td><td>{_e(f['title'])}</td></tr>"
            for f in timed) + "</table>")
    else:
        out.append("<p class='muted'>No time-localised observations.</p>")
    out.append(_img(figures.get("timeline"), "timeline") + "</div>")

    # 8 correlation
    out.append("<h2>8. Evidence correlation</h2><div class='card'>")
    if events:
        out.append("<table><tr><th>Event</th><th>Time</th><th>Strength</th><th>Independent families</th><th>All families</th><th>Findings</th>"
                   "<th>Statistical context</th><th>Possible explanations</th></tr>" + "".join(
            f"<tr><td>{_e(e['event_id'])}</td><td>{e['time_start']:.3f}-{e['time_end']:.3f} s</td><td>{_e(e['strength'])}</td>"
            f"<td>{_e(', '.join(e['independent_families']))}</td><td>{_e(', '.join(e['families']))}</td><td>{_e(', '.join(e['finding_ids']))}</td>"
            f"<td>{_e(', '.join(e['statistical_support']) or '-')}</td><td><ul>{''.join(f'<li>{_e(x)}</li>' for x in e['explanations'])}</ul></td></tr>"
            for e in events) + "</table>")
    else:
        out.append("<p class='muted'>No time-localised events.</p>")
    out.append("<b>File-level (processing history and integrity)</b><table><tr><th>Topic</th><th>Status</th><th>Statement</th><th>Supporting</th><th>Alternatives</th></tr>" + "".join(
        f"<tr><td>{_e(g['topic'])}</td><td>{_e(g['status'])}</td><td>{_e(g['statement'])}</td><td>{_e(', '.join(g['supporting_findings']))}</td>"
        f"<td>{_e('; '.join(g['alternatives']))}</td></tr>" for g in report["global_assessments"]) + "</table>")
    out.append("<p class='muted'>Independence rules: statistical findings never count as corroboration; level/spectral jumps and noise-floor changes "
               "are not counted again when digital silence explains them.</p></div>")

    # 9 FP considerations
    out.append("<h2>9. False-positive considerations</h2><div class='card'><ul>" +
               ("".join(f"<li>{_e(x)}</li>" for x in a["false_positive_considerations"]) or "<li>No indicator families were triggered.</li>") + "</ul></div>")

    # 10 limitations
    lims = sorted({lim for t in tests for lim in t.get("limitations", [])})
    out.append("<h2>10. Methodology limitations</h2><div class='card'><ul>" + "".join(f"<li>{_e(x)}</li>" for x in lims) +
               "<li>Thresholds were calibrated on synthetic data (calibration split) and have not been validated on casework.</li>"
               "<li>Not-applicable tests provide no information either way.</li></ul>"
               + ("<b>Tests not applicable / failed</b><ul>" + "".join(f"<li>{_e(x)}</li>" for x in a["not_applicable_tests"]) + "</ul>" if a["not_applicable_tests"] else "")
               + "</div>")

    # 11 final assessment
    out.append("<h2>11. Final evidence-based assessment</h2><div class='card'>")
    out.append("<h3>Observed technical evidence</h3><ul>" + ("".join(f"<li>{_e(x)}</li>" for x in a["observed_evidence"]) or "<li>None.</li>") + "</ul>")
    out.append(f"<h3>Statistical anomalies</h3><p>{len(a['statistical_anomalies'])} statistical anomaly finding(s) (see 6b).</p>")
    out.append("<h3>Possible explanations</h3><ul>" + ("".join(f"<li>{_e(x)}</li>" for x in a["possible_explanations"]) or "<li>No corroborated events or processing-history indications.</li>") + "</ul>")
    out.append("<h3>What cannot be concluded</h3><ul>" + "".join(f"<li>{_e(x)}</li>" for x in a["cannot_be_concluded"]) + "</ul>")
    out.append(f"<p><b>Summary:</b> {_e(a['summary'])}</p></div>")

    env = report["environment"]
    out.append("<h2>Appendix: environment and configuration</h2><div class='card'>" + _kv_table(env) +
               f"<details><summary>Analysis configuration</summary><pre class='mono'>{_e(_pretty(report['config']))}</pre></details>"
               f"<p class='muted'>Timing: {_e(report['timing'])}</p></div>")
    out.append("</main></body></html>")
    return "\n".join(out)


def _pretty(d) -> str:
    import json

    return json.dumps(d, indent=2, default=str)


def write_html_report(report: dict, path: str | Path, figures: dict[str, Path] | None = None) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_html(report, figures), encoding="utf-8")
    return p
