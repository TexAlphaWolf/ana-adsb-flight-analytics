from __future__ import annotations

import gzip
import json
import random
from pathlib import Path
from typing import Any

import pytest

from adsbstats.trace import (
    ReadStats,
    TraceError,
    decode,
    dump_document,
    is_trace_name,
    parse_document,
    parse_point,
    read_path,
    tar_bytes,
)

ROW = [10.5, 45.0, 9.0, 12000, 400.0, 90.0, 0, None, None, "adsb_icao"]


def doc(rows: list[Any], icao: str = "ABC123", **extra: Any) -> dict[str, Any]:
    return {"icao": icao, "timestamp": 1000.0, "trace": rows, **extra}


def test_parse_point_fields() -> None:
    p = parse_point(ROW, 1000.0)
    assert p is not None
    assert (p.t, p.lat, p.lon, p.alt, p.ground, p.gs, p.flags) == (1010.5, 45.0, 9.0, 12000.0, False, 400.0, 0)


def test_ground_and_null_altitude() -> None:
    ground = parse_point([*ROW[:3], "ground", *ROW[4:]], 0.0)
    unknown = parse_point([*ROW[:3], None, *ROW[4:]], 0.0)
    assert ground is not None and ground.ground and ground.alt is None
    assert unknown is not None and not unknown.ground and unknown.alt is None


@pytest.mark.parametrize(
    "row",
    [
        None,
        "x",
        [1, 2, 3],
        [None, 45, 9, 100, 1, 1, 0],
        [1, 91, 9, 100, 1, 1, 0],
        [1, 45, 181, 100, 1, 1, 0],
        [1, 45, 9, "high", 1, 1, 0],
        [1, 45, 9, 100, 1, 1, "x"],
        [1, 45, 9, 100, 1, 1, True],
        [float("nan"), 45, 9, 100, 1, 1, 0],
        [True, 45, 9, 100, 1, 1, 0],
    ],
)
def test_malformed_points_are_refused(row: Any) -> None:
    assert parse_point(row, 0.0) is None


def test_document_counts_bad_points_and_lowercases_icao() -> None:
    ac, bad, total = parse_document(doc([ROW, "junk", ROW], icao=" ABC123 ", t="A320"))
    assert (ac.icao, ac.type, len(ac.points), bad, total) == ("abc123", "A320", 2, 1, 3)


@pytest.mark.parametrize(
    "bad",
    [
        [],
        "x",
        {"timestamp": 1, "trace": []},
        {"icao": " ", "timestamp": 1, "trace": []},
        {"icao": "a", "trace": []},
        {"icao": "a", "timestamp": 1},
    ],
)
def test_bad_documents(bad: Any) -> None:
    with pytest.raises(TraceError):
        parse_document(bad)


def test_bbox_keeps_points_inside() -> None:
    inside, outside = ROW, [1, 10.0, 9.0, 100, 1, 1, 0]
    ac, bad, total = parse_document(doc([inside, outside]), (40.0, 5.0, 50.0, 15.0))
    assert len(ac.points) == 1 and bad == 0 and total == 2


def test_decode_plain_gzip_and_broken() -> None:
    raw = json.dumps({"a": 1}).encode()
    assert decode(raw) == decode(gzip.compress(raw)) == {"a": 1}
    with pytest.raises(TraceError, match="not valid JSON"):
        decode(b"{oops")
    with pytest.raises(TraceError, match="decompress"):
        decode(gzip.compress(raw)[:-6])
    with pytest.raises(TraceError):
        decode(b"[" * 100000)


def test_names() -> None:
    assert is_trace_name("traces/ab/trace_full_abc123.json")
    assert is_trace_name("trace_recent_abc123.json.gz")
    assert not is_trace_name("airports.csv") and not is_trace_name("traces/ab/readme.json")


def make_dir(tmp_path: Path, n: int = 3) -> Path:
    for i in range(n):
        icao = f"a0000{i}"
        d = tmp_path / "traces" / icao[-2:]
        d.mkdir(parents=True, exist_ok=True)
        (d / f"trace_full_{icao}.json").write_bytes(dump_document(icao, "A320", 1000.0, [ROW, ROW]))
    return tmp_path


def test_read_directory(tmp_path: Path) -> None:
    s = ReadStats()
    got = list(read_path(make_dir(tmp_path), s))
    assert [a.icao for a in got] == ["a00000", "a00001", "a00002"]
    assert (s.files, s.aircraft, s.points, s.kept_points, s.bad_files) == (3, 3, 6, 6, 0)


def test_limit_and_bbox(tmp_path: Path) -> None:
    root = make_dir(tmp_path)
    assert len(list(read_path(root, ReadStats(), limit=2))) == 2
    s = ReadStats()
    assert list(read_path(root, s, bbox=(0.0, 0.0, 10.0, 10.0))) == []
    assert s.points == 6 and s.kept_points == 0 and s.aircraft == 0


def test_bad_file_in_a_directory_is_counted_and_skipped(tmp_path: Path) -> None:
    root = make_dir(tmp_path)
    (root / "traces" / "00" / "trace_full_ffffff.json").write_bytes(b"not json")
    s = ReadStats()
    assert len(list(read_path(root, s))) == 3
    assert s.bad_files == 1 and "ffffff" in s.first_error


def test_single_file_and_its_error(tmp_path: Path) -> None:
    good = tmp_path / "trace_full_a00000.json"
    good.write_bytes(dump_document("a00000", None, 1000.0, [ROW]))
    (ac,) = read_path(good, ReadStats())
    assert ac.type is None
    bad = tmp_path / "trace_full_a00001.json"
    bad.write_bytes(b"oops")
    with pytest.raises(TraceError, match="a00001"):
        list(read_path(bad, ReadStats()))


def test_tar_and_truncated_tar(tmp_path: Path) -> None:
    rng = random.Random(1)
    rows = [[float(i), rng.uniform(40, 50), rng.uniform(5, 15), 12000, 400.0, 90.0, 0] for i in range(3000)]
    files = {
        f"traces/0{i}/trace_full_a0000{i}.json": dump_document(f"a0000{i}", "B738", 1000.0, rows) for i in range(3)
    }
    files["readme.txt"] = b"not a trace"
    blob = tar_bytes(files)
    whole = tmp_path / "day.tar.aa"
    whole.write_bytes(blob)
    s = ReadStats()
    assert len(list(read_path(whole, s))) == 3 and not s.truncated
    cut = tmp_path / "cut.tar.aa"
    cut.write_bytes(blob[: len(blob) // 2])
    s = ReadStats()
    got = list(read_path(cut, s))
    assert 1 <= len(got) < 3 and s.truncated and "ends early" in s.first_error


def test_not_there(tmp_path: Path) -> None:
    with pytest.raises(TraceError, match="no such file"):
        list(read_path(tmp_path / "nope", ReadStats()))


def test_dump_document_round_trip() -> None:
    ac, bad, total = parse_document(decode(dump_document("abc123", "C172", 5.0, [ROW])))
    assert (ac.icao, ac.type, bad, total, ac.points[0].t) == ("abc123", "C172", 0, 1, 15.5)
