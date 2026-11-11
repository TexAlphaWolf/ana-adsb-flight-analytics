# Contributing

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest --cov
```

No service is needed. `ADSB_TEST_DRAWS` and `ADSB_TEST_SEED` run the same tests with more (or different) random days of traffic
(CI also uses 150 draws with seed 11).

Rules that keep the project honest:

- **A change to the definition of a flight needs both implementations.** Change `flights.py` (NumPy) and `reference.py`
  (literal) the same way, update `docs/method.md`, add a hand-computed case to `tests/test_flights.py` (it runs through both) and
  let `adsbstat verify` compare them.
- **A change to the generator needs the truth to stay exact.** `tests/test_generate.py` requires that every true flight is found
  with the right airports, that glitches are all removed and that decoys are not reported, on many seeds; keep it passing.
- **Numbers in the README and `docs/analysis.md` come from `docs/report.json` and `docs/bench.json`**, and `tests/test_docs.py`
  checks them. After a change to the generator or the definitions, regenerate them (`adsbstat analyze --out`, then
  `tools/run_full.ps1` for the benchmark) and update the text where a number moved.
- **The reader stays strict about what it counts.** An unusable point or file is counted and reported, never silently kept; a new
  accepted deviation needs a test that says why.
