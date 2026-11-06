"""Forensic figures (matplotlib, non-interactive Agg backend)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

FAMILY_ROWS = ["structure", "metadata", "waveform", "short_time", "noise", "silence", "duplication", "enf",
               "quantization", "bandwidth", "codec_holes", "statistical"]
FAMILY_COLORS = {"waveform": "#d62728", "short_time": "#ff7f0e", "noise": "#2ca02c", "silence": "#9467bd",
                 "duplication": "#8c564b", "enf": "#e377c2", "quantization": "#17becf", "statistical": "#7f7f7f"}
STRENGTH_COLORS = {"isolated": "#ffd54f", "corroborated": "#ff8a65", "strongly_corroborated": "#e53935"}


def _envelope(x: np.ndarray, width: int = 2000) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(x)
    step = max(1, n // width)
    m = n // step
    xx = x[: m * step].reshape(m, step)
    return np.arange(m) * step, xx.min(axis=1), xx.max(axis=1)


def _shade_events(ax, events: list[dict]) -> None:
    for e in events:
        ax.axvspan(e["time_start"], e["time_end"], color=STRENGTH_COLORS.get(e["strength"], "#ffd54f"), alpha=0.35, lw=0)


def plot_waveform(ctx, report: dict, path: Path) -> Path:
    idx, lo, hi = _envelope(ctx.x)
    t = idx / ctx.sr
    fig, ax = plt.subplots(figsize=(11, 3))
    ax.fill_between(t, lo, hi, color="#1f77b4", lw=0)
    _shade_events(ax, report["correlated_events"])
    ax.set(xlabel="time (s)", ylabel="amplitude", title="Waveform (shaded: correlated events; yellow isolated, orange corroborated, red strong)",
           xlim=(0, ctx.duration))
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def plot_spectrogram(ctx, report: dict, path: Path) -> Path:
    spec = ctx.spec
    step = max(1, spec.mag.shape[1] // 1500)
    S = 20 * np.log10(spec.mag[:, ::step] + 1e-9)
    fig, ax = plt.subplots(figsize=(11, 4))
    vmax = float(np.percentile(S, 99.5))
    im = ax.imshow(S, origin="lower", aspect="auto", cmap="magma", vmin=vmax - 100, vmax=vmax,
                   extent=(0, ctx.duration, 0, ctx.sr / 2000))
    for e in report["correlated_events"]:
        ax.axvline(0.5 * (e["time_start"] + e["time_end"]), color="cyan", lw=0.8, ls="--")
    bl = report["signal_summary"]["band_limit"]
    if bl.get("found") and bl.get("steep"):
        ax.axhline(bl["cutoff_hz"] / 1000, color="lime", lw=1, ls=":")
    ax.set(xlabel="time (s)", ylabel="frequency (kHz)", title="STFT spectrogram (dB; dashed: events, dotted: band limit)")
    fig.colorbar(im, ax=ax, pad=0.01)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def plot_ltas(ctx, report: dict, path: Path) -> Path:
    f, p = ctx.ltas_freqs, ctx.ltas_psd
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.plot(f / 1000, 10 * np.log10(p + 1e-30), lw=0.8)
    bl = report["signal_summary"]["band_limit"]
    if bl.get("cutoff_hz"):
        ax.axvline(bl["cutoff_hz"] / 1000, color="r", ls="--", lw=1, label=f"highest content {bl['cutoff_hz']:.0f} Hz ({'steep' if bl['steep'] else 'gradual'})")
    ax.axvline(ctx.sr / 2000, color="k", ls=":", lw=1, label=f"Nyquist {ctx.sr / 2:.0f} Hz")
    ax.set(xlabel="frequency (kHz)", ylabel="PSD (dB/Hz)", title="Long-term average spectrum (Welch)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def plot_rms(ctx, report: dict, path: Path) -> Path:
    ff = ctx.frames
    fig, ax = plt.subplots(figsize=(11, 3))
    ax.plot(ff.times, np.maximum(ff.rms_db, -120), lw=0.8, label="frame RMS")
    _shade_events(ax, report["correlated_events"])
    ax.set(xlabel="time (s)", ylabel="dBFS", title=f"RMS energy timeline (frame {ff.frame_length} samples)", xlim=(0, ctx.duration))
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def plot_noise_floor(ctx, report: dict, path: Path) -> Path:
    prof = ctx.cache.get("noise_profile")
    fig, ax = plt.subplots(figsize=(11, 3))
    if prof is not None:
        ax.step(prof.block_times, np.maximum(prof.level_db, -120), where="mid", label="noise-floor estimate (10th pct.)")
        ax.axhline(prof.global_floor_db, color="gray", ls=":", label=f"median {prof.global_floor_db:.1f} dBFS")
        ax.legend(fontsize=8)
    for fdict in report["findings"]:
        if fdict["family"] == "noise" and fdict["time_start"] is not None:
            ax.axvline(0.5 * (fdict["time_start"] + fdict["time_end"]), color="g", ls="--")
    ax.set(xlabel="time (s)", ylabel="dBFS", title="Background noise floor (minimum statistics)", xlim=(0, ctx.duration))
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def plot_timeline(ctx, report: dict, path: Path) -> Path:
    fams = [r for r in FAMILY_ROWS if any(f["family"] == r and f["time_start"] is not None for f in report["findings"])] or ["waveform"]
    fig, ax = plt.subplots(figsize=(11, 0.5 * len(fams) + 1.6))
    _shade_events(ax, report["correlated_events"])
    for i, fam in enumerate(fams):
        for f in report["findings"]:
            if f["family"] != fam or f["time_start"] is None:
                continue
            c = FAMILY_COLORS.get(fam, "#333333")
            if f["localization"] == "region" and f["time_end"] - f["time_start"] > 0.01:
                ax.plot([f["time_start"], f["time_end"]], [i, i], color=c, lw=6, solid_capstyle="butt")
            else:
                ax.plot([0.5 * (f["time_start"] + (f["time_end"] or f["time_start"]))], [i], marker="|", ms=16, mew=2, color=c)
    ax.set_yticks(range(len(fams)), fams)
    ax.set(xlim=(0, ctx.duration), xlabel="time (s)", title="Suspicious-region timeline by evidence family")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def make_all(ctx, report: dict, out_dir: Path, stem: str) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plots = {
        "waveform": plot_waveform, "spectrogram": plot_spectrogram, "frequency": plot_ltas,
        "rms": plot_rms, "noise_floor": plot_noise_floor, "timeline": plot_timeline,
    }
    return {k: fn(ctx, report, out_dir / f"{stem}_{k}.png") for k, fn in plots.items()}


def plot_comparison(cmp: dict, ref: np.ndarray, cand: np.ndarray, sr: int, path: Path) -> Path:
    fig, axes = plt.subplots(3, 1, figsize=(11, 8))
    for x, lab in ((ref, "reference"), (cand, "questioned")):
        idx, lo, hi = _envelope(x)
        axes[0].fill_between(idx / sr, lo, hi, alpha=0.5, lw=0, label=lab)
    axes[0].legend(fontsize=8)
    axes[0].set(title="Waveforms (reference vs. questioned)", xlabel="time (s)")
    blocks = cmp["blocks"]
    t = [b["time_s"] for b in blocks]
    axes[1].plot(t, [b["offset_s"] if b["ncc"] >= 0.5 else np.nan for b in blocks], "o-", ms=3)
    axes[1].set(title="Alignment offset of questioned file vs. reference (jumps = removed/inserted material)",
                xlabel="questioned time (s)", ylabel="offset (s)")
    axes[2].plot(t, [b["ncc"] for b in blocks], ".-", label="block NCC")
    axes[2].plot(t, [b["gain_db"] / 20 if b["gain_db"] is not None else np.nan for b in blocks], ".-", label="gain (dB/20)")
    axes[2].axhline(0.5, color="gray", ls=":")
    axes[2].legend(fontsize=8)
    axes[2].set(title="Block similarity and gain", xlabel="questioned time (s)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
