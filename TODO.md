# TODO (not completed within the build deadline)

- [ ] Resolve small empty bands (44.1 -> 48 kHz upsampling): stopband-shape model instead of a fixed 25 dB depth; currently 0/8 (xfail test).
- [ ] Double-compression detection on MP3 bitstreams (MDCT coefficient statistics, frame-grid alignment); currently explicitly "cannot be established".
- [ ] Aliasing indicators for downsampling without anti-alias filtering (not implemented).
- [ ] Inter-channel analysis for stereo splices (channel correlation/phase changes).
- [ ] Noise-gate rule refinement: use attack/release ramps and correlation of zero runs with low-energy context instead of a run count.
- [ ] Crossfaded-edit detection (0/8 found): e.g. comb-filter signature of overlap-add in the spectrogram, or noise-floor phase discontinuities.
- [ ] Bootstrap confidence intervals for benchmark metrics; larger dataset (current defaults: 140 files).
- [ ] Real-recording validation set (licensed public-domain speech) to complement the synthetic benchmark.
- [ ] Vectorise Ogg CRC (currently pure Python, capped at 20 MiB).
- [ ] AAC/MP4 internals (edit lists/priming, ADTS bitrate) beyond box-level inspection.
- [ ] C6: reject duplicate candidates that are self-periodic (e.g. hum-dominated pauses matched at NCC 0.9802, FP-6).
- [ ] D4 low-pass models for VBR/ABR, MPEG-2/2.5 and other encoders (FhG, iTunes/Apple, libshine); detect transcodes whose first generation left a gradual band edge (2/4 tonal transcodes missed).
