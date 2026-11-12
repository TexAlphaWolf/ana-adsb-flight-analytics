"""From the flights of an analysis to the numbers of a report (plain JSON in, plain JSON out)."""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import numpy as np

from . import __version__, score
from .airports import Airport
from .params import ALT_BINS, SPEED_BINS, Params
from .trace import ReadStats

TOP = 10
EDGE_S = (
    600.0  # a flight with no known end within this many seconds of the start or end of the day was in the air across it
)
DAY_S = 86400.0
FL240 = 12  # altitude bins (2,000 ft) below 24,000 ft


def quantiles(xs: list[float]) -> dict[str, float | None]:
    if not xs:
        return {"p10": None, "median": None, "p90": None, "max": None}
    a = np.asarray(xs, float)
    return {
        "p10": float(np.percentile(a, 10)),
        "median": float(np.percentile(a, 50)),
        "p90": float(np.percentile(a, 90)),
        "max": float(a.max()),
    }


def shares(xs: list[float]) -> list[float]:
    total = sum(xs)
    return [x / total if total > 0 else 0.0 for x in xs]


def hour_of(t: float) -> int:
    return datetime.fromtimestamp(t, UTC).hour


def edge_counts(fl: list[dict[str, Any]]) -> tuple[int, int]:
    """(flights that were already in the air when the day began, flights still in the air when it ended).

    The day is the UTC day of the first take-off. A flight counts at the start when its origin is unknown and it takes off
    within EDGE_S of midnight, at the end when its destination is unknown and it lands within EDGE_S of the next midnight.
    """
    if not fl:
        return 0, 0
    start = DAY_S * (min(f["takeoff"] for f in fl) // DAY_S)
    return (
        sum(1 for f in fl if f["origin"] is None and f["takeoff"] < start + EDGE_S),
        sum(1 for f in fl if f["destination"] is None and f["landing"] > start + DAY_S - EDGE_S),
    )


def build_report(
    result: dict[str, Any],
    airports: list[Airport],
    p: Params,
    source: str,
    stats: ReadStats | None = None,
    truth: dict[str, Any] | None = None,
    elapsed_s: float | None = None,
) -> dict[str, Any]:
    fl = result["flights"]
    at_start, at_end = edge_counts(fl)
    names = {a.ident: a for a in airports}
    hours = [0] * 24
    for f in fl:
        hours[hour_of(f["takeoff"])] += 1
    dep: Counter[str] = Counter(f["origin"] for f in fl if f["origin"])
    arr: Counter[str] = Counter(f["destination"] for f in fl if f["destination"])
    both: Counter[str] = Counter()
    both.update(dep)
    both.update(arr)
    routes: Counter[tuple[str, str]] = Counter(
        (f["origin"], f["destination"]) for f in fl if f["origin"] and f["destination"]
    )
    types: Counter[str] = Counter(f["type"] or "unknown" for f in fl)
    alt_share, speed_share = shares(result["alt_s"]), shares(result["speed_s"])
    ap_rows = [
        {
            "ident": i,
            "name": names[i].name if i in names else "",
            "departures": dep[i],
            "arrivals": arr[i],
            "movements": n,
        }
        for i, n in sorted(both.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP]
    ]
    route_rows = [
        {"origin": o, "destination": d, "flights": n}
        for (o, d), n in sorted(routes.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP]
    ]
    type_rows = [{"type": k, "flights": n} for k, n in sorted(types.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP]]
    peak = max(range(24), key=lambda h: (hours[h], -h)) if fl else None
    rep: dict[str, Any] = {
        "kind": "report",
        "version": __version__,
        "source": source,
        "elapsed_s": elapsed_s,
        "params": {k: getattr(p, k) for k in p.__dataclass_fields__},
        "read": None
        if stats is None
        else {
            "files": stats.files,
            "aircraft": stats.aircraft,
            "points": stats.points,
            "bad_points": stats.bad_points,
            "bad_files": stats.bad_files,
            "kept_points": stats.kept_points,
            "truncated": stats.truncated,
            "first_error": stats.first_error,
        },
        "analysis": {
            "totals": {
                "aircraft": result["aircraft"],
                "points": result["points"],
                "glitches": result["glitches"],
                "legs": result["legs"],
                "flights": len(fl),
                "distance_km": sum(f["distance_km"] for f in fl),
                "airborne_h": sum(f["duration_s"] for f in fl) / 3600.0,
                "origin_unknown": sum(1 for f in fl if f["origin"] is None),
                "destination_unknown": sum(1 for f in fl if f["destination"] is None),
                "airborne_at_start": at_start,
                "airborne_at_end": at_end,
                "round_trips": sum(1 for f in fl if f["origin"] is not None and f["origin"] == f["destination"]),
            },
            "hours": hours,
            "peak_hour": peak,
            "altitude_share": alt_share,
            "speed_share": speed_share,
            "above_fl240": sum(alt_share[FL240:]) if sum(result["alt_s"]) > 0 else None,
            "distance_km": quantiles([f["distance_km"] for f in fl]),
            "duration_min": quantiles([f["duration_s"] / 60.0 for f in fl]),
            "mean_gs_kt": statistics.fmean([f["mean_gs_kt"] for f in fl if f["mean_gs_kt"] is not None])
            if any(f["mean_gs_kt"] is not None for f in fl)
            else None,
            "airports": ap_rows,
            "routes": route_rows,
            "types": type_rows,
        },
        "accuracy": score.score(result, truth) if truth is not None else None,
    }
    assert len(alt_share) == ALT_BINS and len(speed_share) == SPEED_BINS
    return rep
