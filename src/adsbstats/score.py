"""Score an analysis against the truth that `generate` wrote: flights found, airports named, faults handled."""

from __future__ import annotations

import statistics
from typing import Any

import numpy as np

MATCH_S = 120.0  # a found flight belongs to a true one of the same aircraft if the take-offs are this close
LEG_FAULTS = ("glitch", "no_start", "no_end", "coverage_gap", "duplicate")
DECOY_FAULTS = ("ground_only", "brief")


def match(found: list[dict[str, Any]], true: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Pairs (true, found): each true flight takes the nearest unused found one of the same aircraft within MATCH_S."""
    by_icao: dict[str, list[dict[str, Any]]] = {}
    for f in found:
        by_icao.setdefault(f["icao"], []).append(f)
    used: set[int] = set()
    pairs = []
    for t in true:
        best, gap = None, MATCH_S
        for f in by_icao.get(t["icao"], []):
            d = abs(f["takeoff"] - t["takeoff"])
            if id(f) not in used and d <= gap:
                best, gap = f, d
        if best is not None:
            used.add(id(best))
            pairs.append((t, best))
    return pairs


def quantile(xs: list[float], q: float) -> float | None:
    return float(np.percentile(xs, q)) if xs else None


def score(result: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    true, found = truth["flights"], result["flights"]
    pairs = match(found, true)
    n_true, n_found, n_match = len(true), len(found), len(pairs)
    origin_ok = sum(1 for t, f in pairs if f["origin"] == t["origin"])
    dest_ok = sum(1 for t, f in pairs if f["destination"] == t["destination"])
    dist = [abs(f["distance_km"] - t["distance_km"]) / t["distance_km"] for t, f in pairs]
    take = [abs(f["takeoff"] - t["takeoff"]) for t, f in pairs]
    land = [abs(f["landing"] - t["landing"]) for t, f in pairs]
    true_km = sum(t["distance_km"] for t, _f in pairs)
    found_km = sum(f["distance_km"] for _t, f in pairs)
    matched = {id(t): f for t, f in pairs}
    kinds: dict[str, dict[str, int]] = {}
    for k in LEG_FAULTS:
        sel = [t for t in true if t.get("fault") == k]
        ok = sum(
            1
            for t in sel
            if id(t) in matched
            and matched[id(t)]["origin"] == t["origin"]
            and matched[id(t)]["destination"] == t["destination"]
        )
        kinds[k] = {"injected": len(sel), "handled": ok}
    decoy_icao = {f["icao"] for f in truth["faults"] if f["kind"] in DECOY_FAULTS}
    for k in DECOY_FAULTS:
        icaos = {f["icao"] for f in truth["faults"] if f["kind"] == k}
        kinds[k] = {"injected": len(icaos), "handled": sum(1 for i in icaos if not any(f["icao"] == i for f in found))}
    injected_glitches = sum(1 for f in truth["faults"] if f["kind"] == "glitch")
    clean = [t for t in true if t.get("fault") is None]
    return {
        "flights": {
            "true": n_true,
            "found": n_found,
            "matched": n_match,
            "missed": n_true - n_match,
            "extra": n_found - n_match,
            "extra_from_decoys": sum(1 for f in found if f["icao"] in decoy_icao),
            "recall": n_match / n_true if n_true else None,
            "precision": n_match / n_found if n_found else None,
        },
        "airports": {
            "origin_correct": origin_ok,
            "destination_correct": dest_ok,
            "matched": n_match,
            "origin_unknown_true": sum(1 for t, _f in pairs if t["origin"] is None),
            "destination_unknown_true": sum(1 for t, _f in pairs if t["destination"] is None),
        },
        "distance": {
            "true_km": true_km,
            "found_km": found_km,
            "total_error": (found_km - true_km) / true_km if true_km else None,
            "median_abs_error": statistics.median(dist) if dist else None,
            "p95_abs_error": quantile(dist, 95),
            "max_abs_error": max(dist) if dist else None,
        },
        "times": {
            "takeoff_error_median_s": statistics.median(take) if take else None,
            "takeoff_error_max_s": max(take) if take else None,
            "landing_error_median_s": statistics.median(land) if land else None,
            "landing_error_max_s": max(land) if land else None,
        },
        "glitches": {"injected": injected_glitches, "removed": result["glitches"]},
        "faults": kinds,
        "clean_flights": len(clean),
    }
