"""Machine-readable JSON report."""

from __future__ import annotations

import json
from pathlib import Path


def write_json_report(report: dict, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return p
