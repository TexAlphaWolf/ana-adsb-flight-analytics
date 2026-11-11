"""Check the NumPy analysis against the literal one, on generated traces and on traces made hostile on purpose."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from . import flights, reference
from .airports import Airport
from .generate import generate
from .params import Params
from .trace import Aircraft, Point

RTOL = 1e-9


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    numbers: int  # how many numbers (and strings) were compared
    max_rel_error: float
    detail: str


def compare(a: Any, b: Any, path: str = "") -> tuple[int, float, str | None]:
    """(values compared, largest relative difference, the first mismatch or None); floats within RTOL, the rest equal."""
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return 0, math.inf, f"{path}: keys differ: {sorted(a.keys() ^ b.keys())}"
        total, worst, bad = 0, 0.0, None
        for k in a:
            n, w, m = compare(a[k], b[k], f"{path}/{k}")
            total, worst, bad = total + n, max(worst, w), bad or m
        return total, worst, bad
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return 0, math.inf, f"{path}: {len(a)} items against {len(b)}"
        total, worst, bad = 0, 0.0, None
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            n, w, m = compare(x, y, f"{path}[{i}]")
            total, worst, bad = total + n, max(worst, w), bad or m
        return total, worst, bad
    if isinstance(a, float) and isinstance(b, float):
        rel = abs(a - b) / max(abs(a), abs(b), 1e-12)
        if math.isclose(a, b, rel_tol=RTOL, abs_tol=1e-12):
            return 1, rel if abs(a - b) > 1e-12 else 0.0, None
        return 1, rel, f"{path}: {a!r} against {b!r}"
    if type(a) is not type(b) or a != b:
        return 1, math.inf, f"{path}: {a!r} against {b!r}"
    return 1, 0.0, None


def random_params(rng: np.random.Generator) -> Params:
    return Params(
        max_kt=float(rng.uniform(300, 1500)),
        jump_km=float(rng.uniform(0.5, 20)),
        gap_s=float(rng.uniform(60, 3600)),
        min_air_points=int(rng.integers(2, 30)),
        min_air_s=float(rng.uniform(30, 900)),
        min_air_km=float(rng.uniform(1, 40)),
        airport_km=float(rng.uniform(1, 40)),
        low_ft=float(rng.uniform(500, 8000)),
        weight_cap_s=float(rng.uniform(5, 300)),
        alt_bin_ft=float(rng.uniform(500, 4000)),
        speed_bin_kt=float(rng.uniform(10, 100)),
    )


def hostile(aircraft: list[Aircraft], rng: np.random.Generator) -> list[Aircraft]:
    """The same traffic spoiled: shuffled order, repeated times, missing values, random flags, runs of wild positions."""
    out = []
    for ac in aircraft:
        pts = list(ac.points)
        n = len(pts)
        if n > 3 and rng.random() < 0.5:
            pts = [pts[i] for i in rng.permutation(n)]
        for i in range(n):
            q = pts[i]
            r = rng.random()
            if r < 0.02:
                pts[i] = q._replace(alt=None)
            elif r < 0.04:
                pts[i] = q._replace(gs=None)
            elif r < 0.06:
                pts[i] = q._replace(flags=int(rng.integers(0, 16)))
            elif r < 0.08 and i > 0:
                pts[i] = q._replace(t=pts[i - 1].t)
            elif r < 0.09:
                pts[i] = q._replace(ground=not q.ground)
        if n > 20:
            for _ in range(int(rng.integers(0, 4))):
                i = int(rng.integers(1, n - 5))
                run = int(rng.integers(1, 4))
                lat, lon = float(rng.uniform(-80, 80)), float(rng.uniform(-179, 179))
                for j in range(i, i + run):
                    pts[j] = pts[j]._replace(lat=lat, lon=lon)
        out.append(Aircraft(ac.icao, ac.type, tuple(Point(*q) for q in pts)))
    return out


def with_twins(airports: list[Airport], rng: np.random.Generator) -> list[Airport]:
    """Two airports on the same spot, so that the tie-break (the first ident wins) is part of the comparison."""
    pick = airports[int(rng.integers(0, len(airports)))]
    twin = Airport("ZZ99", "Twin", pick.lat, pick.lon, pick.kind, pick.country)
    return sorted([*airports, twin], key=lambda a: a.ident)


def verify(draws: int = 25, seed: int = 1) -> list[Check]:
    rng = np.random.default_rng(seed)
    cases: list[tuple[str, list[Aircraft], list[Airport], Params]] = []
    g = generate(40, seed)
    cases.append(("generated traffic, default parameters", g.aircraft(), g.airports, Params()))
    for k in range(draws):
        gk = generate(int(rng.integers(8, 40)), int(rng.integers(0, 10**6)), clean=bool(k % 5 == 4))
        ac = gk.aircraft()
        ap = with_twins(gk.airports, rng) if k % 3 == 0 else gk.airports
        spoiled = k % 4 != 3
        cases.append(
            (
                f"random case {k + 1}" + (" (spoiled)" if spoiled else ""),
                hostile(ac, rng) if spoiled else ac,
                ap,
                random_params(rng) if k % 2 == 0 else Params(),
            )
        )
    out = []
    for name, ac, ap, p in cases:
        a, b = flights.analyze(ac, ap, p), reference.analyze(ac, ap, p)
        n, worst, bad = compare(a, b)
        out.append(Check(name, bad is None, n, worst, bad or f"{a['points']:,} points, {len(a['flights'])} flights"))
    return out
