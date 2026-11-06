# Experiments

All runs: dataset `datasets/sonictrace_v1` generated with seed 1337 (`sonictrace dataset
generate`), 140 files = 70 calibration + 70 evaluation, 6 s each, 44.1 kHz/16-bit
(48 kHz for one control and the 44.1->48 kHz condition). Environment: Python 3.12.5,
NumPy 2.5.4, SciPy 1.18.1, scikit-learn 1.9.1, soundfile 0.14.0, FFmpeg 7.0.1 (gyan.dev
full build, libmp3lame). Full tables: `benchmark_v1.0_calibration.md`,
`benchmark_v1.1_calibration.md`, `benchmark_v1.1_evaluation.md`, `benchmark_v1.2_calibration.md`,
`benchmark_v1.2_evaluation.md`.

> Synthetic data only. None of these numbers is a real-world forensic error rate.

## E1  Methodology v1.0 on calibration (baseline)

| Decision | Precision | Recall | FPR |
|---|---|---|---|
| local edit level >= weak | 0.343 | 1.000 | **1.000** |
| local edit level >= moderate | 0.533 | 0.667 | 0.304 |
| local edit level >= strong | 1.000 | 0.208 | 0.000 |
| C6 duplication | - | **0.000** | 0.000 |
| D3 gain comb (vs. gain_edit) | 0.250 | 0.250 | 0.045 |

Findings: energy/spectral jumps fired on every file; noise gate, normalisation and loops
produced false positives; C6 found no copies (bug); mono 128 kbit/s MP3 was undetectable
(D1/D2 recall 0, dataset design problem). See `false_positive_analysis.md`.

## E2  Methodology v1.1 on calibration (after the FP investigation)

| Decision | Precision | Recall | FPR |
|---|---|---|---|
| local edit level >= weak | 0.567 | 0.708 | 0.283 |
| local edit level >= moderate | 0.765 | 0.542 | **0.087** |
| local edit level >= strong | 0.667 | 0.167 | 0.043 |
| lossy coding indicated | 1.000 | 0.833 | 0.000 |
| upsampling indicated | 1.000 | 0.250 | 0.000 |
| D3 local gain edit | 1.000 | 0.250 | 0.000 |

## E3  Methodology v1.1 on evaluation (held-out sources; afterwards only D4 changed, see E4)

Per technique (label in parentheses; all 70 files are scored, including legitimate processing):

| Test | P | R | F1 | FPR |
|---|---|---|---|---|
| C1 LPC residual impulse (edited) | 0.778 | 0.292 | 0.424 | 0.043 |
| C2 energy jump (edited) | 0.343 | 1.000 | 0.511 | 1.000 |
| C3 spectral jump (edited) | 0.348 | 1.000 | 0.516 | 0.978 |
| C4 noise floor (edited) | 0.600 | 0.125 | 0.207 | 0.043 |
| C5 digital silence (edited) | 0.571 | 0.167 | 0.258 | 0.065 |
| C6 duplication (edited) | 0.667 | 0.167 | 0.267 | 0.043 |
| C7 ENF phase (edited) | 1.000 | 0.125 | 0.222 | 0.000 |
| D1 band limit (compressed) | 0.833 | 0.833 | 0.833 | 0.034 |
| D2 spectral holes (compressed) | 1.000 | 0.833 | 0.909 | 0.000 |
| D3 histogram comb (gain_edit) | 1.000 | 0.500 | 0.667 | 0.000 |
| D4 codec consistency, v1.2 (transcoded_mp3) | 1.000 | 0.500 | 0.667 | 0.000 |
| E1 empty band (resampled) | 0.167 | 0.167 | 0.167 | 0.172 |
| E2 periodicity, experimental (resampled) | 0.500 | 0.333 | 0.400 | 0.069 |
| F1 robust z (edited) | 0.417 | 0.625 | 0.500 | 0.457 |
| F2 Isolation Forest (edited) | 0.343 | 1.000 | 0.511 | 1.000 |
| F3 PELT (edited) | 0.458 | 0.458 | 0.458 | 0.283 |
| F4 KS windows (edited) | 0.433 | 0.542 | 0.481 | 0.370 |
| F5 delta-BIC (edited) | 0.343 | 1.000 | 0.511 | 1.000 |

Correlated (multi-layer) decisions:

| Decision | TP | FP | TN | FN | Precision | Recall | FPR |
|---|---|---|---|---|---|---|---|
| local edit level >= weak | 13 | 7 | 39 | 11 | 0.650 | 0.542 | 0.152 |
| local edit level >= moderate | 11 | 4 | 42 | 13 | 0.733 | 0.458 | 0.087 |
| local edit level >= strong | 4 | 2 | 44 | 20 | 0.667 | 0.167 | 0.043 |
| lossy coding indicated/established | 10 | 0 | 58 | 2 | 1.000 | 0.833 | 0.000 |
| upsampling indicated | 2 | 2 | 56 | 10 | 0.500 | 0.167 | 0.034 |
| digital gain change indicated | 2 | 0 | 66 | 2 | 1.000 | 0.500 | 0.000 |
| transcoding indicated (v1.2) | 2 | 0 | 66 | 2 | 1.000 | 0.500 | 0.000 |

