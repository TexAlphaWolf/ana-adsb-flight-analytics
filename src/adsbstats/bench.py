"""How fast the analysis is, how well it does against the truth, and that it agrees with the literal implementation."""

from __future__ import annotations

import os
import platform
import statistics
import tempfile
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__, flights, reference, score, verify
from .generate import generate
from .params import Params
from .trace import ReadStats, read_path, tar_bytes


def timed(fn: Callable[[], object], repeat: int) -> float:
    runs = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t0)
    return statistics.median(runs)


def sweep(seeds: int, aircraft: int) -> dict[str, Any]:
    """Generate days with seeds 1..seeds, analyse each and add up how the analysis did against its truth."""
    tot = {"true": 0, "found": 0, "matched": 0, "extra": 0}
    ok_o = ok_d = 0
    dist: list[float] = []
    glitches = {"injected": 0, "removed": 0}
    faults: dict[str, dict[str, int]] = {}
    for seed in range(1, seeds + 1):
        g = generate(aircraft, seed)
        res = flights.analyze(g.aircraft(), g.airports)
        sc = score.score(res, g.truth())
        for k in tot:
            tot[k] += sc["flights"][k]
        ok_o += sc["airports"]["origin_correct"]
        ok_d += sc["airports"]["destination_correct"]
        for t, f in score.match(res["flights"], g.flights):
            dist.append(abs(f["distance_km"] - t["distance_km"]) / t["distance_km"])
        for k in glitches:
            glitches[k] += sc["glitches"][k]
        for k, v in sc["faults"].items():
            d = faults.setdefault(k, {"injected": 0, "handled": 0})
            d["injected"] += v["injected"]
            d["handled"] += v["handled"]
    return {
        "seeds": seeds,
        "aircraft": aircraft,
        "flights": tot,
        "origin_correct": ok_o,
        "destination_correct": ok_d,
        "distance_error_median": statistics.median(dist),
        "distance_error_p95": float(np.percentile(dist, 95)),
        "distance_error_max": max(dist),
        "glitches": glitches,
        "faults": faults,
    }


def run_bench(
    sizes: list[int],
    repeat: int,
    seed: int,
    draws: int,
    command: str,
    ref_aircraft: int = 100,
    seeds: int = 20,
    progress: Callable[[str], None] = lambda _m: None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    p = Params()
    rows = []
    for n in sizes:
        progress(f"analysis of {n:,} aircraft")
        g = generate(n, seed)
        ac = g.aircraft()
        airports = g.airports
        del g
        res = flights.analyze(ac, airports, p)
        rows.append(
            {
                "aircraft": n,
                "points": res["points"],
                "flights": len(res["flights"]),
                "seconds": timed(partial(flights.analyze, ac, airports, p), repeat),
            }
        )
        del ac
    progress(f"literal implementation on {ref_aircraft:,} aircraft")
    g = generate(ref_aircraft, seed)
    ac = g.aircraft()
    ref = {
        "aircraft": ref_aircraft,
        "points": sum(len(a.points) for a in ac),
        "seconds": timed(partial(reference.analyze, ac, g.airports, p), max(1, repeat // 2)),
        "fast_seconds": timed(partial(flights.analyze, ac, g.airports, p), repeat),
    }
    progress("write and read trace files")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_s = timed(lambda: g.write(root / "w"), 1)
        n_files = len(g.traces)
        stats = ReadStats()
        list(read_path(root / "w" / "traces", stats))
        files = {
            f"traces/{p_.parent.name}/{p_.name}": p_.read_bytes()
            for p_ in sorted((root / "w" / "traces").rglob("*.json"))
        }
        (root / "t.tar").write_bytes(tar_bytes(files))
        read_dir_s = timed(lambda: list(read_path(root / "w" / "traces", ReadStats())), repeat)
        read_tar_s = timed(lambda: list(read_path(root / "t.tar", ReadStats())), repeat)
    points = stats.points
    progress(f"agreement with the literal implementation on {draws} random cases")
    checks = verify.verify(draws, seed)
    progress(f"accuracy against the truth of {seeds} generated days")
    accuracy = sweep(seeds, 200)
    return {
        "kind": "bench",
        "environment": {
            "adsbstats": __version__,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "system": f"{platform.system()} {platform.machine()}",
            "cpus": os.cpu_count(),
            "seed": seed,
            "repeat": repeat,
            "command": command,
            "seconds": round(time.perf_counter() - t0, 1),
        },
        "analysis": rows,
        "reference": ref,
        "write": {"files": n_files, "points": points, "seconds": write_s},
        "read_dir": {"files": n_files, "points": points, "seconds": read_dir_s},
        "read_tar": {"files": n_files, "points": points, "seconds": read_tar_s},
        "accuracy": accuracy,
        "verification": {
            "checks": len(checks),
            "numbers": sum(c.numbers for c in checks),
            "ok": all(c.ok for c in checks),
            "max_rel_error": max(c.max_rel_error for c in checks),
            "tolerance": verify.RTOL,
        },
    }
