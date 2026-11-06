# Mathematics of the main detection methods

Notation: `x[n]` mono signal, `fs` sample rate, `N` FFT size, `H = N/4` hop, `w[n]` periodic Hann window.

## 1. STFT and spectral descriptors (Module B)

`X[k,m] = sum_{n=0}^{N-1} x[n + mH] w[n] e^{-j2pi kn/N}`, power `P[k,m] = |X[k,m]|^2`.
N is the power of two nearest to 46 ms (2048 at 44.1/48 kHz). The Hann window trades a
-31 dB first sidelobe and 18 dB/octave sidelobe decay for a 4-bin main lobe (Harris, 1978);
spectral *leakage* from strong components therefore stays local, which matters for the
spectral-hole statistic (Sec. 5).

* centroid `c_m = sum_k f_k P / sum_k P`; bandwidth `sqrt(sum_k (f_k - c_m)^2 P / sum_k P)`;
  roll-off = lowest f holding 85 % of the energy; flatness `exp(mean ln P) / mean P`
  (1 for white noise, -> 0 for tones); flux = L2 norm of the positive change of the
  normalised magnitude spectrum.
* MFCC: 40 triangular mel filters (HTK mel `m = 2595 log10(1 + f/700)`), log energies,
  orthonormal DCT-II, 13 coefficients (Davis & Mermelstein, 1980).
* LTAS: Welch average of Hann-windowed periodograms (8192 points, 50 % overlap).

## 2. Waveform discontinuity via the LPC residual (C1)

Autocorrelation-method linear prediction of order p = 16, re-estimated every 4096 samples
(Hann-windowed 8192-sample analysis window, Levinson/Toeplitz solve with 1e-6 white-noise
correction):

`e[n] = x[n] - sum_{k=1}^{p} a_k x[n-k]`.

For a locally stationary signal the predictor removes the spectral envelope and `e[n]`
is close to white (Makhoul, 1975). A hard splice concatenates two waveforms whose values
and derivatives do not continue each other; for the next few samples the predictor
extrapolates the old waveform and `|e[n]|` shows an isolated impulse.

