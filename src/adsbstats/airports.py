"""Airports from an OurAirports `airports.csv`, and the nearest one to a point."""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from .geo import haversine, haversine_np

KINDS = ("large_airport", "medium_airport", "small_airport")


class AirportError(ValueError):
    pass


@dataclass(frozen=True)
class Airport:
    ident: str
    name: str
    lat: float
    lon: float
    kind: str = "small_airport"
    country: str = ""

    @property
    def label(self) -> str:
        return self.ident


def parse_airports(text: str, kinds: tuple[str, ...] = KINDS) -> list[Airport]:
    """The open airports of the given kinds, ordered by ident (so that ties are always broken the same way)."""
    reader = csv.DictReader(io.StringIO(text))
    need = {"ident", "type", "name", "latitude_deg", "longitude_deg"}
    if reader.fieldnames is None or not need <= set(reader.fieldnames):
        raise AirportError(f"not an OurAirports airports.csv: columns {sorted(need)} are needed")
    out: dict[str, Airport] = {}
    for row in reader:
        if row["type"] not in kinds:
            continue
        try:
            lat, lon = float(row["latitude_deg"]), float(row["longitude_deg"])
        except ValueError:
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not row["ident"]:
            continue
        out.setdefault(
            row["ident"], Airport(row["ident"], row["name"], lat, lon, row["type"], row.get("iso_country", ""))
        )
    return sorted(out.values(), key=lambda a: a.ident)


def load_airports(path: str | Path, kinds: tuple[str, ...] = KINDS) -> list[Airport]:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise AirportError(f"{path}: cannot be read: {exc}") from exc
    return parse_airports(text, kinds)


def to_csv(airports: list[Airport]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["ident", "type", "name", "latitude_deg", "longitude_deg", "iso_country"])
    for a in airports:
        w.writerow([a.ident, a.kind, a.name, f"{a.lat:.6f}", f"{a.lon:.6f}", a.country])
    return buf.getvalue()


def nearest_literal(airports: list[Airport], lat: float, lon: float, max_km: float) -> str | None:
    """Every airport in turn; the closest within `max_km`, the first of them if two are equally close."""
    best: str | None = None
    best_km = math.inf
    for a in airports:
        d = haversine(lat, lon, a.lat, a.lon)
        if d <= max_km and d < best_km:
            best, best_km = a.ident, d
    return best


class Index:
    """The same answer from a grid of one-degree cells: only the airports in the cells around a point are measured."""

    def __init__(self, airports: list[Airport], max_km: float) -> None:
        self.airports = airports
        self.max_km = max_km
        self.lat: npt.NDArray[np.float64] = np.array([a.lat for a in airports], dtype=np.float64)
        self.lon: npt.NDArray[np.float64] = np.array([a.lon for a in airports], dtype=np.float64)
        self.cells: dict[tuple[int, int], list[int]] = {}
        for i, a in enumerate(airports):
            self.cells.setdefault((math.floor(a.lat), math.floor(a.lon)), []).append(i)

    def nearest(self, lat: float, lon: float) -> str | None:
        dlat = math.ceil(self.max_km / 111.0) + 1
        cos = max(math.cos(math.radians(min(abs(lat) + self.max_km / 111.0, 89.9))), 1e-3)
        dlon = min(math.ceil(self.max_km / (111.0 * cos)) + 1, 181)
        c_lat, c_lon = math.floor(lat), math.floor(lon)
        found: list[int] = []
        for i in range(c_lat - dlat, c_lat + dlat + 1):
            for j in range(c_lon - dlon, c_lon + dlon + 1):
                found.extend(self.cells.get((i, (j + 180) % 360 - 180), []))
        if not found:
            return None
        idx = np.array(sorted(set(found)))
        d = haversine_np(np.full(len(idx), lat), np.full(len(idx), lon), self.lat[idx], self.lon[idx])
        k = int(np.argmin(d))
        return self.airports[int(idx[k])].ident if d[k] <= self.max_km else None
