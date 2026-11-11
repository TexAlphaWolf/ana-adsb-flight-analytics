"""Synthetic ADS-B traces in the readsb format, with the truth about every flight and every fault put into them.

A fleet of aircraft flies between invented airports. Each leg is simulated (taxi, take-off, climb, cruise along the great
circle, descent, landing, taxi) and written as a trace file the way readsb writes it. Faults are then put into some legs:
a point thrown far away (`glitch`), a trace that starts or ends in mid-air (`no_start`, `no_end`), a hole in the coverage
(`coverage_gap`), repeated timestamps (`duplicate`), and two kinds of aircraft that are not flights (`ground_only`, `brief`).
"""

from __future__ import annotations

import calendar
import itertools
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .airports import Airport, to_csv
from .geo import haversine
from .params import KM_PER_NM
from .trace import NEW_LEG, Aircraft, dump_document, parse_document

DAY = calendar.timegm((2026, 1, 15, 0, 0, 0))
FAULT_KINDS = ("glitch", "no_start", "no_end", "coverage_gap", "duplicate", "ground_only", "brief")
# per aircraft: the number of faults of each kind in the default mix
DEFAULT_RATES = {
    "glitch": 0.07,
    "no_start": 0.03,
    "no_end": 0.03,
    "coverage_gap": 0.04,
    "duplicate": 0.03,
    "ground_only": 0.02,
    "brief": 0.02,
}
HOURS = [0.2] * 5 + [0.6, 0.9, 1.0, 1.0, 0.9, 0.8, 0.8, 0.9, 0.9, 0.8, 0.8, 0.9, 1.0, 1.0, 0.9, 0.7, 0.5, 0.3, 0.2]
# name: (cruise knots, cruise altitude ft, climb/descent km per 1,000 ft, weight, shortest and longest leg km)
TYPES: dict[str, tuple[float, float, float, float, float, float]] = {
    "A320": (450, 36000, 5.5, 5, 300, 1300),
    "B738": (440, 35000, 5.5, 4, 300, 1300),
    "E190": (430, 34000, 5.5, 2, 250, 1100),
    "AT76": (270, 22000, 3.5, 2, 120, 600),
    "PC12": (260, 25000, 3.5, 1, 100, 500),
    "SR22": (170, 8500, 2.5, 1, 40, 200),
    "C172": (110, 5500, 2.0, 2, 30, 120),
}


@dataclass
class Leg:
    icao: str
    kind: str
    rows: list[list[Any]]  # readsb points: seconds after DAY, lat, lon, altitude, gs, track, flags, ...
    origin: str | None
    destination: str | None
    fault: str | None = None


@dataclass
class Generated:
    traces: dict[str, tuple[str, list[list[Any]]]]  # icao -> (type, rows)
    airports: list[Airport]
    flights: list[dict[str, Any]]
    faults: list[dict[str, Any]]
    seed: int = 0
    stats: dict[str, int] = field(default_factory=dict)

    def aircraft(self) -> list[Aircraft]:
        out = []
        for icao, (kind, rows) in self.traces.items():
            ac, _bad, _n = parse_document({"icao": icao, "timestamp": float(DAY), "trace": rows, "t": kind})
            out.append(ac)
        return out

    def truth(self) -> dict[str, Any]:
        return {"seed": self.seed, "flights": self.flights, "faults": self.faults}

    def write(self, directory: str | Path) -> int:
        """traces/xx/trace_full_<icao>.json (gzip), airports.csv and truth.json; returns the number of files."""
        root = Path(directory)
        for icao, (kind, rows) in self.traces.items():
            d = root / "traces" / icao[-2:]
            d.mkdir(parents=True, exist_ok=True)
            (d / f"trace_full_{icao}.json").write_bytes(dump_document(icao, kind, float(DAY), rows))
        (root / "airports.csv").write_text(to_csv(self.airports), encoding="utf-8")
        (root / "truth.json").write_text(json.dumps(self.truth(), indent=1) + "\n", encoding="utf-8")
        return len(self.traces)


def make_airports(rng: random.Random, n: int = 12) -> list[Airport]:
    """Invented airports at least 90 km apart in a box the size of Italy."""
    out: list[Airport] = []
    while len(out) < n:
        lat, lon = round(rng.uniform(37.0, 46.5), 4), round(rng.uniform(7.0, 17.5), 4)
        if all(haversine(lat, lon, a.lat, a.lon) > 90 for a in out):
            i = len(out) + 1
            out.append(
                Airport(
                    f"TA{i:02d}",
                    f"Test Airport {i:02d}",
                    lat,
                    lon,
                    "large_airport" if i <= 4 else "medium_airport",
                    "ZZ",
                )
            )
    return sorted(out, key=lambda a: a.ident)


