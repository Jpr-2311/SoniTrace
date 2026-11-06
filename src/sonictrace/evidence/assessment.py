"""Final evidence-based assessment.

The assessment is a set of ordinal *indicator levels* with explicit rules - never a
probability of manipulation and never a "real/fake" verdict:

local_edit_indicators
    strong    - an event corroborated by >= 3 independent families, or a high-severity
                observed local finding (e.g. a bit-exact duplicated segment)
    moderate  - an event corroborated by 2 independent families, or a medium-severity
                observed local finding (digital silence in a noisy context, a hum-phase
                jump, a local histogram-comb region)
    weak      - isolated indicators only
    none      - no local indicators

structural_integrity  - same scale, from container/metadata findings.
processing_history    - the global assessments (lossy coding, upsampling, gain change).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .correlation import CorrelatedEvent, GlobalAssessment
from .evidence_model import Category, Finding, SEVERITY_RANK, Severity, TestResult, _clean

LEVELS = ["none", "weak", "moderate", "strong"]

CANNOT_CONCLUDE = [
    "Whether the recording is authentic, or whether it truthfully represents the events it appears to capture.",
    "Whether any detected processing was performed with an intent to deceive; most processing (conversion, normalisation, noise gating, compression) is routine.",
    "Whether the voice or content is synthetic/AI-generated: no test in this engine addresses speech synthesis.",
    "That the file is unedited: the absence of indicators does not prove absence of editing. Crossfaded edits at matching levels, consistent backgrounds and re-recording can evade every test.",
    "How many times the audio was lossily encoded (only the presence of at least one lossy generation is measurable).",
    "Whether the audio was downsampled: downsampling leaves no trace distinguishable from a native recording at the lower rate.",
    "Error rates on real casework: all performance figures come from a synthetic benchmark and are not real-world forensic accuracy.",
]


@dataclass
class Assessment:
    local_edit_indicators: str
    structural_integrity: str
    processing_history: list[dict]
    summary: str
    rationale: list[str]
    observed_evidence: list[str]
    statistical_anomalies: list[str]
    possible_explanations: list[str]
    cannot_be_concluded: list[str]
    not_applicable_tests: list[str]
    false_positive_considerations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return _clean(dict(self.__dict__))


def _level_local(events: list[CorrelatedEvent], findings: list[Finding]) -> tuple[str, list[str]]:
    why = []
    lvl = 0
    for e in events:
        if e.strength == "strongly_corroborated":
            lvl = max(lvl, 3)
            why.append(f"{e.event_id} at {e.center:.3f} s is corroborated by {len(e.independent_families)} independent families ({', '.join(e.independent_families)}).")
        elif e.strength == "corroborated":
            lvl = max(lvl, 2)
            why.append(f"{e.event_id} at {e.center:.3f} s is corroborated by {', '.join(e.independent_families)}.")
        elif e.strength == "isolated":
            lvl = max(lvl, 1)
    local_obs = [f for f in findings if f.category == Category.OBSERVED and f.family in ("silence", "duplication", "enf", "quantization")
                 and f.localization.value != "global"]
    for f in local_obs:
        if f.severity == Severity.HIGH:
            lvl = max(lvl, 3)
            why.append(f"High-severity observed finding {f.finding_id}: {f.title}.")
        elif f.severity == Severity.MEDIUM:
            lvl = max(lvl, 2)
            why.append(f"Medium-severity observed finding {f.finding_id}: {f.title}.")
    if lvl == 1:
        why.append(f"{sum(e.strength == 'isolated' for e in events)} isolated indicator(s) without corroboration from an independent method.")
    return LEVELS[lvl], why


def _level_structure(findings: list[Finding]) -> str:
    s = [SEVERITY_RANK[f.severity] for f in findings if f.family in ("structure", "metadata") and f.category == Category.OBSERVED]
    if not s:
        return "none"
    m = max(s)
    return {0: "none", 1: "weak", 2: "moderate", 3: "strong"}[m]


def build_assessment(findings: list[Finding], tests: list[TestResult], events: list[CorrelatedEvent],
                     global_assessments: list[GlobalAssessment]) -> Assessment:
    local, why = _level_local(events, findings)
    structure = _level_structure(findings)
    observed = [f"{f.finding_id}: {f.title}" for f in findings if f.category == Category.OBSERVED and f.severity != Severity.INFO]
    stats = [f"{f.finding_id}: {f.title}" for f in findings if f.category == Category.STATISTICAL]
    expl = []
    for e in events:
        if e.strength != "isolated":
            expl.extend(f"{e.event_id} ({e.center:.2f} s): {x}" for x in e.explanations)
    for g in global_assessments:
        if g.status in ("established", "indicated", "possible"):
            expl.append(f"{g.topic.replace('_', ' ')} [{g.status}]: {g.statement}")
    na = [f"{t.test_id} {t.name}: {t.summary}" for t in tests if t.status != "completed"]
    cannot = list(CANNOT_CONCLUDE) + [f"Test {t.test_id} ({t.name}) could not be applied: {t.summary}" for t in tests if t.status == "not_applicable"]

    fp = []
    fams = {f.family for f in findings if f.severity != Severity.INFO}
    if "silence" in fams:
        fp.append("Digital silence is also produced by noise gates, 'silence removal' and recorder pause functions.")
    if "short_time" in fams:
        fp.append("Level and spectral jumps occur naturally at speech and note onsets; they are reported only as supporting observations.")
    if "waveform" in fams:
        fp.append("Clicks, plosives and percussive transients produce residual impulses similar to hard edits.")
    if "quantization" in fams:
        fp.append("Histogram combing results from any digital gain change - including routine normalisation of a whole file.")
    if "duplication" in fams:
        fp.append("Loop-based music and synthetic signals repeat material legitimately.")
    if "bandwidth" in fams or "codec_holes" in fams:
        fp.append("Band limits and codec holes document processing history (encoding/resampling), which is routine for distributed audio.")
    if "noise" in fams:
        fp.append("Background changes can be caused by the environment, automatic gain control or noise suppression in the device.")

    processing = [g.to_dict() for g in global_assessments]
    hist = [g for g in global_assessments if g.status in ("established", "indicated") and g.topic != "container_integrity"]
    parts = [f"Local edit indicators: {local.upper()}.", f"Structural/metadata inconsistencies: {structure.upper()}."]
    if hist:
        parts.append("Processing history: " + "; ".join(f"{g.topic.replace('_', ' ')} ({g.status})" for g in hist) + ".")
    else:
        parts.append("Processing history: no lossy-coding, upsampling or gain-change fingerprint indicated.")
    parts.append("These are indicator levels from explicit rules, not probabilities of manipulation.")
    return Assessment(local, structure, processing, " ".join(parts), why, observed, stats, expl, cannot, na, fp)
