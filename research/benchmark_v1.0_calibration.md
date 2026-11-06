# SonicTrace benchmark - split `calibration`

Methodology version 1.0; 70/70 files analysed; evidence files unchanged after analysis: True; mean 0.41 s/file.

> Synthetic data only. These figures are not real-world forensic error rates.

## Per-technique performance

| Test | Label | TP | FP | TN | FN | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|---|---|
| A1 | edited | 0 | 0 | 46 | 24 | - | 0.000 | - | 0.000 |
| C1 | edited | 8 | 2 | 44 | 16 | 0.800 | 0.333 | 0.471 | 0.043 |
| C2 | edited | 24 | 46 | 0 | 0 | 0.343 | 1.000 | 0.511 | 1.000 |
| C3 | edited | 24 | 46 | 0 | 0 | 0.343 | 1.000 | 0.511 | 1.000 |
| C4 | edited | 7 | 8 | 38 | 17 | 0.467 | 0.292 | 0.359 | 0.174 |
| C5 | edited | 4 | 3 | 43 | 20 | 0.571 | 0.167 | 0.258 | 0.065 |
| C6 | edited | 0 | 0 | 46 | 24 | - | 0.000 | - | 0.000 |
| C7 | edited | 6 | 0 | 46 | 18 | 1.000 | 0.250 | 0.400 | 0.000 |
| D1 | compressed | 0 | 3 | 55 | 12 | 0.000 | 0.000 | 0.000 | 0.052 |
| D2 | compressed | 0 | 0 | 58 | 12 | - | 0.000 | - | 0.000 |
| D3 | gain_edit | 1 | 3 | 63 | 3 | 0.250 | 0.250 | 0.250 | 0.045 |
| D4 | compressed | 0 | 0 | 58 | 12 | - | 0.000 | - | 0.000 |
| E1 | resampled | 3 | 0 | 58 | 9 | 1.000 | 0.250 | 0.400 | 0.000 |
| E2 | resampled | 4 | 10 | 48 | 8 | 0.286 | 0.333 | 0.308 | 0.172 |
| E3 | resampled | 0 | 0 | 58 | 12 | - | 0.000 | - | 0.000 |
| F1 | edited | 10 | 19 | 27 | 14 | 0.345 | 0.417 | 0.377 | 0.413 |
| F2 | edited | 24 | 46 | 0 | 0 | 0.343 | 1.000 | 0.511 | 1.000 |
| F3 | edited | 10 | 13 | 33 | 14 | 0.435 | 0.417 | 0.426 | 0.283 |
| F4 | edited | 16 | 23 | 23 | 8 | 0.410 | 0.667 | 0.508 | 0.500 |
| F5 | edited | 24 | 46 | 0 | 0 | 0.343 | 1.000 | 0.511 | 1.000 |

## Correlated (multi-layer) assessment

| Decision rule | TP | FP | TN | FN | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|---|
| local_edit_level>=weak | 24 | 46 | 0 | 0 | 0.343 | 1.000 | 0.511 | 1.000 |
| local_edit_level>=moderate | 16 | 14 | 32 | 8 | 0.533 | 0.667 | 0.593 | 0.304 |
| local_edit_level>=strong | 5 | 0 | 46 | 19 | 1.000 | 0.208 | 0.345 | 0.000 |
| lossy_coding indicated/established | 4 | 0 | 58 | 8 | 1.000 | 0.333 | 0.500 | 0.000 |
| lossy_coding possible-or-stronger | 4 | 3 | 55 | 8 | 0.571 | 0.333 | 0.421 | 0.052 |
| upsampling indicated | 3 | 0 | 58 | 9 | 1.000 | 0.250 | 0.400 | 0.000 |
| digital_gain_change indicated | 1 | 3 | 63 | 3 | 0.250 | 0.250 | 0.250 | 0.045 |

## Local-edit indicator level vs. ground truth (confusion matrix)

| Level | edited | not edited |
|---|---|---|
| none | 0 | 0 |
| weak | 8 | 32 |
| moderate | 11 | 14 |
| strong | 5 | 0 |

## Localisation of edit points (tolerance 0.15 s)

| Test | edited files | localised | rate |
|---|---|---|---|
| C1 | 24 | 8 | 0.333 |
| C2 | 24 | 14 | 0.583 |
| C3 | 24 | 19 | 0.792 |
| C4 | 24 | 3 | 0.125 |
| C5 | 24 | 4 | 0.167 |
| C6 | 24 | 0 | 0.000 |
| C7 | 24 | 6 | 0.250 |
| D3 | 24 | 0 | 0.000 |
| corroborated_event | 24 | 12 | 0.500 |

## Detection rate per condition

