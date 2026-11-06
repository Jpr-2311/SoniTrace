"""Module A tests: container structure, declared-vs-actual properties and metadata identity."""

from __future__ import annotations

from ..evidence.evidence_model import Category, EvidenceRegistry, Localization, Severity, TestResult
from ..parsers.common import StructureReport
from ..utils.audio_loader import LoadedAudio

ALTERNATIVES = {
    "trailing_data": ["Metadata appended by tagging software after the RIFF structure", "Byte-level concatenation or editing", "Writer bug"],
    "riff_size_exceeds_file": ["Incomplete copy/download or interrupted recording", "Deliberate truncation"],
    "truncated_chunk": ["Incomplete copy/download or interrupted recording", "Deliberate truncation"],
    "unfinalized_riff_size": ["Streaming writer that could not seek back (e.g. FFmpeg writing to a pipe)", "Recording interrupted before the header was finalised"],
    "unfinalized_data_size": ["Streaming writer that could not seek back", "Interrupted recording"],
    "multiple_data_chunks": ["Naive byte-level concatenation of WAV files", "Non-standard writer"],
    "multiple_fmt_chunks": ["Naive byte-level concatenation of WAV files", "Non-standard writer"],
    "byte_rate_mismatch": ["Non-conforming writer", "Hand-edited header"],
    "block_align_mismatch": ["Non-conforming writer", "Hand-edited header"],
    "sample_rate_change": ["Concatenation of separately encoded streams", "Stream capture across a format change"],
    "midstream_vbr_header": ["Byte-level concatenation of two encoded MP3 files", "Some stream rippers"],
    "sync_gap": ["Byte-level edit or concatenation", "Storage/transmission corruption", "Embedded tag"],
    "md5_mismatch": ["Audio frames altered after encoding", "Faulty encoder", "Storage corruption"],
    "ogg_crc_mismatch": ["Bytes altered after the page was written", "Storage/transmission corruption"],
    "ogg_chained_stream": ["Concatenated Ogg files (chained stream)", "Internet-radio capture"],
}
GENERIC_ALTERNATIVES = ["Non-standard but legitimate software behaviour", "Corruption during storage or transfer"]
SEVERITY = {"info": Severity.INFO, "low": Severity.LOW, "medium": Severity.MEDIUM, "high": Severity.HIGH}


def run_container_structure(structure: StructureReport, reg: EvidenceRegistry) -> TestResult:
    test = TestResult("A1", "Container structure and binary consistency", "A: file structure", "structure",
                      score_name="issues of medium/high severity")
    for iss in structure.issues:
        f = reg.add_finding(
            "STR", test_id="A1", module=test.module, method=f"binary parse ({structure.parser})", family="structure",
            category=Category.OBSERVED, severity=SEVERITY.get(iss.severity, Severity.LOW), title=iss.message,
            description=f"[{iss.code}] {iss.message}", localization=Localization.GLOBAL, measurements=iss.details,
            alternative_explanations=ALTERNATIVES.get(iss.code, GENERIC_ALTERNATIVES),
        )
        test.finding_ids.append(f.finding_id)
    serious = [i for i in structure.issues if i.severity in ("medium", "high")]
    test.score = float(len(serious))
    test.detected = bool(serious)
    test.measurements = {"parser": structure.parser, "issue_codes": [i.code for i in structure.issues]}
    test.summary = (f"{len(structure.issues)} structural observation(s), {len(serious)} of medium/high severity."
                    if structure.issues else "Container structure is internally consistent.")
    return test


def run_declared_vs_actual(structure: StructureReport, meta: dict, audio: LoadedAudio, reg: EvidenceRegistry) -> TestResult:
    test = TestResult("A2", "Declared vs. decoded properties", "A: file structure", "metadata", score_name="mismatches")
    checks = []
    d = structure.details
    decoded = audio.duration
    declared = None
    if structure.container == "wav":
        declared = d.get("declared_duration_s")
        fmt = d.get("fmt") or {}
        if fmt.get("channels") and fmt["channels"] != audio.channels:
            checks.append(("channels", fmt["channels"], audio.channels))
    elif structure.container == "flac":
        declared = d.get("declared_duration_s")
    elif structure.container == "mp3":
        declared = d.get("duration_from_frames_s")
    tech = meta.get("technical", {})
    test.measurements = {"decoded_duration_s": decoded, "header_duration_s": declared,
                         "ffprobe_duration_s": tech.get("format_duration_s")}
    if declared:
        tol = 0.05 if structure.container == "mp3" else max(2.0 / audio.sample_rate, 1e-3)
        # MP3 frame counts include encoder delay/padding that gapless decoders trim (< ~0.05 s)
        if abs(declared - decoded) > tol:
            checks.append(("duration_s", round(declared, 4), round(decoded, 4)))
    if tech.get("channels") and tech["channels"] != audio.channels:
        checks.append(("ffprobe_channels", tech["channels"], audio.channels))
    ident = meta.get("identity", {})
    ext_c, real_c = ident.get("container_from_extension"), ident.get("container_from_content")
    if ext_c and real_c and ext_c != real_c:
        f = reg.add_finding(
            "MET", test_id="A2", module=test.module, method="extension vs. magic bytes", family="metadata",
            category=Category.OBSERVED, severity=Severity.MEDIUM,
            title=f"File extension '{ident.get('extension')}' does not match content ({real_c})",
            description=f"The name suggests {ext_c} but the bytes are {ident.get('container_description')}.",
            alternative_explanations=["File renamed by a user or tool", "Software that writes a different container than its extension"],
        )
        test.finding_ids.append(f.finding_id)
    for name, a, b in checks:
        f = reg.add_finding(
            "MET", test_id="A2", module=test.module, method="header vs. decoder cross-check", family="metadata",
            category=Category.OBSERVED, severity=Severity.MEDIUM,
            title=f"Declared {name} ({a}) differs from decoded {name} ({b})",
            description=f"The container declares {name} = {a}, but decoding yields {b}.",
            measurements={"declared": a, "decoded": b},
            alternative_explanations=["Truncated or appended audio data", "Header written by non-conforming software", "Decoder tolerance"],
        )
        test.finding_ids.append(f.finding_id)
    for w in audio.warnings:
        if "non-finite" in w:
            f = reg.add_finding("MET", test_id="A2", module=test.module, method="decoder sanity check", family="metadata",
                                category=Category.OBSERVED, severity=Severity.MEDIUM, title="Non-finite sample values",
                                description=w, alternative_explanations=["Corrupted float data", "Buggy writer"])
            test.finding_ids.append(f.finding_id)
    test.score = float(len(test.finding_ids))
    test.detected = bool(test.finding_ids)
    test.summary = f"{len(test.finding_ids)} mismatch(es)." if test.finding_ids else "Declared and decoded properties agree."
    return test
