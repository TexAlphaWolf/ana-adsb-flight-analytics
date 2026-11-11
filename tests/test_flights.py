from __future__ import annotations

import pytest

from adsbstats.airports import Airport
from adsbstats.params import Params
from adsbstats.trace import Point

from .conftest import KM_PER_DEG, T0, Both, aircraft, cruise

KM_30_STEPS = 30 * 1.852


def test_one_flight_by_hand(both: Both) -> None:
    res = both([aircraft(cruise())])
    (f,) = res["flights"]
    assert (res["aircraft"], res["points"], res["glitches"], res["legs"]) == (1, 31, 0, 1)
    assert f["takeoff"] == T0 and f["landing"] == T0 + 300 and f["duration_s"] == 300
    assert f["distance_km"] == pytest.approx(KM_30_STEPS, rel=1e-6)
    assert f["max_alt_ft"] == 10000 and f["mean_gs_kt"] == pytest.approx(360) and f["max_gs_kt"] == 360
    assert f["origin"] is None and f["destination"] is None and f["type"] == "A320"


def test_histograms_weight_each_report_by_the_time_to_the_next(both: Both) -> None:
    res = both([aircraft(cruise())])
    assert res["alt_s"][5] == pytest.approx(300)  # 10,000 ft is in the 10,000-12,000 ft bin
    assert sum(res["alt_s"]) == pytest.approx(300)  # 30 gaps of 10 s: the last report counts for nothing
    assert res["speed_s"][7] == pytest.approx(300)  # 360 kt is in the 350-400 kt bin


def test_a_long_silence_counts_for_at_most_the_cap(both: Both) -> None:
    res = both([aircraft(cruise(n=12, step_s=120.0, speed_kt=200))])
    assert sum(res["alt_s"]) == pytest.approx(11 * 60)


@pytest.mark.parametrize(
    ("kwargs", "why"),
    [
        ({"n": 9, "step_s": 60.0}, "9 airborne points"),
        ({"n": 20, "step_s": 10.0}, "190 s in the air"),
        ({"n": 31, "step_s": 10.0, "speed_kt": 30.0}, "9 km covered"),
        ({"alt": None}, "altitude unknown"),
    ],
)
def test_not_a_flight(both: Both, kwargs: dict[str, float | None], why: str) -> None:
    assert both([aircraft(cruise(**kwargs))])["flights"] == [], why


def test_ground_points_are_not_airborne(both: Both) -> None:
    ground = [Point(T0 - 100 + i * 20, 0.0, 0.0, None, True, 5.0, 0) for i in range(5)]
    res = both([aircraft([*ground, *cruise()])])
    (f,) = res["flights"]
    assert f["takeoff"] == T0 and res["legs"] == 1


def test_limits_are_inclusive(both: Both) -> None:
    p = Params(min_air_points=31, min_air_s=300.0, min_air_km=KM_30_STEPS - 0.001)
    assert len(both([aircraft(cruise())], None, p)["flights"]) == 1
    assert both([aircraft(cruise())], None, Params(min_air_points=32))["flights"] == []


def test_one_wild_point_is_a_glitch(both: Both) -> None:
    pts = cruise()
    pts[15] = pts[15]._replace(lat=20.0)
    res = both([aircraft(pts)])
    assert res["glitches"] == 1 and res["legs"] == 1 and len(res["flights"]) == 1
    assert res["flights"][0]["distance_km"] == pytest.approx(KM_30_STEPS, rel=1e-3)


def test_two_wild_points_in_a_row_split_the_leg(both: Both) -> None:
    pts = cruise(n=80)
    for i in (40, 41):
        pts[i] = pts[i]._replace(lat=20.0)
    res = both([aircraft(pts)])
    assert res["glitches"] == 0 and res["legs"] == 3
    assert [f["takeoff"] for f in res["flights"]] == [
        T0,
        T0 + 420,
    ]  # the two stretches at either end, 40 and 38 reports