| Condition | n | C1 | C2 | C4 | C5 | C6 | C7 | D1 | D2 | D3 | E1 | E2 | level>=moderate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| added_noise | 4 | 0.000 | 1.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 |
| clean | 4 | 0.000 | 1.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.250 |
| control | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.000 |
| copy_overwrite | 4 | 0.750 | 1.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.750 |
| cut_crossfade | 4 | 0.000 | 1.000 | 0.500 | 0.000 | 0.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.500 |
| cut_hard | 4 | 0.250 | 1.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 |
| gain_step | 4 | 0.500 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.000 | 0.000 | 0.750 |
| insert_silence | 4 | 0.500 | 1.000 | 0.750 | 1.000 | 0.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 |
| legit_loop | 2 | 0.500 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.500 | 0.500 |
| legit_noise_gate | 4 | 0.250 | 1.000 | 0.000 | 0.750 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.750 |
| legit_normalize | 4 | 0.000 | 1.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.750 | 0.000 | 0.250 | 0.750 |
| mp3_1gen | 4 | 0.000 | 1.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.250 |
| mp3_2gen | 4 | 0.000 | 1.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.250 |
| mp3_transcoded | 4 | 0.000 | 1.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.250 |
| noise_env_splice | 4 | 0.000 | 1.000 | 0.500 | 0.000 | 0.000 | 0.500 | 0.000 | 0.000 | 0.000 | 0.000 | 0.250 | 0.750 |
| resample_48k | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| resample_linear | 4 | 0.000 | 1.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.500 | 0.250 |
| resample_poly | 4 | 0.000 | 1.000 | 0.250 | 0.000 | 0.000 | 0.000 | 0.750 | 0.000 | 0.000 | 0.750 | 0.500 | 0.250 |

## Threshold sensitivity (primary score only)

**C1**: x0.5: P=0.833 R=0.417 FPR=0.043; x0.75: P=0.800 R=0.333 FPR=0.043; x1.0: P=0.800 R=0.333 FPR=0.043; x1.25: P=0.800 R=0.333 FPR=0.043; x1.5: P=0.889 R=0.333 FPR=0.022; x2.0: P=0.889 R=0.333 FPR=0.022

**C2**: x0.5: P=0.343 R=1.000 FPR=1.000; x0.75: P=0.343 R=1.000 FPR=1.000; x1.0: P=0.343 R=1.000 FPR=1.000; x1.25: P=0.343 R=1.000 FPR=1.000; x1.5: P=0.338 R=0.958 FPR=0.978; x2.0: P=0.357 R=0.833 FPR=0.783

**C3**: x0.5: P=0.343 R=1.000 FPR=1.000; x0.75: P=0.343 R=1.000 FPR=1.000; x1.0: P=0.343 R=1.000 FPR=1.000; x1.25: P=0.343 R=1.000 FPR=1.000; x1.5: P=0.343 R=1.000 FPR=1.000; x2.0: P=0.423 R=0.917 FPR=0.652

**C4**: x0.5: P=0.328 R=0.875 FPR=0.935; x0.75: P=0.333 R=0.583 FPR=0.609; x1.0: P=0.391 R=0.375 FPR=0.304; x1.25: P=0.389 R=0.292 FPR=0.239; x1.5: P=0.375 R=0.250 FPR=0.217; x2.0: P=0.571 R=0.167 FPR=0.065

**C5**: x0.5: P=0.571 R=0.167 FPR=0.065; x0.75: P=0.571 R=0.167 FPR=0.065; x1.0: P=0.571 R=0.167 FPR=0.065; x1.25: P=0.667 R=0.167 FPR=0.043; x1.5: P=0.667 R=0.167 FPR=0.043; x2.0: P=0.667 R=0.167 FPR=0.043

**C6**: x0.5: P=- R=0.000 FPR=0.000; x0.75: P=- R=0.000 FPR=0.000; x1.0: P=- R=0.000 FPR=0.000; x1.25: P=- R=0.000 FPR=0.000; x1.5: P=- R=0.000 FPR=0.000; x2.0: P=- R=0.000 FPR=0.000

**C7**: x0.5: P=1.000 R=0.250 FPR=0.000; x0.75: P=1.000 R=0.250 FPR=0.000; x1.0: P=1.000 R=0.250 FPR=0.000; x1.25: P=1.000 R=0.250 FPR=0.000; x1.5: P=1.000 R=0.250 FPR=0.000; x2.0: P=1.000 R=0.250 FPR=0.000

**D1**: x0.5: P=0.000 R=0.000 FPR=0.052; x0.75: P=0.000 R=0.000 FPR=0.052; x1.0: P=0.000 R=0.000 FPR=0.052; x1.25: P=0.000 R=0.000 FPR=0.034; x1.5: P=0.000 R=0.000 FPR=0.017; x2.0: P=0.000 R=0.000 FPR=0.017

