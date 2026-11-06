# SonicTrace - Project Completion Report

Date: 2026-11-06. Version 0.1.0, methodology 1.2. Platform used for all runs: Windows 11,
Python 3.12.5 (venv), NumPy 2.5.4, SciPy 1.18.1, scikit-learn 1.9.1, soundfile 0.14.0,
matplotlib 3.11.2, Typer 0.28.0, FFmpeg/FFprobe 7.0.1.

## 1. Implemented features

**CLI** `sonictrace`: `analyze`, `report`, `metadata`, `inspect`, `compare`,
`dataset generate`, `benchmark`, `version`; text and JSON output, progress bars, distinct
exit codes, no tracebacks for expected errors (malformed, unsupported, missing, empty,
over-limit inputs are tested).

**Module A - file structure (binary parsers written from the specifications)**
RIFF/WAVE/RF64 chunk walker (fmt/extensible, data, fact, LIST-INFO, bext/CodingHistory,
ds64; trailing data, truncation, duplicate chunks, header field consistency, pad bytes);
MPEG audio frame walker (ID3v2/v1, APE, frame headers, Xing/Info/VBRI, LAME tag with
lowpass and encoder delay/padding, sample-rate/version/channel changes, sync gaps,
mid-stream VBR headers = concatenation); FLAC (STREAMINFO, Vorbis comments, **MD5 of
decoded PCM verified against STREAMINFO**); Ogg (page CRC-32 verification, sequence gaps,
granule regression, chained streams, Vorbis/Opus headers and vendor); MP4/M4A box tree
(mvhd/mdhd times, stsd codec, ilst tags); ADTS; AIFF; magic-byte sniffing vs extension;
FFprobe metadata; software-signature classification; SHA-256.

**Module B - signal analysis**: RMS, peak, true peak, crest factor, DC offset, clipping
runs, ZCR, STFT, spectral centroid/bandwidth/roll-off/flatness/flux, own mel filterbank
and MFCC, Welch LTAS, band-energy distribution, band-limit characterisation,
minimum-statistics noise floor and SNR.

**Detectors (21 tests)**: A1 container structure, A2 declared vs decoded;
C1 LPC-residual impulses, C2 energy, C3 spectral discontinuity, C4 noise-floor
consistency, C5 digital silence/padding (+ gating pattern), C6 copy-move duplication
(self-similarity + waveform NCC), C7 ENF hum-phase continuity; D1 band limit, D2 spectral
holes, D3 bit depth + histogram combing (local vs whole-file), D4 codec lowpass/bitrate
consistency (LAME tag, or - v1.2 - a measured libmp3lame low-pass model when FFmpeg's tag
records none) + explicit "generations cannot be established"; E1 empty band with candidate
source rates, E2 interpolation periodicity (experimental), E3 sample-rate metadata
consistency; F1 robust z/MAD, F2 Isolation Forest, F3 PELT, F4 KS windows, F5 delta-BIC.

**Module G**: Finding model (ID, test, method, family, category, severity, time and sample
range, measurements, baseline/threshold, alternatives, limitations, supporting evidence);
temporal correlation with independence rules; file-level processing-history assessments;
ordinal indicator levels; false-positive considerations; cannot-conclude list.

**Reference comparison**: block NCC alignment -> removed/inserted material, unmatched
blocks, gain changes, bandwidth differences, figure.

**Reporting**: JSON report; self-contained HTML report with the 11 required sections;
figures: waveform, spectrogram, LTAS/frequency, RMS timeline, noise floor, suspicious-region
timeline, comparison.

**Dataset**: deterministic generator, 140 files (70 calibration / 70 evaluation,
source-disjoint), 18 condition types incl. 4 legitimate-processing probes and controls,
manifest with labels, edit times, transformation logs, hashes.

**Integrity**: read-only access, SHA-256 before/after (all 140 benchmark files verified
unchanged), private temp dirs for FFmpeg, resource limits, deterministic output,
tool/dependency versions in every report.

## 2. Architecture

See README "Architecture". Data flow: validate -> hash -> sniff -> binary parse ->
FFprobe -> decode (read-only) -> shared AnalysisContext (frames, STFT, MFCC, LTAS,
band limit) -> 21 isolated tests -> EvidenceRegistry -> correlation -> assessment ->
re-hash -> JSON/HTML/figures.

## 3. Tests executed

Command: `python -m pytest` -> **54 collected: 53 passed, 0 failed, 1 xfailed** (22-100 s
depending on machine load; final audit run: 99.9 s). Without FFmpeg: 49 passed, 4 skipped,
1 xfailed.
The xfail (`test_44k1_to_48k_upsampling_detected`) documents a known limitation of E1 and
is not counted as a pass.

