"""Binary container parsers (Module A: file-structure intelligence)."""

from .common import StructuralIssue, StructureReport
from .codec_inspector import inspect_structure

__all__ = ["StructuralIssue", "StructureReport", "inspect_structure"]