**D2**: x0.5: P=0.000 R=0.000 FPR=0.034; x0.75: P=- R=0.000 FPR=0.000; x1.0: P=- R=0.000 FPR=0.000; x1.25: P=- R=0.000 FPR=0.000; x1.5: P=- R=0.000 FPR=0.000; x2.0: P=- R=0.000 FPR=0.000

**D3**: x0.5: P=0.250 R=0.250 FPR=0.045; x0.75: P=0.250 R=0.250 FPR=0.045; x1.0: P=0.250 R=0.250 FPR=0.045; x1.25: P=0.250 R=0.250 FPR=0.045; x1.5: P=0.250 R=0.250 FPR=0.045; x2.0: P=0.250 R=0.250 FPR=0.045

**E1**: x0.5: P=0.200 R=0.250 FPR=0.207; x0.75: P=0.200 R=0.250 FPR=0.207; x1.0: P=1.000 R=0.250 FPR=0.000; x1.25: P=1.000 R=0.250 FPR=0.000; x1.5: P=1.000 R=0.250 FPR=0.000; x2.0: P=1.000 R=0.250 FPR=0.000

**E2**: x0.5: P=0.176 R=0.750 FPR=0.724; x0.75: P=0.227 R=0.417 FPR=0.293; x1.0: P=0.286 R=0.333 FPR=0.172; x1.25: P=1.000 R=0.250 FPR=0.000; x1.5: P=1.000 R=0.167 FPR=0.000; x2.0: P=- R=0.000 FPR=0.000

**F1**: x0.5: P=0.343 R=1.000 FPR=1.000; x0.75: P=0.343 R=1.000 FPR=1.000; x1.0: P=0.333 R=0.958 FPR=1.000; x1.25: P=0.312 R=0.833 FPR=0.957; x1.5: P=0.320 R=0.667 FPR=0.739; x2.0: P=0.345 R=0.417 FPR=0.413

**F4**: x0.5: P=0.343 R=1.000 FPR=1.000; x0.75: P=0.359 R=0.958 FPR=0.891; x1.0: P=0.410 R=0.667 FPR=0.500; x1.25: P=0.478 R=0.458 FPR=0.261; x1.5: P=1.000 R=0.167 FPR=0.000; x2.0: P=- R=0.000 FPR=0.000

## False positives by technique

- **C1** (2): legit_loop x1, legit_noise_gate x1
- **C2** (46): added_noise x4, clean x4, control x4, legit_loop x2, legit_noise_gate x4, legit_normalize x4, mp3_1gen x4, mp3_2gen x4, mp3_transcoded x4, resample_48k x4, resample_linear x4, resample_poly x4
- **C3** (46): added_noise x4, clean x4, control x4, legit_loop x2, legit_noise_gate x4, legit_normalize x4, mp3_1gen x4, mp3_2gen x4, mp3_transcoded x4, resample_48k x4, resample_linear x4, resample_poly x4
- **C4** (8): added_noise x1, clean x1, legit_normalize x1, mp3_1gen x1, mp3_2gen x1, mp3_transcoded x1, resample_linear x1, resample_poly x1
- **C5** (3): legit_noise_gate x3
- **D1** (3): resample_poly x3
- **D3** (3): legit_normalize x3
- **E2** (10): clean x1, control x1, cut_crossfade x1, legit_loop x1, legit_noise_gate x1, legit_normalize x1, mp3_1gen x1, mp3_2gen x1, mp3_transcoded x1, noise_env_splice x1
- **F1** (19): clean x2, control x3, legit_loop x2, legit_noise_gate x1, legit_normalize x2, mp3_1gen x2, mp3_2gen x2, mp3_transcoded x2, resample_48k x1, resample_linear x1, resample_poly x1
- **F2** (46): added_noise x4, clean x4, control x4, legit_loop x2, legit_noise_gate x4, legit_normalize x4, mp3_1gen x4, mp3_2gen x4, mp3_transcoded x4, resample_48k x4, resample_linear x4, resample_poly x4
- **F3** (13): added_noise x1, clean x1, control x3, legit_loop x1, legit_noise_gate x1, legit_normalize x1, mp3_1gen x1, mp3_2gen x1, mp3_transcoded x1, resample_linear x1, resample_poly x1
- **F4** (23): added_noise x2, clean x2, control x1, legit_noise_gate x3, legit_normalize x2, mp3_1gen x2, mp3_2gen x2, mp3_transcoded x1, resample_48k x3, resample_linear x2, resample_poly x3
- **F5** (46): added_noise x4, clean x4, control x4, legit_loop x2, legit_noise_gate x4, legit_normalize x4, mp3_1gen x4, mp3_2gen x4, mp3_transcoded x4, resample_48k x4, resample_linear x4, resample_poly x4
