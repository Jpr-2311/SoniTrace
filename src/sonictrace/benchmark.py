"""Benchmark: run the engine over a dataset split and score every technique against ground truth.

Each technique is evaluated against the label it is designed for (e.g. splice detectors
against ``edited``, codec detectors against ``compressed``) on *all* files of the split,
including unmodified controls and legitimately processed files, so false positives on
routine processing are counted rather than hidden.

The numbers describe this synthetic dataset only. They are not real-world error rates.
"""

from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable

from . import METHODOLOGY_VERSION
from .config import AnalysisConfig
from .dataset.manifest import load_manifest
from .engine import ForensicEngine

TECHNIQUE_LABEL = {
    "A1": "edited", "C1": "edited", "C2": "edited", "C3": "edited", "C4": "edited", "C5": "edited", "C6": "edited",
    "C7": "edited", "D1": "compressed", "D2": "compressed", "D3": "gain_edit", "D4": "transcoded_mp3",
    "E1": "resampled", "E2": "resampled", "E3": "resampled",
    "F1": "edited", "F2": "edited", "F3": "edited", "F4": "edited", "F5": "edited",
}
LOCALIZING = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "D3"]
SWEEP = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
LEVELS = ["none", "weak", "moderate", "strong"]


def truth(sample: dict, label: str) -> bool:
    """Ground-truth label of a manifest sample; ``transcoded_mp3`` is derived (D4 can only act on MP3 containers)."""
    if label == "transcoded_mp3":
        return sample["file"].endswith(".mp3") and sample["labels"].get("compression_generations", 0) >= 2
    return bool(sample["labels"][label])


def metrics(pairs: list[tuple[bool, bool]]) -> dict:
    tp = sum(1 for t, p in pairs if t and p)
    fp = sum(1 for t, p in pairs if not t and p)
    tn = sum(1 for t, p in pairs if not t and not p)
    fn = sum(1 for t, p in pairs if t and not p)
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if prec is not None and rec is not None else None)
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "precision": prec, "recall": rec, "f1": f1,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None, "n": len(pairs)}


def _hit(f: dict, times: list[float], tol: float) -> bool:
    if f.get("time_start") is None:
        return False
    lo, hi = f["time_start"] - tol, (f["time_end"] if f.get("time_end") is not None else f["time_start"]) + tol
    if f["localization"] == "region":
        return any(abs(t - f["time_start"]) <= tol + 0.4 or abs(t - f["time_end"]) <= tol + 0.4 for t in times) \
            if f["family"] == "quantization" else any(abs(t - f["time_start"]) <= tol or abs(t - f["time_end"]) <= tol for t in times)
    return any(lo <= t <= hi for t in times)


def analyse_split(root: Path, split: str, config: AnalysisConfig | None = None,
                  progress: Callable[[str], None] | None = None) -> list[dict]:
    man = load_manifest(root)
    engine = ForensicEngine(config)
    rows = []
    samples = [s for s in man["samples"] if split == "all" or s["split"] == split]
    for s in samples:
        t0 = time.perf_counter()
        try:
            res = engine.analyze(root / s["file"]).to_dict()
            err = None
        except Exception as exc:  # recorded as a failed analysis, never skipped silently
            res, err = None, f"{type(exc).__name__}: {exc}"
        row = {"sample": s, "error": err, "seconds": time.perf_counter() - t0}
        if res:
            row["tests"] = {t["test_id"]: {"detected": t["detected"], "score": t["score"], "threshold": t["threshold"],
                                           "status": t["status"], "summary": t["summary"], "finding_ids": t["finding_ids"]}
                            for t in res["tests"]}
            row["findings"] = {f["finding_id"]: f for f in res["findings"]}
            row["events"] = res["correlated_events"]
            row["local_level"] = res["assessment"]["local_edit_indicators"]
            row["structure_level"] = res["assessment"]["structural_integrity"]
            row["global"] = {g["topic"]: g["status"] for g in res["global_assessments"]}
            row["integrity_unchanged"] = res["integrity"]["unchanged"]
        rows.append(row)
        if progress:
            progress(s["sample_id"])
    return rows