def slerp(lat1: float, lon1: float, lat2: float, lon2: float, f: float) -> tuple[float, float]:
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (math.cos(p1) * math.cos(l1), math.cos(p1) * math.sin(l1), math.sin(p1))
    b = (math.cos(p2) * math.cos(l2), math.cos(p2) * math.sin(l2), math.sin(p2))
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=True))))
    w = math.acos(dot)
    if w < 1e-12:
        return lat1, lon1
    s = math.sin(w)
    ca, cb = math.sin((1 - f) * w) / s, math.sin(f * w) / s
    v = [ca * x + cb * y for x, y in zip(a, b, strict=True)]
    return math.degrees(math.asin(max(-1.0, min(1.0, v[2])))), math.degrees(math.atan2(v[1], v[0]))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def row(
    t: float, lat: float, lon: float, alt: float | str | None, gs: float | None, track: float, flags: int
) -> list[Any]:
    return [
        round(t - DAY, 1),
        round(lat, 6),
        round(lon, 6),
        alt,
        None if gs is None else round(gs, 1),
        round(track, 1),
        flags,
        None,
        None,
        "adsb_icao",
    ]


def ground_points(
    rng: random.Random, t0: float, t1: float, ap: Airport, step: tuple[float, float], flags0: int
) -> list[list[Any]]:
    out = []
    t = t0
    first = True
    while t < t1:
        out.append(
            row(
                t,
                ap.lat + rng.uniform(-0.003, 0.003),
                ap.lon + rng.uniform(-0.003, 0.003),
                "ground",
                rng.uniform(0, 18),
                rng.uniform(0, 360),
                flags0 if first else 0,
            )
        )
        first = False
        t += rng.uniform(*step)
    return out


def fly(
    rng: random.Random, t0: float, o: Airport, d: Airport, spec: tuple[float, float, float, float, float, float]
) -> tuple[list[list[Any]], float]:
    """The airborne points of a leg from the instant of lift-off, and the time of the last one."""
    cruise_kt, cruise_ft, km_per_kft, _w, _lo, _hi = spec
    dist = haversine(o.lat, o.lon, d.lat, d.lon)
    cruise_ft = min(cruise_ft, 0.9 * dist / (2 * km_per_kft) * 1000)
    cruise_ft = max(1500.0, math.floor(cruise_ft / 500) * 500)
    climb_km = min(0.4 * dist, cruise_ft / 1000 * km_per_kft)
    desc_km = min(0.4 * dist, cruise_ft / 1000 * km_per_kft)
    v_lo = 0.3 * cruise_kt + 40
    out: list[list[Any]] = []
    s, t = 0.0, t0
    while True:
        if s < climb_km:
            f = s / climb_km
            alt, v = 200 + f * (cruise_ft - 200), v_lo + f * (cruise_kt - v_lo)
            dt = rng.uniform(4, 12)
        elif s > dist - desc_km:
            f = (dist - s) / desc_km
            alt, v = 200 + f * (cruise_ft - 200), v_lo + f * (cruise_kt - v_lo)
            dt = rng.uniform(4, 12)
        else:
            alt, v, dt = cruise_ft, cruise_kt, rng.uniform(15, 45)
        fr = min(1.0, s / dist)
        lat, lon = slerp(o.lat, o.lon, d.lat, d.lon, fr)
        if 0 < fr < 1:
            lat, lon = lat + rng.uniform(-0.0004, 0.0004), lon + rng.uniform(-0.0004, 0.0004)
        else:
            lat, lon = lat + rng.uniform(-0.004, 0.004), lon + rng.uniform(-0.004, 0.004)
        gs = None if rng.random() < 0.03 else v + rng.uniform(-3, 3)
        out.append(row(t, lat, lon, round(alt / 25) * 25, gs, bearing(o.lat, o.lon, d.lat, d.lon), 0))
        if fr >= 1.0:
            return out, t
        s = min(dist, s + max(v, 60) * KM_PER_NM / 3600 * dt)
        t += dt


def simulate_leg(
    rng: random.Random, icao: str, kind: str, t_gate: float, o: Airport, d: Airport, first: bool
) -> tuple[Leg, float]:
    spec = TYPES[kind]
    out_s = rng.uniform(240, 700)
    rows = ground_points(rng, t_gate, t_gate + out_s, o, (20, 60), 0 if first else NEW_LEG)
    air, t_land = fly(rng, t_gate + out_s + rng.uniform(30, 90), o, d, spec)
    rows += air
    in_s = rng.uniform(180, 600)
    rows += ground_points(rng, t_land + rng.uniform(15, 40), t_land + in_s, d, (20, 60), 0)
    return Leg(icao, kind, rows, o.ident, d.ident), t_land + in_s