## 4. Benchmark results (synthetic data only - not real-world accuracy)

Held-out evaluation split, methodology 1.2 (full tables: `research/benchmark_v1.2_evaluation.md`;
identical to v1.1 except the D4 and transcoding rows):

| Decision | P | R | FPR |
|---|---|---|---|
| local edit level >= moderate | 0.733 | 0.458 | 0.087 |
| local edit level >= strong | 0.667 | 0.167 | 0.043 |
| lossy coding indicated/established | 1.000 | 0.833 | 0.000 |
| D2 spectral holes | 1.000 | 0.833 | 0.000 |
| D1 band limit | 0.833 | 0.833 | 0.034 |
| D3 local gain edit | 1.000 | 0.500 | 0.000 |
| D4 transcoded MP3 / transcoding indicated (not fully blind, see section 5 item 6) | 1.000 | 0.500 | 0.000 |
| C1 waveform discontinuity | 0.778 | 0.292 | 0.043 |
| C6 duplication | 0.667 | 0.167 | 0.043 |
| C7 ENF phase | 1.000 | 0.125 | 0.000 |
| E1 empty band (raw) vs upsampling indicated (correlated) | 0.167 vs 0.500 | 0.167 vs 0.167 | 0.172 vs 0.034 |
| C2 energy jumps / F2 Isolation Forest / F5 delta-BIC | 0.343 | 1.000 | 1.000 |

Per edit type at level >= moderate (n = 4 each): inserted silence 4/4, copy-overwrite 3/4,
gain step 2/4, hard cut 1/4, background splice 1/4, crossfaded cut 0/4. The single
background splice at >= moderate reached that level through a coincidental C6 duplicate in
hum-dominated pauses (NCC 0.9802), which also counts as one of C6's four true positives -
found during the documentation audit (`research/false_positive_analysis.md`, FP-6).

## 5. Actual experimental findings

1. v1.0 -> v1.1 (calibration): FPR of level >= moderate 0.304 -> 0.087, FPR of
   level >= weak 1.000 -> 0.283, after three justified changes (energy/spectral jumps made
   supporting-only; whole-file histogram comb = processing; noise-gate pattern rule).
2. Multi-layer correlation measurably helps: codec low-passes make E1 alone produce
   FPR 0.172; conditioning on absent codec holes gives 0.034.
3. Directly observed fingerprints (codec holes, exact digital silence, verified
   duplicates, histogram combs, hum-phase jumps) are precise; continuity-preserving edits
   (crossfades, cuts inside pauses) are largely invisible.
4. Unsupervised anomaly detectors flag most or all unedited files; they are reported but
   excluded from corroboration.
5. Bugs/failed experiments found by the benchmark and fixed or documented: C6 0 % recall
   (activity rule, frame grid), band-limit cutoff at stopband edge, uninformative mono
   128 kbit/s MP3 condition, E1 blind to 44.1->48 kHz.
6. v1.2: FFmpeg-written MP3 tags record a low-pass of 0, so D4 could never fire. 56
   libmp3lame encodes of noise (`scripts/verify_lame_lowpass.py`) gave a measured low-pass
   model (mono ~1.5x stereo, ~20 kHz ceiling; remembered source-code values for stereo
   64-96 kbit/s did not match and were not used). D4 recall on transcoded MP3s 0 -> 0.5,
   0 false positives; misses are first generations with a gradual band edge. Disclosure:
   the gap was noticed on an evaluation-split file, so the D4 evaluation numbers are not
   fully blind (`research/experiments.md`, E4).

## 6. Limitations

`research/limitations.md`. Key: synthetic benchmark only, small n; no synthetic-speech
detection; crossfaded edits; downsampling undetectable; generation counting not
implemented; loops and noise gates produce genuine observations needing context.

## 7. Outstanding issues

`TODO.md`: 44.1->48 kHz upsampling, MDCT double-compression, aliasing indicators,
stereo-specific tests, crossfade detection, noise-gate rule refinement, confidence
intervals, real-recording validation, faster Ogg CRC, deeper AAC/MP4 analysis.

