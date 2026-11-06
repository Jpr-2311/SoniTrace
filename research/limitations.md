# Limitations

## Scope

* SonicTrace does **not** decide authenticity, does not detect AI-generated/synthetic
  speech, and cannot determine intent. It reports technical observations and their
  possible explanations.
* All benchmark figures come from a synthetic dataset (formant-synthesised speech-like
  and harmonic music-like signals). They are **not** real-world forensic error rates.
  Real recordings contain reverberation, codec chains, AGC and non-stationary noise that
  the synthetic data only partly models.
* Thresholds were calibrated on 70 synthetic files; confidence intervals at n = 70 are wide
  (one file changes a rate by up to 25 percentage points in a 4-file condition).

## Per technique

| Test | Fails or misleads when |
|---|---|
| C1 LPC residual | edits are crossfaded or made at zero crossings with matching slope (0/8 crossfaded cuts found); cuts fall inside background noise; percussive onsets, clicks and plosives mimic impulses |
| C2/C3 energy/spectral | fire on every natural onset (FPR ~1.0); supporting context only |
| C4 noise floor | no pauses (continuous music): the minimum-statistics floor is the content itself; real environmental changes and AGC look identical |
| C5 digital silence | dithered or noise-filled insertions; noise gates produce the same exact zeros |
| C6 duplication | copies that were re-filtered, time-stretched, mixed or re-encoded at low bitrate; loops/samples are true duplicates; strongly periodic backgrounds can match themselves - two pauses dominated by mains hum matched with NCC 0.9802 on one evaluation file, just above the 0.98 threshold, although nothing was copied (FP-6 in `false_positive_analysis.md`) |
| C7 ENF | no mains hum (battery recorders); removals of an integer number of hum periods; +/- 0.2 s resolution |
| D1 band limit | cannot tell codec vs. resampler vs. filter vs. band-limited microphone |
| D2 spectral holes | high-bitrate encodes; dithered decoding; spectral denoisers also create holes |
| D3 histogram comb | gains that are exact integer ratios (0.5) map codes onto codes; dither after the gain change; float files without an integer grid; lossy decodes |
| D4 codec consistency | MP3 only; without a recorded low-pass the expectation comes from a measured libmp3lame model covering CBR MPEG-1 Layer III at 44.1/48 kHz (VBR/ABR, MPEG-2/2.5, other encoders such as FhG/iTunes/libshine and custom `--lowpass` settings are not covered); transcodes between bitrates with similar low-pass (within 15 %) and first generations that leave a gradual band edge are missed; number of lossy generations is never established |
| E1 empty band | downsampling leaves no trace; small empty bands (44.1 -> 48 kHz, ~8 %) and resamplers with shallow stopbands are missed; codec low-pass mimics it |
| E2 periodicity | experimental; long sinc kernels leave little periodic structure; tonal content creates peaks |
| E3 rate metadata | only detects disagreement between declared rates, never resampling itself |
| F1-F5 | unsupervised; describe unusualness relative to the same file, not manipulation |
| compare | assumes the reference is the original; heavy processing lowers block NCC; shifts beyond +/- 2 s are not tracked |

## Engineering

* Maximum input 512 MiB / 600 s / 16 channels by default (configurable); duplication
  search is skipped above 180 s (quadratic cost).
* Multi-channel files are analysed on the mono mix-down (quantisation analysis uses
  channel 0); inter-channel splices are not specifically tested.
* MP3/AAC/M4A decoding depends on FFmpeg; FFmpeg's decoder applies gapless trimming, so
  decoded sample counts reflect FFmpeg, not the raw bitstream.
* Ogg CRC verification is pure Python and limited to the first 20 MiB of pages.
