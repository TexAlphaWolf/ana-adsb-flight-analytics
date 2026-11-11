# Architecture

```
                     cli.py ──────────────────────────────────────────────┐
                       │                                                   │
   ┌────────────┬──────┴───────┬───────────────┬──────────────┐           │
   ▼            ▼              ▼               ▼              ▼           ▼
trace.py    flights.py    reference.py    generate.py    analysis.py   verify.py
airports.py (NumPy)       (literal)       (+ truth)      report.py     bench.py
(readers)                                                score.py
   │            │              │               │              │           │
   └────────────┴──────┬───────┴───────────────┴──────────────┴───────────┘
                       ▼
               params.py, geo.py
```

| Module | Role |
|---|---|
| `trace.py` | Reads readsb trace files from a file, a directory or a tar stream; `Point`, `Aircraft`, `ReadStats`; writes them too (for the generator and the tests) |
| `airports.py` | Reads OurAirports `airports.csv`; `nearest_literal` (every airport) and `Index` (a one-degree grid) that must agree |
| `geo.py` | Great-circle distance, scalar and NumPy, the same formula |
| `params.py` | The parameters of the definition of a flight, with defaults |
| `flights.py` | The fast implementation: NumPy over the points of each aircraft |
| `reference.py` | The literal implementation: one point at a time, every airport measured |
| `generate.py` | Simulates a day of traffic in the readsb format, injects faults, keeps the truth |
| `score.py` | The found flights against the true ones and the injected faults |
| `verify.py` | Generated and spoiled traffic with random parameters, and the comparison |
| `analysis.py`, `report.py`, `bench.py` | The report (JSON, Markdown, figure) and the benchmark |
| `cli.py` | The command line |

## Decisions

- **Two implementations that share only the definition.** One uses arrays and a grid index for airports, the other loops over
  points and airports. A disagreement is a bug in one of them. The same formula is used for distances in both, so floats agree
  to rounding (1.5e-15 in the benchmark) and are compared within 1e-9.
- **Aircraft are read one at a time.** `analyze` consumes a generator: the points of an aircraft live until it has been
  analysed, so a day of traces does not have to fit in memory. The cost is that nothing about an aircraft can depend on another.
- **A flight is defined, not guessed.** Five steps with named parameters (`docs/method.md`), because the same trace gives a
  different number of flights under different definitions and that has to be visible.
- **The truth comes from the simulator.** The generator writes the flights it simulated and the faults it injected, before the
  faults are applied, so the score compares the analysis with what really flew.
- **A bad file is a count, not a crash.** In a directory or archive an unreadable file or point is counted and reported; for a
  single file the error is raised, because that is the only thing asked for.
- **Few dependencies.** NumPy and matplotlib (for the figures); gzip, JSON and tar come from the standard library.
- **The report is rebuilt from its JSON.** `adsbstat render` produces the Markdown and the figure from `report.json` or
  `bench.json` alone, and a test checks that the files in `docs/` are exactly that render.
- **No network, no service.** The program reads files and writes files; the Docker image runs without network, with a read-only
  root and no capabilities, and the input is mounted read-only.