def air_rows(leg: Leg) -> list[list[Any]]:
    return [r for r in leg.rows if r[3] != "ground" and r[3] is not None]


def truth_of(leg: Leg) -> dict[str, Any]:
    air = air_rows(leg)
    km = sum(haversine(a[1], a[2], b[1], b[2]) for a, b in itertools.pairwise(air))
    return {
        "icao": leg.icao,
        "type": leg.kind,
        "takeoff": DAY + air[0][0],
        "landing": DAY + air[-1][0],
        "distance_km": km,
        "max_alt_ft": max(r[3] for r in air),
        "origin": leg.origin,
        "destination": leg.destination,
    }


def pick_dest(
    rng: random.Random, here: Airport, airports: list[Airport], spec: tuple[float, float, float, float, float, float]
) -> Airport:
    options = [
        a for a in airports if a is not here and spec[4] <= haversine(here.lat, here.lon, a.lat, a.lon) <= spec[5]
    ]
    return rng.choice(options or [a for a in airports if a is not here])


def make_fleet(rng: random.Random, airports: list[Airport], n: int) -> list[list[Leg]]:
    kinds = list(TYPES)
    weights = [TYPES[k][3] for k in kinds]
    fleet: list[list[Leg]] = []
    seen: set[str] = set()
    for _ in range(n):
        icao = f"{rng.randrange(0x100000, 0xFFFFFF):06x}"
        while icao in seen:
            icao = f"{rng.randrange(0x100000, 0xFFFFFF):06x}"
        seen.add(icao)
        kind = rng.choices(kinds, weights)[0]
        spec = TYPES[kind]
        here = rng.choice(airports)
        t = DAY + 3600 * rng.choices(range(24), HOURS)[0] + rng.uniform(0, 3000)
        legs: list[Leg] = []
        for k in range(rng.randint(1, 4 if spec[1] > 10000 else 3)):
            there = pick_dest(rng, here, airports, spec)
            leg, t_end = simulate_leg(rng, f"{icao}", kind, t, here, there, k == 0)
            if t_end > DAY + 86400 - 600:
                break
            legs.append(leg)
            here = there
            t = t_end + rng.uniform(1800, 5400) if spec[1] > 10000 else t_end + rng.uniform(1200, 4000)
        if not legs:
            leg, _ = simulate_leg(rng, icao, kind, DAY + 3600, here, pick_dest(rng, here, airports, spec), True)
            legs.append(leg)
        fleet.append(legs)
    return fleet


def apply_structural(rng: random.Random, leg: Leg, kind: str) -> None:
    air = air_rows(leg)
    if kind == "no_start":
        peak = max(r[3] for r in air)
        cut = next(i for i, r in enumerate(leg.rows) if r[3] not in ("ground", None) and r[3] > max(4000.0, 0.7 * peak))
        leg.rows = leg.rows[cut:]
        leg.origin = None
    elif kind == "no_end":
        peak = max(r[3] for r in air)
        last = max(i for i, r in enumerate(leg.rows) if r[3] not in ("ground", None) and r[3] > max(4000.0, 0.7 * peak))
        leg.rows = leg.rows[: last + 1]
        leg.destination = None


def apply_value(rng: random.Random, leg: Leg, kind: str) -> dict[str, Any]:
    """A fault that leaves the truth as it was; returns what was done."""
    air = air_rows(leg)
    if kind == "glitch":
        pick = rng.choice(air[5:-5])
        far = rng.uniform(300, 2000)
        brg = rng.uniform(0, 360)
        lat, lon = pick[1], pick[2]
        dlat = far / 111.0 * math.cos(math.radians(brg))
        pick[1] = round(max(-80.0, min(80.0, lat + dlat)), 6)
        pick[2] = round(lon + far / (111.0 * max(0.2, math.cos(math.radians(lat)))) * math.sin(math.radians(brg)), 6)
        return {"kind": kind, "icao": leg.icao, "t": DAY + pick[0]}
    if kind == "coverage_gap":
        span = air[-1][0] - air[0][0]
        mid = [r for r in air if air[0][0] + 0.2 * span < r[0] < air[0][0] + 0.5 * span]
        start = rng.choice(mid)[0]
        length = min(rng.uniform(600, 1500), 0.3 * span)  # a hole that swallows the landing is a flight that ends early
        before = len(leg.rows)
        leg.rows = [r for r in leg.rows if not (start <= r[0] < start + length and r[3] != "ground")]
        return {"kind": kind, "icao": leg.icao, "t": DAY + start, "seconds": length, "points": before - len(leg.rows)}
    # duplicate: the same instant twice, the second copy a little off
    picks = rng.sample(range(5, len(air) - 5), 4)
    copies = []
    for i in picks:
        r = air[i]
        copies.append((leg.rows.index(r), [r[0], round(r[1] + 0.01, 6), round(r[2] + 0.01, 6), *r[3:]]))
    for idx, c in sorted(copies, reverse=True):
        leg.rows.insert(idx + 1, c)
    return {"kind": kind, "icao": leg.icao, "t": DAY + air[picks[0]][0], "points": len(copies)}


