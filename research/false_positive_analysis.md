# Controlled false-positive investigation

Methodology v1.0 was run on the **calibration split** (70 files). Every false positive was
traced to its cause; changes were made only where the cause was understood, and the
change was re-measured. Nothing below was tuned on the evaluation split. Numbers are
from `research/benchmark_v1.0_calibration.md` (v1.0) and
`research/benchmark_v1.1_calibration.md` / `research/benchmark_v1.1_evaluation.md` (v1.1).
Regression tests: `tests/test_regression_fp.py`.

## FP-1  Natural onsets read as edit points (C2 energy / C3 spectral discontinuity)

* **Observation (v1.0):** C2 fired on 46/46 unedited calibration files, C3 on 46/46.
  Every file therefore had at least one "isolated" event and the local-edit level was
  never `none` (`local_edit_level>=weak`: FPR 1.000).
* **Cause:** syllable and note onsets after pauses raise the 10 ms level by 20-30 dB
  within one window - the same signature as an inserted or removed segment. A level
  step is not specific to editing.
* **Change (v1.1):** energy/spectral jumps form a *supporting* family: still measured
  and reported per test, attached to events as context, but they can neither create an
  event nor count toward corroboration (`evidence/correlation.py`, `SUPPORTING_FAMILIES`).
* **Effect (calibration):** `local_edit_level>=weak` FPR 1.000 -> 0.283; precision
  0.343 -> 0.567. The tests themselves keep FPR ~1.0 (reported honestly in every benchmark).

## FP-2  Peak normalisation read as a local gain edit (D3 histogram comb)

* **Observation (v1.0):** D3 flagged 3/4 `legit_normalize` files; each became a "gain-edit
  region" whose boundaries were treated as edit points.
* **Cause:** a whole-file gain on 16-bit data produces exactly the comb a local gain edit
  produces; only the *spatial extent* differs.
* **Change (v1.1):** if >= 80 % of analysed blocks are combed, D3 reports one global
  `processing` finding ("whole-file digital gain change") and no regions; the correlation
  engine lists it under processing history (`whole_file_gain_change`).
* **Effect:** D3 false positives 3 -> 0 (calibration) and 0 on evaluation; the
  normalisation is still reported as an observed processing step.

## FP-3  Noise gate read as inserted silence (C5 digital silence)

* **Observation (v1.0):** 3/4 `legit_noise_gate` files had MEDIUM digital-silence findings;
  3/4 reached local level `moderate`.
* **Cause:** a hard gate writes exact zeros in pauses - physically identical to inserted
  digital silence. The only difference is the *pattern*: many runs spread over the file.
* **Change (v1.1):** >= 5 interior zero runs => a `systematic gating pattern` finding,
  individual runs downgraded to LOW. Runs are still listed as observed facts.
* **Effect:** gated files at level >= moderate: 3/4 -> 1/4 (calibration), 2/4 (evaluation).
  **Residual:** gates that close fewer than 5 times, or whose run boundaries coincide with
  C1 impulses (a gate closing on a non-zero sample is a real waveform discontinuity),
  remain moderate. Known trade-off: repeated deliberate insertions would be labelled a
  gating pattern; the observed runs remain in the report either way.

## FP-4  Loop-based music read as copy-move (C6 duplication)

* **Observation (v1.1):** both evaluation `legit_loop` files have verified duplicates
  (NCC > 0.99) and reach level `moderate`; one calibration loop likewise.
* **Cause:** the material really is duplicated sample-for-sample. The observation is
  correct; only its interpretation is ambiguous.
* **Decision:** no change. Suppressing it would hide a true observation. Every DUP finding
  lists "loop-based music production or sampled/repeated material" as an alternative, and
  the report's false-positive section repeats it. Distinguishing a loop from a forgery
  needs context (genre, provenance) that a signal-level tool does not have.

## FP-5  Codec low-pass read as upsampling (E1 empty band)

