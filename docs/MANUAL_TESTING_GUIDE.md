# SonicTrace - Manual Testing Guide

Step-by-step manual tests for beginners. Every command below was executed on Windows 11
(PowerShell 5.1, Python 3.12.5, FFmpeg 7.0.1) and the "Expected output" sections quote
what it actually printed. Because both the dataset generator and the analysis are
deterministic, you should see the same values.

Conventions:

* Run everything in **PowerShell from the project root** (the folder containing
  `pyproject.toml`; `D:\SoniTrace` in the examples).
* The virtual environment must be **activated** (`.\.venv\Scripts\Activate.ps1`), so that
  `python` and `sonictrace` refer to the project's copies.
* After any command, `$LASTEXITCODE` shows its exit code (0 = success).
* Long console tables are shortened with `...` below.

Exit codes you will see: `0` ok, `2` invalid input / option, `3` unsupported format,
`4` malformed or empty file, `5` resource limit, `6` FFmpeg needed but missing,
`1` unexpected internal error.

---

## Test case index

| ID | Area | Needs FFmpeg |
|---|---|---|
| [MT-01](#mt-01-environment-preparation) | environment preparation | no |
| [MT-02](#mt-02-installation) | installation | no |
| [MT-03](#mt-03-dependency-verification) | dependency verification | no |
| [MT-04](#mt-04-starting-the-application) | starting the CLI | no |
| [MT-05](#mt-05-generating-sample-audio) | generating sample audio | optional |
| [MT-06](#mt-06-clean-audio) | clean audio | no |
| [MT-07](#mt-07-manipulated-audio-inserted-silence) | manipulated audio (inserted silence) | no |
| [MT-08](#mt-08-audio-splicing-hard-cut) | audio splicing (hard cut, and a documented miss) | no |
| [MT-09](#mt-09-copy-move-duplicated-segment) | copy-move | no |
| [MT-10](#mt-10-local-gain-edit) | local gain edit | no |
| [MT-11](#mt-11-resampling) | resampling | no |
| [MT-12](#mt-12-lossy-history-inside-a-wav) | lossy history in a WAV | no |
| [MT-13](#mt-13-transcoded-mp3) | transcoded MP3 | **yes** |
| [MT-14](#mt-14-legitimate-processing-false-positive-handling) | legitimate processing / false positives | no |
| [MT-15](#mt-15-metadata-extraction) | metadata extraction | optional |
| [MT-16](#mt-16-binary-structure-inspection) | binary structure inspection | MP3 part only |
| [MT-17](#mt-17-file-comparison) | file comparison | no |
| [MT-18](#mt-18-anomaly-detection-module-f) | anomaly detection (Module F) | no |
| [MT-19](#mt-19-report-generation) | report generation | no |
| [MT-20](#mt-20-json-output) | JSON output | no |
| [MT-21](#mt-21-html-output) | HTML output | no |
| [MT-22](#mt-22-malformed-file) | malformed file | no |
| [MT-23](#mt-23-unsupported-format) | unsupported format | no |
| [MT-24](#mt-24-missing-and-empty-files) | missing and empty files | no |
| [MT-25](#mt-25-resource-limit-and-invalid-option) | resource limit, invalid option | no |
| [MT-26](#mt-26-running-without-ffmpeg) | running without FFmpeg | - |
| [MT-27](#mt-27-automated-tests) | automated tests | optional |
| [MT-28](#mt-28-benchmark) | benchmark | optional |
| [E2E](#final-end-to-end-demonstration) | end-to-end demonstration A-H | no |

---

## MT-01 Environment preparation

| | |
|---|---|
| **Objective** | Confirm a suitable Python is installed. |
| **Prerequisites** | Windows PowerShell open in the project folder. |
| **Command** | `python --version` and `py -0` |
| **Expected output** | `Python 3.11.x` or newer (the project was tested with 3.12.5). `py -0` lists installed versions, e.g. `-V:3.12  Python 3.12 (64-bit)`. |
| **What it means** | Python 3.11+ is available for the virtual environment. |
| **If it fails** | Install Python 3.12 from python.org (tick "Add python.exe to PATH") or `winget install Python.Python.3.12`; reopen PowerShell. If several versions exist, use `py -3.12` in MT-02. |

## MT-02 Installation

| | |
|---|---|
| **Objective** | Create an isolated environment and install SonicTrace with its test dependencies. |
| **Prerequisites** | MT-01 passed; internet access for pip. |
| **Command** | see block below |
| **Expected output** | pip ends with `Successfully installed ... sonictrace-0.1.0 ...`; `pip show sonictrace` prints `Name: sonictrace` / `Version: 0.1.0`. |
| **What it means** | The `sonictrace` command now exists in `.venv\Scripts`. |
| **If it fails** | *"running scripts is disabled"* when activating: run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` (your decision - it changes a PowerShell security setting) or use `.\.venv\Scripts\python.exe` / `.\.venv\Scripts\sonictrace.exe` without activating. pip errors: upgrade pip and retry; check the Python version. |

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pip show sonictrace
```

## MT-03 Dependency verification

| | |
|---|---|
| **Objective** | Check every component SonicTrace uses, including optional FFmpeg. |
| **Prerequisites** | MT-02. |
| **Command** | `sonictrace version` |
| **Expected output** | A table titled `SonicTrace 0.1.0 (methodology 1.2)` with rows `sonictrace 0.1.0`, `methodology_version 1.2`, `python 3.12.5`, `numpy 2.5.4`, `scipy 1.18.1`, `scikit_learn 1.9.1`, `soundfile 0.14.0`, `libsndfile 1.2.2`, `matplotlib 3.11.2`, `ffmpeg ffmpeg version 7.0.1...`, `ffprobe ffprobe version 7.0.1...` (your versions may differ). Exit code 0. |
| **What it means** | All mandatory libraries import correctly. `ffmpeg`/`ffprobe` showing `not found` is acceptable - see MT-26. |
| **If it fails** | `sonictrace` not recognised: the venv is not active (MT-02). Import errors: reinstall with `python -m pip install -e ".[dev]"`. |

## MT-04 Starting the application

| | |
|---|---|
| **Objective** | Confirm the CLI starts and lists its commands. |
| **Prerequisites** | MT-02. |
| **Command** | `sonictrace --help` then `sonictrace analyze --help` |
| **Expected output** | Commands: `analyze`, `report`, `metadata`, `inspect`, `compare`, `benchmark`, `version`, `dataset`; global option `--debug`. `analyze --help` lists `--format/-f`, `--json-out`, `--html-out`, `--no-stats`, `--max-mib`, `--max-duration`. |
| **What it means** | Typer parsed the command definitions. |
| **If it fails** | Same as MT-03. `python -m sonictrace --help` is an equivalent entry point. |

## MT-05 Generating sample audio

| | |
|---|---|
| **Objective** | Create the deterministic test material used by MT-06 to MT-28. |
| **Prerequisites** | MT-02. FFmpeg optional (without it the MP3 conditions are skipped). |
| **Command** | `sonictrace dataset generate` and `python scripts\run_demo.py` |
| **Expected output** | `Generated 140 samples {'calibration': 70, 'evaluation': 70} in datasets\sonictrace_v1 (seed 1337). Manifest: datasets\sonictrace_v1\manifest.json, datasets\sonictrace_v1\manifest.csv` (about 11 s, 69 MB; without FFmpeg fewer files and the message `MP3 conditions skipped ...`). The demo script prints the ground truth, then runs `report`, `analyze` and `compare`; it creates `examples\demo\original.wav`, `examples\demo\manipulated.wav` and `examples\demo\ground_truth.json`. |
| **What it means** | File names encode split, source and condition, e.g. `eva_src01__insert_silence.wav` = evaluation split, source 1, digital silence inserted. `manifest.csv` lists the labels and exact edit times of every file. |
| **If it fails** | Disk space; write permission in the project folder. Re-running is safe: the same seed produces identical files. |

Open `datasets\sonictrace_v1\manifest.csv` in a spreadsheet to see the ground truth
(`edited`, `edit_type`, `edit_times_s`, ...).

## MT-06 Clean audio

| | |
|---|---|
| **Objective** | An unedited recording must not produce local edit indicators. |
| **Prerequisites** | MT-05. |
| **Command** | `sonictrace analyze datasets\sonictrace_v1\audio\eva_src00__clean.wav` |
| **Expected output** | `Local edit indicators: NONE    Structural inconsistencies: NONE`; no "Correlated events" table; the tests table still shows `REPORTED` for C2/C3 (level and spectral changes) and some F tests. Exit code 0. |
| **What it means** | Natural speech onsets are measured (C2/C3) but, by design, cannot create an edit event; statistical F results are context only. |
| **If it fails** | Different values: check the methodology version (`sonictrace version` -> 1.2) and that the dataset was generated with seed 1337. |

## MT-07 Manipulated audio (inserted silence)

| | |
|---|---|
| **Objective** | Detect 0.549 s of digital silence inserted at 3.888 s into a music-like recording with mains hum. |
| **Prerequisites** | MT-05. |
| **Command** | `sonictrace analyze datasets\sonictrace_v1\audio\eva_src01__insert_silence.wav` |
| **Expected output** | `Local edit indicators: STRONG`; events `EV-001 3.808-3.968 corroborated (silence, waveform)` and `EV-002 4.110-4.517 strongly_corroborated (enf, silence, waveform)`; observed evidence `SPL-001 Isolated waveform discontinuity at 3.8884 s`, `SPL-002 ... at 4.4371 s`, `SIL-001 Digital silence of 549 ms at 3.888-4.437 s`, `ENF-001 Mains-hum phase jumps by 1.98 rad near 4.26 s`. |
| **What it means** | Three independent principles agree at the insertion boundaries: exact zeros where the background noise should be, waveform impulses at both edges, and a broken hum phase. |
| **If it fails** | Compare with `manifest.csv` (`eva_src01__insert_silence`: edit times 3.888 and 4.437 s). |

## MT-08 Audio splicing (hard cut)

| | |
|---|---|
| **Objective** | (a) Localise a hard cut; (b) observe a documented limitation. |
| **Prerequisites** | MT-05. |
| **Command (a)** | `sonictrace analyze datasets\sonictrace_v1\audio\eva_src01__cut_hard.wav` |
| **Expected output (a)** | `Local edit indicators: MODERATE`; `EV-001 4.010-4.310 corroborated (enf, waveform)`; `SPL-001 Isolated waveform discontinuity at 4.1840 s`; `ENF-001 Mains-hum phase jumps by 2.75 rad near 4.16 s`. Ground truth: 0.289 s removed at 4.184 s. |
| **Command (b)** | `sonictrace analyze datasets\sonictrace_v1\audio\eva_src00__cut_hard.wav` |
| **Expected output (b)** | `Local edit indicators: NONE` although 0.539 s was removed at 3.723 s. |
| **What it means** | (a) The waveform impulse and the hum-phase step are independent observations of the same cut. (b) This cut lies in a pause of a speech-like recording without hum: background noise joins background noise, so nothing is measurable - an absent indicator is **not** proof of an unedited file. |
| **If it fails** | (a) Check ENF is applicable: the tests table must show `C7 ... completed ... 50 Hz hum present`. |

## MT-09 Copy-move (duplicated segment)

| | |
|---|---|
| **Objective** | Detect a segment pasted from earlier in the same recording. |
| **Prerequisites** | MT-05. |
| **Command** | `sonictrace analyze datasets\sonictrace_v1\audio\eva_src02__copy_overwrite.wav` |
| **Expected output** | `Local edit indicators: STRONG`; two `isolated (duplication)` events (4.854-5.014 and 5.063-5.223); `DUP-001 Segment at 4.93-5.14 s duplicates 1.57-1.78 s`. |
| **What it means** | The waveform match (NCC = 1.0, HIGH severity) is direct evidence of a copy; the level is STRONG because of that HIGH observed finding even though no second family corroborates it. Ground truth: 0.469 s copied from 1.533 s to 4.899 s; pauses split the match into a shorter verified run inside the pasted region. |
| **If it fails** | C6 is skipped for files longer than 180 s; this file is 6 s. |

## MT-10 Local gain edit

| | |
|---|---|
| **Objective** | Detect a +4 dB gain applied to 2.14-3.02 s of a 16-bit file. |
| **Prerequisites** | MT-05. |
| **Command** | `sonictrace analyze datasets\sonictrace_v1\audio\eva_src02__gain_step.wav` |
| **Expected output** | `Local edit indicators: MODERATE`; `QNT-001 Histogram combing in 1.50-3.50 s (digital amplitude scaling after ...)`; processing history `digital_gain_change: indicated - 1 region(s) show histogram combing ...`. |
| **What it means** | After the gain, certain integer sample values occur periodically more or less often (periodicity 34.9 dB). Resolution is the 1 s block size, so the region is wider than the edit. |
| **If it fails** | The test needs an integer PCM file (not a decoded MP3); see MT-14 for the whole-file case. |

## MT-11 Resampling

| | |
|---|---|
| **Objective** | Recognise a 16 kHz recording stored at 44.1 kHz. |
| **Prerequisites** | MT-05. |
| **Command** | `sonictrace analyze datasets\sonictrace_v1\audio\eva_src00__resample_poly.wav` |
| **Expected output** | `Local edit indicators: NONE`; `CMP-001 Content ends abruptly at 7.57 kHz (34 % of Nyquist)`; `RES-001 66 % of the representable band is empty`; `lossy_coding: possible - A steep band limit is present without codec holes ...`; `upsampling: indicated - The content stops well below Nyquist with a steep ...` (consistent with 16000 Hz). |
| **What it means** | Resampling is processing history, not a local edit. Because no codec holes were found, upsampling is the simpler explanation of the band limit. Note: the sample rate itself is never treated as evidence. |
| **If it fails** | Compare `eva_src00__resample_48k.wav`: 44.1 -> 48 kHz upsampling is a known miss (TODO.md). |

## MT-12 Lossy history inside a WAV

| | |
|---|---|
| **Objective** | Detect that a WAV file was decoded from a 64 kbit/s MP3. |
| **Prerequisites** | MT-05 with FFmpeg (the MP3 conditions exist only then). |
| **Command** | `sonictrace analyze datasets\sonictrace_v1\audio\eva_src00__mp3_1gen.wav` |
| **Expected output** | `CMP-001 Content ends abruptly at 16.46 kHz (75 % of Nyquist)`; `CMP-002 3.3 % of time-frequency bins are spectral holes`; `RES-001 25 % of the representable band is empty`; `lossy_coding: indicated - Spectral holes and a steep band limit together ...`; `upsampling: possible - The band limit is accompanied by codec holes ...`. Local level NONE. |
| **What it means** | Two independent codec fingerprints agree, so lossy coding is indicated and upsampling is only "possible". |
| **If it fails** | File missing: the dataset was generated without FFmpeg. |

## MT-13 Transcoded MP3

| | |
|---|---|
| **Objective** | Detect an MP3 whose content is narrower than its own encode explains (64 kbit/s source re-encoded at 192 kbit/s). |
| **Prerequisites** | FFmpeg installed; MT-05. |
| **Command** | `sonictrace analyze datasets\sonictrace_v1\audio\eva_src00__mp3_transcoded.mp3` |
| **Expected output** | Panel line `Audio: 44100 Hz, 1 ch, 6.000 s, FLOAT (decoded by FFmpeg)`; `lossy_coding: established - The file itself is a lossy-coded format ...`; `transcoding: indicated - The audio bandwidth is narrower than the current ...`. |
| **What it means** | Test D4: libmp3lame keeps about 20 026 Hz at 192 kbit/s mono (measured model, because FFmpeg's tag records no low-pass), but the content ends at 16 478 Hz. |
| **If it fails** | Exit code 6 = FFmpeg not found (MT-26). |

## MT-14 Legitimate processing (false-positive handling)

| | |
|---|---|
| **Objective** | See how routine processing is reported without being called an edit. |
| **Prerequisites** | MT-05. |
| **Command 1** | `sonictrace analyze datasets\sonictrace_v1\audio\eva_src00__legit_noise_gate.wav` |
| **Expected output 1** | `Local edit indicators: WEAK`; test C5 `REPORTED` with `15 interior digital-silence run(s) >= 10 ms`. In the JSON/HTML report (e.g. add `--html-out output\gate.html`) the findings include `15 digital-silence runs: systematic gating pattern` (LOW) and every run is LOW, which is why the console's "medium/high" evidence list stays empty. |
| **Command 2** | `sonictrace analyze datasets\sonictrace_v1\audio\eva_src00__legit_normalize.wav` |
| **Expected output 2** | `Local edit indicators: NONE`; processing history `whole_file_gain_change: indicated - Histogram combing throughout the file ...`. |
| **What it means** | Exact zeros and histogram combs are still reported as observed facts, but their pattern (many gate closures; a comb over 100 % of the file) identifies routine processing. These rules came from the false-positive investigation (`research/false_positive_analysis.md`). |
| **If it fails** | Check methodology 1.2; v1.0 reported these files as moderate. |

## MT-15 Metadata extraction

| | |
|---|---|
| **Objective** | View identity, technical metadata, tags and software signatures. |
| **Prerequisites** | MT-05. FFprobe optional. |
| **Commands** | `sonictrace metadata examples\demo\original.wav`; `sonictrace metadata datasets\sonictrace_v1\audio\eva_src00__mp3_transcoded.mp3`; `sonictrace metadata examples\demo\original.wav --json` |
| **Expected output** | WAV: rows `sha256 d20a5c1b35d9...`, `identity.container_from_content wav`, `identity.container_description RIFF/WAVE (or RF64)`, `technical.codec_name pcm_s16le`, `technical.sample_rate 44100`. MP3: `technical.codec_name mp3`, `technical.stream_bit_rate 192000`, `tag.TSSE Lavf61.1.100`, `software Lavc61.3. -> FFmpeg (...)`. `--json` prints a JSON object starting with `{`. |
| **What it means** | Software signatures document the *last* tool that wrote the file (here FFmpeg); they do not prove editing. |
| **If it fails** | Without FFprobe the `technical.*` rows are missing and a yellow note says `FFprobe not found: technical metadata limited to SonicTrace's own parsers.` - expected. |

## MT-16 Binary structure inspection

| | |
|---|---|
| **Objective** | See the container structure parsed by SonicTrace's own parsers. |
| **Prerequisites** | MT-05. |
| **Commands** | `sonictrace inspect examples\demo\original.wav`; `sonictrace inspect datasets\sonictrace_v1\audio\eva_src00__mp3_transcoded.mp3 --json` |
| **Expected output** | WAV: a "RIFF chunks" table with `fmt ` at offset 12 (size 16) and `data` at offset 36 (size 705600), the decoded `fmt` fields (`PCM`, 1 channel, 44100 Hz), and `No structural inconsistencies found.` MP3 JSON: `"frames": 232`, `"bitrate_mode": "CBR"`, a `vbr_header` with `"encoder": "Lavc61.3."` and `"lowpass_hz": 0`, and an empty `issues` list. |
| **What it means** | `inspect` never decodes audio; it shows exactly what the bytes say. A non-empty issue list (e.g. `trailing_data`, `midstream_vbr_header`, `md5_mismatch`, `ogg_crc_mismatch`) would be structural evidence. |
| **If it fails** | The file must exist; `inspect` works without FFmpeg. |

## MT-17 File comparison

| | |
|---|---|
| **Objective** | Locate removed and inserted material against a known original. |
| **Prerequisites** | `python scripts\run_demo.py` has been run (MT-05). |
| **Command** | `sonictrace compare examples\demo\original.wav examples\demo\manipulated.wav --out-dir output\compare` |
| **Expected output** | `identical bytes: False; matched blocks: 84 %; global offset: 0.0 s`; `About 0.352 s of material was removed from the questioned file between 2.00 s and 2.75 s (alignment offset step).`; `About 0.400 s of material was inserted into the questioned file between 3.75 s and 4.75 s (alignment offset step).`; `Block at 4.25 s has no counterpart ... (NCC 0.13)`; `Block at 6.25 s has no counterpart ... (NCC 0.48)`; `Wrote output\compare\comparison.json and output\compare\comparison.png`. |
| **What it means** | Matches the ground truth (0.352 s cut, 0.400 s silence). The pasted copy's source is 5 s away, beyond the +/-2 s search, so it is reported as "no counterpart". Open `output\compare\comparison.png` to see the offset steps. |
| **If it fails** | Order matters: reference first, questioned second. |

## MT-18 Anomaly detection (Module F)

| | |
|---|---|
| **Objective** | Observe the statistical tests and confirm they are separated from evidence. |
| **Prerequisites** | MT-05. |
| **Commands** | `sonictrace analyze examples\demo\original.wav` then `sonictrace analyze examples\demo\original.wav --no-stats` |
| **Expected output** | First run: rows F1-F5 appear (e.g. `F1 ... REPORTED ... 8 of 31 windows exceed |z| > 3.5`, `F2 ... 6 of 31 windows flagged as anomalous by Isolation Forest`, `F5 ... 4 positive delta-BIC point(s)`) while the level is `NONE`. Second run: no F rows; level still `NONE`. |
| **What it means** | Robust z, Isolation Forest, PELT, KS and delta-BIC describe unusual windows relative to the same file. They are never counted as corroboration, so they cannot raise the indicator level. |
| **If it fails** | n/a - F2 needs at least 16 windows (about 4 s of audio) and reports `not_applicable` for shorter files. |

## MT-19 Report generation

| | |
|---|---|
| **Objective** | Produce the full forensic report. |
| **Prerequisites** | MT-05 (demo files). |
| **Command** | `sonictrace report examples\demo\manipulated.wav --out-dir output\reports` |
| **Expected output** | `Local edit indicators: STRONG; structural: NONE`, `HTML report : output\reports\manipulated_report.html`, `JSON report : output\reports\manipulated_report.json`, `Figures     : 6 PNG files in output\reports\manipulated_report_figures`. |
| **What it means** | One command writes all three artefacts; figures are waveform, spectrogram, frequency, rms, noise_floor, timeline. |
| **If it fails** | Write permission for `output\`. |

## MT-20 JSON output

| | |
|---|---|
| **Objective** | Verify machine-readable output. |
| **Prerequisites** | MT-05. |
| **Commands** | `sonictrace analyze examples\demo\manipulated.wav --format json --json-out output\manipulated.json` then `(Get-Content output\manipulated.json -Raw | ConvertFrom-Json).assessment.local_edit_indicators` and `(Get-Content output\manipulated.json -Raw | ConvertFrom-Json).integrity.unchanged` |
| **Expected output** | The first command prints the JSON report to the console (first line `{`) and writes the file. The queries print `strong` and `True`. |
| **What it means** | JSON contains every test, finding, threshold and the integrity check; it can be processed by other tools. Top-level keys: `report_type`, `schema_version`, `generated_utc`, `tool`, `file_identity`, `integrity`, `metadata`, `structure`, `audio`, `signal_summary`, `frequency_distribution`, `assessment`, `global_assessments`, `correlated_events`, `tests`, `findings`, `environment`, `config`, `timing`. |
| **If it fails** | Use `--json-out` rather than `>` redirection when you need a clean UTF-8 file (PowerShell redirection may change the encoding). |

## MT-21 HTML output

| | |
|---|---|
| **Objective** | Generate and view the human-readable report. |
| **Prerequisites** | MT-05. |
| **Commands** | `sonictrace analyze examples\demo\manipulated.wav --html-out output\manipulated.html` then `start output\manipulated.html` |
| **Expected output** | `Wrote output\manipulated.html`; folder `output\manipulated_figures` with 6 PNG files; the browser shows sections 1 Investigation summary ... 11 Final evidence-based assessment plus an appendix. |
| **What it means** | The HTML is self-contained (figures embedded), so it can be archived or shared as one file. |
| **If it fails** | Open the file manually from Explorer. |

## MT-22 Malformed file

| | |
|---|---|
| **Objective** | A file that claims to be WAV but has no audio must fail cleanly. |
| **Prerequisites** | `output` folder exists (created by earlier tests, or `mkdir output`). |
| **Commands** | `Set-Content -Path output\bad.wav -Value "RIFF....WAVEjunk" -NoNewline` then `sonictrace analyze output\bad.wav` and `$LASTEXITCODE` |
| **Expected output** | `Error: libsndfile could not open the file: Error opening 'D:\\SoniTrace\\output\\bad.wav': Error in WAV file. No 'data' chunk marker.` and exit code `4`. No traceback. |
| **What it means** | Malformed input is reported, not crashed on. (`sonictrace inspect output\bad.wav` shows the structural issues the parser found: missing `fmt `/`data`, RIFF size larger than the file.) |
| **If it fails** | A traceback would be a bug - re-run with `sonictrace --debug analyze output\bad.wav` and report it. |

## MT-23 Unsupported format

| | |
|---|---|
| **Objective** | Non-audio content must be rejected with a clear message. |
| **Commands** | `Set-Content -Path output\notes.xyz -Value "this is not audio"` then `sonictrace analyze output\notes.xyz` and `$LASTEXITCODE` |
| **Expected output** | `Error: Unsupported or unrecognised format (content sniffed as 'unknown'). Supported: WAV natively; FLAC/Ogg/AIFF via libsndfile; MP3/AAC/M4A via FFmpeg.` and exit code `3`. |
| **What it means** | The format is decided from the bytes; renaming a text file to `.wav` would be reported as malformed instead. |
| **If it fails** | Report as a bug. |

## MT-24 Missing and empty files

| | |
|---|---|
| **Commands** | `sonictrace analyze output\does_not_exist.wav`; then `New-Item -ItemType File -Path output\empty.wav` and `sonictrace analyze output\empty.wav` |
| **Expected output** | `Error: Input file not found: output\does_not_exist.wav` (exit `2`); `Error: Input file is empty (0 bytes): output\empty.wav` (exit `4`). |
| **What it means** | Input validation happens before anything is read. |
| **If it fails** | `New-Item` fails if `output\empty.wav` already exists - delete it first. |

## MT-25 Resource limit and invalid option

| | |
|---|---|
| **Commands** | `sonictrace analyze examples\demo\original.wav --max-duration 1`; `sonictrace analyze examples\demo\original.wav --format xml` |
| **Expected output** | `Error: Audio duration 8.0 s exceeds the configured limit of 1 s. Raise --max-duration to analyse it.` (exit `5`); `Error: --format must be 'text' or 'json'.` (exit `2`). |
| **What it means** | Limits protect against oversized inputs (defaults 512 MiB, 600 s); bad option values are rejected. |

## MT-26 Running without FFmpeg

| | |
|---|---|
| **Objective** | Confirm the optional-dependency behaviour. |
| **Prerequisites** | MT-05. |
| **Commands** | In a **new** PowerShell window (activate the venv again): `$env:PATH = ($env:PATH -split ';' | Where-Object { $_ -notmatch 'ffmpeg|scoop' }) -join ';'` (affects only this window; adjust the pattern to wherever your FFmpeg lives), then `sonictrace version`, `sonictrace analyze examples\demo\manipulated.wav`, `sonictrace analyze datasets\sonictrace_v1\audio\eva_src00__mp3_transcoded.mp3` |
| **Expected output** | `ffmpeg not found` / `ffprobe not found` in the version table; the WAV analysis works (`STRONG`, exit 0); the MP3 analysis prints `Error: Decoding this format requires FFmpeg, which was not found on PATH. WAV, FLAC and Ogg files can be analysed without FFmpeg.` (exit `6`). |
| **What it means** | FFmpeg is optional; only MP3/AAC/M4A decoding, FFprobe metadata and MP3 dataset conditions need it. |
| **If it fails** | Close the window to restore your PATH. |

## MT-27 Automated tests

| | |
|---|---|
| **Command** | `python -m pytest` |
| **Expected output** | `53 passed, 1 xfailed` (with FFmpeg); without FFmpeg `49 passed, 4 skipped, 1 xfailed`. Duration observed between 22 s and 100 s on the same laptop, depending on machine load. |
| **What it means** | The xfail is `test_44k1_to_48k_upsampling_detected`, which documents a known limitation and is expected to fail. Use `python -m pytest -rxs` to print the reasons for skipped/xfailed tests, `python -m pytest tests\test_cli.py -v` to run one file verbosely. |
| **If it fails** | Read the first failure; ensure the venv is active and dependencies are installed. |

## MT-28 Benchmark

| | |
|---|---|
| **Prerequisites** | MT-05 (complete dataset). |
| **Command** | `sonictrace benchmark --split evaluation --out output\benchmark` |
| **Expected output** | A progress bar over 70 files (about 35 s), a table "Per-technique performance (evaluation, methodology 1.2) - synthetic data only", lines such as `local_edit_level>=moderate: P=0.733 R=0.458 F1=0.564 FPR=0.087` and `lossy_coding indicated/established: P=1.000 R=0.833 F1=0.909 FPR=0.000`, and `Wrote output\benchmark\benchmark_evaluation.md, ...json, ..._per_file.csv`. |
| **What it means** | Each technique is scored against the label it targets, on all files including legitimate processing. These are synthetic numbers, not forensic error rates. `--split calibration` and `--split all` are also available. |
| **If it fails** | `No manifest.json in ...` means MT-05 was not run (exit 2). Without FFmpeg the MP3 conditions are absent and the numbers differ. |

---

## Final end-to-end demonstration

### A. Generate an original audio file

```powershell
python scripts\run_demo.py
```

`scripts/run_demo.py` synthesises an 8 s speech-like recording with a 50 Hz mains-hum
background (`examples\demo\original.wav`). In the same run it also creates the
manipulated copy (step C) and runs `report`, `analyze` and `compare` once; the steps below
repeat those commands individually so you can study each result.

### B. Analyse the original

```powershell
sonictrace analyze examples\demo\original.wav
```

Expected: `SHA-256 d20a5c1b35d90e0adb339d98b35fda538ad87a87ff29dbd209d812cc811fd45d`,
`Evidence unchanged after analysis: yes`, `Local edit indicators: NONE`, and
`C7 ... 50 Hz hum present; phase evolves continuously.`

### C. The manipulated copy

The same script created `examples\demo\manipulated.wav` with three edits; the exact
ground truth is in `examples\demo\ground_truth.json`:

```powershell
Get-Content examples\demo\ground_truth.json
```

1. **cut**: 0.3519 s removed at 2.300 s;
2. **insert_digital_silence**: 0.40 s of exact zeros at 4.10-4.50 s;
3. **copy_overwrite**: 0.5 s copied from 1.0 s and pasted over 6.0-6.5 s.

### D. Analyse the manipulated copy

```powershell
sonictrace analyze examples\demo\manipulated.wav
```

Expected: `Local edit indicators: STRONG`; events `EV-001 2.170-2.470 corroborated (enf,
waveform)`, `EV-002 4.020-4.580 corroborated (enf, silence)`, `EV-003 5.870-6.264
corroborated (duplication, enf)`, `EV-004 6.290-6.630 corroborated (duplication, enf)`;
observed evidence `SIL-001 Digital silence of 400 ms at 4.100-4.500 s`, `DUP-001 Segment at
6.18-6.37 s duplicates 1.18-1.37 s`, `ENF-001 ... 2.13 rad near 2.32 s`, `ENF-002 ... 6.15
rad near 4.30 s`, `ENF-003 ... 0.76 rad near 6.02 s`, `ENF-004 ... 0.65 rad near 6.48 s`.

### E. Compare both files

```powershell
sonictrace compare examples\demo\original.wav examples\demo\manipulated.wav --out-dir output\compare
```

Expected as in MT-17: 0.352 s removed (2.00-2.75 s), 0.400 s inserted (3.75-4.75 s),
two blocks without counterpart (4.25 s = the silence, 6.25 s = the pasted copy).

### F. Generate the forensic report

```powershell
sonictrace report examples\demo\manipulated.wav --out-dir output\reports
```

### G. Inspect the report

```powershell
start output\reports\manipulated_report.html
```

What to look at:

| Section | What you should see |
|---|---|
| 1 Investigation summary | two coloured boxes: local edit indicators STRONG, structural NONE; rationale lines naming the corroborated events |
| 2 File identity | SHA-256 before and after are identical, "Evidence unchanged: YES" |
| 4 Audio characteristics | waveform with shaded events, spectrogram (dark vertical band at 4.1-4.5 s), long-term spectrum without a steep band limit (D1 not reported) |
| 5 Individual tests | all 21 tests with status, score, threshold and summary (C1, C5, C6, C7 REPORTED, plus the supporting C2/C3 and the statistical F tests) |
| 6 Detected anomalies | 6a observed evidence cards (SIL-001, DUP-001, ENF-001..004, SPL-001) with measurements, thresholds, alternative explanations and limitations; 6b statistical anomalies collapsed |
| 7 Suspicious timestamps | table sorted by time + timeline figure, one row per evidence family |
| 8 Evidence correlation | the four events with independent families and explanations; file-level table (lossy coding, upsampling, container integrity: not indicated) |
| 9-11 | false-positive considerations, limitations, final assessment with the "What cannot be concluded" list |

The JSON twin is `output\reports\manipulated_report.json`.

### H. Which findings are meaningful and which are inconclusive

| Finding | Meaningful? | Why |
|---|---|---|
| EV-001 (2.17-2.47 s): C1 impulse at 2.300 s + hum phase jump 2.13 rad | **yes - corroborated** | two independent principles agree exactly at the cut (truth 2.300 s) |
| SIL-001: 400 ms exact zeros at 4.10-4.50 s, background around it -44.6 dBFS | **yes - observed fact** | a microphone cannot record exact zeros while the room is noisy; corroborated by the hum-phase jump ENF-002 |
| DUP-001: 6.18-6.37 s duplicates 1.18-1.37 s, NCC 1.0 | **yes - observed fact** | sample-exact repetition; corroborated by ENF-003/ENF-004 at the paste boundaries |
| compare: 0.352 s removed, 0.400 s inserted | **yes** (with a trusted reference) | matches the ground truth to the millisecond |
| C2/C3 level and spectral jumps | inconclusive | occur at every natural onset; context only |
| F1-F5 statistical anomalies | inconclusive | unusual windows relative to the same file, not evidence |
| compare "no counterpart" at 6.25 s | partially | says the block is not in the reference within +/-2 s, not where it came from (C6 answers that) |
| What cannot be concluded | - | authenticity, intent, synthetic speech, the number of encodes, downsampling, real-world error rates - and that an unflagged file is unedited |

Interview tip: present the corroborated events, then immediately name one innocent
explanation each test lists (click, noise gate, loop) and how the correlation rules
handle it.