@pytest.mark.parametrize(("flag", "legs"), [(0, 1), (2, 2), (1, 1), (4, 1), (6, 2)])
def test_flag_bit_two_starts_a_new_leg(both: Both, flag: int, legs: int) -> None:
    pts = cruise(n=80)
    pts[40] = pts[40]._replace(flags=flag)
    assert both([aircraft(pts)])["legs"] == legs


def test_a_silence_over_the_limit_starts_a_new_leg(both: Both) -> None:
    first, second = cruise(n=31), cruise(n=31, t0=T0 + 300 + 1800, lon=0.5)
    assert both([aircraft(first + second)])["legs"] == 1  # exactly 1,800 s is not more than 1,800 s
    later = cruise(n=31, t0=T0 + 300 + 1801, lon=0.5)
    assert both([aircraft(first + later)])["legs"] == 2


def test_same_time_twice_keeps_the_first(both: Both) -> None:
    pts = cruise()
    dup = pts[10]._replace(lat=0.01, alt=1234.0)
    res = both([aircraft([*pts[:11], dup, *pts[11:]])])
    assert res["flights"][0]["max_alt_ft"] == 10000


def test_order_of_the_input_does_not_matter(both: Both) -> None:
    pts = cruise(n=60)
    shuffled = pts[::2] + pts[1::2][::-1]
    assert both([aircraft(shuffled)]) == both([aircraft(pts)])


def test_airports_name_the_ends_of_a_flight(both: Both) -> None:
    deg_8km = 8.0 / KM_PER_DEG
    near = Airport("AAA1", "Near start", 0.0, -0.5 * deg_8km, "large_airport", "ZZ")
    end = 30 * 1.852 / KM_PER_DEG
    far = Airport("BBB1", "End", 0.0, end + 2 * deg_8km, "small_airport", "ZZ")
    pts = [p._replace(alt=1500.0 if i in (0, 30) else 10000.0) for i, p in enumerate(cruise())]
    (f,) = both([aircraft(pts)], [near, far])["flights"]
    assert f["origin"] == "AAA1" and f["destination"] is None  # BBB1 is 16 km from the last report


def test_an_end_above_the_low_altitude_is_not_named(both: Both) -> None:
    ap = Airport("AAA1", "Here", 0.0, 0.0, "large_airport", "ZZ")
    pts = [p._replace(alt=4000.0 if i == 0 else 10000.0) for i, p in enumerate(cruise())]
    assert both([aircraft(pts)], [ap])["flights"][0]["origin"] is None
    assert both([aircraft(pts)], [ap], Params(low_ft=4000.0))["flights"][0]["origin"] == "AAA1"


def test_two_airports_on_the_same_spot_the_first_ident_wins(both: Both) -> None:
    a = Airport("AAA1", "A", 0.0, 0.0, "large_airport", "ZZ")
    b = Airport("BBB1", "B", 0.0, 0.0, "large_airport", "ZZ")
    pts = [p._replace(alt=500.0 if i == 0 else 10000.0) for i, p in enumerate(cruise())]
    assert both([aircraft(pts)], [a, b])["flights"][0]["origin"] == "AAA1"


def test_flights_are_sorted_by_takeoff_then_aircraft(both: Both) -> None:
    res = both([aircraft(cruise(), "bbbbbb"), aircraft(cruise(), "aaaaaa"), aircraft(cruise(t0=T0 - 500), "cccccc")])
    assert [f["icao"] for f in res["flights"]] == ["cccccc", "aaaaaa", "bbbbbb"]


def test_no_aircraft_and_empty_aircraft(both: Both) -> None:
    res = both([])
    assert res["flights"] == [] and res["aircraft"] == 0 and sum(res["alt_s"]) == 0
    res = both([aircraft([])])
    assert res["aircraft"] == 1 and res["points"] == 0 and res["legs"] == 0


def test_missing_ground_speed(both: Both) -> None:
    pts = [p._replace(gs=None) for p in cruise()]
    (f,) = both([aircraft(pts)])["flights"]
    assert f["mean_gs_kt"] is None and f["max_gs_kt"] is None
