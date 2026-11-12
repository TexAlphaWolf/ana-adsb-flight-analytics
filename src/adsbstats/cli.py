"""Command line: generate, analyze, verify, bench, render."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable, Iterator
from dataclasses import fields
from pathlib import Path
from typing import Any

from . import __version__, analysis, bench, flights, report, verify
from .airports import AirportError, load_airports
from .generate import generate
from .params import Params
from .trace import Aircraft, ReadStats, TraceError, read_path

Error = (TraceError, AirportError, ValueError, OSError)

HELP = {
    "max_kt": "ground speed (kt) above which a move is a jump",
    "jump_km": "shortest move (km) that can be a jump",
    "gap_s": "silence (s) that ends a leg",
    "min_air_points": "fewest airborne points in a flight",
    "min_air_s": "shortest flight (s)",
    "min_air_km": "shortest flight (km of ground covered)",
    "airport_km": "farthest an airport can be (km) to be named",
    "low_ft": "highest altitude (ft) at which an end of a flight is named after an airport",
    "weight_cap_s": "most seconds one position report counts for",
    "alt_bin_ft": "width of an altitude bin (ft)",
    "speed_bin_kt": "width of a ground speed bin (kt)",
}


def params_from(args: argparse.Namespace) -> Params:
    given = {f.name: getattr(args, f.name) for f in fields(Params) if getattr(args, f.name, None) is not None}
    return Params(**given)


def parse_bbox(text: str | None) -> tuple[float, float, float, float] | None:
    if text is None:
        return None
    try:
        a, b, c, d = (float(x) for x in text.split(","))
    except ValueError as exc:
        raise ValueError("--bbox needs four numbers: lat0,lon0,lat1,lon1") from exc
    if not (a < c and b < d) or not (-90 <= a <= 90 and -90 <= c <= 90 and -180 <= b <= 180 and -180 <= d <= 180):
        raise ValueError("--bbox needs lat0 < lat1 and lon0 < lon1, within the globe")
    return (a, b, c, d)


def summary_lines(rep: dict[str, Any]) -> list[str]:
    a = rep["analysis"]
    t = a["totals"]
    lines = [
        f"{rep['source']}: {t['aircraft']:,} aircraft, {t['points']:,} position reports, {t['flights']:,} flights, "
        f"{t['distance_km']:,.0f} km in {t['airborne_h']:,.1f} h",
    ]
    if t["flights"]:
        lines.append(
            f"busiest hour {a['peak_hour']:02d}:00 UTC, {report.pct(a['above_fl240'])} of airborne time above 24,000 ft, "
            f"origin unknown for {t['origin_unknown']:,} flights, destination for {t['destination_unknown']:,}"
        )
    lines.append(f"{t['glitches']:,} glitches removed, {t['legs']:,} legs")
    acc = a_acc = rep["accuracy"]
    if acc:
        f = a_acc["flights"]
        lines.append(
            f"against the truth: {f['matched']:,} of {f['true']:,} flights found, {f['extra']:,} extra, "
            f"origin right for {acc['airports']['origin_correct']:,}, destination for {acc['airports']['destination_correct']:,}"
        )
    return lines


PROGRESS_EVERY = 5000


def watch(aircraft: Iterable[Aircraft], stats: ReadStats, t0: float, every: int = 0) -> Iterator[Aircraft]:
    """The same aircraft, with a line on stderr every `every` aircraft (a real day takes minutes)."""
    every = every or PROGRESS_EVERY
    for ac in aircraft:
        yield ac
        if stats.aircraft % every == 0:
            print(
                f"  {stats.aircraft:,} aircraft, {stats.points:,} reports, {time.perf_counter() - t0:.0f} s",
                file=sys.stderr,
                flush=True,
            )


def cmd_generate(a: argparse.Namespace) -> int:
    out = Path(a.directory)
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"{out} is not empty")
    g = generate(a.aircraft, a.seed, clean=a.clean)
    n = g.write(out)
    print(f"written: {out} ({n:,} trace files, {len(g.flights):,} flights, faults {g.stats})")
    return 0


def cmd_analyze(a: argparse.Namespace) -> int:
    p = params_from(a)
    truth = None
    t0 = time.perf_counter()
    if a.path:
        root = Path(a.path)
        ap_path = Path(a.airports) if a.airports else (root / "airports.csv" if root.is_dir() else None)
        airports = load_airports(ap_path) if ap_path and ap_path.exists() else []
        if a.airports and not airports:
            raise ValueError(f"no airports in {a.airports}")
        truth_path = Path(a.truth) if a.truth else (root / "truth.json" if root.is_dir() else None)
        if truth_path and truth_path.exists():
            truth = json.loads(truth_path.read_text(encoding="utf-8"))
        elif a.truth:
            raise ValueError(f"cannot read the truth file {a.truth}")
        stats = ReadStats()
        aircraft: Iterable[Aircraft] = watch(
            read_path(root, stats, a.limit, parse_bbox(a.bbox)), stats, t0
        )  # one aircraft at a time: a day does not fit in memory
        source = str(a.path) if not a.name else a.name
    else:
        if a.truth or a.airports or a.bbox or a.limit:
            raise ValueError("--truth, --airports, --bbox and --limit need a path to read")
        g = generate(150, 1)
        aircraft, airports, truth, stats = g.aircraft(), g.airports, g.truth(), None
        source = "demo day (synthetic, 150 aircraft, seed 1)"
    result = flights.analyze(aircraft, airports, p)
    if a.path and not result["aircraft"]:
        raise TraceError(f"no aircraft with positions found in {a.path}")
    rep = analysis.build_report(result, airports, p, source, stats, truth, time.perf_counter() - t0 if stats else None)
    for line in summary_lines(rep):
        print(line)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
        (out / "report.md").write_text(report.render_report(rep), encoding="utf-8")
        report.report_figure(rep, out / "summary.png")
        print(f"written: {out / 'report.json'}, {out / 'report.md'}, {out / 'summary.png'}")
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    checks = verify.verify(a.draws, a.seed)
    bad = [c for c in checks if not c.ok]
    for c in checks:
        print(
            f"{'ok  ' if c.ok else 'FAIL'} {c.name}: {c.numbers:,} values, largest relative difference {c.max_rel_error:.2e} ({c.detail})"
        )
    print(f"{len(checks) - len(bad)} of {len(checks)} comparisons agree with the literal implementation")
    return 1 if bad else 0


def cmd_bench(a: argparse.Namespace) -> int:
    sizes = [int(p.replace("_", "")) for p in a.sizes.split(",") if p.strip()]
    if not sizes or any(s < 10 for s in sizes):
        raise ValueError("--sizes needs at least one whole number of 10 or more")
    result = bench.run_bench(
        sizes, a.repeat, a.seed, a.draws, a.cmdline, a.ref_aircraft, a.seeds, lambda m: print(m, flush=True)
    )
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "bench.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    (out / "bench.md").write_text(report.render_bench(result), encoding="utf-8")
    report.bench_figure(result, out / "summary.png")
    print(f"written: {out / 'bench.json'}, {out / 'bench.md'}, {out / 'summary.png'}")
    return 0 if result["verification"]["ok"] else 1


def cmd_render(a: argparse.Namespace) -> int:
    try:
        data = json.loads(Path(a.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {a.file}: {exc}") from exc
    kind = data.get("kind") if isinstance(data, dict) else None
    if kind not in ("report", "bench"):
        raise ValueError(f"{a.file} is neither a report.json nor a bench.json")
    text = report.render_report(data) if kind == "report" else report.render_bench(data)
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8")
        print(f"written: {a.output}")
    else:
        print(text, end="")
    if a.figure:
        (report.report_figure if kind == "report" else report.bench_figure)(data, Path(a.figure))
        print(f"written: {a.figure}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="adsbstat", description="Flights and traffic statistics from ADS-B trace files.")
    p.add_argument("--version", action="version", version=f"adsbstat {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="write a synthetic day of traces, airports.csv and truth.json")
    g.add_argument("directory")
    g.add_argument("--aircraft", type=int, default=300)
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--clean", action="store_true", help="no injected faults")
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("analyze", help="flights, airports and traffic statistics (a synthetic demo day without a path)")
    r.add_argument("path", nargs="?", help="a directory of trace files, a tar archive of them, or one trace file")
    r.add_argument("--airports", help="OurAirports airports.csv (default: airports.csv inside a directory)")
    r.add_argument("--truth", help="truth.json of a generated day, to score the analysis (default: inside a directory)")
    r.add_argument("--bbox", help="lat0,lon0,lat1,lon1: keep only the positions inside this box")
    r.add_argument("--limit", type=int, help="stop after this many aircraft")
    r.add_argument("--name", help="name of the source in the report")
    r.add_argument("--out", help="write report.json, report.md and summary.png here")
    for f in fields(Params):
        r.add_argument(
            "--" + f.name.replace("_", "-"),
            dest=f.name,
            type=type(f.default),
            help=f"{HELP[f.name]} (default {f.default:g})",
        )
    r.set_defaults(func=cmd_analyze)

    c = sub.add_parser(
        "verify", help="compare with the literal implementation on random traffic; exit 1 on a difference"
    )
    c.add_argument("--draws", type=int, default=25)
    c.add_argument("--seed", type=int, default=1)
    c.set_defaults(func=cmd_verify)

    b = sub.add_parser("bench", help="speed, accuracy against the truth and agreement with the literal implementation")
    b.add_argument("--sizes", default="100,300,1000,2000", help="numbers of aircraft")
    b.add_argument("--repeat", type=int, default=5)
    b.add_argument("--draws", type=int, default=25)
    b.add_argument("--ref-aircraft", type=int, default=100)
    b.add_argument("--seeds", type=int, default=20, help="generated days (seeds 1..N) for the accuracy sweep")
    b.add_argument("--seed", type=int, default=1)
    b.add_argument("--out", default="adsbstat-out")
    b.set_defaults(func=cmd_bench)

    n = sub.add_parser("render", help="rebuild the Markdown (and figure) from report.json or bench.json")
    n.add_argument("file")
    n.add_argument("-o", "--output")
    n.add_argument("--figure")
    n.set_defaults(func=cmd_render)
    return p


def main(argv: list[str] | None = None) -> int:
    given = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(given)
    args.cmdline = " ".join(given)
    try:
        return int(args.func(args))
    except Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
