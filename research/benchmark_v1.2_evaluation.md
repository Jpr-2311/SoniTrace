# SonicTrace benchmark - split `evaluation`

Methodology version 1.2; 70/70 files analysed; evidence files unchanged after analysis: True; mean 0.43 s/file.

> Synthetic data only. These figures are not real-world forensic error rates.

## Per-technique performance

| Test | Label | TP | FP | TN | FN | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|---|---|
| A1 | edited | 0 | 0 | 46 | 24 | - | 0.000 | - | 0.000 |
| C1 | edited | 7 | 2 | 44 | 17 | 0.778 | 0.292 | 0.424 | 0.043 |
| C2 | edited | 24 | 46 | 0 | 0 | 0.343 | 1.000 | 0.511 | 1.000 |
| C3 | edited | 24 | 45 | 1 | 0 | 0.348 | 1.000 | 0.516 | 0.978 |
| C4 | edited | 3 | 2 | 44 | 21 | 0.600 | 0.125 | 0.207 | 0.043 |
| C5 | edited | 4 | 3 | 43 | 20 | 0.571 | 0.167 | 0.258 | 0.065 |
| C6 | edited | 4 | 2 | 44 | 20 | 0.667 | 0.167 | 0.267 | 0.043 |
| C7 | edited | 3 | 0 | 46 | 21 | 1.000 | 0.125 | 0.222 | 0.000 |
| D1 | compressed | 10 | 2 | 56 | 2 | 0.833 | 0.833 | 0.833 | 0.034 |
| D2 | compressed | 10 | 0 | 58 | 2 | 1.000 | 0.833 | 0.909 | 0.000 |
| D3 | gain_edit | 2 | 0 | 66 | 2 | 1.000 | 0.500 | 0.667 | 0.000 |
| D4 | transcoded_mp3 | 2 | 0 | 66 | 2 | 1.000 | 0.500 | 0.667 | 0.000 |
| E1 | resampled | 2 | 10 | 48 | 10 | 0.167 | 0.167 | 0.167 | 0.172 |
| E2 | resampled | 4 | 4 | 54 | 8 | 0.500 | 0.333 | 0.400 | 0.069 |
| E3 | resampled | 0 | 0 | 58 | 12 | - | 0.000 | - | 0.000 |
| F1 | edited | 15 | 21 | 25 | 9 | 0.417 | 0.625 | 0.500 | 0.457 |
| F2 | edited | 24 | 46 | 0 | 0 | 0.343 | 1.000 | 0.511 | 1.000 |
| F3 | edited | 11 | 13 | 33 | 13 | 0.458 | 0.458 | 0.458 | 0.283 |
| F4 | edited | 13 | 17 | 29 | 11 | 0.433 | 0.542 | 0.481 | 0.370 |
| F5 | edited | 24 | 46 | 0 | 0 | 0.343 | 1.000 | 0.511 | 1.000 |

## Correlated (multi-layer) assessment

| Decision rule | TP | FP | TN | FN | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|---|
| local_edit_level>=weak | 13 | 7 | 39 | 11 | 0.650 | 0.542 | 0.591 | 0.152 |
| local_edit_level>=moderate | 11 | 4 | 42 | 13 | 0.733 | 0.458 | 0.564 | 0.087 |
| local_edit_level>=strong | 4 | 2 | 44 | 20 | 0.667 | 0.167 | 0.267 | 0.043 |
| lossy_coding indicated/established | 10 | 0 | 58 | 2 | 1.000 | 0.833 | 0.909 | 0.000 |
| lossy_coding possible-or-stronger | 12 | 2 | 56 | 0 | 0.857 | 1.000 | 0.923 | 0.034 |
| upsampling indicated | 2 | 2 | 56 | 10 | 0.500 | 0.167 | 0.250 | 0.034 |
| transcoding indicated | 2 | 0 | 66 | 2 | 1.000 | 0.500 | 0.667 | 0.000 |
| digital_gain_change indicated | 2 | 0 | 66 | 2 | 1.000 | 0.500 | 0.667 | 0.000 |

## Local-edit indicator level vs. ground truth (confusion matrix)

| Level | edited | not edited |
|---|---|---|
| none | 11 | 39 |
| weak | 2 | 3 |
| moderate | 7 | 2 |
| strong | 4 | 2 |

## Localisation of edit points (tolerance 0.15 s)

| Test | edited files | localised | rate |
|---|---|---|---|
| C1 | 24 | 7 | 0.292 |
| C2 | 24 | 17 | 0.708 |
| C3 | 24 | 16 | 0.667 |
| C4 | 24 | 1 | 0.042 |
| C5 | 24 | 4 | 0.167 |
| C6 | 24 | 2 | 0.083 |
| C7 | 24 | 3 | 0.125 |
| D3 | 24 | 2 | 0.083 |
| corroborated_event | 24 | 5 | 0.208 |

