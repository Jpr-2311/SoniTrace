"""Dataset manifest: ground-truth labels, transformation logs, hashes and splits."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class SampleRecord:
    sample_id: str
    file: str  # relative to the dataset root
    split: str  # calibration | evaluation
    source_id: str
    source_type: str
    environment: str
    condition: str
    sample_rate: int
    duration_s: float
    labels: dict
    edit_times_s: list[float]
    transformation_log: list[dict]
    sha256: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Manifest:
    name: str
    version: str
    seed: int
    created_with: dict
    parameters: dict
    samples: list[SampleRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "version": self.version, "seed": self.seed, "created_with": self.created_with,
                "parameters": self.parameters, "sample_count": len(self.samples),
                "samples": [s.to_dict() for s in self.samples]}

    def write(self, root: Path) -> tuple[Path, Path]:
        jp = root / "manifest.json"
        jp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        cp = root / "manifest.csv"
        with open(cp, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["sample_id", "file", "split", "source_id", "source_type", "environment", "condition", "sample_rate",
                        "duration_s", "edited", "edit_type", "compressed", "resampled", "gain_edit", "duplication",
                        "legit_processing", "edit_times_s", "sha256"])
            for s in self.samples:
                L = s.labels
                w.writerow([s.sample_id, s.file, s.split, s.source_id, s.source_type, s.environment, s.condition, s.sample_rate,
                            f"{s.duration_s:.4f}", L["edited"], L.get("edit_type") or "", L["compressed"], L["resampled"],
                            L["gain_edit"], L["duplication"], "|".join(L.get("legit_processing", [])),
                            "|".join(f"{t:.4f}" for t in s.edit_times_s), s.sha256])
        return jp, cp


def load_manifest(root: str | Path) -> dict:
    p = Path(root) / "manifest.json"
    if not p.exists():
        raise FileNotFoundError(f"No manifest.json in {root}. Run 'sonictrace dataset generate' first.")
    return json.loads(p.read_text(encoding="utf-8"))
