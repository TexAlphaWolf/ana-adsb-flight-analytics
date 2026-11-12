"""The documentation must say what the measurements say."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from adsbstats import analysis, cli, flights, report
from adsbstats.generate import DEFAULT_RATES, FAULT_KINDS, generate
from adsbstats.params import Params
from adsbstats.verify import compare

ROOT = Path(__file__).resolve().parent.parent
REPORT = json.loads((ROOT / "docs" / "report.json").read_text(encoding="utf-8"))
REAL = json.loads((ROOT / "docs" / "real.json").read_text(encoding="utf-8"))
BENCH = json.loads((ROOT / "docs" / "bench.json").read_text(encoding="utf-8"))
README = (ROOT / "README.md").read_text(encoding="utf-8")
ANALYSIS = (ROOT / "docs" / "analysis.md").read_text(encoding="utf-8")
METHOD = (ROOT / "docs" / "method.md").read_text(encoding="utf-8")
ONE_LINE = re.compile(r"\s+")
ACC = BENCH["accuracy"]
ROWS = BENCH["analysis"]


def flat(text: str) -> str:
    return ONE_LINE.sub(" ", text.replace("**", ""))


def test_the_benchmark_is_what_the_text_says_it_is() -> None:
    env = BENCH["environment"]
    assert env["adsbstats"] == "1.0.0" and env["seed"] == 1 and env["repeat"] == 5
    assert env["cpus"] == 12 and env["python"] == "3.14.10" and env["system"] == "Linux x86_64"
    assert [r["aircraft"] for r in ROWS] == [100, 300, 1000, 2000]
    assert BENCH["reference"]["aircraft"] == 100
    assert BENCH["verification"]["checks"] == 26 and BENCH["verification"]["numbers"] == 31259
    assert BENCH["verification"]["ok"] is True
    assert ACC["seeds"] == 20 and ACC["aircraft"] == 200
    assert ACC["flights"] == {"true": 8692, "found": 8692, "matched": 8692, "extra": 0}
    assert ACC["origin_correct"] == ACC["destination_correct"] == 8692
    assert ACC["glitches"] == {"injected": 280, "removed": 280}
    assert sum(v["injected"] for v in ACC["faults"].values()) == 960
    assert all(v["injected"] == v["handled"] for v in ACC["faults"].values()) and set(ACC["faults"]) == set(FAULT_KINDS)


def test_markdown_is_the_render_of_the_json(tmp_path: Path) -> None:
    for name in ("report", "bench", "real"):
        out = tmp_path / f"{name}.md"
        assert cli.main(["render", str(ROOT / "docs" / f"{name}.json"), "-o", str(out)]) == 0
        assert out.read_text(encoding="utf-8") == (ROOT / "docs" / f"{name}.md").read_text(encoding="utf-8")


def test_the_report_is_what_the_demo_gives_today() -> None:
    g = generate(150, 1)
    p = Params()
    res = flights.analyze(g.aircraft(), g.airports, p)
    rep = analysis.build_report(res, g.airports, p, "demo day (synthetic, 150 aircraft, seed 1)", None, g.truth())
    # same structure and values; floats within the tolerance of `verify`, because the last digits of a sum of
    # great-circle distances differ between platforms and Python versions (libm), as CI on Windows, macOS and 3.11 showed
    _n, _worst, bad = compare(json.loads(json.dumps(rep)), REPORT)
    assert bad is None, bad


def test_figures_exist() -> None:
    for name in ("report.png", "bench.png", "real.png"):
        assert (ROOT / "docs" / name).stat().st_size > 10_000


@pytest.mark.parametrize("name", ["README.md", "docs/analysis.md"])
def test_no_scaffold_left(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    assert not re.search(r"work in progress|TODO|TBD|lorem|measurements pending|provisional", text, re.I)


@pytest.mark.parametrize(
    "name", ["README.md", "docs/analysis.md", "docs/architecture.md", "docs/method.md", "docs/limitations.md"]
)
def test_local_links_resolve(name: str) -> None:
    path = ROOT / name
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://")):
            continue
        assert (path.parent / target).exists(), f"{name}: {target}"


def blocks(title: str) -> str:
    m = re.search(re.escape(title) + r":\n\n```text\n(.*?)```", README, re.S)
    assert m, title
    return m.group(1)


def test_the_real_output_blocks_are_the_real_output(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["generate", "day", "--aircraft", "40", "--seed", "3"]) == 0
    first = capsys.readouterr().out
    assert cli.main(["analyze", "day"]) == 0
    first += capsys.readouterr().out
    assert blocks("`adsbstat generate day --aircraft 40 --seed 3` and `adsbstat analyze day`") == first
    assert cli.main(["analyze"]) == 0
    assert blocks("`adsbstat analyze` (the demo day)") == capsys.readouterr().out


def test_the_readme_numbers_are_the_measurements() -> None:
    a, r = REPORT["analysis"], BENCH["reference"]
    t, f = a["totals"], ACC["flights"]
    worst = ACC["distance_error_max"]
    assert f"{100 * worst:.3f}%" == "0.013%"
    must = [
        f"{sum(v['injected'] for v in ACC['faults'].values())} faults injected in all, {f['true']:,} true flights, {f['found']:,} found, {f['extra']} extra",
        f"origin airport right for {ACC['origin_correct']:,} and destination for {ACC['destination_correct']:,}",
        f"{ACC['glitches']['removed']} of {ACC['glitches']['injected']} position glitches removed",
        "within 0.013% of the true one in the worst case",
        f"on {BENCH['verification']['checks']} comparisons",
        f"{BENCH['verification']['numbers']:,} values, largest relative difference {BENCH['verification']['max_rel_error']:.1e}",
        f"The demo day has {t['flights']} flights and the analysis finds the same {t['flights']}",
        f"{t['points']:,} position reports from {t['aircraft']} aircraft: {t['distance_km']:,.0f} km flown in {t['airborne_h']:.1f} hours",
        f"the busiest hour for take-offs is {a['peak_hour']}:00 UTC, and {100 * a['above_fl240']:.1f}% of the airborne time is spent above 24,000 ft",
        f"It removes {t['glitches']} glitches",
        f"{ROWS[0]['points']:,} reports) take {report.duration(ROWS[0]['seconds'])} and 2,000 aircraft ({ROWS[3]['points']:,} reports) take {report.duration(ROWS[3]['seconds'])}",
        f"{ROWS[3]['seconds'] / ROWS[0]['seconds']:.0f} times more for {ROWS[3]['points'] / ROWS[0]['points']:.0f} times the reports",
        f"{BENCH['read_dir']['points'] / BENCH['read_dir']['seconds']:,.0f} reports a second from a directory and {BENCH['read_tar']['points'] / BENCH['read_tar']['seconds']:,.0f} from a tar archive",
        f"{BENCH['read_dir']['seconds'] / ROWS[0]['seconds']:.1f} times as long as the analysis",
        f"NumPy is only {r['seconds'] / r['fast_seconds']:.1f} times faster",
        f"{BENCH['environment']['cpus']} CPUs and Python {BENCH['environment']['python']}",
    ]
    text = flat(README)
    for m in must:
        assert flat(m) in text, m


def test_the_analysis_numbers_are_the_measurements() -> None:
    a, text = REPORT["analysis"], flat(ANALYSIS)
    t, d, m = a["totals"], a["distance_km"], a["duration_min"]
    for row in ROWS:
        assert (
            f"| {row['aircraft']:,} | {row['points']:,} | {row['flights']:,} | {report.duration(row['seconds'])} | {row['points'] / row['seconds']:,.0f} |"
            in ANALYSIS
        )
    for k, v in ACC["faults"].items():
        assert f"| {report.FAULTS[k]} | {v['injected']:,} | {v['handled']:,} | 0 |" in ANALYSIS, k
    must = [
        f"{t['aircraft']} aircraft sent {t['points']:,} position reports: {t['flights']} flights, {t['distance_km']:,.0f} km flown in {t['airborne_h']:.1f} hours",
        f"a median flight of {d['median']:.0f} km and {m['median']:.0f} minutes (10th to 90th percentile: {d['p10']:.0f} to {d['p90']:.0f} km and {m['p10']:.0f} to {m['p90']:.0f} minutes)",
        f"The mean ground speed over a flight is {a['mean_gs_kt']:.0f} kt",
        f"(00:00 to 04:59 UTC: {sum(a['hours'][:5])} in all)",
        f"the busiest hour at 19:00 UTC with {max(a['hours'])}",
        f"{100 * a['altitude_share'][2]:.1f}% is in the 4,000 to 6,000 ft bin",
        f"{100 * a['altitude_share'][17]:.1f}% is between 34,000 and 36,000 ft",
        f"a further {100 * a['altitude_share'][18]:.1f}% is between 36,000 and 38,000 ft",
        f"In all {100 * a['above_fl240']:.1f}% of the airborne time is above 24,000 ft",
        f"{100 * a['speed_share'][8]:.1f}%, is between 400 and 450 kt",
        f"The analysis removes {t['glitches']} glitches",
        f"the busiest, {a['airports'][0]['ident']}, has {a['airports'][0]['movements']} movements and the 10th, {a['airports'][9]['ident']}, has {a['airports'][9]['movements']}",
        f"the busiest route has {a['routes'][0]['flights']} flights",
        f"{a['types'][0]['type']} ({a['types'][0]['flights']} flights), {a['types'][1]['type']} ({a['types'][1]['flights']}) and {a['types'][2]['type']} ({a['types'][2]['flights']})",
        f"{ACC['flights']['true']:,} true flights, {ACC['flights']['found']:,} found, 0 extra",
        f"{ACC['glitches']['injected']} glitches were injected and {ACC['glitches']['removed']} removed",
        f"{BENCH['verification']['numbers']:,} values were compared",
        f"largest relative difference is {BENCH['verification']['max_rel_error']:.1e}",
        f"{BENCH['reference']['seconds'] * 1e3:.1f} ms",
        f"{BENCH['reference']['fast_seconds'] * 1e3:.1f} ms in the same run: {BENCH['reference']['seconds'] / BENCH['reference']['fast_seconds']:.1f} times",
        f"is {ROWS[0]['seconds'] * 1e3:.1f} ms",
        f"{ROWS[3]['seconds'] / ROWS[0]['seconds']:.0f} times more time for {ROWS[3]['points'] / ROWS[0]['points']:.0f} times the reports",
        f"between {min(r['points'] / r['seconds'] for r in ROWS) / 1e6:.2f} and {max(r['points'] / r['seconds'] for r in ROWS) / 1e6:.1f} million reports a second",
        f"differ by {100 * (BENCH['reference']['fast_seconds'] / ROWS[0]['seconds'] - 1):.0f}%",
        f"reading is {BENCH['read_dir']['seconds'] / ROWS[0]['seconds']:.1f} times slower than the analysis",
        "(463.4 against 373.1 ms)",
    ]
    for item in must:
        assert flat(item) in text, item
    exponent = math.log(ROWS[3]["seconds"] / ROWS[0]["seconds"]) / math.log(ROWS[3]["points"] / ROWS[0]["points"])
    assert round(exponent, 1) == 1.1 and "the measured exponent is 1.1" in text
    assert f"{100 * ACC['distance_error_max']:.3f}%" == "0.013%" and ACC["distance_error_p95"] < 1e-9
    assert (
        round(BENCH["read_tar"]["seconds"] * 1e3, 1) == 463.4 and round(BENCH["read_dir"]["seconds"] * 1e3, 1) == 373.1
    )


def test_the_demo_claims() -> None:
    a = REPORT["analysis"]
    t = a["totals"]
    assert (t["aircraft"], t["flights"], t["origin_unknown"], t["destination_unknown"]) == (156, 331, 4, 4)
    assert (t["airborne_at_start"], t["airborne_at_end"], t["round_trips"]) == (0, 0, 0)
    assert sum(a["altitude_share"]) == pytest.approx(1) and a["hours"][23] == 0
    assert (
        REPORT["accuracy"]["faults"]["no_start"]["injected"] == 4
        and REPORT["accuracy"]["faults"]["no_end"]["injected"] == 4
    )
    assert REPORT["accuracy"]["flights"]["recall"] == 1.0


def test_the_method_matches_the_code() -> None:
    p = Params()
    for field in p.__dataclass_fields__:
        row = re.search(rf"\| `{field}` \| `--{field.replace('_', '-')}` \| ([0-9.]+) \|", METHOD)
        assert row, field
        assert float(row.group(1)) == float(getattr(p, field)), field
    rates = {"glitch": 7, "no_start": 3, "no_end": 3, "coverage_gap": 4, "duplicate": 3, "ground_only": 2, "brief": 2}
    assert {k: round(100 * v) for k, v in DEFAULT_RATES.items()} == rates
    assert (
        "7 glitches, 3 + 3 traces that start or end in mid-air, 4 holes, 3 repeated-timestamp runs and 2 + 2 decoys per 100"
        in flat(METHOD)
    )
    for kind in FAULT_KINDS:
        assert f"| `{kind}` |" in METHOD, kind


def test_the_real_day_is_what_the_text_says() -> None:
    a, rd = REAL["analysis"], REAL["read"]
    t = a["totals"]
    assert REAL["version"] == "1.1.0" and REAL["accuracy"] is None and rd["truncated"] is True
    assert (rd["bad_points"], rd["bad_files"]) == (0, 0)
    assert (t["aircraft"], t["points"], t["flights"]) == (53099, 72983747, 135278)
    assert (t["airborne_at_start"], t["airborne_at_end"], t["round_trips"]) == (5057, 5147, 16842)
    assert a["hours"][0] - t["airborne_at_start"] == 5412 and a["hours"][23] == 5321 and a["hours"][1] == 4664
    reports_a_second = t["points"] / REAL["elapsed_s"]
    synthetic = BENCH["read_dir"]["points"] / (BENCH["read_dir"]["seconds"] + ROWS[0]["seconds"])
    must = [
        f"{t['aircraft']:,} aircraft and {t['points']:,} position reports became {t['flights']:,} flights",
        f"{t['distance_km']:,.0f} km flown in {t['airborne_h']:,.1f} hours",
        f"It took {REAL['elapsed_s']:.0f} s, {reports_a_second:,.0f} reports a second",
        f"about {100 * (1 - reports_a_second / synthetic):.0f}% below the {synthetic:,.0f} a second",
        f"{100 * t['origin_unknown'] / t['flights']:.1f}% of the flights have no origin and {100 * t['destination_unknown'] / t['flights']:.1f}% no destination",
        f"({t['origin_unknown']:,} and {t['destination_unknown']:,} of {t['flights']:,})",
        f"{t['airborne_at_start']:,} flights are already in the air when the day begins",
        f"without them hour 00 has {a['hours'][0] - t['airborne_at_start']:,} take-offs, in line with {a['hours'][23]:,} at 23:00",
        f"{t['airborne_at_end']:,} flights still in the air",
        f"{t['round_trips']:,} flights ({100 * t['round_trips'] / t['flights']:.1f}%) start and end at the same airport",
        f"{t['glitches']} removed in {t['points']:,} reports ({1e6 * t['glitches'] / t['points']:.1f} per million)",
        f"{a['types'][0]['flights']:,} flights",
        f"{a['above_fl240'] * 100:.1f}% of the airborne time is above 24,000 ft",
    ]
    text = flat(README)
    for m in must:
        assert flat(m) in text, m
    assert f"{REAL['elapsed_s']:.0f} s ({reports_a_second:,.0f} reports a second)" in flat(ANALYSIS)
    ap = a["airports"]
    assert [x["ident"] for x in ap[:3]] == ["KORD", "KATL", "KDFW"] and ap[0]["movements"] == 1878
    assert a["routes"][0] == {"origin": "KDAB", "destination": "KDAB", "flights": 267}
    assert round(a["duration_min"]["max"]) == 1440 and round(a["distance_km"]["max"]) == 7192
    assert "took 9 minutes" in flat(README) and round(REAL["elapsed_s"] / 60) == 9