## 8. Exact commands to reproduce

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
sonictrace dataset generate --out datasets/sonictrace_v1 --seed 1337
sonictrace benchmark --dataset datasets/sonictrace_v1 --split calibration --out output/benchmark_v1.2
sonictrace benchmark --dataset datasets/sonictrace_v1 --split evaluation --out output/benchmark_v1.2
python scripts/verify_lame_lowpass.py
python scripts/run_demo.py
sonictrace report examples/demo/manipulated.wav --out-dir output/reports
sonictrace compare examples/demo/original.wav examples/demo/manipulated.wav --out-dir output/compare
```
(`scripts/reproduce.ps1` / `scripts/reproduce.sh` run the same sequence.)

## 9. Final quality gate

| Check | Status | Evidence |
|---|---|---|
| Project installs | yes | `pip install -e ".[dev]"` in a clean Python 3.12 venv |
| CLI starts | yes | `sonictrace --help`, `sonictrace version` |
| WAV parsing | yes | tests/test_parsers.py (6 WAV tests incl. malformed) |
| Metadata extraction | yes | `sonictrace metadata`, test_cli |
| Signal analysis | yes | tests/test_analysis.py |
| Splice investigation | yes | tests/test_splicing.py, benchmark C1-C7 |
| Resampling investigation | yes, with documented gap | tests/test_resampling.py (3 pass, 1 xfail) |
| Compression analysis | yes | D1/D2 evaluation P 0.83/1.00; D4 transcoding P 1.00 R 0.50 (tests/test_compression.py) |
| Evidence correlation | yes | tests/test_evidence.py, demo events |
| Dataset generation | yes | 140 files, bit-reproducible (test_dataset) |
| Benchmark execution | yes | `output/benchmark_v1.2/`, `research/benchmark_v1.2_*.md` (v1.0/v1.1 tables kept) |
| HTML report | yes | `examples/demo/reports/*_report.html` |
| JSON report | yes | `examples/demo/reports/*_report.json` |
| Visualisations | yes | `examples/demo/reports/*_figures/` (6 PNG each), `examples/demo/compare/comparison.png` |
| Tests execute | yes | 53 passed, 1 xfailed, 0 failed |
| README instructions | yes | every command in README and the manual testing guide was executed (scripted run, exit codes checked) |
| No fabricated performance claims | yes | all numbers copied from generated benchmark files |
| No empty placeholders | yes | every module implements working functionality |
| Original inputs unmodified | yes | before/after SHA-256 + mtime check in every report; benchmark: all unchanged |
| No API keys / secrets | yes | audit: no keys, tokens, `.env`, environment-variable reads or network code (`KEYS_AND_SETUP_GUIDE.md`) |

## 10. Documentation and final audit

Deliverables:

| File | Content |
|---|---|
| `README.md` | full project README (overview, techniques, stack, architecture diagram, folder structure, Windows installation, every CLI command, actual example output, report structure, benchmark, tests, limitations, security, contributing) |
| `KEYS_AND_SETUP_GUIDE.md` | API-key/secret/environment/network audit, PowerShell setup, mandatory vs optional dependencies, verified behaviour without FFmpeg |
| `docs/INTERNAL_WORKING.md` | fundamentals, technology stack, every module, every algorithm with maths and real examples, `analyze` execution trace with flowchart, decision rules, applications, 34 interview Q&As, 2- and 5-minute explanations |
| `docs/MANUAL_TESTING_GUIDE.md` | 28 manual test cases (ID, objective, prerequisites, command, expected output, meaning, troubleshooting) + end-to-end demonstration A-H |
| `docs/PROJECT_WORKFLOW.md` | workflow, architecture, module-interaction, data-flow, evidence and report diagrams, CLI reference, I/O, dependency map, troubleshooting, one-page quick reference |

Audit results:

* **Keys and services:** none required. No environment variables or `.env` files are read;
  no network libraries are imported; the only subprocesses are FFmpeg/FFprobe (local) and
  `scripts/run_demo.py` calling the CLI.
* **Verified behaviour:** all documented commands were executed in PowerShell, including
  every error path (exit codes 2, 3, 4, 5, 6), and the suite was also run with FFmpeg
  removed from `PATH`: 49 passed, 4 skipped, 1 xfailed.
* **Documentation-level code fixes (no behaviour change):** help strings for
  `report --max-mib/--max-duration` and the `metadata`/`inspect` file arguments; an outdated
  comment in `engine.py` (cache reuse) and an outdated docstring in
  `evidence/correlation.py` (supporting-only `short_time` family).
* **New finding disclosed:** FP-6 (coincidental C6 duplicate in hum-dominated pauses),
  added to `research/false_positive_analysis.md`, `research/experiments.md` and `TODO.md`.
* **Mermaid diagrams:** 12 diagrams; structure linted locally (quotes, brackets,
  subgraph/end balance, sequence syntax). They were not rendered with an external service.
* **Final test run:** see section 3 (54 collected: 53 passed, 1 xfailed).