def decoys(rng: random.Random, airports: list[Airport], kinds: list[str]) -> dict[str, tuple[str, list[list[Any]]]]:
    out: dict[str, tuple[str, list[list[Any]]]] = {}
    for kind in kinds:
        icao = f"{rng.randrange(0x100000, 0xFFFFFF):06x}"
        ap = rng.choice(airports)
        t0 = DAY + rng.uniform(3600, 70000)
        if kind == "ground_only":
            rows = ground_points(rng, t0, t0 + 1500, ap, (10, 30), 0)
            out[icao] = ("A320", rows)
        else:  # brief: 12 airborne points in 165 seconds around the airport
            rows = ground_points(rng, t0, t0 + 300, ap, (20, 40), 0)
            t = t0 + 330
            for i in range(12):
                ang = 2 * math.pi * i / 12
                rows.append(
                    row(t, ap.lat + 0.02 * math.sin(ang), ap.lon + 0.02 * math.cos(ang), 400 + 25 * i, 60.0, 0.0, 0)
                )
                t += 15
            rows += ground_points(rng, t + 20, t + 300, ap, (20, 40), 0)
            out[icao] = ("C172", rows)
    return out


def generate(
    aircraft: int = 300, seed: int = 1, faults: dict[str, int] | None = None, clean: bool = False
) -> Generated:
    rng = random.Random(seed)
    airports = make_airports(rng)
    fleet = make_fleet(rng, airports, aircraft)
    all_legs = [leg for legs in fleet for leg in legs]
    if clean:
        want: dict[str, int] = {}
    elif faults is not None:
        want = faults
    else:
        want = {k: round(aircraft * r) for k, r in DEFAULT_RATES.items()}
    unknown = set(want) - set(FAULT_KINDS)
    if unknown:
        raise ValueError(f"unknown faults: {sorted(unknown)}")
    on_legs = ("glitch", "no_start", "no_end", "coverage_gap", "duplicate")
    need = sum(want.get(k, 0) for k in on_legs)
    if need > len(all_legs) // 2:
        raise ValueError("too many faults for the number of flights")
    pool = [leg for leg in all_legs if len(air_rows(leg)) >= 60]
    rng.shuffle(pool)
    assigned: list[tuple[Leg, str]] = []
    for kind in on_legs:
        for _ in range(want.get(kind, 0)):
            if not pool:
                raise ValueError("too many faults for the number of flights")
            leg = pool.pop()
            leg.fault = kind
            assigned.append((leg, kind))
    for leg, kind in assigned:
        if kind in ("no_start", "no_end"):
            apply_structural(rng, leg, kind)
    flights = [{**truth_of(leg), "fault": leg.fault} for leg in all_legs]
    fault_log: list[dict[str, Any]] = []
    for leg, kind in assigned:
        if kind in ("glitch", "coverage_gap", "duplicate"):
            fault_log.append(apply_value(rng, leg, kind))
        else:
            fault_log.append({"kind": kind, "icao": leg.icao, "t": DAY + air_rows(leg)[0][0]})
    traces: dict[str, tuple[str, list[list[Any]]]] = {}
    for legs in fleet:
        rows = [r for leg in legs for r in leg.rows]
        traces[legs[0].icao] = (legs[0].kind, rows)
    extra = [k for k in ("ground_only", "brief") for _ in range(want.get(k, 0))]
    for (icao, trace), k in zip(decoys(rng, airports, extra).items(), extra, strict=True):
        traces[icao] = trace
        fault_log.append({"kind": k, "icao": icao})
    flights.sort(key=lambda f: (f["takeoff"], f["icao"]))
    fault_log.sort(key=lambda f: (f["kind"], f.get("icao", ""), f.get("t", 0)))
    counts = {k: sum(1 for f in fault_log if f["kind"] == k) for k in FAULT_KINDS}
    return Generated(traces, airports, flights, fault_log, seed, counts)
