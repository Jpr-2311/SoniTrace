"""Multi-layer evidence correlation.

Findings are grouped in time and, independently, at file level. An edit point is only
called *corroborated* when detectors that rely on different physical principles agree.

Independence rules (documented in research/methodology.md):

* Statistical (Module F) findings never count toward corroboration; they are attached
  to events as context only.
* Energy and spectral discontinuity share one family (``short_time``) because both react
  to the same onsets. Since v1.1 that family is *supporting* only: it is attached to
  events as context but can neither create an event nor corroborate one.
* ``noise`` is *implied by* ``silence``: an inserted run of digital zeros necessarily
  changes the noise floor, so it is not counted again when digital silence explains the
  event.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .evidence_model import Category, Finding, Localization, Severity, SEVERITY_RANK, TestResult, _clean

LOCAL_FAMILIES = {"waveform", "short_time", "noise", "silence", "enf", "duplication", "quantization"}
# v1.1: short_time (energy/spectral jumps) is supporting context only. Benchmark v1.0 showed it fires on
# 100 % of unedited calibration files (natural speech/note onsets), so it cannot corroborate anything.
SUPPORTING_FAMILIES = {"short_time"}
PRIMARY_FAMILIES = LOCAL_FAMILIES - SUPPORTING_FAMILIES
IMPLIED_BY = {"noise": {"silence"}}
REGION_TOLERANCE = {"quantization": 0.5}


@dataclass
class CorrelatedEvent:
    event_id: str
    time_start: float
    time_end: float
    finding_ids: list[str]
    families: list[str]
    independent_families: list[str]
    statistical_support: list[str]
    strength: str
    explanations: list[str]
    max_severity: str

    @property
    def center(self) -> float:
        return 0.5 * (self.time_start + self.time_end)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["center"] = self.center
        return _clean(d)


@dataclass
class GlobalAssessment:
    topic: str
    status: str  # established | indicated | possible | not_indicated | not_assessable
    statement: str
    supporting_findings: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return _clean(dict(self.__dict__))


def _anchors(f: Finding, tol: float) -> list[tuple[float, float]]:
    if f.time_start is None or f.localization == Localization.GLOBAL:
        return []
    t0 = f.time_start
    t1 = f.time_end if f.time_end is not None else t0
    if f.localization == Localization.POINT:
        c = 0.5 * (t0 + t1)
        return [(c, max(tol, 0.5 * (t1 - t0)))]
    rt = REGION_TOLERANCE.get(f.family, tol)
    return [(t0, rt), (t1, rt)]


def _explain(fams: set[str]) -> list[str]:
    ex = []
    if "silence" in fams:
        ex.append("Insertion of digital silence, or muting/gating, at this point")
    if "duplication" in fams:
        ex.append("Copy-move edit: material repeated from elsewhere in the recording (or loop-based/repetitive source material)")
    if "enf" in fams and ({"waveform", "short_time"} & fams):
        ex.append("Samples removed or inserted here: mains-hum phase continuity is broken at the same point as the waveform")
    elif "enf" in fams:
        ex.append("Mains-hum phase discontinuity: removal/insertion of samples or a change of electrical environment")
    if "noise" in fams and "waveform" in fams:
        ex.append("Splice joining material with a different background (different takes or recordings)")
    elif "noise" in fams:
        ex.append("Change of the acoustic background: environmental change or splice")
    if "quantization" in fams and ("waveform" in fams or "short_time" in fams):
        ex.append("Boundary of a region whose gain was changed digitally")
    if fams == {"waveform"}:
        ex.append("Hard edit point, or an impulsive sound (click, plosive, percussive onset)")
    if fams <= {"short_time", "statistical"} and "short_time" in fams:
        ex.append("Natural onset/offset of sound is the most common cause; an edit cannot be excluded")
    if not ex:
        ex.append("No specific mechanism suggested by this combination of observations")
    return ex


def correlate_events(findings: list[Finding], tolerance: float) -> list[CorrelatedEvent]:
    # Events are seeded by primary-family anchors only; supporting and statistical findings are
    # attached afterwards as context, so they can neither create nor chain-merge events.
    primary, context = [], []
    for f in findings:
        if f.family in PRIMARY_FAMILIES and f.severity != Severity.INFO:
            primary.extend((t - tol, t + tol, f) for t, tol in _anchors(f, tolerance))
        elif f.family in SUPPORTING_FAMILIES or f.family == "statistical":
            context.extend((t - tol, t + tol, f) for t, tol in _anchors(f, tolerance))
    primary.sort(key=lambda a: a[0])
    clusters: list[list] = []
    for lo, hi, f in primary:
        if clusters and lo <= clusters[-1][1]:
            clusters[-1][1] = max(clusters[-1][1], hi)
            clusters[-1][2].append(f)
        else:
            clusters.append([lo, hi, [f]])
    for lo, hi, f in context:
        for c in clusters:
            if lo <= c[1] and hi >= c[0]:
                c[2].append(f)
    events = []
    for lo, hi, fs in clusters:
        uniq = {f.finding_id: f for f in fs}
        fams = {f.family for f in uniq.values()}
        local = fams & PRIMARY_FAMILIES
        indep = {fam for fam in local if not (IMPLIED_BY.get(fam, set()) & local)}
        stat = sorted(f.finding_id for f in uniq.values() if f.family == "statistical")
        if not local:
            continue  # supporting/statistical-only clusters are reported per test, not as events
        n = len(indep)
        strength = "strongly_corroborated" if n >= 3 else "corroborated" if n == 2 else "isolated"
        sev = max((f.severity for f in uniq.values()), key=lambda s: SEVERITY_RANK[s])
        events.append(CorrelatedEvent(
            event_id="", time_start=max(0.0, lo), time_end=hi,
            finding_ids=sorted(k for k, f in uniq.items() if f.family != "statistical"),
            families=sorted(fams), independent_families=sorted(indep), statistical_support=stat,
            strength=strength, explanations=_explain(fams), max_severity=sev.value,
        ))
    for i, e in enumerate(events, 1):
        e.event_id = f"EV-{i:03d}"
    return events


def _tests(tests: list[TestResult]) -> dict[str, TestResult]:
    return {t.test_id: t for t in tests}


def assess_global(findings: list[Finding], tests: list[TestResult], container: str, lossy_decoded: bool) -> list[GlobalAssessment]:
    T = _tests(tests)
    ids = lambda tid: [f for f in T[tid].finding_ids] if tid in T else []  # noqa: E731
    det = lambda tid: bool(tid in T and T[tid].detected)  # noqa: E731
    out = []

    # ---- lossy coding history
    if lossy_decoded or container in ("mp3", "mp4", "aac_adts", "ogg"):
        out.append(GlobalAssessment("lossy_coding", "established",
                                    "The file itself is a lossy-coded format; lossy processing is a property of the container, not a finding.",
                                    alternatives=[]))
        if det("D4"):
            out.append(GlobalAssessment("transcoding", "indicated",
                                        "The audio bandwidth is narrower than the current encode explains: an earlier lossy generation or band-limiting preceded it.",
                                        ids("D4"), ["Band-limited original", "Prior resampling"]))
    else:
        holes, cutoff = det("D2"), det("D1")
        if holes and cutoff:
            out.append(GlobalAssessment("lossy_coding", "indicated",
                                        "Spectral holes and a steep band limit together indicate that this lossless file was decoded from a lossy codec at some point.",
                                        ids("D2") + ids("D1"), ["Spectral denoising combined with low-pass filtering"]))
        elif holes:
            out.append(GlobalAssessment("lossy_coding", "possible",
                                        "Spectral holes are present without a band limit; consistent with high-bitrate lossy coding or spectral denoising.",
                                        ids("D2"), ["Spectral noise reduction", "Sparse synthetic content"]))
        elif cutoff:
            out.append(GlobalAssessment("lossy_coding", "possible",
                                        "A steep band limit is present without codec holes; a codec cannot be distinguished from resampling or filtering on this basis.",
                                        ids("D1"), ["Upsampling", "Low-pass filtering"]))
        else:
            out.append(GlobalAssessment("lossy_coding", "not_indicated",
                                        "No band-limit or spectral-hole fingerprint of lossy coding was measured.",
                                        alternatives=["High-bitrate or dithered decodes can leave no measurable fingerprint"]))

    # ---- resampling
    if det("E1") and not det("D2"):
        rates = T["E1"].measurements.get("consistent_source_rates") or []
        out.append(GlobalAssessment("upsampling", "indicated",
                                    "The content stops well below Nyquist with a steep digital edge and no codec holes"
                                    + (f"; consistent with an original rate of {', '.join(map(str, rates))} Hz." if rates else "."),
                                    ids("E1"), ["Low-pass filtering", "Band-limited source"]))
    elif det("E1"):
        out.append(GlobalAssessment("upsampling", "possible",
                                    "The band limit is accompanied by codec holes, so it is more simply explained by lossy coding; upsampling is not separately established.",
                                    ids("E1")))
    else:
        out.append(GlobalAssessment("upsampling", "not_indicated", "No empty band below Nyquist.",
                                    alternatives=["Downsampling and high-quality resampling to a lower rate leave no measurable trace"]))
    if det("E2"):
        out.append(GlobalAssessment("interpolation_trace", "possible",
                                    "Experimental periodic-residual indicator of short-kernel interpolation.", ids("E2"),
                                    ["Tonal or periodic content"]))

    # ---- post-quantisation gain
    if "D3" in T and T["D3"].measurements.get("whole_file_gain_processing"):
        out.append(GlobalAssessment("whole_file_gain_change", "indicated",
                                    "Histogram combing throughout the file: the whole recording was scaled digitally (routine normalisation or volume change).",
                                    [f for f in T["D3"].finding_ids], ["Format conversion with scaling"]))
    if det("D3"):
        q = [f for f in findings if f.test_id == "D3" and f.localization == Localization.REGION]
        if q:
            out.append(GlobalAssessment("digital_gain_change", "indicated",
                                        f"{len(q)} region(s) show histogram combing: sample values were scaled after quantisation.",
                                        [f.finding_id for f in q], ["Normalisation or volume change", "Format conversion with scaling"]))

    # ---- container integrity
    struct_f = [f for f in findings if f.family == "structure" and SEVERITY_RANK[f.severity] >= 2]
    if struct_f:
        worst = max(struct_f, key=lambda f: SEVERITY_RANK[f.severity])
        out.append(GlobalAssessment("container_integrity", "indicated",
                                    f"{len(struct_f)} structural inconsistency(ies); most severe: {worst.title}.",
                                    [f.finding_id for f in struct_f], ["Non-conforming but legitimate software", "Storage/transfer corruption"]))
    else:
        out.append(GlobalAssessment("container_integrity", "not_indicated", "No medium or high severity structural inconsistency."))
    return out