Score: `r[n] = |e[n]| / max(|e[m]| : g <= |m - n| <= W)` with guard `g = 0.5 ms` (skips the
predictor's own p-sample recovery) and `W = 20 ms`. Using the neighbourhood **maximum**
(rather than RMS) means a periodic train of residual peaks - glottal pulses, plucked
notes - scores about 1, while an isolated edit impulse scores >> 1. Threshold `r >= 4`.

*Assumes* local predictability. *Fails* for edits at zero crossings with matching slope,
crossfaded edits (none in 4/4 crossfaded calibration cuts were found), and cuts inside
background noise (both sides unpredictable).

## 3. Short-time energy and spectral discontinuity (C2, C3)

`L(t) = 10 log10( (1/W) sum_{n=t}^{t+W-1} x^2[n] )`, W = 10 ms, hop 2.5 ms;
`d(t) = L(t) - L(t - W)`. Modified z-score of |d| (Sec. 8), threshold z >= 6 and |d| >= 15 dB.
C3 uses the log-spectral distance between non-overlapping STFT frames
`D(m) = sqrt(mean_k (20log10|X[k,m]| - 20log10|X[k,m-4]|)^2)`.
Both respond to every natural onset; experiment v1.0 measured a 100 % false-positive rate,
so since v1.1 they are *supporting* observations only (never create or corroborate events).

## 4. Noise-floor consistency (C4)

Minimum statistics (Martin, 2001): in blocks of 0.25 s the 10th percentile of frame RMS
levels estimates the background level `N_b`; per mel band, the 10th percentile gives the
noise spectrum `S_b(k)`. For each block boundary b the medians over 4 blocks on each side
give a level step `dN = med(N_{b..b+3}) - med(N_{b-4..b-1})` and a shape change
`dS = RMS_k[(S_R - mean S_R) - (S_L - mean S_L)]`. Robust z of both, threshold z >= 4 and
(|dN| >= 6 dB or dS >= 6 dB). Assumes pauses exist; continuous content biases N upward.

## 5. Spectral holes (D2)

Perceptual codecs quantise MDCT coefficients per scale-factor band; masked bands become
exactly zero. For a noise-like, unquantised signal `P[k,m]` in a band is approximately
exponentially distributed, with median `mu ln 2`, so

`Pr(P < median * 10^{-R/10}) = 1 - exp(-ln2 * 10^{-R/10})` = 0.22 % for R = 25 dB.

The test reports the fraction of active time-frequency bins in 2 kHz..min(16 kHz, cutoff)
below `median_band(m) * 10^{-2.5}`. Threshold 3 % (14x the Gaussian baseline). Fails for
high-bitrate encodes and when decoding adds dither; spectral denoisers also create holes.

## 6. Band limit and resampling (D1, E1)

From the smoothed LTAS (150 Hz moving average, dB): stopband floor `F` = median level in
[0.965, 0.995] fs/2; stopband edge = highest f >= 1.5 kHz with level >= F + 15 dB; passband
level `P` = 90th percentile over [f_edge/2, f_edge]; reported cutoff `f_c` = highest f with
level >= P - 6 dB (the nominal edge of a digital filter); depth `P - F`; transition = width
between the 90 % and 10 % points of the drop. *Steep* = depth >= 25 dB and transition
<= max(600 Hz, 0.30 f_c). E1 reports an empty band when steep and `1 - f_c/(fs/2) >= 5 %`;
consistent source rates r satisfy `0.80 <= f_c/(r/2) <= 1.05`.
Downsampling leaves no such trace; a native recording through a band-limited microphone or
a codec low-pass produces the same signature, hence the cross-check with D2 in the
correlation engine (Sec. 10).

## 7. Interpolation periodicity (E2, experimental)

After interpolation by a factor L with a short kernel, the residual variance of a fixed
linear predictor varies with period L (Popescu & Farid, 2005). We compute the Welch
spectrum of `e^2[n] - mean` and report the peak-to-local-median ratio (65-bin median
filter) above 0.01 cycles/sample. Long windowed-sinc resamplers remove most of this trace.

## 8. Robust statistics (Module F and thresholds)

Modified z-score (Iglewicz & Hoaglin, 1993): `z = (x - median(x)) / (1.4826 * MAD)`,
`MAD = median|x - median(x)|`; the constant makes `1.4826*MAD` consistent for Gaussian
sigma. Robust to the very outliers being searched for, unlike mean/std.

* Isolation Forest (Liu, Ting & Zhou, 2008): average isolation path length over 200
  random trees; `decision_function < 0` flags easily isolated windows.
* PELT (Killick et al., 2012) with Gaussian mean-shift cost
  `C(a,b) = sum ||x_i||^2 - ||sum x_i||^2/(b-a)`, penalty `beta * d * ln n` (beta = 3),
  pruning `F(s) + C(s,t) <= F(t)`.
* Two-sample KS on spectral flatness of the quieter half of frames, 1 s either side.
* Delta-BIC (Chen & Gopalakrishnan, 1998):
  `dBIC = N log|S| - (N/2) log|S_1| - (N/2) log|S_2| - (lambda/2)(d + d(d+1)/2) log N`.

## 9. ENF phase continuity (C7)

Downsample to 1 kHz, 4th-order Butterworth band-pass f0 +/- 2 Hz (zero-phase), frames of
10 cycles, hop 1 cycle, phase `phi_k = arg sum_n w[n] h[n] e^{-j2pi f0 n/1000}` with an
absolute time index. Removing D samples shifts the hum phase by `2pi f0 D / fs (mod 2pi)`.
Step statistic `d_k = med(phi_{k..k+9}) - med(phi_{k-10..k-1})`, de-trended by its median;
threshold robust z >= 6 and |d| >= 0.35 rad. Blind to removals of an integer number of hum
periods; resolution about +/- 0.2 s (Rodriguez, Apolinario & Biscainho, 2010; Grigoras, 2005).

## 10. Histogram combing (D3)

If integer samples k are scaled by g and rounded, outputs are `round(g k)`. For g > 1
about `1 - 1/g` of the integers in the populated range become unreachable (empty bins);
for g < 1 some outputs receive two inputs (periodic peaks). Per 1 s block: histogram over
|code| <= median|code|, expected counts by Gaussian smoothing (sigma 4 codes), bins with
expectation >= 4; flagged if the empty fraction >= max(5 %, 5 x Poisson baseline
`mean exp(-lambda)`) or the spectrum of `h/expected - 1` has a peak >= 18 dB over its
median. Gains that are exact integer ratios (e.g. 0.5) and dithered re-quantisation are
invisible to this test.

## 11. Duplicated segments (C6)

Cosine similarity of mean-removed log-mel frames `s_ij = z_i . z_j`; runs of length >= 0.15 s
with `s >= 0.92` on diagonals of lag >= 0.5 s are candidates, ranked by
`(mean s - 0.92) * length`; each is verified by the normalised cross-correlation of the raw
waveforms over a +/- one-hop alignment search:
`NCC = sum (a - abar) b / (||a - abar|| ||b - bbar||)`. NCC >= 0.98 is reported.

## 12. Codec bandwidth consistency (D4)

For an MP3 file let `B_exp` be the low-pass of *this* encode: the LAME-tag value when
recorded, otherwise (v1.2) the measured libmp3lame cutoff for the file's CBR bitrate,
channel count and sample rate (`research/lame_lowpass_verification.md`). With `f_c` the
measured -6 dB band limit (Sec. 6), D4 reports an inconsistency when the band limit is
steep and `f_c < 0.85 B_exp`: content that ends well below what the current encoder keeps
was band-limited before this encoding (typically an earlier lower-bitrate encode). The
model is used only where it was measured with a steep edge; elsewhere D4 states that it
cannot check the file.

## 13. Correlation and indicator levels (Module G)

Each localised finding contributes anchors (point: its centre +/- max(80 ms, half-width);
region: both boundaries +/- 80 ms, 0.5 s for histogram blocks). Primary-family anchors are
merged into events when their intervals overlap; supporting (energy/spectral) and
statistical findings are attached as context only. The number of *independent* primary
families - after removing `noise` when explained by `silence` - gives
isolated (1), corroborated (2) or strongly corroborated (>= 3). Indicator levels are
ordinal rules (see `evidence/assessment.py`); no score is ever presented as a probability.
