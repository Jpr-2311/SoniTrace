import json

from sonictrace.evidence.assessment import CANNOT_CONCLUDE, build_assessment
from sonictrace.evidence.correlation import correlate_events
from sonictrace.evidence.evidence_model import Category, EvidenceRegistry, Localization, Severity


def add(reg, fam, t, cat=Category.OBSERVED, sev=Severity.LOW, loc=Localization.POINT, t1=None):
    return reg.add_finding("X", test_id="T", module="m", method="m", family=fam, category=cat, severity=sev,
                           title=fam, description=fam, localization=loc, time_start=t, time_end=t if t1 is None else t1)


def test_ids_are_sequential_per_prefix():
    reg = EvidenceRegistry()
    a, b = add(reg, "waveform", 1.0), add(reg, "noise", 2.0)
    assert (a.finding_id, b.finding_id) == ("X-001", "X-002")


def test_independent_families_corroborate():
    reg = EvidenceRegistry()
    add(reg, "waveform", 2.00)
    add(reg, "noise", 2.03, cat=Category.STATISTICAL)
    add(reg, "enf", 2.05)
    ev = correlate_events(reg.findings, 0.08)
    assert len(ev) == 1 and ev[0].strength == "strongly_corroborated"


def test_supporting_and_implied_families_do_not_corroborate():
    reg = EvidenceRegistry()
    add(reg, "silence", 3.0, loc=Localization.REGION, t1=3.4)
    add(reg, "short_time", 3.0, cat=Category.STATISTICAL)  # implied by the silence itself
    add(reg, "noise", 3.0, cat=Category.STATISTICAL)  # implied by the silence itself
    ev = correlate_events(reg.findings, 0.08)
    first = min(ev, key=lambda e: e.time_start)
    assert first.independent_families == ["silence"] and first.strength == "isolated"


def test_statistical_and_short_time_alone_make_no_event():
    reg = EvidenceRegistry()
    add(reg, "short_time", 1.0, cat=Category.STATISTICAL)
    add(reg, "statistical", 1.0, cat=Category.STATISTICAL)
    assert correlate_events(reg.findings, 0.08) == []


def test_assessment_levels_and_scope_statements():
    reg = EvidenceRegistry()
    add(reg, "waveform", 1.0)
    add(reg, "noise", 1.02, cat=Category.STATISTICAL)
    ev = correlate_events(reg.findings, 0.08)
    a = build_assessment(reg.findings, [], ev, [])
    assert a.local_edit_indicators == "moderate"
    assert all(c in a.cannot_be_concluded for c in CANNOT_CONCLUDE)
    empty = build_assessment([], [], [], [])
    assert empty.local_edit_indicators == "none"


def test_reports_contain_no_probabilities(tonal_clean):
    from sonictrace.engine import ForensicEngine

    txt = json.dumps(ForensicEngine().analyze(tonal_clean).to_dict()).lower()
    assert "probability" not in txt.replace("probabilities of manipulation", "")
