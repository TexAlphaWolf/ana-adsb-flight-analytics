from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import pytest

from adsbstats import flights, reference
from adsbstats.airports import Airport
from adsbstats.generate import Generated, generate
from adsbstats.geo import EARTH_KM
from adsbstats.params import Params
from adsbstats.trace import Aircraft, Point
from adsbstats.verify import compare

SEED = int(os.environ.get("ADSB_TEST_SEED", "1"))
DRAWS = int(os.environ.get("ADSB_TEST_DRAWS", "12"))
KM_PER_DEG = EARTH_KM * 3.141592653589793 / 180.0  # along the equator or a meridian

T0 = 1_800_000_000.0


def cruise(
    n: int = 31,
    step_s: float = 10.0,
    speed_kt: float = 360.0,
    alt: float | None = 10000.0,
    t0: float = T0,
    lat: float = 0.0,
    lon: float = 0.0,
    flags: int = 0,
) -> list[Point]:
    """Points flying due east on the equator at `speed_kt`, one every `step_s` seconds."""
    deg = speed_kt * 1.852 * step_s / 3600.0 / KM_PER_DEG
    return [
        Point(t0 + i * step_s, lat, lon + i * deg, alt, False, float(speed_kt), flags if i == 0 else 0)
        for i in range(n)
    ]


def aircraft(points: list[Point], icao: str = "abc123", kind: str | None = "A320") -> Aircraft:
    return Aircraft(icao, kind, tuple(points))


Both = Callable[..., dict[str, Any]]


@pytest.fixture
def both() -> Both:
    """Run the NumPy and the literal implementation, require that they agree, and return the result."""

    def run(ac: list[Aircraft], airports: list[Airport] | None = None, p: Params | None = None) -> dict[str, Any]:
        a = flights.analyze(ac, airports or [], p)
        b = reference.analyze(ac, airports or [], p)
        _n, _w, bad = compare(a, b)
        assert bad is None, bad
        return a

    return run


@pytest.fixture(scope="session")
def day() -> Generated:
    return generate(120, SEED)