## Detection rate per condition

| Condition | n | C1 | C2 | C4 | C5 | C6 | C7 | D1 | D2 | D3 | E1 | E2 | level>=moderate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| added_noise | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| clean | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| control | 4 | 0.000 | 1.000 | 0.500 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.000 |
| copy_overwrite | 4 | 0.750 | 1.000 | 0.000 | 0.000 | 0.750 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.750 |
| cut_crossfade | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| cut_hard | 4 | 0.250 | 1.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 |
| gain_step | 4 | 0.250 | 1.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.500 | 0.000 | 0.000 | 0.500 |
| insert_silence | 4 | 0.500 | 1.000 | 0.250 | 1.000 | 0.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 |
| legit_loop | 2 | 0.500 | 1.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 |
| legit_noise_gate | 4 | 0.250 | 1.000 | 0.000 | 0.750 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.500 |
| legit_normalize | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| mp3_1gen | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | 0.750 | 0.000 | 1.000 | 0.250 | 0.000 |
| mp3_2gen | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | 0.750 | 0.000 | 1.000 | 0.250 | 0.000 |
| mp3_transcoded | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.500 | 1.000 | 0.000 | 0.500 | 0.250 | 0.000 |
| noise_env_splice | 4 | 0.000 | 1.000 | 0.250 | 0.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 |
| resample_48k | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| resample_linear | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.500 | 0.000 |
| resample_poly | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.500 | 0.000 | 0.000 | 0.500 | 0.500 | 0.000 |

## Threshold sensitivity (primary score only)

**C1**: x0.5: P=0.692 R=0.375 FPR=0.087; x0.75: P=0.727 R=0.333 FPR=0.065; x1.0: P=0.778 R=0.292 FPR=0.043; x1.25: P=0.750 R=0.250 FPR=0.043; x1.5: P=0.857 R=0.250 FPR=0.022; x2.0: P=0.857 R=0.250 FPR=0.022

**C2**: x0.5: P=0.343 R=1.000 FPR=1.000; x0.75: P=0.343 R=1.000 FPR=1.000; x1.0: P=0.343 R=1.000 FPR=1.000; x1.25: P=0.348 R=1.000 FPR=0.978; x1.5: P=0.338 R=0.958 FPR=0.978; x2.0: P=0.345 R=0.792 FPR=0.783

**C3**: x0.5: P=0.343 R=1.000 FPR=1.000; x0.75: P=0.343 R=1.000 FPR=1.000; x1.0: P=0.348 R=1.000 FPR=0.978; x1.25: P=0.353 R=1.000 FPR=0.957; x1.5: P=0.393 R=0.917 FPR=0.739; x2.0: P=0.410 R=0.667 FPR=0.500

**C4**: x0.5: P=0.396 R=0.875 FPR=0.696; x0.75: P=0.407 R=0.458 FPR=0.348; x1.0: P=0.571 R=0.333 FPR=0.130; x1.25: P=0.714 R=0.208 FPR=0.043; x1.5: P=0.833 R=0.208 FPR=0.022; x2.0: P=1.000 R=0.167 FPR=0.000

**C5**: x0.5: P=0.571 R=0.167 FPR=0.065; x0.75: P=0.571 R=0.167 FPR=0.065; x1.0: P=0.571 R=0.167 FPR=0.065; x1.25: P=0.667 R=0.167 FPR=0.043; x1.5: P=0.667 R=0.167 FPR=0.043; x2.0: P=0.667 R=0.167 FPR=0.043

**C6**: x0.5: P=0.323 R=0.875 FPR=0.957; x0.75: P=0.359 R=0.583 FPR=0.543; x1.0: P=0.667 R=0.167 FPR=0.043; x1.25: P=- R=0.000 FPR=0.000; x1.5: P=- R=0.000 FPR=0.000; x2.0: P=- R=0.000 FPR=0.000

**C7**: x0.5: P=0.353 R=0.250 FPR=0.239; x0.75: P=0.500 R=0.125 FPR=0.065; x1.0: P=1.000 R=0.125 FPR=0.000; x1.25: P=1.000 R=0.125 FPR=0.000; x1.5: P=1.000 R=0.125 FPR=0.000; x2.0: P=1.000 R=0.125 FPR=0.000

**D1**: x0.5: P=0.833 R=0.833 FPR=0.034; x0.75: P=0.833 R=0.833 FPR=0.034; x1.0: P=0.833 R=0.833 FPR=0.034; x1.25: P=0.833 R=0.833 FPR=0.034; x1.5: P=0.833 R=0.833 FPR=0.034; x2.0: P=1.000 R=0.333 FPR=0.000