* **Observation (v1.1):** E1 flags 8/8 MP3 decodes at 64/96 kbit/s (calibration) and 10/12
  on evaluation: LAME's 15-16 kHz low-pass leaves the top of the band empty.
* **Cause:** bandwidth alone cannot separate codec low-pass, resampling and filtering.
* **Mitigation:** the correlation engine only reports `upsampling: indicated` when the band
  limit has **no** codec spectral holes (D2); otherwise `possible` with the codec as the
  simpler explanation. Evaluation: E1 raw FPR 0.172 vs. correlated `upsampling indicated`
  FPR 0.034 - the clearest measured benefit of multi-layer correlation in this project.

## FP-6  Periodic mains hum in pauses read as a duplicate (C6) - found during the documentation audit

* **Observation (v1.2, evaluation):** `eva_src00__noise_env_splice.wav` (background switches
  from "room" to "hum" at 3.75 s) has a verified duplicate "5.16-5.40 s duplicates 4.64-4.88 s"
  with NCC 0.9802 - just above the 0.98 threshold - although nothing was copied.
* **Cause:** after the splice the pauses are dominated by 50 Hz hum and its harmonics, a
  quasi-periodic signal that matches itself at lags of whole hum periods.
* **Effect on the numbers:** the benchmark counts it as a C6 true positive (the file is
  edited), so C6's evaluation recall of 4/24 contains one coincidental match, and this
  file's `moderate` level (and the "background splice 1/4 at >= moderate" figure) comes from
  that match, not from the C4 noise-floor event, which alone is `isolated`.
* **Decision:** not changed - noticed after the evaluation run, while writing the
  documentation. Candidate fix (TODO): reject candidates whose segment also matches itself
  at short lags (self-periodicity check).

## Failed experiments and bugs found by the benchmark

* **C6 v1.0 had 0 % recall.** Two causes: (a) the "active frame" rule (noise floor
  + 15 dB) marked every frame of continuous music inactive; (b) a 46 ms frame hop
  misaligned copies against the frame grid and pauses split copies into runs shorter than
  the 0.25 s minimum. Fixed in v1.1 (relative activity rule, full STFT hop for files
  <= 30 s, 0.15 s minimum, ranking by excess similarity). Recall 0 -> 0.17 (both splits);
  copy-overwrite detection 0/4 -> 3/4 on evaluation.
* **Band-limit cutoff at the stopband edge.** v1.0 reported the frequency where content
  meets the floor; for scipy's polyphase resampler this lies 1.5-2 kHz above the
  passband edge, so candidate source rates were wrong (a 22.05 kHz upsample was reported
  as 24 kHz). v1.1 reports the -6 dB point.
* **Mono 128 kbit/s MP3 was not a meaningful compression condition.** LAME allocates the
  whole budget to one channel and low-passes at ~20 kHz with few holes; D1/D2 recall was 0.
  The dataset now uses 64 kbit/s mono (the per-channel budget of 128 kbit/s stereo). This
  is a *dataset* change; v1.0 and v1.1 compression numbers are not comparable.
* **44.1 -> 48 kHz upsampling is not resolved by E1** (0/8 across splits): scipy's default
  Kaiser(beta = 5) filter for 160/147 leaves only ~15 dB of stopband attenuation and the
  empty band is ~8 % of Nyquist. Recorded as a limitation (`tests/test_resampling.py`
  keeps an `xfail` test).
* **D4 could never fire on FFmpeg-written MP3s** (found while running the CLI, fixed in
  v1.2): FFmpeg's muxer records a LAME-tag low-pass of 0. D4 now falls back to a measured
  libmp3lame low-pass model (`research/lame_lowpass_verification.md`); recall on
  transcoded MP3s 0 -> 0.5 on both splits, 0 false positives (`experiments.md`, E4).
* **Statistical anomaly detectors (Module F)** flag 28-100 % of unedited files (F2 Isolation
  Forest and F5 delta-BIC: 100 %). This is the expected behaviour of unsupervised outlier
  methods on non-stationary content and the reason they are excluded from corroboration.
