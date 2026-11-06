# SonicTrace - Keys, Environment and Setup Guide

This guide is based on an audit of the actual code (SonicTrace 0.1.0, methodology 1.2).
Every behaviour described under "verified" was executed on Windows 11 with Python 3.12.5.

---

## 1. Does the project require API keys?

**No. This project does not require API keys or paid API subscriptions.**

What the audit checked (all of `src/`, `tests/`, `scripts/`, `pyproject.toml`,
`requirements.txt`):

| Checked for | Result |
|---|---|
| API keys, tokens, secret keys, passwords, credentials | none in code, configuration or data files |
| `.env`, `.env.example`, `*.ini`, `*.cfg`, `*.yaml` files | none exist; nothing reads them |
| Environment variables (`os.environ`, `os.getenv`) | **never read** by SonicTrace |
| Network libraries (`requests`, `urllib`, `http.client`, `socket`, `httpx`) | not imported anywhere |
| URLs / web services / cloud SDKs | none |
| Databases or external servers | none (all results are local files) |
| Third-party accounts or paid services | none |
| Subprocess calls | only `ffmpeg` / `ffprobe` (local programs) through `src/sonictrace/utils/tools.py`, and `scripts/run_demo.py`, which calls the `sonictrace` CLI itself |

Audio never leaves your computer. The only time the internet is needed is to download
Python packages (`pip install`) and, optionally, FFmpeg.

## 2-5. Required keys, where to obtain them, where to put them

Not applicable - there are no keys. Nothing needs to be obtained, stored or placed
anywhere.

## 6. Windows PowerShell setup commands

Run these from the project folder (`D:\SoniTrace` in the examples below; use your own path).

```powershell
# 1. Check Python (3.11 or newer is required; 3.12 is what the project was tested with)
python --version
# if several versions are installed, the Windows launcher can pick one:
py -0
```

```powershell
# 2. Create and activate a virtual environment
cd D:\SoniTrace
py -3.12 -m venv .venv          # or: python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If activation fails with *"running scripts is disabled on this system"*, either allow
local scripts for your user account (this changes a PowerShell security setting - your
decision):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

or skip activation and call the venv programs directly, e.g.
`.\.venv\Scripts\python.exe -m pip ...` and `.\.venv\Scripts\sonictrace.exe ...`.

```powershell
# 3. Install SonicTrace and its dependencies (editable install, with the test extra)
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

```powershell
# 4. Optional: install FFmpeg (needed only for MP3/AAC/M4A input and MP3 dataset conditions)
winget install --id Gyan.FFmpeg -e      # or: scoop install ffmpeg   /   choco install ffmpeg
# open a NEW PowerShell window afterwards so PATH is refreshed, then:
ffmpeg -version
ffprobe -version
```

Manual alternative: download a static build from <https://ffmpeg.org/download.html>,
unzip it (e.g. to `C:\ffmpeg`) and add `C:\ffmpeg\bin` to your user PATH
(Settings -> System -> About -> Advanced system settings -> Environment Variables).

## 7. `.env` configuration examples

SonicTrace reads **no** `.env` file and **no** environment variables, so there is nothing
to configure this way. Creating a `.env` file has no effect.

The only environment setting that matters is the operating system's `PATH`, because
SonicTrace finds FFmpeg with `shutil.which("ffmpeg")` / `shutil.which("ffprobe")`.

Configuration that *does* exist:

| What | Where | How to change |
|---|---|---|
| Input size limit (default 512 MiB) | `AnalysisConfig.max_file_bytes` | `--max-mib` on `analyze` / `report` |
| Duration limit (default 600 s) | `AnalysisConfig.max_duration_s` | `--max-duration` on `analyze` / `report` |
| Skip statistical Module F | - | `--no-stats` on `analyze` |
| Tracebacks for unexpected errors | - | global `--debug` (before the command) |
| All detection thresholds | `src/sonictrace/config.py` (`AnalysisConfig`) | edit the dataclass defaults (every report records the values used in its `config` section) |

Console encoding: not needed. Output redirected to a file falls back to ASCII table
borders automatically (verified: `sonictrace version > out.txt` works without setting
`PYTHONIOENCODING`).

## 8. How to verify the setup

```powershell
sonictrace version
```

