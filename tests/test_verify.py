from __future__ import annotations

import numpy as np

from adsbstats import verify
from adsbstats.generate import generate
from adsbstats.verify import compare, hostile, random_params, with_twins

from .conftest import DRAWS, SEED


def test_compare_equal_and_different() -> None:
    assert compare({"a": [1.0, "x", None]}, {"a": [1.0, "x", None]}) == (3, 0.0, None)
    n, worst, bad = compare({"a": 1.0}, {"a": 1.1})
    assert n == 1 and worst > 0.05 and bad is not None and "/a" in bad
    assert compare([1.0], [1.0 + 1e-12])[2] is None
    assert compare([1], [1.0])[2] is not None
    assert compare({"a": 1}, {"b": 1})[2] is not None
    assert compare([1, 2], [1])[2] is not None
    assert compare("a", "b")[2] is not None


def test_agreement_on_generated_and_spoiled_traffic() -> None:
    checks = verify.verify(DRAWS, SEED)
    assert len(checks) == DRAWS + 1
    bad = [c for c in checks if not c.ok]
    assert not bad, bad[0].detail
    assert sum(c.numbers for c in checks) > 5000


def test_hostile_changes_the_traffic_but_keeps_the_aircraft() -> None:
    rng = np.random.default_rng(5)
    ac = generate(15, 2).aircraft()
    spoiled = hostile(ac, rng)
    assert [a.icao for a in spoiled] == [a.icao for a in ac] and spoiled != ac


def test_random_parameters_are_valid_and_vary() -> None:
    rng = np.random.default_rng(1)
    a, b = random_params(rng), random_params(rng)
    assert a != b and a.min_air_points >= 2 and a.alt_bin_ft > 0


def test_twins_sit_on_an_existing_airport() -> None:
    rng = np.random.default_rng(1)
    aps = generate(10, 1).airports
    twin = next(a for a in with_twins(aps, rng) if a.ident == "ZZ99")
    assert any((a.lat, a.lon) == (twin.lat, twin.lon) for a in aps)
