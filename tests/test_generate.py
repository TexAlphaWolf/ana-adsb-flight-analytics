from __future__ import annotations

import json
from pathlib import Path

import pytest

from adsbstats import flights
from adsbstats.generate import DAY, FAULT_KINDS, generate, make_airports, slerp
from adsbstats.geo import haversine
from adsbstats.score import score
from adsbstats.trace import ReadStats, read_path

from .conftest import DRAWS, SEED


def test_same_seed_same_traffic() -> None:
    a, b = generate(30, SEED), generate(30, SEED)
    assert a.traces == b.traces and a.flights == b.flights and a.faults == b.faults
    assert generate(30, SEED + 1).traces != a.traces


def test_airports_are_far_apart_and_named_in_order() -> None:
    import random

    aps = make_airports(random.Random(3))
    assert [a.ident for a in aps] == [f"TA{i:02d}" for i in range(1, 13)]
    assert min(haversine(a.lat, a.lon, b.lat, b.lon) for a in aps for b in aps if a is not b) > 90


def test_slerp_ends_and_middle() -> None:
    assert slerp(10, 10, 20, 20, 0) == pytest.approx((10, 10))
    assert slerp(10, 10, 20, 20, 1) == pytest.approx((20, 20))
    assert slerp(0, 0, 0, 90, 0.5) == pytest.approx((0, 45))
    assert slerp(5, 5, 5, 5, 0.3) == (5, 5)


def test_faults_are_counted_as_asked() -> None:
    g = generate(100, SEED)
    assert set(g.stats) == set(FAULT_KINDS)
    assert g.stats["glitch"] == 7 and g.stats["ground_only"] == 2
    assert sum(1 for f in g.flights if f["fault"]) == sum(
        g.stats[k] for k in ("glitch", "no_start", "no_end", "coverage_gap", "duplicate")
    )
    c = generate(100, SEED, clean=True)
    assert not c.faults and all(f["fault"] is None for f in c.flights)
    one = generate(100, SEED, faults={"glitch": 3})
    assert one.stats["glitch"] == 3 and one.stats["no_start"] == 0


def test_bad_requests() -> None:
    with pytest.raises(ValueError, match="unknown faults"):
        generate(20, 1, faults={"boom": 1})
    with pytest.raises(ValueError, match="too many faults"):
        generate(20, 1, faults={"glitch": 500})


def test_flights_are_inside_the_day_and_in_order() -> None:
    g = generate(60, SEED)
    take = [f["takeoff"] for f in g.flights]
    assert take == sorted(take) and take[0] >= DAY and g.flights[-1]["landing"] < DAY + 86400
    assert all(f["distance_km"] > 10 and f["landing"] - f["takeoff"] > 300 for f in g.flights)


def test_the_truth_is_found_exactly_over_many_seeds() -> None:
    for seed in range(SEED, SEED + DRAWS):
        g = generate(80, seed)
        s = score(flights.analyze(g.aircraft(), g.airports), g.truth())
        f = s["flights"]
        assert (f["missed"], f["extra"]) == (0, 0), seed
        assert s["airports"]["origin_correct"] == f["matched"] == s["airports"]["destination_correct"], seed
        assert s["glitches"]["injected"] == s["glitches"]["removed"], seed
        assert all(v["injected"] == v["handled"] for v in s["faults"].values()), seed
        assert s["distance"]["max_abs_error"] < 0.01, seed


def test_write_and_read_back(tmp_path: Path) -> None:
    g = generate(25, SEED)
    n = g.write(tmp_path)
    assert n == len(g.traces) and (tmp_path / "airports.csv").is_file()
    truth = json.loads((tmp_path / "truth.json").read_text(encoding="utf-8"))
    assert truth["seed"] == SEED and len(truth["flights"]) == len(g.flights)
    stats = ReadStats()
    back = list(read_path(tmp_path / "traces", stats))
    assert len(back) == n and stats.bad_points == 0
    assert flights.analyze(back, g.airports)["flights"] == flights.analyze(g.aircraft(), g.airports)["flights"]
