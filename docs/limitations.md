# Limitations

- **No real day has been analysed.** The reader was written from the documentation of the readsb trace format and tested on
  files the generator writes in that format (gzip, plain, directories, tar, truncated tar, malformed points). A real day has
  features this does not exercise: aircraft with several documents, positions from other sources (MLAT, TIS-B, ADS-C), odd flags,
  and a size of billions of reports. `tools/run_real.ps1` is there to run it; until the result is in `docs/`, treat the real-world
  behaviour as untested.
- **The detection score is a ceiling.** The faults are injected by the same code base that defines the flights. 960 of 960 handled
  says the two agree, not that the definitions cover what goes wrong in real traces. Real glitches come in runs of several points,
  and the definition splits the leg on those instead of removing them.
- **The data is synthetic.** The demo and the benchmark use 12 invented airports and 7 aircraft types with smooth profiles and
  clean departures; real aircraft hold, go around, fly circuits and have irregular climbs. The altitude and speed distributions
  of the report describe the simulator, not the sky.
- **A flight is an airborne stretch, not a scheduled flight.** Training circuits, helicopters, gliders and airborne holds count
  when they reach 10 airborne points, 5 minutes and 10 km. A touch-and-go without a new-leg flag is one flight. A flight that
  crosses midnight UTC is cut in two by the daily files: the first part has no destination, the second no origin.
- **Airports are named by distance only.** The nearest large, medium or small airport within 8 km of the first or last
  airborne point at or below 3,000 ft. Heliports, closed airports and private strips are not in the list; a flight that starts
  where the receiver does not hear it low enough has an unknown origin. There are no runways and no approach paths.
- **The bounding box is a rectangle that filters points.** It does not wrap the antimeridian, it is applied after parsing (so it
  does not make reading faster), and a flight that leaves the box is cut where it leaves.
- **Altitudes are barometric** (what the trace has in field 3), not geometric, and the ground speed is what the aircraft
  reports; a point without a speed is left out of the speed histogram and of the mean speed.
- **Reading is Python speed.** About 215,000 reports a second from a directory (the benchmark above), single-threaded, with the
  gzip and JSON decoding of each file. A day of adsb.lol traces has hundreds of millions of reports; extrapolating the benchmark
  gives hours, not minutes (an extrapolation, not a measurement). Use `--limit` and `--bbox` to try it.
- **The benchmark timings are for synthetic files** with about 800 reports per aircraft; the real part averages 1,374 per aircraft
  and the throughput was 24% lower than the benchmark's combined figure.
- **The two implementations share their reading and their parameters.** They are compared on the same parsed points, so a bug
  in the reader is not caught by `verify`; the reader has its own tests.