Expected (verified): a table listing `sonictrace 0.1.0`, `methodology_version 1.2`,
Python, NumPy, SciPy, scikit-learn, soundfile, libsndfile, matplotlib, and either an
FFmpeg/FFprobe version string or `not found`.

```powershell
python -m pytest
```

Expected (verified): `53 passed, 1 xfailed` with FFmpeg installed;
`49 passed, 4 skipped, 1 xfailed` without FFmpeg (the 4 skipped tests need FFmpeg; the
xfail documents a known limitation).

```powershell
python scripts\run_demo.py
```

Expected: creates `examples\demo\original.wav` and `examples\demo\manipulated.wav`, and
reports `Local edit indicators: NONE` for the original and `STRONG` for the manipulated
copy.

## 9. Mandatory versus optional dependencies

| Component | Mandatory? | Purpose | Installed by |
|---|---|---|---|
| Python >= 3.11 | **yes** | runtime | you |
| numpy >= 1.26 | **yes** | arrays, FFT, statistics | `pip install -e .` |
| scipy >= 1.11 | **yes** | filters, Welch PSD, resampling, Toeplitz solve, KS test, DCT | `pip install -e .` |
| soundfile >= 0.12 (bundles libsndfile) | **yes** | read/write WAV, FLAC, Ogg, AIFF | `pip install -e .` |
| scikit-learn >= 1.3 | **yes** | Isolation Forest (test F2) | `pip install -e .` |
| matplotlib >= 3.8 | **yes** | report figures | `pip install -e .` |
| typer >= 0.12 | **yes** | command-line interface | `pip install -e .` |
| rich >= 13 | **yes** | console tables, progress bars | `pip install -e .` |
| pytest >= 8 | optional (tests only) | automated tests | `pip install -e ".[dev]"` |
| FFmpeg / FFprobe | optional | decode MP3/AAC/M4A; FFprobe metadata; MP3 dataset conditions; `scripts/verify_lame_lowpass.py` | you (section 6) |

Versions used for all documented runs: numpy 2.5.4, scipy 1.18.1, soundfile 0.14.0
(libsndfile 1.2.2), scikit-learn 1.9.1, matplotlib 3.11.2, typer 0.28.0, rich 15.0.0,
pytest 9.2.0, FFmpeg 7.0.1. librosa is **not** used (mel filterbank and MFCC are
implemented directly with NumPy/SciPy). Click is not a direct dependency (Typer 0.28 does
not install it).

On Linux, if `import soundfile` fails because libsndfile is missing, install the system
library (Debian/Ubuntu: `sudo apt install libsndfile1`).

## 10. What works offline

Everything. No feature contacts the network: analysis, reports, comparison, dataset
generation, benchmarking and tests all run offline once the packages are installed.

## 11. External software that must be installed manually

* **Python 3.11+** - always.
* **FFmpeg** (includes FFprobe) - only if you want MP3/AAC/M4A input, FFprobe metadata,
  the MP3 conditions of the synthetic dataset, or the LAME low-pass verification script.

Nothing else (no database, server, GPU driver or account).

## 12. Running without the optional dependencies

Verified with FFmpeg removed from `PATH`:

| Action | Result without FFmpeg |
|---|---|
| `sonictrace version` | works; ffmpeg/ffprobe shown as `not found` |
| `sonictrace analyze file.wav` (also FLAC/Ogg/AIFF) | works, exit code 0 |
| `sonictrace metadata file.wav` | works; prints `FFprobe not found: technical metadata limited to SonicTrace's own parsers.` |
| `sonictrace analyze file.mp3` | stops with exit code 6: `Error: Decoding this format requires FFmpeg, which was not found on PATH. WAV, FLAC and Ogg files can be analysed without FFmpeg.` |
| `sonictrace dataset generate` | works; MP3 conditions are skipped automatically (`MP3 conditions skipped (FFmpeg unavailable or --no-mp3).`); `--no-mp3` forces the same |
| `sonictrace benchmark` | works on a dataset generated without MP3 conditions |
| `python -m pytest` | 49 passed, 4 skipped, 1 xfailed |
| `python scripts\verify_lame_lowpass.py` | requires FFmpeg |

Without pytest you can still use every CLI command; only `python -m pytest` needs it.

---

**Security note.** Because no secrets exist in this project, none are exposed in the
documentation or reports. Reports do contain the analysed file's absolute path, size,
SHA-256 and filesystem timestamps - treat reports of real evidence as sensitive.