Confusion of the local-edit level against ground truth (evaluation):

| Level | edited | not edited |
|---|---|---|
| none | 11 | 39 |
| weak | 2 | 3 |
| moderate | 7 | 2 |
| strong | 4 | 2 |

Detection at level >= moderate per edit type (evaluation, n = 4 each): insert_silence 4/4,
copy_overwrite 3/4, gain_step 2/4, cut_hard 1/4, noise_env_splice 1/4, cut_crossfade 0/4.
Caveat found during the documentation audit: the single noise_env_splice file at
>= moderate got there through a coincidental C6 duplicate in hum-dominated pauses
(NCC 0.9802), not through its C4 background event (`false_positive_analysis.md`, FP-6).
Non-edited files at >= moderate: legit_loop 2/2, legit_noise_gate 2/4; all clean, control,
added-noise, normalised, MP3 and resampled files stayed below moderate.

## E4  D4 transcoding cross-check without a recorded low-pass (methodology v1.2)

**Problem found while running the tool:** FFmpeg's MP3 muxer writes the LAME-style Info tag
with encoder "Lavc61.3." and a low-pass byte of 0. D4 compared the measured band limit with
the tag's low-pass only, so it could never fire on FFmpeg-written MP3s (v1.1: D4 recall 0).
Disclosure: the gap was noticed while running the CLI on an evaluation-split file
(`eva_src00__mp3_transcoded.mp3`). The fix is grounded in a separate measurement on noise
(below), its 85 % margin is the pre-existing v1.0 value, and nothing was tuned on dataset
files - but the D4 evaluation numbers are not fully blind.

**Measurement:** `scripts/verify_lame_lowpass.py` encoded Gaussian noise with libmp3lame at
all 14 MPEG-1 Layer III CBR bitrates, mono and stereo, at 44.1 and 48 kHz (56 encodes) and
measured the -6 dB band limit (`research/lame_lowpass_verification.md`). Observations:
every tag recorded low-pass 0; mono cutoffs are about 1.5x the stereo cutoff at the same
bitrate (e.g. 44.1 kHz, 64 kbit/s: mono 16 505 Hz, stereo 8 979 Hz) and saturate at about
20.0 kHz (44.1 kHz) / 20.3 kHz (48 kHz) from 80 kbit/s mono; 5 of 56 configurations
(stereo 56/64 kbit/s at 44.1 kHz; 56/80/96 kbit/s at 48 kHz) had no steep edge and are
excluded from the model. The values I remembered from LAME's source for stereo 64-96 kbit/s
(11-15 kHz) did **not** match these measurements, so the model uses measured values only
(`src/sonictrace/data/lame_cbr_cutoffs.json`, written by the script).

**Change (v1.2):** if the tag records no low-pass and the file is CBR, MPEG-1 Layer III,
LAME/Lavc-tagged, at a measured configuration, D4 uses the measured cutoff as the expected
bandwidth; it flags a steep measured band limit below 85 % of it (finding severity LOW,
since the expectation is a model, MEDIUM when the tag records the value). Benchmark label
for D4 corrected from `compressed` (incl. WAV decodes D4 cannot examine) to the derived
`transcoded_mp3` (MP3 container, >= 2 generations).

**Result (both splits identical):** D4 TP 2, FP 0, TN 66, FN 2 (P 1.000, R 0.500); every
other number in the v1.2 tables is identical to v1.1. The two misses per split are the
tonal sources: their first-generation encode leaves a *gradual* edge (e.g. eva_src01:
measured cutoff 14 869 Hz = 74 % of the expected 20 026 Hz, but transition 5 265 Hz >
0.30 x cutoff), and D4 deliberately keeps D1's steepness requirement so that natural
high-frequency roll-off in a single encode is not reported as transcoding.

## Interpretation

1. **Correlation reduces false positives of weak single detectors.** The clearest case is
   resampling: E1 alone has FPR 0.172 because codec low-passes mimic an empty band;
   requiring the absence of codec holes (D2) cuts the correlated FPR to 0.034.
2. **Directly observed fingerprints are the most reliable**: spectral holes (D2: P 1.0,
   FPR 0), digital silence, verified duplicates, histogram combs, hum-phase jumps.
3. **Edits that preserve continuity are hard**: crossfaded cuts were never found; hard cuts
   inside pauses are physically invisible to waveform tests. Localisation of
   corroborated events within 0.15 s: 5/24 edited evaluation files.
4. **Statistical anomaly detection is not manipulation detection**: Isolation Forest and
   delta-BIC flag 100 % of unedited files.
5. Calibration and evaluation agree within a few files on every correlated decision,
   i.e. no sign of over-fitting the v1.1 rules - but n is small.

## Reproduce

```
sonictrace dataset generate --out datasets/sonictrace_v1 --seed 1337
sonictrace benchmark --dataset datasets/sonictrace_v1 --split calibration --out output/benchmark_v1.2
sonictrace benchmark --dataset datasets/sonictrace_v1 --split evaluation --out output/benchmark_v1.2
python scripts/verify_lame_lowpass.py
```
Mean analysis time: 0.42-0.50 s per 6 s file (all 21 tests, Windows 11 laptop).
