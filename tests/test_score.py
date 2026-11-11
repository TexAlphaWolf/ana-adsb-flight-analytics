from __future__ import annotations

from typing import Any

import pytest

from adsbstats.score import match, score

TRUE = {
    "icao": "a",
    "takeoff": 1000.0,
    "landing": 2000.0,
    "distance_km": 100.0,
    "origin": "X",
    "destination": "Y",
    "fault": None,
}


def found(**kw: Any) -> dict[str, Any]:
    return {
        "icao": "a",
        "takeoff": 1000.0,
        "landing": 2000.0,
        "distance_km": 100.0,
        "origin": "X",
        "destination": "Y",
        **kw,
    }


def truth(*flights: dict[str, Any], faults: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"flights": list(flights), "faults": faults or []}


def result(*flights: dict[str, Any], glitches: int = 0) -> dict[str, Any]:
    return {"flights": list(flights), "glitches": glitches}


def test_perfect() -> None:
    s = score(result(found()), truth(TRUE))
    assert s["flights"]["recall"] == s["flights"]["precision"] == 1.0
    assert s["distance"]["total_error"] == 0 and s["airports"]["origin_correct"] == 1


def test_miss_extra_and_wrong_airport() -> None:
    t2 = {**TRUE, "icao": "b"}
    s = score(result(found(destination="Z"), found(icao="c")), truth(TRUE, t2))
    f = s["flights"]
    assert (f["true"], f["found"], f["matched"], f["missed"], f["extra"]) == (2, 2, 1, 1, 1)
    assert s["airports"]["destination_correct"] == 0 and s["airports"]["origin_correct"] == 1


def test_matching_is_by_aircraft_and_takeoff_within_two_minutes() -> None:
    t = {**TRUE}
    assert len(match([found(takeoff=1119.0)], [t])) == 1
    assert match([found(takeoff=1121.0)], [t]) == []
    assert match([found(icao="b")], [t]) == []


def test_each_found_flight_is_used_once() -> None:
    t1, t2 = {**TRUE, "takeoff": 1000.0}, {**TRUE, "takeoff": 1100.0}
    pairs = match([found(takeoff=1090.0)], [t1, t2])
    assert len(pairs) == 1 and pairs[0][0] is t1  # true flights are taken in order
    assert len(match([found(takeoff=1000.0), found(takeoff=1100.0)], [t1, t2])) == 2


def test_distance_errors() -> None:
    s = score(result(found(distance_km=90.0)), truth(TRUE))
    assert s["distance"]["total_error"] == pytest.approx(-0.1) and s["distance"]["max_abs_error"] == pytest.approx(0.1)


def test_faults_and_decoys() -> None:
    glitch = {**TRUE, "fault": "glitch"}
    faults = [
        {"kind": "glitch", "icao": "a", "t": 1500.0},
        {"kind": "brief", "icao": "d"},
        {"kind": "ground_only", "icao": "e"},
    ]
    s = score(result(found(), found(icao="d", takeoff=5.0), glitches=1), truth(glitch, faults=faults))
    assert s["faults"]["glitch"] == {"injected": 1, "handled": 1}
    assert s["faults"]["brief"] == {"injected": 1, "handled": 0}
    assert s["faults"]["ground_only"] == {"injected": 1, "handled": 1}
    assert s["flights"]["extra_from_decoys"] == 1 and s["glitches"] == {"injected": 1, "removed": 1}


def test_nothing_at_all() -> None:
    s = score(result(), truth())
    assert s["flights"]["recall"] is None and s["flights"]["precision"] is None
    assert s["distance"]["median_abs_error"] is None and s["times"]["takeoff_error_max_s"] is None
