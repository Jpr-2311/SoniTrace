"""SonicTrace command-line interface."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Callable, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from . import METHODOLOGY_VERSION, __version__
from .config import AnalysisConfig
from .errors import SonicTraceError

app = typer.Typer(name="sonictrace", help="SonicTrace - explainable digital audio forensics engine.",
                  add_completion=False, no_args_is_help=True, pretty_exceptions_enable=False)
dataset_app = typer.Typer(help="Synthetic forensic dataset tools.", no_args_is_help=True)
app.add_typer(dataset_app, name="dataset")
console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)
STATE = {"debug": False}
LEVEL_STYLE = {"none": "green", "weak": "yellow", "moderate": "dark_orange", "strong": "bold red"}


@app.callback()
def _root(debug: bool = typer.Option(False, "--debug", help="Show tracebacks for unexpected errors.")) -> None:
    STATE["debug"] = debug


def _guard(fn: Callable[[], None]) -> None:
    """Run a command body; turn every failure into a clear message and a non-zero exit code."""
    try:
        fn()
    except typer.Exit:
        raise
    except SonicTraceError as exc:
        err_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(exc.exit_code)
    except KeyboardInterrupt:
        err_console.print("[yellow]Interrupted.[/yellow]")
        raise typer.Exit(130)
    except Exception as exc:  # never crash silently
        err_console.print(f"[bold red]Unexpected internal error:[/bold red] {type(exc).__name__}: {exc}")
        if STATE["debug"]:
            err_console.print(traceback.format_exc())
        else:
            err_console.print("Re-run with --debug for a traceback.")
        raise typer.Exit(1)


def _config(max_mib: Optional[float], max_duration: Optional[float]) -> AnalysisConfig:
    cfg = AnalysisConfig()
    if max_mib:
        cfg.max_file_bytes = int(max_mib * 1024 * 1024)
    if max_duration:
        cfg.max_duration_s = float(max_duration)
    return cfg


def _print_analysis(rep: dict) -> None:
    a = rep["assessment"]
    ident = rep["file_identity"]
    console.print(Panel.fit(
        f"[bold]{ident['file_name']}[/bold]  ({ident['size_bytes']} bytes, {rep['metadata']['identity']['container_description']})\n"
        f"SHA-256 {ident['sha256']}\n"
        f"Evidence unchanged after analysis: {'yes' if rep['integrity']['unchanged'] else 'NO'}\n"
        f"Audio: {rep['audio']['sample_rate']} Hz, {rep['audio']['channels']} ch, {rep['audio']['duration_s']:.3f} s, {rep['audio']['subtype']}",
        title="SonicTrace investigation"))
    lvl, st = a["local_edit_indicators"], a["structural_integrity"]
    console.print(f"Local edit indicators: [{LEVEL_STYLE[lvl]}]{lvl.upper()}[/]    "
                  f"Structural inconsistencies: [{LEVEL_STYLE[st]}]{st.upper()}[/]")
    t = Table(title="Forensic tests", show_lines=False)
    for c in ("ID", "Test", "Status", "Result", "Score", "Summary"):
        t.add_column(c, overflow="fold")
    for x in rep["tests"]:
        res = "[dark_orange]REPORTED[/]" if x["detected"] else "[green]-[/]"
        if x["status"] != "completed":
            res = f"[grey50]{x['status']}[/]"
        sc = f"{x['score']:.3g}" if isinstance(x["score"], (int, float)) else ""
        t.add_row(x["test_id"], x["name"] + (" (exp.)" if x.get("experimental") else ""), x["status"], res, sc, x["summary"])
    console.print(t)
    if rep["correlated_events"]:
        e = Table(title="Correlated events")
        for c in ("Event", "Time (s)", "Strength", "Independent families", "Possible explanations"):
            e.add_column(c, overflow="fold")
        for ev in rep["correlated_events"]:
            e.add_row(ev["event_id"], f"{ev['time_start']:.3f}-{ev['time_end']:.3f}", ev["strength"],
                      ", ".join(ev["independent_families"]), "; ".join(ev["explanations"]))
        console.print(e)
    obs = [f for f in rep["findings"] if f["category"] == "observed" and f["severity"] in ("medium", "high")]
    if obs:
        console.print("[bold]Observed technical evidence (medium/high):[/bold]")
        for f in obs[:20]:
            console.print(f"  {f['finding_id']} [{f['severity']}] {f['title']}")
    console.print("[bold]Processing history:[/bold]")
    for g in rep["global_assessments"]:
        console.print(f"  {g['topic']}: {g['status']} - {g['statement']}")
    console.print("[bold]Cannot be concluded:[/bold]")
    for c in a["cannot_be_concluded"][:7]:
        console.print(f"  - {c}")
    console.print(f"[grey50]{a['summary']}[/grey50]")


@app.command()
def analyze(
    file: Path = typer.Argument(..., help="Audio file to investigate (read-only)."),
    fmt: str = typer.Option("text", "--format", "-f", help="Console output: text or json."),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Write the JSON report here."),
    html_out: Optional[Path] = typer.Option(None, "--html-out", help="Write the HTML report (with figures) here."),
    no_stats: bool = typer.Option(False, "--no-stats", help="Skip Module F statistical anomaly detection."),
    max_mib: Optional[float] = typer.Option(None, "--max-mib", help="Maximum input size in MiB (default 512)."),
    max_duration: Optional[float] = typer.Option(None, "--max-duration", help="Maximum audio duration in seconds (default 600)."),
) -> None:
    """Run the full forensic investigation on one file."""
    def body() -> None:
        from .engine import ForensicEngine

        if fmt not in ("text", "json"):
            raise SonicTraceError("--format must be 'text' or 'json'.")
        with console.status("Analysing...", spinner="dots") if fmt == "text" else _nullctx():
            res = ForensicEngine(_config(max_mib, max_duration)).analyze(file, keep_context=html_out is not None, run_statistics=not no_stats)
        rep = res.to_dict()
        if json_out:
            from .reporting.json_report import write_json_report

            write_json_report(rep, json_out)
        if html_out:
            _write_html(res, rep, html_out)
        if fmt == "json":
            sys.stdout.write(json.dumps(rep, indent=2) + "\n")
        else:
            _print_analysis(rep)
            for p in (json_out, html_out):
                if p:
                    console.print(f"Wrote {p}")
    _guard(body)


class _nullctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _write_html(res, rep: dict, html_out: Path) -> dict:
    from .reporting.html_report import write_html_report
    from .reporting.visualizations import make_all

    fig_dir = html_out.parent / f"{html_out.stem}_figures"
    figs = make_all(res.context, rep, fig_dir, Path(rep["file_identity"]["file_name"]).stem)
    write_html_report(rep, html_out, figs)
    return figs


@app.command()
def report(
    file: Path = typer.Argument(..., help="Audio file to investigate."),
    out_dir: Path = typer.Option(Path("output/reports"), "--out-dir", "-o", help="Directory for HTML, JSON and figures."),
    max_mib: Optional[float] = typer.Option(None, "--max-mib", help="Maximum input size in MiB (default 512)."),
    max_duration: Optional[float] = typer.Option(None, "--max-duration", help="Maximum audio duration in seconds (default 600)."),
) -> None:
    """Generate the full HTML + JSON forensic report with figures."""
    def body() -> None:
        from .engine import ForensicEngine
        from .reporting.json_report import write_json_report

        with console.status("Analysing and rendering report...", spinner="dots"):
            res = ForensicEngine(_config(max_mib, max_duration)).analyze(file, keep_context=True)
            rep = res.to_dict()
            stem = Path(file).stem
            out_dir.mkdir(parents=True, exist_ok=True)
            jp = write_json_report(rep, out_dir / f"{stem}_report.json")
            hp = out_dir / f"{stem}_report.html"
            figs = _write_html(res, rep, hp)
        a = rep["assessment"]
        console.print(f"Local edit indicators: [{LEVEL_STYLE[a['local_edit_indicators']]}]{a['local_edit_indicators'].upper()}[/]; "
                      f"structural: {a['structural_integrity'].upper()}")
        console.print(f"HTML report : {hp}\nJSON report : {jp}\nFigures     : {len(figs)} PNG files in {hp.parent / (hp.stem + '_figures')}")
    _guard(body)


@app.command()
def metadata(file: Path = typer.Argument(..., help="Audio file to examine (read-only)."),
             as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """Extract file identity, technical metadata, tags and software signatures."""
    def body() -> None:
        from .parsers.codec_inspector import inspect_structure
        from .parsers.metadata import build_metadata, probe_ffprobe
        from .utils.hashing import sha256_file
        from .utils.validation import sniff_file, validate_input_file

        cfg = AnalysisConfig()
        p = validate_input_file(file, cfg.max_file_bytes)
        c = sniff_file(p)
        st = inspect_structure(p, c)
        meta = build_metadata(p, c, st, probe_ffprobe(p))
        meta["sha256"] = sha256_file(p)
        if as_json:
            sys.stdout.write(json.dumps(meta, indent=2, default=str) + "\n")
            return
        t = Table(title=f"Metadata: {p.name}")
        t.add_column("Field")
        t.add_column("Value", overflow="fold")
        t.add_row("sha256", meta["sha256"])
        for sect in ("identity", "technical"):
            for k, v in meta.get(sect, {}).items():
                t.add_row(f"{sect}.{k}", str(v))
        for k, v in meta["tags"].items():
            t.add_row(f"tag.{k}", str(v))
        for s in meta["software_signatures"]:
            t.add_row("software", f"{s['signature']}  ->  {s['product'] or 'unclassified'} ({s['category']})")
        console.print(t)
        if not meta["ffprobe"]["available"]:
            console.print("[yellow]FFprobe not found: technical metadata limited to SonicTrace's own parsers.[/yellow]")
    _guard(body)


@app.command()
def inspect(file: Path = typer.Argument(..., help="Audio file to examine (read-only)."),
            as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """Inspect the binary container structure (RIFF chunks, MP3 frames, FLAC blocks, Ogg pages, MP4 boxes)."""
    def body() -> None:
        from .parsers.codec_inspector import inspect_structure
        from .utils.validation import CONTAINER_NAMES, sniff_file, validate_input_file

        p = validate_input_file(file, AnalysisConfig().max_file_bytes)
        c = sniff_file(p)
        st = inspect_structure(p, c)
        d = st.to_dict()
        if as_json:
            sys.stdout.write(json.dumps(d, indent=2, default=str) + "\n")
            return
        console.print(Panel.fit(f"{p.name}: {CONTAINER_NAMES.get(c, c)} (parser {st.parser})", title="Binary structure"))
        det = d["details"]
        if c == "wav":
            t = Table(title="RIFF chunks")
            for col in ("ID", "Offset", "Declared size", "Present"):
                t.add_column(col)
            for ch in det["chunks"]:
                t.add_row(ch["chunk_id"], str(ch["offset"]), str(ch["size"]), str(ch["available"]))
            console.print(t)
            console.print(f"fmt: {det['fmt']}")
            if det.get("info"):
                console.print(f"LIST/INFO: {det['info']}")
            if det.get("bext"):
                console.print(f"bext: {det['bext']}")
        else:
            console.print_json(json.dumps({k: v for k, v in det.items() if k not in ("sync_gaps",)}, default=str))
        if d["signatures"]:
            console.print(f"Software signatures: {d['signatures']}")
        if st.issues:
            t = Table(title="Structural observations")
            for col in ("Severity", "Code", "Message"):
                t.add_column(col, overflow="fold")
            for i in st.issues:
                t.add_row(i.severity, i.code, i.message)
            console.print(t)
        else:
            console.print("[green]No structural inconsistencies found.[/green]")
    _guard(body)


@app.command()
def compare(
    original: Path = typer.Argument(..., help="Reference (original) recording."),
    modified: Path = typer.Argument(..., help="Questioned recording."),
    out_dir: Optional[Path] = typer.Option(None, "--out-dir", "-o", help="Write comparison JSON and figure here."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Controlled reference comparison: locate removed, inserted and re-levelled material."""
    def body() -> None:
        from .compare import compare_files

        res, a, b, sr = compare_files(original, modified)
        if out_dir:
            from .reporting.json_report import write_json_report
            from .reporting.visualizations import plot_comparison

            out_dir.mkdir(parents=True, exist_ok=True)
            write_json_report(res, out_dir / "comparison.json")
            plot_comparison(res, a, b, sr, out_dir / "comparison.png")
        if as_json:
            sys.stdout.write(json.dumps(res, indent=2) + "\n")
            return
        console.print(Panel.fit(f"reference  {res['reference']['path']}\n  sha256 {res['reference']['sha256']}\n"
                                f"questioned {res['questioned']['path']}\n  sha256 {res['questioned']['sha256']}\n"
                                f"identical bytes: {res['identical_files']}; matched blocks: {100 * res['matched_block_fraction']:.0f} %; "
                                f"global offset: {res['global_offset_s']} s", title="Comparison"))
        for n in res["notes"]:
            console.print(f"[yellow]{n}[/yellow]")
        if res["findings"]:
            for f in res["findings"][:40]:
                console.print(f"  [{f['type']}] {f['statement']}")
        else:
            console.print("[green]No alignment steps, unmatched blocks or gain changes found.[/green]")
        if out_dir:
            console.print(f"Wrote {out_dir / 'comparison.json'} and {out_dir / 'comparison.png'}")
    _guard(body)


