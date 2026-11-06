"""Data structures shared by all container parsers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class StructuralIssue:
    """A deviation from the container specification or an internal inconsistency."""

    code: str
    severity: str  # info | low | medium | high
    message: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StructureReport:
    container: str
    parser: str
    details: dict = field(default_factory=dict)
    issues: list[StructuralIssue] = field(default_factory=list)
    signatures: list[str] = field(default_factory=list)  # encoder/software strings found in the binary
    tags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "container": self.container,
            "parser": self.parser,
            "details": self.details,
            "issues": [i.to_dict() for i in self.issues],
            "signatures": list(self.signatures),
            "tags": dict(self.tags),
        }
