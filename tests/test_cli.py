from __future__ import annotations

import json
from pathlib import Path

import pytest

from adsbstats import __version__
from adsbstats.cli import main, parse_bbox
from adsbstats.generate import generate
from adsbstats.trace import dump_document, tar_bytes

from .conftest import SEED


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("day") / "day"
    assert main(["generate", str(root), "--aircraft", "40", "--seed", str(SEED)]) == 0
    return root


def test_generate_layout_and_refuses_a_full_directory(made: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        (made / "airports.csv").is_file()
        and (made / "truth.json").is_file()
        and any((made / "traces").rglob("trace_*.json"))
    )
    code, _out, err = run(capsys, "generate", str(made))
    assert code == 2 and "is not empty" in err


def test_analyze_a_generated_directory_scores_itself(
    made: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(capsys, "analyze", str(made), "--out", str(tmp_path / "o"))
    assert code == 0 and "against the truth" in out and "0 extra" in out
    rep = json.loads((tmp_path / "o" / "report.json").read_text(encoding="utf-8"))
    assert rep["kind"] == "report" and rep["read"]["bad_files"] == 0 and rep["accuracy"]["flights"]["missed"] == 0
    assert (tmp_path / "o" / "report.md").is_file() and (tmp_path / "o" / "summary.png").is_file()


def test_analyze_a_tar_with_options(made: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = {f"traces/{p.parent.name}/{p.name}": p.read_bytes() for p in sorted((made / "traces").rglob("*.json"))}
    tar = tmp_path / "day.tar.aa"
    tar.write_bytes(tar_bytes(files))
    code, out, _ = run(
        capsys,
        "analyze",
        str(tar),
        "--airports",
        str(made / "airports.csv"),
        "--limit",
        "10",
        "--min-air-km",
        "20",
        "--name",
        "named",
    )
    assert code == 0 and out.startswith("named: 10 aircraft") and "against the truth" not in out
    code, out, _ = run(capsys, "analyze", str(tar), "--bbox", "0,0,1,1")
    assert code == 2


def test_analyze_demo(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "analyze")
    assert code == 0 and "demo day" in out and "0 extra" in out
    code, _, err = run(capsys, "analyze", "--truth", "x.json")
    assert code == 2 and "need a path" in err


@pytest.mark.parametrize(
    "args",
    [
        ("analyze", "does-not-exist"),
        ("analyze", "--bbox", "1,2,3", "x"),
        ("analyze", "--bbox", "10,0,5,1", "x"),
        ("render", "does-not-exist.json"),
    ],
)
def test_errors_exit_two(capsys: pytest.CaptureFixture[str], args: tuple[str, ...]) -> None:
    code, _, err = run(capsys, *args)
    assert code == 2 and err.startswith("error:")


def test_missing_files_next_to_a_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "trace_full_a00001.json"
    f.write_bytes(dump_document("a00001", None, 0.0, [[0, 1.0, 1.0, 1000, 100.0, 0.0, 0]]))
    code, out, _ = run(capsys, "analyze", str(f))
    assert code == 0 and "1 aircraft" in out and "0 flights" in out
    code, _, err = run(capsys, "analyze", str(f), "--truth", str(tmp_path / "nope.json"))
    assert code == 2 and "truth" in err
    (tmp_path / "empty.csv").write_text("ident,type,name,latitude_deg,longitude_deg\n", encoding="utf-8")
    code, _, err = run(capsys, "analyze", str(f), "--airports", str(tmp_path / "empty.csv"))
    assert code == 2 and "no airports" in err
    bad = tmp_path / "trace_full_a00002.json"
    bad.write_bytes(b"{")
    code, _, err = run(capsys, "analyze", str(bad))
    assert code == 2 and "a00002" in err
    code, _, err = run(capsys, "analyze", str(tmp_path / "d"))
    assert code == 2


def test_verify_and_render(made: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "verify", "--draws", "2")
    assert code == 0 and "3 of 3 comparisons agree" in out
    run(capsys, "analyze", str(made), "--out", str(tmp_path))
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    code, out, _ = run(capsys, "render", str(tmp_path / "report.json"), "--figure", str(tmp_path / "again.png"))
    assert code == 0 and out.startswith(md) and (tmp_path / "again.png").is_file()
    code, out, _ = run(capsys, "render", str(tmp_path / "report.json"), "-o", str(tmp_path / "again.md"))
    assert (tmp_path / "again.md").read_text(encoding="utf-8") == md
    (tmp_path / "x.json").write_text('{"kind": "other"}', encoding="utf-8")
    assert run(capsys, "render", str(tmp_path / "x.json"))[0] == 2


def test_bench_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(
        capsys,
        "bench",
        "--sizes",
        "20",
        "--repeat",
        "1",
        "--draws",
        "1",
        "--seeds",
        "1",
        "--ref-aircraft",
        "20",
        "--out",
        str(tmp_path),
    )
    assert code == 0 and "written:" in out
    assert json.loads((tmp_path / "bench.json").read_text(encoding="utf-8"))["kind"] == "bench"
    code, _, err = run(capsys, "bench", "--sizes", "5", "--out", str(tmp_path))
    assert code == 2 and "10 or more" in err
    assert run(capsys, "render", str(tmp_path / "bench.json"))[0] == 0


def test_parse_bbox() -> None:
    assert parse_bbox(None) is None and parse_bbox("36,6,47,19") == (36.0, 6.0, 47.0, 19.0)
    for bad in ("a,b,c,d", "1,2,3", "50,0,40,10", "-100,0,0,10", "0,-200,10,10"):
        with pytest.raises(ValueError, match="bbox"):
            parse_bbox(bad)


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--version"])
    assert f"adsbstat {__version__}" in capsys.readouterr().out
    assert generate(5, 1).stats  # the generator also works for tiny fleets