**D2**: x0.5: P=0.857 R=1.000 FPR=0.034; x0.75: P=0.923 R=1.000 FPR=0.017; x1.0: P=1.000 R=0.833 FPR=0.000; x1.25: P=1.000 R=0.583 FPR=0.000; x1.5: P=1.000 R=0.417 FPR=0.000; x2.0: P=1.000 R=0.417 FPR=0.000

**D3**: x0.5: P=0.200 R=0.250 FPR=0.061; x0.75: P=0.200 R=0.250 FPR=0.061; x1.0: P=0.200 R=0.250 FPR=0.061; x1.25: P=0.200 R=0.250 FPR=0.061; x1.5: P=0.200 R=0.250 FPR=0.061; x2.0: P=0.200 R=0.250 FPR=0.061

**E1**: x0.5: P=0.167 R=0.167 FPR=0.172; x0.75: P=0.167 R=0.167 FPR=0.172; x1.0: P=0.167 R=0.167 FPR=0.172; x1.25: P=0.167 R=0.167 FPR=0.172; x1.5: P=0.167 R=0.167 FPR=0.172; x2.0: P=0.167 R=0.167 FPR=0.172

**E2**: x0.5: P=0.195 R=0.667 FPR=0.569; x0.75: P=0.261 R=0.500 FPR=0.293; x1.0: P=0.500 R=0.333 FPR=0.069; x1.25: P=0.400 R=0.167 FPR=0.052; x1.5: P=1.000 R=0.083 FPR=0.000; x2.0: P=- R=0.000 FPR=0.000

**F1**: x0.5: P=0.343 R=1.000 FPR=1.000; x0.75: P=0.343 R=1.000 FPR=1.000; x1.0: P=0.338 R=0.917 FPR=0.935; x1.25: P=0.365 R=0.792 FPR=0.717; x1.5: P=0.370 R=0.708 FPR=0.630; x2.0: P=0.417 R=0.625 FPR=0.457

**F4**: x0.5: P=0.343 R=1.000 FPR=1.000; x0.75: P=0.345 R=0.833 FPR=0.826; x1.0: P=0.433 R=0.542 FPR=0.370; x1.25: P=1.000 R=0.208 FPR=0.000; x1.5: P=1.000 R=0.167 FPR=0.000; x2.0: P=- R=0.000 FPR=0.000

## False positives by technique

- **C1** (2): legit_loop x1, legit_noise_gate x1
- **C2** (46): added_noise x4, clean x4, control x4, legit_loop x2, legit_noise_gate x4, legit_normalize x4, mp3_1gen x4, mp3_2gen x4, mp3_transcoded x4, resample_48k x4, resample_linear x4, resample_poly x4
- **C3** (45): added_noise x4, clean x4, control x4, legit_loop x2, legit_noise_gate x4, legit_normalize x4, mp3_1gen x4, mp3_2gen x4, mp3_transcoded x3, resample_48k x4, resample_linear x4, resample_poly x4
- **C4** (2): control x2
- **C5** (3): legit_noise_gate x3
- **C6** (2): legit_loop x2
- **D1** (2): resample_poly x2
- **E1** (10): mp3_1gen x4, mp3_2gen x4, mp3_transcoded x2
- **E2** (4): control x1, mp3_1gen x1, mp3_2gen x1, mp3_transcoded x1
- **F1** (21): clean x2, control x2, legit_loop x1, legit_noise_gate x3, legit_normalize x2, mp3_1gen x2, mp3_2gen x2, mp3_transcoded x2, resample_48k x2, resample_linear x2, resample_poly x1
- **F2** (46): added_noise x4, clean x4, control x4, legit_loop x2, legit_noise_gate x4, legit_normalize x4, mp3_1gen x4, mp3_2gen x4, mp3_transcoded x4, resample_48k x4, resample_linear x4, resample_poly x4
- **F3** (13): clean x1, control x1, legit_noise_gate x3, legit_normalize x1, mp3_1gen x1, mp3_2gen x1, mp3_transcoded x1, resample_48k x1, resample_linear x2, resample_poly x1
- **F4** (17): added_noise x2, clean x2, control x1, legit_noise_gate x2, legit_normalize x2, mp3_1gen x1, mp3_2gen x1, mp3_transcoded x1, resample_48k x2, resample_linear x1, resample_poly x2
- **F5** (46): added_noise x4, clean x4, control x4, legit_loop x2, legit_noise_gate x4, legit_normalize x4, mp3_1gen x4, mp3_2gen x4, mp3_transcoded x4, resample_48k x4, resample_linear x4, resample_poly x4
