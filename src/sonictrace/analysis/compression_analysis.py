"""Module D: re-encoding and compression investigation.

D1  Spectral band limit (steep low-pass well below Nyquist).
D2  Spectral holes: time-frequency bins quantised to (near) zero by a perceptual codec.
D3  Quantisation: effective bit depth and sample-value histogram combing.
D4  Codec signature / bitrate / declared-bandwidth consistency.

Why D2 works: in MP3/AAC the MDCT coefficients of each scale-factor band are quantised
with a step chosen by the psychoacoustic model; whole bands whose content is masked are
set to zero. After decoding, the STFT shows bins far below their neighbours. For a
noise-like signal without such quantisation, |X|^2 in a band is approximately
exponentially distributed, so the fraction of bins more than R dB below the band median
is 1 - exp(-ln2 * 10^(-R/10)) (0.22 % for R = 25 dB). Ratios far above that baseline are
a codec fingerprint.

Why D3 works: if integer samples are multiplied by a gain g and re-rounded, the output
can only take values round(g*k); for g > 1 some integers become unreachable (empty
histogram bins at a regular spacing) and for g < 1 some receive two inputs (periodic
peaks). Cf. M. Stamm & K.J.R. Liu, "Forensic detection of image manipulation using
statistical intrinsic fingerprints", IEEE TIFS 5(3), 2010, for the analogous image case.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d

from ..evidence.evidence_model import Category, EvidenceRegistry, Localization, Severity, TestResult
from .codec_models import LAME_LIKE_ENCODERS, MODEL_SOURCE, expected_lame_cutoff
from .context import AnalysisContext
from .spectral_analysis import candidate_source_rates


# ----------------------------------------------------------------------------- D1
def run_spectral_cutoff(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    bl = ctx.bandlimit
    test = TestResult("D1", "Spectral band limit (codec/resampler low-pass)", "D: compression", "bandwidth",
                      score_name="drop depth (dB) of a steep band limit", threshold=cfg.cutoff_min_depth_db)
    test.measurements = bl.to_dict()
    below = bl.found and bl.cutoff_hz is not None and bl.cutoff_hz < (1 - cfg.nyquist_gap_fraction) * bl.nyquist_hz
    test.score = float(bl.depth_db) if (bl.found and bl.steep and below) else 0.0
    if bl.found and bl.steep and below:
        rates = candidate_source_rates(bl.cutoff_hz, ctx.sr)
        test.measurements["consistent_source_rates"] = rates
        f = reg.add_finding(
            "CMP", test_id=test.test_id, module=test.module, method="long-term spectrum band-limit detection", family="bandwidth",
            category=Category.OBSERVED, severity=Severity.MEDIUM,
            title=f"Content ends abruptly at {bl.cutoff_hz / 1000:.2f} kHz ({100 * bl.cutoff_ratio:.0f} % of Nyquist)",
            description=(f"The long-term spectrum drops by {bl.depth_db:.0f} dB within {bl.transition_hz:.0f} Hz at "
                         f"{bl.cutoff_hz:.0f} Hz although the file can represent frequencies up to {bl.nyquist_hz:.0f} Hz. "
                         "Acoustic roll-off is gradual; a drop this steep is typical of a digital low-pass filter."),
            localization=Localization.GLOBAL,
            measurements={"cutoff_hz": bl.cutoff_hz, "depth_db": bl.depth_db, "transition_hz": bl.transition_hz,
                          "cutoff_to_nyquist": bl.cutoff_ratio, "consistent_source_rates": rates},
            baseline={"min_depth_db": cfg.cutoff_min_depth_db, "max_transition_fraction": cfg.cutoff_max_transition_frac,
                      "nyquist_gap_fraction": cfg.nyquist_gap_fraction},
            alternative_explanations=["Lossy encoding (codec low-pass, e.g. MP3/AAC at moderate bitrates)",
                                      "Upsampling from a lower sample rate" + (f" (consistent with {', '.join(map(str, rates))} Hz)" if rates else ""),
                                      "Deliberate low-pass filtering / EQ", "Band-limited source (telephone, narrow-band microphone)"],
            limitations=["Cannot by itself distinguish codec, resampler or filter; see D2 and E1/E2."],
        )
        test.finding_ids.append(f.finding_id)
        test.detected = True
        test.summary = f"Steep band limit at {bl.cutoff_hz:.0f} Hz (depth {bl.depth_db:.0f} dB)."
    else:
        test.summary = f"No steep band limit below Nyquist ({bl.reason})."
    return test


# ----------------------------------------------------------------------------- D2
def spectral_hole_stats(ctx: AnalysisContext, rel_db: float) -> dict | None:
    spec = ctx.spec
    nyq = ctx.sr / 2.0
    hi = min(16000.0, 0.9 * nyq)
    bl = ctx.bandlimit
    if bl.found and bl.steep and bl.cutoff_hz:
        hi = min(hi, bl.cutoff_hz - 300.0)
    band = (spec.freqs >= 2000.0) & (spec.freqs <= hi)
    if band.sum() < 32:
        return None
    active = ctx.frames.rms_db[: spec.mag.shape[1]] > -100.0
    if active.sum() < 10:
        return None
    thr = 10 ** (-rel_db / 10.0)
    holes = 0
    total = 0
    per_frame = np.zeros(spec.mag.shape[1])
    for s in range(0, spec.mag.shape[1], 2048):
        p = spec.mag[band, s : s + 2048].astype(np.float64) ** 2
        med = np.median(p, axis=0)
        h = p < (med * thr)[None, :]
        cnt = h.sum(axis=0)
        per_frame[s : s + p.shape[1]] = cnt / p.shape[0]
        act = active[s : s + p.shape[1]] & (med > 0)
        holes += int(cnt[act].sum())
        total += int(act.sum()) * p.shape[0]
    ratio = holes / total if total else 0.0
    return {"ratio": ratio, "per_frame": per_frame, "band_hz": [2000.0, hi], "bins": int(band.sum()),
            "baseline_noise_ratio": float(1 - np.exp(-np.log(2) * thr))}


def run_spectral_holes(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    test = TestResult("D2", "Spectral holes (codec quantisation to zero)", "D: compression", "codec_holes",
                      score_name="fraction of TF bins > 25 dB below band median", threshold=cfg.hole_ratio_threshold)
    st = spectral_hole_stats(ctx, cfg.hole_rel_db)
    if st is None:
        test.status = "not_applicable"
        test.summary = "Insufficient bandwidth or active frames above 2 kHz."
        return test
    ctx.cache["spectral_holes"] = st
    test.score = st["ratio"]
    test.measurements = {"hole_ratio": st["ratio"], "analysis_band_hz": st["band_hz"],
                         "gaussian_noise_baseline": st["baseline_noise_ratio"],
                         "frames_with_over_10pct_holes": float(np.mean(st["per_frame"] > 0.1))}
    if st["ratio"] >= cfg.hole_ratio_threshold:
        f = reg.add_finding(
            "CMP", test_id=test.test_id, module=test.module, method="STFT bin-level hole statistics", family="codec_holes",
            category=Category.OBSERVED, severity=Severity.MEDIUM,
            title=f"{100 * st['ratio']:.1f} % of time-frequency bins are spectral holes",
            description=(f"In {st['band_hz'][0]:.0f}-{st['band_hz'][1]:.0f} Hz, {100 * st['ratio']:.2f} % of active time-frequency bins lie "
                         f"more than {cfg.hole_rel_db:.0f} dB below their frame's band median, against "
                         f"{100 * st['baseline_noise_ratio']:.2f} % expected for unquantised noise-like content."),
            localization=Localization.GLOBAL,
            measurements={"hole_ratio": st["ratio"], "expected_ratio_unquantised": st["baseline_noise_ratio"]},
            baseline={"ratio_threshold": cfg.hole_ratio_threshold, "relative_level_db": cfg.hole_rel_db},
            alternative_explanations=["Decoded perceptual codec (MP3, AAC, Vorbis, Opus) at some point in the file's history",
                                      "Spectral noise reduction / denoising that zeroes bins", "Very sparse synthetic content (pure tones)"],
            limitations=["High-bitrate encodes leave few holes; dithered decoding partially fills them."],
        )
        test.finding_ids.append(f.finding_id)
        test.detected = True
        test.summary = f"Hole ratio {100 * st['ratio']:.2f} % (baseline {100 * st['baseline_noise_ratio']:.2f} %): codec quantisation pattern."
    else:
        test.summary = f"Hole ratio {100 * st['ratio']:.2f} %: no codec-like spectral holes."
    return test


# ----------------------------------------------------------------------------- D3
def integer_codes(ctx: AnalysisContext) -> tuple[np.ndarray | None, int | None, str]:
    a = ctx.audio
    if a.is_integer_pcm and a.bit_depth:
        scale = 2.0 ** (a.bit_depth - 1)
        return np.round(a.samples * scale).astype(np.int64), a.bit_depth, "integer PCM container"
    if not a.lossy_decoded and a.subtype in ("FLOAT", "DOUBLE"):
        for bits in (16, 24):
            scaled = a.samples * 2.0 ** (bits - 1)
            if np.max(np.abs(scaled - np.round(scaled))) < 1e-6:
                return np.round(scaled).astype(np.int64), bits, f"float container holding {bits}-bit grid values"
    return None, None, "no integer sample grid (lossy-decoded or true floating-point data)"


def histogram_comb_blocks(codes: np.ndarray, sr: int, block_s: float, min_expected: float) -> list[dict]:
    block = max(1024, int(block_s * sr))
    hop = block // 2
    out = []
    for s in range(0, max(1, len(codes) - block + 1), hop):
        c = codes[s : s + block]
        a = np.abs(c)
        R = int(min(np.percentile(a, 50), 30000))  # densest part of the amplitude distribution
        if R < 64:
            continue
        sel = c[a <= R]
        h = np.bincount(sel + R, minlength=2 * R + 1).astype(np.float64)
        expected = gaussian_filter1d(h, sigma=4.0, mode="nearest")
        valid = expected >= min_expected
        if valid.sum() < 64:
            continue
        hv, ev = h[valid], expected[valid]
        empty = float(np.mean(hv == 0))
        baseline = float(np.mean(np.exp(-ev)))
        r = hv / ev - 1.0
        spec = np.abs(np.fft.rfft(r - r.mean()))
        spec = spec[5:]
        periodicity = float(20 * np.log10(spec.max() / (np.median(spec) + 1e-12) + 1e-12)) if spec.size > 8 else 0.0
        out.append({"start": s, "end": s + block, "empty_fraction": empty, "poisson_baseline": baseline, "periodicity_db": periodicity})
    return out


def run_quantization(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    sr = ctx.sr
    test = TestResult("D3", "Quantisation: bit depth and histogram combing", "D: compression", "quantization",
                      score_name="max block empty-bin fraction", threshold=cfg.comb_empty_fraction)
    codes, bits, how = integer_codes(ctx)
    test.measurements["sample_grid"] = how
    if codes is None:
        test.status = "not_applicable"
        test.summary = "No integer sample grid to analyse (" + how + ")."
        return test
    nz = np.abs(codes[codes != 0])
    container_bits = ctx.audio.bit_depth if ctx.audio.is_integer_pcm else bits
    if nz.size:
        acc = int(np.bitwise_or.reduce(nz))
        tz = (acc & -acc).bit_length() - 1
        eff = container_bits - tz
        test.measurements.update({"container_bits": container_bits, "effective_bits": eff, "always_zero_lsbs": tz})
        if tz >= 4 and container_bits > 8:
            f = reg.add_finding(
                "QNT", test_id=test.test_id, module=test.module, method="bitwise OR of all sample codes", family="quantization",
                category=Category.OBSERVED, severity=Severity.LOW,
                title=f"{container_bits}-bit container carries only {eff}-bit audio",
                description=f"The lowest {tz} bits of every non-zero sample are zero: the audio was quantised to {eff} bits before being stored at {container_bits} bits.",
                localization=Localization.GLOBAL, measurements={"effective_bits": eff, "zero_lsbs": tz},
                alternative_explanations=["Format conversion from a lower bit depth (e.g. 16-bit material exported as 24-bit)",
                                          "Recorder with a lower-resolution converter writing a wider container"],
            )
            test.finding_ids.append(f.finding_id)
    elif not ctx.audio.is_integer_pcm:
        test.measurements["container_bits"] = None
    if not ctx.audio.is_integer_pcm and bits:
        f = reg.add_finding(
            "QNT", test_id=test.test_id, module=test.module, method="grid test of floating-point samples", family="quantization",
            category=Category.OBSERVED, severity=Severity.INFO,
            title=f"Floating-point file contains exact {bits}-bit values",
            description=f"Every sample is an exact multiple of 2^-{bits - 1}: the data was {bits}-bit integer PCM before conversion to float.",
            localization=Localization.GLOBAL, alternative_explanations=["Lossless conversion from integer PCM to float"],
        )
        test.finding_ids.append(f.finding_id)
    blocks = histogram_comb_blocks(codes[:, 0], sr, cfg.comb_block_s, cfg.comb_min_expected)
    test.measurements["analysed_blocks"] = len(blocks)
    if not blocks:
        test.summary = "Signal too quiet for histogram analysis."
        return test
    flags = []
    for b in blocks:
        comb = b["empty_fraction"] >= max(cfg.comb_empty_fraction, 5 * b["poisson_baseline"])
        periodic = b["periodicity_db"] >= cfg.comb_periodicity_db
        b["flagged"] = bool(comb or periodic)
        b["kind"] = "missing codes" if comb else ("periodic code doubling" if periodic else "")
        flags.append(b["flagged"])
    ctx.cache["histogram_blocks"] = blocks
    test.score = float(max(b["empty_fraction"] for b in blocks))
    test.measurements["max_periodicity_db"] = float(max(b["periodicity_db"] for b in blocks))
    test.measurements["flagged_block_fraction"] = float(np.mean(flags))
    # merge consecutive flagged blocks into regions
    regions = []
    cur = None
    for b in blocks:
        if b["flagged"]:
            if cur and b["start"] <= cur["end"]:
                cur["end"] = b["end"]
                cur["blocks"].append(b)
            else:
                cur = {"start": b["start"], "end": b["end"], "blocks": [b]}
                regions.append(cur)
    # v1.1: a comb present almost everywhere is a whole-file gain change (normalisation / volume change),
    # a routine processing step with no edit boundaries (benchmark v1.0: 3/4 normalised controls flagged as local edits).
    whole_file = float(np.mean(flags)) >= cfg.comb_global_fraction
    test.measurements["whole_file_gain_processing"] = whole_file
    if whole_file:
        f = reg.add_finding(
            "QNT", test_id=test.test_id, module=test.module, method="sample-value histogram comb / periodicity analysis",
            family="processing", category=Category.OBSERVED, severity=Severity.LOW,
            title=f"Histogram combing across {100 * np.mean(flags):.0f} % of the file (whole-file digital gain change)",
            description=("Missing or doubled sample values occur throughout the recording: the whole file was scaled digitally "
                         "after quantisation. This is the fingerprint of normalisation or a volume change, not of a local edit."),
            localization=Localization.GLOBAL,
            measurements={"flagged_block_fraction": float(np.mean(flags)),
                          "max_empty_fraction": float(max(b["empty_fraction"] for b in blocks))},
            baseline={"global_fraction_threshold": cfg.comb_global_fraction},
            alternative_explanations=["Peak/loudness normalisation", "Volume change on export", "Format conversion with scaling"],
        )
        test.finding_ids.append(f.finding_id)
        regions = []
    for rg in regions:
        ef = max(x["empty_fraction"] for x in rg["blocks"])
        pd = max(x["periodicity_db"] for x in rg["blocks"])
        t0, t1 = rg["start"] / sr, min(rg["end"], len(codes)) / sr
        f = reg.add_finding(
            "QNT", test_id=test.test_id, module=test.module, method="sample-value histogram comb / periodicity analysis",
            family="quantization", category=Category.OBSERVED, severity=Severity.MEDIUM,
            title=f"Histogram combing in {t0:.2f}-{t1:.2f} s (digital amplitude scaling after quantisation)",
            description=(f"In this region up to {100 * ef:.1f} % of well-populated sample values never occur "
                         f"(periodicity {pd:.0f} dB). Rounding after a digital gain change produces exactly this pattern."),
            localization=Localization.REGION, time_start=t0, time_end=t1, sample_start=int(rg["start"]), sample_end=int(rg["end"]),
            measurements={"max_empty_fraction": ef, "max_periodicity_db": pd, "blocks": len(rg["blocks"])},
            baseline={"empty_fraction_threshold": cfg.comb_empty_fraction, "periodicity_threshold_db": cfg.comb_periodicity_db},
            alternative_explanations=["Digital gain change / normalisation applied to already-quantised audio",
                                      "Sample-format conversion with scaling", "Some lossless DSP chains (e.g. fixed-point mixing)"],
            limitations=["Gains that are integer ratios (e.g. exactly 0.5) map codes onto codes without a comb and are not detected.",
                         "Dither added after the gain change hides the comb."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(regions)
    if whole_file:
        test.summary = "Whole-file histogram combing: global gain change (e.g. normalisation); no local gain-edit region."
    else:
        test.summary = (f"{len(regions)} region(s) with histogram combing covering {100 * np.mean(flags):.0f} % of analysed blocks."
                        if regions else "Sample-value histogram is smooth (no evidence of post-quantisation gain).")
    return test


# ----------------------------------------------------------------------------- D4
def run_codec_consistency(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    test = TestResult("D4", "Codec signature, bitrate and declared-bandwidth consistency", "D: compression", "codec_metadata",
                      score_name="number of inconsistencies")
    st = ctx.structure
    meta = ctx.metadata or {}
    bl = ctx.bandlimit
    n_issues = 0
    tech = meta.get("technical", {})
    sigs = meta.get("software_signatures", [])
    test.measurements = {"codec": tech.get("codec_name"), "signatures": [s["signature"] for s in sigs]}
    lossless_container = ctx.audio.is_integer_pcm or ctx.audio.subtype in ("FLOAT", "DOUBLE")
    checkable = None
    if st is not None and st.container == "mp3":
        d = st.details
        vbr = d.get("vbr_header") or {}
        lp = vbr.get("lowpass_hz") or None  # FFmpeg's muxer writes 0 = "not recorded"
        mean_br = d.get("bitrate_kbps_mean")
        channels = 1 if d.get("channel_mode") == "mono" else 2
        expected, source = (float(lp), "lame_tag") if lp else (None, None)
        # v1.2: FFmpeg-written tags never record the low-pass, so D4 could not fire on them; fall back to the
        # measured libmp3lame model, only for the configurations it covers (CBR, MPEG-1 Layer III, 44.1/48 kHz)
        encoder = str(vbr.get("encoder") or "")
        if expected is None and d.get("bitrate_mode") == "CBR" and d.get("mpeg_version") == "1" and d.get("layer") == 3 \
                and mean_br and encoder.startswith(LAME_LIKE_ENCODERS):
            model = expected_lame_cutoff(d.get("sample_rate"), channels, mean_br)
            if model:
                expected, source = model, "measured_libmp3lame_model"
        checkable = expected is not None
        test.measurements.update({"encoder": encoder or None, "encoder_lowpass_hz": lp, "mean_bitrate_kbps": mean_br,
                                  "bitrate_mode": d.get("bitrate_mode"), "channels": channels,
                                  "expected_cutoff_hz": expected, "expected_cutoff_source": source,
                                  "measured_cutoff_hz": bl.cutoff_hz if bl.found else None,
                                  "encoder_delay": vbr.get("encoder_delay"), "encoder_padding": vbr.get("encoder_padding")})
        if not checkable:
            test.limitations.append("The encoder low-pass is not recorded and the measured libmp3lame model does not cover this "
                                    "configuration (VBR/ABR, MPEG-2/2.5, other encoder or sample rate): no bandwidth cross-check.")
        if checkable and bl.found and bl.steep and bl.cutoff_hz and bl.cutoff_hz < 0.85 * expected:
            n_issues += 1
            from_tag = source == "lame_tag"
            why = (f"the encoder applied a {expected:.0f} Hz low-pass (LAME tag)" if from_tag else
                   f"libmp3lame applies a low-pass at about {expected:.0f} Hz for {mean_br:.0f} kbit/s CBR "
                   f"{'mono' if channels == 1 else 'stereo'} at {d.get('sample_rate')} Hz (measured model; this file's "
                   f"'{encoder}' tag records no low-pass)")
            f = reg.add_finding(
                "CMP", test_id=test.test_id, module=test.module,
                method="LAME-tag lowpass vs. measured band limit" if from_tag else "measured libmp3lame low-pass model vs. measured band limit",
                family="codec_metadata", category=Category.OBSERVED, severity=Severity.MEDIUM if from_tag else Severity.LOW,
                title="Audio bandwidth is narrower than this encode can explain",
                description=(f"For this encode {why}, but the audio content already ends at {bl.cutoff_hz:.0f} Hz "
                             f"({100 * bl.cutoff_hz / expected:.0f} % of the expected bandwidth). The material was band-limited "
                             "before this encoding - typically by an earlier, lower-bitrate lossy encode (transcoding) or by resampling."),
                localization=Localization.GLOBAL,
                measurements={"expected_cutoff_hz": expected, "expected_cutoff_source": source, "measured_cutoff_hz": bl.cutoff_hz,
                              "bitrate_kbps": mean_br, "channels": channels},
                baseline={"flag_below_fraction_of_expected": 0.85, "model": None if from_tag else MODEL_SOURCE},
                alternative_explanations=["Transcoding from a lower-bitrate lossy source", "Band-limited original material", "Prior resampling"]
                + ([] if from_tag else ["An encoder other than libmp3lame, or a non-default low-pass setting"]),
                limitations=[] if from_tag else ["The expected low-pass comes from an empirical libmp3lame model; other encoders "
                                                 "and custom --lowpass settings behave differently.",
                                                 "Transcodes between bitrates with similar low-pass (within 15 %) are not detected."],
            )
            test.finding_ids.append(f.finding_id)
    if lossless_container and ctx.structure is not None:
        products = {s["product"] for s in sigs if s.get("product")}
        if products:
            f = reg.add_finding(
                "MET", test_id=test.test_id, module=test.module, method="metadata software-signature scan", family="metadata",
                category=Category.OBSERVED, severity=Severity.INFO,
                title=f"Writing software identified: {', '.join(sorted(products))}",
                description="The file's metadata names the software that wrote it. This documents the last processing step only.",
                localization=Localization.GLOBAL, measurements={"signatures": [s["signature"] for s in sigs]},
                alternative_explanations=["Legitimate conversion or export", "Editing session"],
            )
            test.finding_ids.append(f.finding_id)
    test.score = float(n_issues)
    test.detected = n_issues > 0
    f = reg.add_finding(
        "CMP", test_id=test.test_id, module=test.module, method="scope statement", family="codec_metadata",
        category=Category.UNDETERMINED, severity=Severity.INFO,
        title="Number of compression generations cannot be established",
        description=("Detecting how many times a signal was lossily encoded requires access to the codec's internal frame grid "
                     "and quantiser (e.g. MDCT-coefficient statistics). SonicTrace measures the band-limit and spectral-hole "
                     "fingerprints of *at least one* lossy generation; it does not count generations."),
        localization=Localization.GLOBAL,
    )
    test.finding_ids.append(f.finding_id)
    if n_issues:
        test.summary = f"{n_issues} codec/bandwidth inconsistency(ies)."
    elif checkable is False:
        test.summary = "MP3 bandwidth cross-check not possible (no recorded low-pass, configuration outside the measured model)."
    else:
        test.summary = "No codec/bandwidth inconsistency found."
    return test
