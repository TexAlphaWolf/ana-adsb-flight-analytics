"""The literal implementation: the definitions of `flights.py` written as plain loops over single points, with every airport
measured for every query. Slow on purpose; it exists to be read, and to be compared with the fast one."""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable
from typing import Any

from .airports import Airport, nearest_literal
from .geo import haversine
from .params import ALT_BINS, KM_PER_NM, SPEED_BINS, Params
from .trace import NEW_LEG, Aircraft, Point


def is_jump(a: Point, b: Point, p: Params) -> bool:
    d = haversine(a.lat, a.lon, b.lat, b.lon)
    kt = d / KM_PER_NM / ((b.t - a.t) / 3600.0)
    return d > p.jump_km and kt > p.max_kt


def analyze_aircraft(
    ac: Aircraft, airports: list[Airport], p: Params
) -> tuple[list[dict[str, Any]], int, int, list[float], list[float]]:
    alt_s = [0.0] * ALT_BINS
    speed_s = [0.0] * SPEED_BINS
    ordered = sorted(ac.points, key=lambda q: q.t)
    pts: list[Point] = []
    for q in ordered:
        if not pts or q.t != pts[-1].t:
            pts.append(q)
    glitch = [False] * len(pts)
    for i in range(1, len(pts) - 1):
        glitch[i] = is_jump(pts[i - 1], pts[i], p) and is_jump(pts[i], pts[i + 1], p)
    clean = [q for q, g in zip(pts, glitch, strict=True) if not g]
    legs: list[list[Point]] = []
    for i, q in enumerate(clean):
        new = i == 0
        if i > 0:
            prev = clean[i - 1]
            new = bool(q.flags & NEW_LEG) or q.t - prev.t > p.gap_s or is_jump(prev, q, p)
        if new:
            legs.append([])
        legs[-1].append(q)
    flights: list[dict[str, Any]] = []
    for leg in legs:
        air = [k for k, q in enumerate(leg) if not q.ground and q.alt is not None]
        if len(air) < p.min_air_points:
            continue
        if leg[air[-1]].t - leg[air[0]].t < p.min_air_s:
            continue
        km = 0.0
        for k, m in itertools.pairwise(air):
            km += haversine(leg[k].lat, leg[k].lon, leg[m].lat, leg[m].lon)
        if km < p.min_air_km:
            continue
        weight = [0.0] * len(leg)
        for k in range(len(leg) - 1):
            weight[k] = min(leg[k + 1].t - leg[k].t, p.weight_cap_s)
        num = den = 0.0
        max_alt = -math.inf
        max_gs: float | None = None
        for k in air:
            q = leg[k]
            assert q.alt is not None
            max_alt = max(max_alt, q.alt)
            alt_s[min(max(math.floor(q.alt / p.alt_bin_ft), 0), ALT_BINS - 1)] += weight[k]
            if q.gs is not None:
                speed_s[min(max(math.floor(q.gs / p.speed_bin_kt), 0), SPEED_BINS - 1)] += weight[k]
                max_gs = q.gs if max_gs is None else max(max_gs, q.gs)
                if weight[k] > 0:
                    num += q.gs * weight[k]
                    den += weight[k]
        first, last = leg[air[0]], leg[air[-1]]
        assert first.alt is not None and last.alt is not None
        origin = nearest_literal(airports, first.lat, first.lon, p.airport_km) if first.alt <= p.low_ft else None
        dest = nearest_literal(airports, last.lat, last.lon, p.airport_km) if last.alt <= p.low_ft else None
        flights.append(
            {
                "icao": ac.icao,
                "type": ac.type,
                "takeoff": first.t,
                "landing": last.t,
                "duration_s": last.t - first.t,
                "distance_km": km,
                "max_alt_ft": max_alt,
                "mean_gs_kt": num / den if den > 0 else None,
                "max_gs_kt": max_gs,
                "origin": origin,
                "destination": dest,
            }
        )
    return flights, sum(glitch), len(legs), alt_s, speed_s


def analyze(aircraft: Iterable[Aircraft], airports: list[Airport], p: Params | None = None) -> dict[str, Any]:
    p = p or Params()
    flights: list[dict[str, Any]] = []
    n_aircraft = points = glitches = legs = 0
    alt_s = [0.0] * ALT_BINS
    speed_s = [0.0] * SPEED_BINS
    for ac in aircraft:
        f, g, nl, a, s = analyze_aircraft(ac, airports, p)
        flights.extend(f)
        n_aircraft += 1
        points += len(ac.points)
        glitches += g
        legs += nl
        alt_s = [x + y for x, y in zip(alt_s, a, strict=True)]
        speed_s = [x + y for x, y in zip(speed_s, s, strict=True)]
    flights.sort(key=lambda x: (x["takeoff"], x["icao"]))
    return {
        "aircraft": n_aircraft,
        "points": points,
        "glitches": glitches,
        "legs": legs,
        "flights": flights,
        "alt_s": alt_s,
        "speed_s": speed_s,
    }