def score_rows(rows: list[dict], loc_tol: float = 0.15) -> dict:
    ok = [r for r in rows if r.get("tests")]
    out: dict = {"methodology_version": METHODOLOGY_VERSION, "files": len(rows), "analysed": len(ok),
                 "failed": [{"sample": r["sample"]["sample_id"], "error": r["error"]} for r in rows if r.get("error")],
                 "integrity_all_unchanged": all(r.get("integrity_unchanged") for r in ok)}
    per_tech, sweeps, fps, fns = {}, {}, defaultdict(list), defaultdict(list)
    for tid, label in TECHNIQUE_LABEL.items():
        pairs, applicable = [], 0
        for r in ok:
            t = r["tests"].get(tid)
            if t is None:
                continue
            true = truth(r["sample"], label)
            pred = bool(t["detected"])
            applicable += t["status"] == "completed"
            pairs.append((true, pred))
            if pred and not true:
                fps[tid].append({"sample": r["sample"]["sample_id"], "condition": r["sample"]["condition"], "summary": t["summary"]})
            if true and not pred:
                fns[tid].append({"sample": r["sample"]["sample_id"], "condition": r["sample"]["condition"], "summary": t["summary"]})
        m = metrics(pairs)
        m.update({"label": label, "applicable": applicable})
        per_tech[tid] = m
        thr = next((r["tests"][tid]["threshold"] for r in ok if tid in r["tests"] and r["tests"][tid]["threshold"]), None)
        if thr:
            sw = []
            for k in SWEEP:
                sp = [(truth(r["sample"], label), (r["tests"][tid]["score"] or 0) >= k * thr) for r in ok if tid in r["tests"]]
                mm = metrics(sp)
                sw.append({"factor": k, "threshold": k * thr, "precision": mm["precision"], "recall": mm["recall"],
                           "false_positive_rate": mm["false_positive_rate"], "f1": mm["f1"]})
            sweeps[tid] = sw
    out["per_technique"] = per_tech
    out["threshold_sensitivity"] = sweeps
    out["false_positives"] = dict(fps)
    out["false_negatives"] = dict(fns)

    # correlated assessment (multi-layer) vs single techniques
    agg = {}
    for lvl in ("weak", "moderate", "strong"):
        k = LEVELS.index(lvl)
        agg[f"local_edit_level>={lvl}"] = metrics([(bool(r["sample"]["labels"]["edited"]), LEVELS.index(r["local_level"]) >= k) for r in ok])
    agg["lossy_coding indicated/established"] = metrics(
        [(bool(r["sample"]["labels"]["compressed"]), r["global"].get("lossy_coding") in ("indicated", "established")) for r in ok])
    agg["lossy_coding possible-or-stronger"] = metrics(
        [(bool(r["sample"]["labels"]["compressed"]), r["global"].get("lossy_coding") in ("possible", "indicated", "established")) for r in ok])
    agg["upsampling indicated"] = metrics([(bool(r["sample"]["labels"]["resampled"]), r["global"].get("upsampling") == "indicated") for r in ok])
    agg["transcoding indicated"] = metrics([(truth(r["sample"], "transcoded_mp3"), r["global"].get("transcoding") == "indicated") for r in ok])
    agg["digital_gain_change indicated"] = metrics([(bool(r["sample"]["labels"]["gain_edit"]), r["global"].get("digital_gain_change") == "indicated") for r in ok])
    out["correlated_assessment"] = agg
    cm = {lvl: {"edited": 0, "not_edited": 0} for lvl in LEVELS}
    for r in ok:
        cm[r["local_level"]]["edited" if r["sample"]["labels"]["edited"] else "not_edited"] += 1
    out["local_level_confusion"] = cm

    # per-condition detection rates
    cond = defaultdict(lambda: defaultdict(list))
    for r in ok:
        c = r["sample"]["condition"]
        for tid in TECHNIQUE_LABEL:
            if tid in r["tests"]:
                cond[c][tid].append(bool(r["tests"][tid]["detected"]))
        cond[c]["level>=moderate"].append(LEVELS.index(r["local_level"]) >= 2)
    out["per_condition_detection_rate"] = {c: {k: sum(v) / len(v) for k, v in d.items()} | {"n": len(next(iter(d.values())))}
                                           for c, d in sorted(cond.items())}

    # localisation on edited files
    loc = {}
    for tid in LOCALIZING + ["corroborated_event"]:
        hits, n = 0, 0
        for r in ok:
            times = r["sample"]["edit_times_s"]
            if not r["sample"]["labels"]["edited"] or not times:
                continue
            n += 1
            if tid == "corroborated_event":
                hit = any(e["strength"] != "isolated" and any(e["time_start"] - loc_tol <= t <= e["time_end"] + loc_tol for t in times)
                          for e in r["events"])
            else:
                fids = r["tests"].get(tid, {}).get("finding_ids", [])
                hit = any(_hit(r["findings"][f], times, loc_tol) for f in fids if f in r["findings"])
            hits += hit
        loc[tid] = {"edited_files": n, "localised": hits, "rate": hits / n if n else None}
    out["localisation"] = {"tolerance_s": loc_tol, "per_technique": loc}
    out["mean_seconds_per_file"] = sum(r["seconds"] for r in rows) / max(1, len(rows))
    return out


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def write_benchmark(out_dir: Path, rows: list[dict], scored: dict, split: str) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {"json": out_dir / f"benchmark_{split}.json", "csv": out_dir / f"benchmark_{split}_per_file.csv",
             "md": out_dir / f"benchmark_{split}.md"}
    paths["json"].write_text(json.dumps(scored, indent=2), encoding="utf-8")
    tids = list(TECHNIQUE_LABEL)
    with open(paths["csv"], "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["sample_id", "split", "condition", "edited", "compressed", "resampled", "gain_edit", "local_level",
                    "lossy_coding", "upsampling"] + [f"{t}_detected" for t in tids] + [f"{t}_score" for t in tids])
        for r in rows:
            s = r["sample"]
            if not r.get("tests"):
                w.writerow([s["sample_id"], s["split"], s["condition"], "ERROR", r.get("error")])
                continue
            L = s["labels"]
            w.writerow([s["sample_id"], s["split"], s["condition"], L["edited"], L["compressed"], L["resampled"], L["gain_edit"],
                        r["local_level"], r["global"].get("lossy_coding"), r["global"].get("upsampling")]
                       + [r["tests"].get(t, {}).get("detected") for t in tids] + [_fmt(r["tests"].get(t, {}).get("score")) for t in tids])
    lines = [f"# SonicTrace benchmark - split `{split}`", "",
             f"Methodology version {scored['methodology_version']}; {scored['analysed']}/{scored['files']} files analysed; "
             f"evidence files unchanged after analysis: {scored['integrity_all_unchanged']}; "
             f"mean {scored['mean_seconds_per_file']:.2f} s/file.", "",
             "> Synthetic data only. These figures are not real-world forensic error rates.", "",
             "## Per-technique performance", "", "| Test | Label | TP | FP | TN | FN | Precision | Recall | F1 | FPR |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for tid, m in scored["per_technique"].items():
        lines.append(f"| {tid} | {m['label']} | {m['tp']} | {m['fp']} | {m['tn']} | {m['fn']} | {_fmt(m['precision'])} | "
                     f"{_fmt(m['recall'])} | {_fmt(m['f1'])} | {_fmt(m['false_positive_rate'])} |")
    lines += ["", "## Correlated (multi-layer) assessment", "", "| Decision rule | TP | FP | TN | FN | Precision | Recall | F1 | FPR |",
              "|---|---|---|---|---|---|---|---|---|"]
    for k, m in scored["correlated_assessment"].items():
        lines.append(f"| {k} | {m['tp']} | {m['fp']} | {m['tn']} | {m['fn']} | {_fmt(m['precision'])} | {_fmt(m['recall'])} | "
                     f"{_fmt(m['f1'])} | {_fmt(m['false_positive_rate'])} |")
    lines += ["", "## Local-edit indicator level vs. ground truth (confusion matrix)", "", "| Level | edited | not edited |", "|---|---|---|"]
    for lvl, d in scored["local_level_confusion"].items():
        lines.append(f"| {lvl} | {d['edited']} | {d['not_edited']} |")
    lines += ["", f"## Localisation of edit points (tolerance {scored['localisation']['tolerance_s']} s)", "",
              "| Test | edited files | localised | rate |", "|---|---|---|---|"]
    for tid, d in scored["localisation"]["per_technique"].items():
        lines.append(f"| {tid} | {d['edited_files']} | {d['localised']} | {_fmt(d['rate'])} |")
    show = ["C1", "C2", "C4", "C5", "C6", "C7", "D1", "D2", "D3", "E1", "E2", "level>=moderate"]
    lines += ["", "## Detection rate per condition", "", "| Condition | n | " + " | ".join(show) + " |", "|---|---|" + "---|" * len(show)]
    for c, d in scored["per_condition_detection_rate"].items():
        lines.append(f"| {c} | {d['n']} | " + " | ".join(_fmt(d.get(k)) for k in show) + " |")
    lines += ["", "## Threshold sensitivity (primary score only)", ""]
    for tid, sw in scored["threshold_sensitivity"].items():
        lines.append(f"**{tid}**: " + "; ".join(f"x{s['factor']}: P={_fmt(s['precision'])} R={_fmt(s['recall'])} FPR={_fmt(s['false_positive_rate'])}" for s in sw))
        lines.append("")
    lines += ["## False positives by technique", ""]
    for tid, lst in scored["false_positives"].items():
        conds = defaultdict(int)
        for x in lst:
            conds[x["condition"]] += 1
        lines.append(f"- **{tid}** ({len(lst)}): " + ", ".join(f"{c} x{n}" for c, n in sorted(conds.items())))
    paths["md"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths
