"""The fast implementation: NumPy over the points of each aircraft, an airport grid for the nearest-airport lookup.

Definitions (the literal implementation in `reference.py` follows the same text, point by point):

1. Points are put in time order and a point with the same time as the one before it is dropped.
2. A point is a glitch if the move to it and the move from it are both jumps: more than `jump_km` of ground at more than
   `max_kt`. Glitches are dropped, all at once.
3. A leg starts at the first point, and again wherever the flags say a new leg starts (bit 2), where more than `gap_s` of
   silence precedes the point, or where the move from the previous point is a jump.
4. A leg is a flight if its airborne points (not on the ground, altitude known) are at least `min_air_points`, last at least
   `min_air_s` and cover at least `min_air_km` of ground (summed between consecutive airborne points).
5. A flight takes off at its first airborne point and lands at its last. Its origin is the nearest airport within
   `airport_km` of the first one if the aircraft was at or below `low_ft` there; the destination likewise for the last one.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import numpy.typing as npt

from .airports import Airport, Index
from .geo import haversine_np
from .params import ALT_BINS, KM_PER_NM, SPEED_BINS, Params
from .trace import NEW_LEG, Aircraft

F64 = npt.NDArray[np.float64]


def jumps(lat: F64, lon: F64, t: F64, p: Params) -> npt.NDArray[np.bool_]:
    """For each pair of consecutive points, whether the move between them is a jump."""
    d = haversine_np(lat[:-1], lon[:-1], lat[1:], lon[1:])
    kt = d / KM_PER_NM / (np.diff(t) / 3600.0)
    out: npt.NDArray[np.bool_] = (d > p.jump_km) & (kt > p.max_kt)
    return out


def analyze_aircraft(ac: Aircraft, index: Index | None, p: Params) -> tuple[list[dict[str, Any]], int, int, F64, F64]:
    """(flights, glitches removed, legs, altitude histogram, speed histogram) of one aircraft."""
    alt_s = np.zeros(ALT_BINS)
    speed_s = np.zeros(SPEED_BINS)
    if not ac.points:
        return [], 0, 0, alt_s, speed_s
    pts = sorted(ac.points, key=lambda q: q.t)
    t = np.array([q.t for q in pts])
    keep = np.r_[True, np.diff(t) > 0]
    pts = [q for q, k in zip(pts, keep, strict=True) if k]
    n = len(pts)
    t = np.array([q.t for q in pts])
    lat = np.array([q.lat for q in pts])
    lon = np.array([q.lon for q in pts])
    glitches = 0
    if n >= 3:
        jp = jumps(lat, lon, t, p)
        bad = np.r_[False, jp[:-1] & jp[1:], False]
        glitches = int(bad.sum())
        if glitches:
            pts = [q for q, b in zip(pts, bad, strict=True) if not b]
            t, lat, lon = t[~bad], lat[~bad], lon[~bad]
    n = len(pts)
    alt = np.array([np.nan if q.alt is None else q.alt for q in pts])
    gs = np.array([np.nan if q.gs is None else q.gs for q in pts])
    ground = np.array([q.ground for q in pts])
    flags = np.array([q.flags for q in pts])
    brk = np.zeros(n, dtype=bool)
    if n > 1:
        brk[1:] = ((flags[1:] & NEW_LEG) != 0) | (np.diff(t) > p.gap_s) | jumps(lat, lon, t, p)
    starts = np.flatnonzero(brk | (np.arange(n) == 0))
    ends = np.r_[starts[1:], n]
    flights: list[dict[str, Any]] = []
    for a, b in zip(starts, ends, strict=True):
        air = np.flatnonzero(~ground[a:b] & ~np.isnan(alt[a:b])) + a
        if len(air) < p.min_air_points:
            continue
        if t[air[-1]] - t[air[0]] < p.min_air_s:
            continue
        steps = haversine_np(lat[air[:-1]], lon[air[:-1]], lat[air[1:]], lon[air[1:]])
        km = float(steps.sum())
        if km < p.min_air_km:
            continue
        w = np.zeros(b - a)
        w[:-1] = np.minimum(np.diff(t[a:b]), p.weight_cap_s)
        wa, aa = w[air - a], alt[air]
        np.add.at(alt_s, np.clip(np.floor(aa / p.alt_bin_ft), 0, ALT_BINS - 1).astype(int), wa)
        g = gs[air]
        has = ~np.isnan(g)
        np.add.at(speed_s, np.clip(np.floor(g[has] / p.speed_bin_kt), 0, SPEED_BINS - 1).astype(int), wa[has])
        use = has & (wa > 0)
        mean_gs = float((g[use] * wa[use]).sum() / wa[use].sum()) if use.any() else None
        first, last = int(air[0]), int(air[-1])
        origin = index.nearest(float(lat[first]), float(lon[first])) if index and alt[first] <= p.low_ft else None
        dest = index.nearest(float(lat[last]), float(lon[last])) if index and alt[last] <= p.low_ft else None
        flights.append(
            {
                "icao": ac.icao,
                "type": ac.type,
                "takeoff": float(t[first]),
                "landing": float(t[last]),
                "duration_s": float(t[last] - t[first]),
                "distance_km": km,
                "max_alt_ft": float(aa.max()),
                "mean_gs_kt": mean_gs,
                "max_gs_kt": float(g[has].max()) if has.any() else None,
                "origin": origin,
                "destination": dest,
            }
        )
    return flights, glitches, len(starts), alt_s, speed_s


def analyze(aircraft: Iterable[Aircraft], airports: list[Airport], p: Params | None = None) -> dict[str, Any]:
    p = p or Params()
    index = Index(airports, p.airport_km) if airports else None
    flights: list[dict[str, Any]] = []
    n_aircraft = points = glitches = legs = 0
    alt_s = np.zeros(ALT_BINS)
    speed_s = np.zeros(SPEED_BINS)
    for ac in aircraft:
        f, g, nl, a, s = analyze_aircraft(ac, index, p)
        flights.extend(f)
        n_aircraft += 1
        points += len(ac.points)
        glitches += g
        legs += nl
        alt_s += a
        speed_s += s
    flights.sort(key=lambda x: (x["takeoff"], x["icao"]))
    return {
        "aircraft": n_aircraft,
        "points": points,
        "glitches": glitches,
        "legs": legs,
        "flights": flights,
        "alt_s": [float(x) for x in alt_s],
        "speed_s": [float(x) for x in speed_s],
    }


__all__ = ["analyze", "analyze_aircraft"]
