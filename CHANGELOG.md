# Changelog

## 1.1.0

A real day, and what it asked for.

- First real data: the first part of adsb.lol's archive for 10 November 2026 (53,099 aircraft, 72,983,747 reports, 135,278
  flights, 547 s) in `docs/real.json`, `docs/real.md` and `docs/real.png`, with the analysis in `docs/analysis.md` section 6.
- Three new totals: flights already in the air when the day began, flights still in the air when it ended (the first and last
  10 minutes of the UTC day) and round trips (the same airport at both ends). They explain the spike at 00:00 UTC and the
  busiest "routes" of a real day.
- The report records the time taken (`elapsed_s`) and prints reports a second; `analyze` writes a progress line to stderr every
  5,000 aircraft, so a run of minutes is not silent.
- The limits and the speed statements are rewritten from what the real day measured.

## 1.0.0

First release.

- A reader of readsb trace files (the format of adsb.lol's open history): one gzip or plain JSON document per aircraft, from a
  directory, a tar archive (a truncated one is read as far as it goes) or a single file; unusable points and files are counted.
- A reader of OurAirports `airports.csv`, with a one-degree grid to name the nearest airport.
- A definition of a flight in five steps with named parameters: time order, glitch removal, legs, the flight test, take-off and
  landing with origin and destination.
- Two implementations: NumPy, and a literal point-by-point one. `adsbstat verify` compares them (flights, counts and
  histograms) on generated and spoiled traffic with random parameters.
- A generator of synthetic days in the readsb format with the truth about every flight and 7 kinds of injected fault, and a scoring of
  the analysis against it.
- A report (JSON, Markdown, figure): totals, take-offs by UTC hour, altitude and speed shares, busiest airports and routes, types,
  distance and duration quantiles; rebuilt exactly from its JSON. A benchmark of speed, reading and accuracy.
- A command line with exit codes for a pipeline (0 ok, 1 a mismatch, 2 an error).
- Docker image (no network, read-only, no capabilities); CI on Python 3.11 to 3.14, Linux, Windows and macOS.
