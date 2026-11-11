from __future__ import annotations

import random
from pathlib import Path

import pytest

from adsbstats.airports import Airport, AirportError, Index, load_airports, nearest_literal, parse_airports, to_csv

CSV = """id,ident,type,name,latitude_deg,longitude_deg,iso_country
1,LIMC,large_airport,Milano Malpensa,45.63,8.72,IT
2,LIML,medium_airport,Milano Linate,45.45,9.28,IT
3,XX01,heliport,A heliport,45.0,9.0,IT
4,BAD1,small_airport,Bad,north,9.0,IT
5,BAD2,small_airport,Bad,95.0,9.0,IT
6,,small_airport,No ident,45.0,9.0,IT
7,LIML,small_airport,Duplicate ident,10.0,10.0,IT
"""


def test_parse_keeps_open_kinds_and_skips_bad_rows() -> None:
    got = parse_airports(CSV)
    assert [a.ident for a in got] == ["LIML", "LIMC"] or [a.ident for a in got] == sorted(a.ident for a in got)
    assert {a.ident for a in got} == {"LIMC", "LIML"}
    assert next(a for a in got if a.ident == "LIML").name == "Milano Linate"  # the first of two equal idents
    assert [a.ident for a in parse_airports(CSV, ("heliport",))] == ["XX01"]


def test_not_an_airports_file(tmp_path: Path) -> None:
    with pytest.raises(AirportError, match="OurAirports"):
        parse_airports("a,b\n1,2\n")
    with pytest.raises(AirportError, match="cannot be read"):
        load_airports(tmp_path / "nope.csv")
    p = tmp_path / "a.csv"
    p.write_text("﻿" + CSV, encoding="utf-8")
    assert len(load_airports(p)) == 2


def test_csv_round_trip() -> None:
    airports = parse_airports(CSV)
    assert parse_airports(to_csv(airports)) == [
        Airport(a.ident, a.name, round(a.lat, 6), round(a.lon, 6), a.kind, a.country) for a in airports
    ]


def test_nearest_literal() -> None:
    airports = parse_airports(CSV)
    assert nearest_literal(airports, 45.46, 9.27, 8.0) == "LIML"
    assert nearest_literal(airports, 45.0, 0.0, 8.0) is None
    assert nearest_literal([], 0, 0, 8.0) is None


@pytest.mark.parametrize("seed", range(5))
def test_index_agrees_with_the_brute_force_everywhere(seed: int) -> None:
    rng = random.Random(seed)
    spots = [(rng.uniform(-80, 80), rng.uniform(-180, 180)) for _ in range(300)]
    spots += [(10.0, 179.99), (10.0, -179.99), (89.0, 0.0), (-89.5, 100.0), (45.0, 9.0), (45.0, 9.0)]
    airports = sorted(
        (Airport(f"A{i:03d}", "x", la, lo, "small_airport", "ZZ") for i, (la, lo) in enumerate(spots)),
        key=lambda a: a.ident,
    )
    index = Index(airports, 8.0)
    for _ in range(400):
        base = rng.choice(spots)
        lat = max(-90.0, min(90.0, base[0] + rng.uniform(-0.15, 0.15)))
        lon = (base[1] + rng.uniform(-0.3, 0.3) + 180) % 360 - 180
        assert index.nearest(lat, lon) == nearest_literal(airports, lat, lon, 8.0)
