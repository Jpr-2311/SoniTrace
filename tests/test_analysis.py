import numpy as np
from scipy.signal import butter, resample_poly, sosfilt

from sonictrace.analysis.signal_features import compute_frame_features, runs_of_true
from sonictrace.analysis.spectral_analysis import (
    candidate_source_rates,
    compute_ltas,
    compute_spectral_features,
    compute_stft,
    detect_bandlimit,
    mel_filterbank,
)
from sonictrace.analysis.splice_detection import lpc_residual
from sonictrace.analysis.stats import local_maxima, robust_z

SR = 44100


def sine(f=1000.0, a=0.5, dur=1.0):
    t = np.arange(int(SR * dur)) / SR
    return a * np.sin(2 * np.pi * f * t)


def test_rms_peak_zcr_of_sine():
    ff = compute_frame_features(sine(), SR, 2048, 512)
    mid = ff.rms[5:-5]
    assert np.allclose(mid, 0.5 / np.sqrt(2), rtol=0.01)
    assert np.allclose(ff.peak[5:-5], 0.5, rtol=0.01)
    assert np.allclose(ff.zcr[5:-5], 2 * 1000 / SR, rtol=0.05)


def test_spectral_descriptors():
    spec = compute_stft(sine(3000.0), SR, 2048, 512)
    sf_ = compute_spectral_features(spec)
    assert abs(np.median(sf_.centroid) - 3000) < 60
    assert np.median(sf_.flatness) < 0.01
    noise = np.random.default_rng(0).normal(0, 0.1, SR)
    nf = compute_spectral_features(compute_stft(noise, SR, 2048, 512))
    assert np.median(nf.flatness) > 0.4
    assert sf_.mfcc.shape[0] == 13 and sf_.log_mel.shape[0] == 40


def test_mel_filterbank_shape_and_coverage():
    fb = mel_filterbank(SR, 2048, 40)
    assert fb.shape == (40, 1025) and (fb >= 0).all() and (fb.sum(axis=0)[5:-5] > 0).all()


def test_bandlimit_detects_steep_lowpass_but_not_full_band():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.05, 3 * SR)
    f, p = compute_ltas(x, SR)
    assert not detect_bandlimit(f, p, SR).found
    up = resample_poly(resample_poly(x, 1, 2), 2, 1)  # 44.1 -> 22.05 -> 44.1 kHz
    up = np.round(up * 32767) / 32767
    f, p = compute_ltas(up, SR)
    bl = detect_bandlimit(f, p, SR)
    assert bl.found and bl.steep and 9000 < bl.cutoff_hz < 11600
    assert 22050 in candidate_source_rates(bl.cutoff_hz, SR)
    # a gentle acoustic-like roll-off is "found" but not steep
    soft = sosfilt(butter(2, 3000, fs=SR, output="sos"), x)
    f, p = compute_ltas(soft + rng.normal(0, 1e-5, len(soft)), SR)
    assert not detect_bandlimit(f, p, SR).steep


def test_lpc_residual_whitens_predictable_signal():
    x = sine(440.0) + np.random.default_rng(2).normal(0, 1e-3, SR)
    e = lpc_residual(x, 16, 4096)
    assert np.std(e[4096:]) < 0.01 * np.std(x)


def test_robust_z_and_helpers():
    x = np.r_[np.zeros(99), 10.0] + np.random.default_rng(3).normal(0, 0.01, 100)
    z = robust_z(x)
    assert z[-1] > 100 and np.abs(z[:-1]).max() < 6
    v = np.array([0, 5, 1, 0, 0, 7, 0])
    assert [i for i in local_maxima(v, 1) if v[i] > 0] == [1, 5]
    assert runs_of_true(np.array([0, 1, 1, 0, 1], bool)) == [(1, 3), (4, 5)]
