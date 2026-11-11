from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from adsbstats import analysis, bench, flights, report
from adsbstats.generate import Generated
from adsbstats.params import Params
from adsbstats.trace import ReadStats


@pytest.fixture(scope="module")
def rep(day: Generated) -> dict[str, Any]:
    p = Params()
    res = flights.analyze(day.aircraft(), day.airports, p)
    stats = ReadStats(files=3, aircraft=2, points=10, bad_points=1, kept_points=9, truncated=True)
    return analysis.build_report(res, day.airports, p, "a test day", stats, day.truth())


def test_report_numbers(rep: dict[str, Any], day: Generated) -> None:
    a = rep["analysis"]
    t = a["totals"]
    assert t["flights"] == len(day.flights) and sum(a["hours"]) == t["flights"]
    assert a["peak_hour"] == a["hours"].index(max(a["hours"]))
    assert sum(a["altitude_share"]) == pytest.approx(1) and sum(a["speed_share"]) == pytest.approx(1)
    assert 0 < a["above_fl240"] < 1
    assert a["distance_km"]["p10"] <= a["distance_km"]["median"] <= a["distance_km"]["p90"] <= a["distance_km"]["max"]
    assert a["airports"][0]["movements"] >= a["airports"][-1]["movements"] and a["airports"][0]["name"].startswith(
        "Test Airport"
    )
    assert len(a["routes"]) == 10 and a["types"][0]["flights"] >= a["types"][-1]["flights"]
    assert t["origin_unknown"] == t["destination_unknown"] == sum(1 for f in day.flights if f["fault"] == "no_start")


def test_the_markdown_is_a_function_of_the_json(rep: dict[str, Any]) -> None:
    again = json.loads(json.dumps(rep))
    assert report.render_report(rep) == report.render_report(again)
    md = report.render_report(rep)
    for part in (
        "# Flight analysis",
        "## Take-offs by hour",
        "## Busiest airports",
        "## Busiest routes",
        "## Against the truth",
        "the archive ended early",
    ):
        assert part in md


def test_report_without_flights_or_truth() -> None:
    p = Params()
    res = flights.analyze([], [], p)
    r = analysis.build_report(res, [], p, "empty")
    md = report.render_report(r)
    assert (
        "| Flights | 0 |" in md
        and "## Busiest" not in md
        and r["analysis"]["peak_hour"] is None
        and r["analysis"]["above_fl240"] is None
    )


def test_figures(rep: dict[str, Any], tmp_path: Path) -> None:
    report.report_figure(rep, tmp_path / "r.png")
    assert (tmp_path / "r.png").stat().st_size > 10_000


@pytest.fixture(scope="module")
def bn() -> dict[str, Any]:
    return bench.run_bench([20, 40], 2, 1, 2, "bench --test", 20, 2)


def test_bench_structure_and_markdown(bn: dict[str, Any], tmp_path: Path) -> None:
    assert [r["aircraft"] for r in bn["analysis"]] == [20, 40] and bn["verification"]["ok"]
    assert bn["analysis"][1]["points"] > bn["analysis"][0]["points"]
    assert bn["read_tar"]["points"] == bn["read_dir"]["points"] > 0
    md = report.render_bench(bn)
    for part in ("# Benchmark", "## 1.", "## 2.", "## 3.", "## 4.", "All agree.", "bench --test"):
        assert part in md
    assert report.render_bench(json.loads(json.dumps(bn))) == md
    report.bench_figure(bn, tmp_path / "b.png")
    assert (tmp_path / "b.png").stat().st_size > 10_000


def test_formatting_helpers() -> None:
    assert (
        report.duration(0.0000042) == "4 us"
        and report.duration(0.0123) == "12.3 ms"
        and report.duration(3.456) == "3.46 s"
    )
    assert report.pct(None) == "n/a" and report.pct(0.1234, 2) == "12.34%" and report.num(None) == "n/a"
    assert report.flight_levels([0.5, 0.5], 2000.0) == [("0", 0.5), ("2,000", 0.5)]
