# Changelog

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
