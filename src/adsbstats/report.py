"""Markdown and figures built from a report or a benchmark (both are plain JSON)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORS = {"blue": "#0072b2", "orange": "#d55e00", "green": "#009e73", "pink": "#cc79a7", "grey": "#666666"}
FAULTS = {
    "glitch": "Position thrown far away",
    "no_start": "Trace starts in mid-air",
    "no_end": "Trace ends in mid-air",
    "coverage_gap": "Hole in the coverage",
    "duplicate": "Repeated timestamps",
    "ground_only": "Only on the ground (not a flight)",
    "brief": "Brief hop (not a flight)",
}


def pct(x: float | None, digits: int = 1) -> str:
    if x is None:
        return "n/a"
    text = f"{100 * x:.{digits}f}"
    return (text[1:] if text.startswith("-") and float(text) == 0 else text) + "%"  # not "-0.000%"


def num(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x:,.{digits}f}"


def duration(s: float) -> str:
    if s < 1e-3:
        return f"{s * 1e6:.0f} us"
    if s < 1:
        return f"{s * 1e3:.1f} ms"
    return f"{s:.2f} s"


def flight_levels(share: list[float], alt_bin_ft: float) -> list[tuple[str, float]]:
    return [(f"{int(i * alt_bin_ft):,}", s) for i, s in enumerate(share)]


def render_report(rep: dict[str, Any]) -> str:
    a = rep["analysis"]
    t = a["totals"]
    out = [
        "# Flight analysis",
        "",
        f"Source: {rep['source']}. adsbstat {rep['version']}.",
        "",
        "## Totals",
        "",
        "| What | Value |",
        "|---|---|",
        f"| Aircraft | {t['aircraft']:,} |",
        f"| Position reports | {t['points']:,} |",
        f"| Glitches removed | {t['glitches']:,} |",
        f"| Legs (stretches of one trace) | {t['legs']:,} |",
        f"| Flights | {t['flights']:,} |",
        f"| Distance flown | {num(t['distance_km'], 0)} km |",
        f"| Time in the air | {num(t['airborne_h'], 1)} h |",
        f"| Origin unknown | {t['origin_unknown']:,} |",
        f"| Destination unknown | {t['destination_unknown']:,} |",
        "",
    ]
    rd = rep.get("read")
    if rd:
        out += [
            "## Reading",
            "",
            f"{rd['files']:,} files, {rd['aircraft']:,} aircraft with positions, {rd['points']:,} points of which "
            f"{rd['bad_points']:,} were unusable and {rd['kept_points']:,} were kept; {rd['bad_files']:,} unreadable files"
            + ("; the archive ended early." if rd["truncated"] else "."),
            "",
        ]
    if t["flights"]:
        out += ["## Flights", "", "| | 10th percentile | Median | 90th percentile | Longest |", "|---|---|---|---|---|"]
        d, m = a["distance_km"], a["duration_min"]
        out.append(
            f"| Distance (km) | {num(d['p10'], 0)} | {num(d['median'], 0)} | {num(d['p90'], 0)} | {num(d['max'], 0)} |"
        )
        out.append(
            f"| Duration (min) | {num(m['p10'], 0)} | {num(m['median'], 0)} | {num(m['p90'], 0)} | {num(m['max'], 0)} |"
        )
        out += [
            "",
            f"Mean ground speed {num(a['mean_gs_kt'], 0)} kt (per flight, weighted by time). "
            f"Busiest hour for take-offs: {a['peak_hour']:02d}:00 UTC ({a['hours'][a['peak_hour']]:,} flights). "
            f"Share of airborne time above 24,000 ft: {pct(a['above_fl240'])}.",
            "",
            "## Take-offs by hour (UTC)",
            "",
            "| Hour | " + " | ".join(f"{h:02d}" for h in range(24)) + " |",
            "|---|" + "---|" * 24,
            "| Flights | " + " | ".join(str(x) for x in a["hours"]) + " |",
            "",
        ]
    if a["airports"]:
        out += [
            "## Busiest airports",
            "",
            "| Airport | Name | Departures | Arrivals | Movements |",
            "|---|---|---|---|---|",
        ]
        out += [
            f"| {r['ident']} | {r['name']} | {r['departures']:,} | {r['arrivals']:,} | {r['movements']:,} |"
            for r in a["airports"]
        ]
        out.append("")
    if a["routes"]:
        out += ["## Busiest routes", "", "| Route | Flights |", "|---|---|"]
        out += [f"| {r['origin']} to {r['destination']} | {r['flights']:,} |" for r in a["routes"]]
        out.append("")
    if a["types"]:
        out += ["## Aircraft types", "", "| Type | Flights |", "|---|---|"]
        out += [f"| {r['type']} | {r['flights']:,} |" for r in a["types"]]
        out.append("")
    acc = rep.get("accuracy")
    if acc:
        f, ap, di, ti, gl = acc["flights"], acc["airports"], acc["distance"], acc["times"], acc["glitches"]
        out += [
            "## Against the truth",
            "",
            f"{f['matched']:,} of {f['true']:,} true flights found (recall {pct(f['recall'], 2)}), {f['extra']:,} extra "
            f"(precision {pct(f['precision'], 2)}), of which {f['extra_from_decoys']:,} come from aircraft that never flew. "
            f"Origin named correctly for {ap['origin_correct']:,} of {ap['matched']:,}, destination for "
            f"{ap['destination_correct']:,}. Distance: total error {pct(di['total_error'], 3)}, median error "
            f"{pct(di['median_abs_error'], 4)}, largest {pct(di['max_abs_error'], 2)}. Take-off time error: median "
            f"{num(ti['takeoff_error_median_s'], 1)} s, largest {num(ti['takeoff_error_max_s'], 1)} s. Glitches: "
            f"{gl['injected']:,} injected, {gl['removed']:,} removed.",
            "",
            "| Fault | Injected | Handled |",
            "|---|---|---|",
        ]
        out += [f"| {FAULTS[k]} | {v['injected']:,} | {v['handled']:,} |" for k, v in acc["faults"].items()]
        out.append("")
    return "\n".join(out)


def report_figure(rep: dict[str, Any], path: Path) -> None:
    a = rep["analysis"]
    alt_bin = rep["params"]["alt_bin_ft"]
    spd_bin = rep["params"]["speed_bin_kt"]
    fig, ax = plt.subplots(2, 2, figsize=(12, 8), dpi=110)
    ax[0, 0].bar(range(24), a["hours"], color=COLORS["blue"])
    ax[0, 0].set(title="Take-offs by hour (UTC)", xlabel="hour", ylabel="flights", xticks=range(0, 24, 3))
    alt = a["altitude_share"]
    ax[0, 1].bar(
        [i * alt_bin / 1000 for i in range(len(alt))],
        [100 * x for x in alt],
        width=alt_bin / 1000 * 0.9,
        align="edge",
        color=COLORS["green"],
    )
    ax[0, 1].set(title="Airborne time by altitude", xlabel="altitude (1,000 ft)", ylabel="% of airborne time")
    spd = a["speed_share"]
    ax[1, 0].bar(
        [i * spd_bin for i in range(len(spd))],
        [100 * x for x in spd],
        width=spd_bin * 0.9,
        align="edge",
        color=COLORS["orange"],
    )
    ax[1, 0].set(title="Airborne time by ground speed", xlabel="ground speed (kt)", ylabel="% of airborne time")
    top = a["airports"][:8][::-1]
    ax[1, 1].barh([r["ident"] for r in top], [r["movements"] for r in top], color=COLORS["pink"])
    ax[1, 1].set(title="Busiest airports (movements)", xlabel="take-offs and landings")
    for x in ax.flat:
        x.spines[["top", "right"]].set_visible(False)
    fig.suptitle(
        f"{rep['source']}: {a['totals']['flights']:,} flights, {a['totals']['aircraft']:,} aircraft", fontsize=12
    )
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def render_bench(b: dict[str, Any]) -> str:
    e = b["environment"]
    ref = b["reference"]
    out = [
        "# Benchmark",
        "",
        f"Run on {e['system']}, {e['cpus']} CPUs, Python {e['python']}; seed {e['seed']}; each time is the median of "
        f"{e['repeat']} runs (at most {max(1, e['repeat'] // 2)} for the literal implementation); command `{e['command']}`.",
        "",
        "## 1. Analysing traces: NumPy against the literal implementation",
        "",
        "| Aircraft | Position reports | Flights | NumPy | Reports per second |",
        "|---|---|---|---|---|",
    ]
    out += [
        f"| {r['aircraft']:,} | {r['points']:,} | {r['flights']:,} | {duration(r['seconds'])} | {r['points'] / r['seconds']:,.0f} |"
        for r in b["analysis"]
    ]
    ratio = ref["seconds"] / ref["fast_seconds"]
    out += [
        "",
        f"The literal implementation took {duration(ref['seconds'])} on {ref['aircraft']:,} aircraft "
        f"({ref['points']:,} reports), the NumPy one {duration(ref['fast_seconds'])}: {ratio:,.1f}x.",
        "",
        "## 2. Reading",
        "",
        "| Step | Files | Time | Reports per second |",
        "|---|---|---|---|",
    ]
    for k, label in (
        ("write", "Write gzip trace files"),
        ("read_dir", "Read them from a directory"),
        ("read_tar", "Read them from a tar archive"),
    ):
        r = b[k]
        out.append(f"| {label} | {r['files']:,} | {duration(r['seconds'])} | {r['points'] / r['seconds']:,.0f} |")
    acc = b["accuracy"]
    f = acc["flights"]
    out += [
        "",
        "## 3. Accuracy against the truth",
        "",
        f"{acc['seeds']} generated days of {acc['aircraft']} aircraft (seeds 1 to {acc['seeds']}): {f['matched']:,} of "
        f"{f['true']:,} true flights found, {f['extra']:,} extra; origin correct for {acc['origin_correct']:,}, destination "
        f"for {acc['destination_correct']:,}; distance error median {pct(acc['distance_error_median'], 4)}, "
        f"95th percentile {pct(acc['distance_error_p95'], 4)}, largest {pct(acc['distance_error_max'], 2)}; glitches "
        f"{acc['glitches']['injected']:,} injected, {acc['glitches']['removed']:,} removed.",
        "",
        "| Fault | Injected | Handled | Missed |",
        "|---|---|---|---|",
    ]
    out += [
        f"| {FAULTS[k]} | {v['injected']:,} | {v['handled']:,} | {v['injected'] - v['handled']:,} |"
        for k, v in acc["faults"].items()
    ]
    v = b["verification"]
    out += [
        "",
        "## 4. Agreement",
        "",
        f"{v['checks']} comparisons (generated and spoiled traffic, random parameters): {v['numbers']:,} values compared, "
        f"largest relative difference {v['max_rel_error']:.1e} (tolerance {v['tolerance']:.0e}). "
        + ("All agree." if v["ok"] else "THERE ARE DIFFERENCES."),
        "",
    ]
    return "\n".join(out)


def bench_figure(b: dict[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5), dpi=110)
    rows = b["analysis"]
    ax[0].plot([r["points"] for r in rows], [r["seconds"] for r in rows], "o-", color=COLORS["blue"], label="NumPy")
    ref = b["reference"]
    ax[0].plot([ref["points"]], [ref["seconds"]], "s", color=COLORS["orange"], label="literal")
    ax[0].set(xscale="log", yscale="log", xlabel="position reports", ylabel="seconds", title="Analysis time")
    ax[0].legend(frameon=False)
    faults = b["accuracy"]["faults"]
    names = list(faults)
    ax[1].barh(
        names[::-1],
        [100 * faults[k]["handled"] / faults[k]["injected"] if faults[k]["injected"] else 0 for k in names[::-1]],
        color=COLORS["green"],
    )
    ax[1].set(xlim=(0, 100), xlabel="% handled", title="Injected faults handled")
    for x in ax:
        x.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