@dataset_app.command("generate")
def dataset_generate(
    out: Path = typer.Option(Path("datasets/sonictrace_v1"), "--out", "-o", help="Output directory."),
    seed: int = typer.Option(1337, help="Master random seed."),
    sources: int = typer.Option(4, help="Source recordings per split."),
    controls: int = typer.Option(4, help="Unmodified control recordings per split."),
    duration: float = typer.Option(6.0, help="Duration of each recording (s)."),
    no_mp3: bool = typer.Option(False, "--no-mp3", help="Skip MP3 conditions (no FFmpeg needed)."),
) -> None:
    """Generate the reproducible synthetic dataset with ground truth and transformation logs."""
    def body() -> None:
        from .dataset.generator import generate_dataset

        per_split = sources * 17 + (sources // 2) + controls
        with Progress(TextColumn("[progress.description]{task.description}"), BarColumn(), MofNCompleteColumn(),
                      TimeElapsedColumn(), console=console) as prog:
            task = prog.add_task("Generating", total=2 * per_split)
            man = generate_dataset(out, seed=seed, sources_per_split=sources, controls_per_split=controls, duration=duration,
                                   include_mp3=not no_mp3, progress=lambda _: prog.advance(task))
        splits = {}
        for s in man.samples:
            splits[s.split] = splits.get(s.split, 0) + 1
        console.print(f"Generated {len(man.samples)} samples {splits} in {out} (seed {seed}). "
                      f"Manifest: {out / 'manifest.json'}, {out / 'manifest.csv'}")
        if not man.parameters["mp3_conditions"]:
            console.print("[yellow]MP3 conditions skipped (FFmpeg unavailable or --no-mp3).[/yellow]")
    _guard(body)


@app.command()
def benchmark(
    dataset: Path = typer.Option(Path("datasets/sonictrace_v1"), "--dataset", "-d", help="Dataset directory (with manifest.json)."),
    split: str = typer.Option("evaluation", help="calibration, evaluation or all."),
    out: Path = typer.Option(Path("output/benchmark"), "--out", "-o", help="Output directory."),
) -> None:
    """Score every technique against ground truth (precision/recall/F1, confusion, sensitivity)."""
    def body() -> None:
        from .benchmark import analyse_split, score_rows, write_benchmark
        from .dataset.manifest import load_manifest

        if split not in ("calibration", "evaluation", "all"):
            raise SonicTraceError("--split must be calibration, evaluation or all.")
        try:
            man = load_manifest(dataset)
        except FileNotFoundError as exc:
            raise SonicTraceError(str(exc)) from exc
        n = sum(1 for s in man["samples"] if split == "all" or s["split"] == split)
        with Progress(TextColumn("[progress.description]{task.description}"), BarColumn(), MofNCompleteColumn(),
                      TimeElapsedColumn(), console=console) as prog:
            task = prog.add_task(f"Benchmark ({split})", total=n)
            rows = analyse_split(dataset, split, progress=lambda _: prog.advance(task))
        scored = score_rows(rows)
        paths = write_benchmark(out, rows, scored, split)
        t = Table(title=f"Per-technique performance ({split}, methodology {METHODOLOGY_VERSION}) - synthetic data only")
        for c in ("Test", "Label", "TP", "FP", "TN", "FN", "Precision", "Recall", "F1", "FPR"):
            t.add_column(c)
        f = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
        for tid, m in scored["per_technique"].items():
            t.add_row(tid, m["label"], str(m["tp"]), str(m["fp"]), str(m["tn"]), str(m["fn"]), f(m["precision"]), f(m["recall"]), f(m["f1"]), f(m["false_positive_rate"]))
        console.print(t)
        for k, m in scored["correlated_assessment"].items():
            console.print(f"  {k}: P={f(m['precision'])} R={f(m['recall'])} F1={f(m['f1'])} FPR={f(m['false_positive_rate'])}")
        console.print(f"Wrote {paths['md']}, {paths['json']}, {paths['csv']}")
    _guard(body)


@app.command()
def version() -> None:
    """Show versions of SonicTrace and every analysis dependency."""
    def body() -> None:
        from .utils.tools import environment_report

        env = environment_report()
        t = Table(title=f"SonicTrace {__version__} (methodology {METHODOLOGY_VERSION})")
        t.add_column("Component")
        t.add_column("Version", overflow="fold")
        for k, v in env.items():
            t.add_row(k, str(v) if v else "[yellow]not found[/yellow]")
        console.print(t)
    _guard(body)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
