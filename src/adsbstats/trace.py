"""Reading readsb trace files: one JSON document per aircraft per day, usually gzip-compressed.

A document has `icao`, `timestamp` (Unix seconds) and `trace`, a list of points. Each point is a list: seconds after
`timestamp`, latitude, longitude, altitude in feet (a number, "ground" or null), ground speed in knots, track, flags, and
more that is not used here. Bit 2 of the flags marks the start of a new leg (a likely landing and take-off in between).
"""

from __future__ import annotations

import gzip
import io
import json
import math
import tarfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

NEW_LEG = 2


class TraceError(ValueError):
    pass


class Point(NamedTuple):
    t: float  # Unix seconds
    lat: float
    lon: float
    alt: float | None  # feet; None when on the ground or unknown
    ground: bool
    gs: float | None  # knots
    flags: int


@dataclass(frozen=True)
class Aircraft:
    icao: str
    type: str | None
    points: tuple[Point, ...]


@dataclass
class ReadStats:
    files: int = 0
    aircraft: int = 0
    points: int = 0
    bad_points: int = 0
    bad_files: int = 0
    kept_points: int = 0
    truncated: bool = False
    first_error: str = field(default="")


def number(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x):
        return None
    return float(x)


def parse_document(doc: Any, bbox: tuple[float, float, float, float] | None = None) -> tuple[Aircraft, int, int]:
    """(the aircraft, points dropped as malformed, points read). Points outside `bbox` (lat0, lon0, lat1, lon1) are not kept."""
    if not isinstance(doc, dict):
        raise TraceError("a trace file is a JSON object")
    icao = doc.get("icao")
    if not isinstance(icao, str) or not icao.strip():
        raise TraceError("missing 'icao'")
    base = number(doc.get("timestamp"))
    if base is None:
        raise TraceError("missing 'timestamp'")
    raw = doc.get("trace")
    if not isinstance(raw, list):
        raise TraceError("missing 'trace'")
    kind = doc.get("t")
    points: list[Point] = []
    bad = 0
    for row in raw:
        p = parse_point(row, base)
        if p is None:
            bad += 1
        elif bbox is None or (bbox[0] <= p.lat <= bbox[2] and bbox[1] <= p.lon <= bbox[3]):
            points.append(p)
    return (
        Aircraft(icao.strip().lower(), kind if isinstance(kind, str) and kind else None, tuple(points)),
        bad,
        len(raw),
    )


def parse_point(row: Any, base: float) -> Point | None:
    if not isinstance(row, list) or len(row) < 7:
        return None
    dt, lat, lon = number(row[0]), number(row[1]), number(row[2])
    if dt is None or lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    alt = row[3]
    ground = alt == "ground"
    alt_ft = None if ground else number(alt)
    if not ground and alt is not None and alt_ft is None:
        return None
    flags = row[6]
    if isinstance(flags, bool) or not isinstance(flags, int):
        return None
    return Point(base + dt, lat, lon, alt_ft, ground, number(row[4]), flags)


def decode(data: bytes) -> Any:
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError, zlib.error) as exc:
            raise TraceError(f"cannot decompress: {exc}") from exc
    try:
        return json.loads(data)
    except (ValueError, RecursionError) as exc:
        raise TraceError(f"not valid JSON: {exc}") from exc


def is_trace_name(name: str) -> bool:
    base = name.rsplit("/", 1)[-1]
    return base.startswith("trace_") and (base.endswith((".json", ".json.gz")))


def is_single(p: Path) -> bool:
    return is_trace_name(p.name) or p.name.endswith((".json", ".json.gz"))


def blobs(path: Path, stats: ReadStats) -> Iterator[tuple[str, bytes]]:
    """(name, bytes) of every trace file in a file, a directory or a tar stream (a truncated tar part is read as far as it goes)."""
    if path.is_dir():
        for p in sorted(path.rglob("*")):
            if p.is_file() and is_trace_name(p.name):
                try:
                    yield str(p), p.read_bytes()
                except OSError as exc:
                    stats.bad_files += 1
                    stats.first_error = stats.first_error or f"{p}: {exc}"
        return
    if not path.is_file():
        raise TraceError(f"{path}: no such file or directory")
    if is_single(path):
        yield str(path), path.read_bytes()
        return
    try:
        with tarfile.open(path, mode="r|*") as tar:
            for member in tar:
                if member.isfile() and is_trace_name(member.name):
                    f = tar.extractfile(member)
                    if f is not None:
                        yield member.name, f.read()
    except (tarfile.ReadError, EOFError, OSError, zlib.error) as exc:
        stats.truncated = True
        stats.first_error = stats.first_error or f"{path}: the archive ends early ({exc})"


def read_path(
    path: str | Path,
    stats: ReadStats,
    limit: int | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> Iterator[Aircraft]:
    """The aircraft of a file, directory or tar (stats are updated as it goes); a bad file inside is counted and skipped."""
    p = Path(path)
    single = p.is_file() and is_single(p)
    for name, data in blobs(p, stats):
        stats.files += 1
        try:
            ac, bad, total = parse_document(decode(data), bbox)
        except TraceError as exc:
            if single:
                raise TraceError(f"{name}: {exc}") from exc
            stats.bad_files += 1
            stats.first_error = stats.first_error or f"{name}: {exc}"
            continue
        stats.points += total
        stats.bad_points += bad
        if not ac.points:
            continue
        stats.aircraft += 1
        stats.kept_points += len(ac.points)
        yield ac
        if limit is not None and stats.aircraft >= limit:
            return


def dump_document(ac_hex: str, kind: str | None, base: float, rows: list[list[Any]]) -> bytes:
    """A trace file as readsb writes it, gzip-compressed."""
    doc: dict[str, Any] = {"icao": ac_hex, "timestamp": base, "trace": rows}
    if kind:
        doc["t"] = kind
    return gzip.compress(json.dumps(doc, separators=(",", ":")).encode(), mtime=0)


def tar_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()
