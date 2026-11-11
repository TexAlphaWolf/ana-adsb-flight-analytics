# Analysis

Source: [`report.json`](report.json) (the demo day: 150 aircraft generated with seed 1, plus 6 decoys that never fly) and
[`bench.json`](bench.json) (one run in Docker on Linux x86_64 with 12 CPUs, Python 3.14.10; medians of 5 runs, 2 for the literal
implementation; 20 generated days of 200 aircraft for the accuracy). **The traffic is synthetic**: it comes from a simulator built
to be plausible, and the faults are the ones that simulator injects. Read the structure of the results, not the airports (they
are invented: `TA01` to `TA12`) and not the numbers of flights per hour.

## 1. The demo day

156 aircraft sent 115,347 position reports: 331 flights, 189,615 km flown in 349.0 hours, a median flight of 522 km and 57
minutes (10th to 90th percentile: 304 to 913 km and 35 to 85 minutes). The mean ground speed over a flight is 298 kt.

- **Hours.** Take-offs follow the daily curve the generator uses: 3 to 5 an hour at night (00:00 to 04:59 UTC: 22 in all), a rise from 06:00, 10 to 28 an hour between 08:00 and 22:00 and the busiest hour at 19:00 UTC with 28. Nothing takes off in the 23:00 hour because the simulator does not start a leg that cannot end before midnight.
- **Altitudes.** The airborne time has two bumps. 16.3% is in the 4,000 to 6,000 ft bin (the light aircraft cruise at 5,500 ft, and everything passes through it climbing and descending) and 16.8% is between 34,000 and 36,000 ft, where the jets cruise; a further
  7.0% is between 36,000 and 38,000 ft. In all 36.1% of the airborne time is above 24,000 ft.
- **Speeds.** The largest share of airborne time, 25.4%, is between 400 and 450 kt (the cruise of the A320, B738 and E190);
  the rest, from 50 to 400 kt, is turboprops, light aircraft, and climbs and descents.
- **Faults.** The analysis removes 11 glitches and finds 4 flights that start in mid-air and 4 that end in mid-air; those have no
  origin, or no destination, and are the 4 and 4 of the totals.
- **Airports and routes.** 12 airports share the traffic fairly evenly (the busiest, TA07, has 67 movements and the 10th, TA09,
  has 46) because the simulator picks destinations at random within reach of the aircraft type; the busiest route has 8 flights.
  Real traffic is concentrated: a few airports and routes carry most of it. B738 (103 flights), A320 (81) and E190 (75) are the
  most frequent types.

## 2. Accuracy against the truth, over 20 generated days

20 days (seeds 1 to 20) of 200 aircraft, each with the default mix of faults: 8,692 true flights, 8,692 found, 0 extra, and the
origin and destination named correctly for all 8,692. The distance of a flight differs from the true one by less than
1e-9 (relative) for 95% of the flights, and by 0.013% at the most (where a glitch was removed or a hole in the coverage leaves a straight line over a few minutes of track). 280 glitches were injected and 280 removed.

| Fault | Injected | Handled | Missed |
|---|---|---|---|
| Position thrown far away | 280 | 280 | 0 |
| Trace starts in mid-air | 120 | 120 | 0 |
| Trace ends in mid-air | 120 | 120 | 0 |
| Hole in the coverage | 160 | 160 | 0 |
| Repeated timestamps | 120 | 120 | 0 |
| Only on the ground (not a flight) | 80 | 80 | 0 |
| Brief hop (not a flight) | 80 | 80 | 0 |

*Handled* means different things for different faults: for a glitch, a hole, a repeated time or a trace that starts or ends in
mid-air, the flight is found with the right origin and destination (unknown where the truth says unknown); for a decoy (an
aircraft that only taxis, a brief hop) it means that no flight is reported for it.

Every number here is a ceiling. The faults are injected by the code that defines what the analysis does, and
the generator is built so that every one of them is within what the definition handles: isolated glitches (a run of wild points is
not a glitch by definition, it splits the leg), holes shorter than the 30-minute gap, no hole that swallows the landing. A hole that swallows the landing is the same fault as a trace that ends in mid-air, which is injected separately, so the generator keeps its holes to the middle of the flight.

## 3. Two implementations, one answer

`adsbstat verify` (26 comparisons in the benchmark, 25 random cases and the default one) compares the NumPy implementation with the
literal one on generated traffic and on traffic spoiled on purpose: shuffled order, repeated times, missing altitudes and
speeds, random flags, flipped on-ground states, runs of 1 to 3 wild positions and random parameters, with some airports duplicated on the same spot to test the tie-break. 31,259 values were compared
(every number and string in the results, the flights and the two histograms) and the largest relative difference is 1.5e-15, rounding
in the last digit of a floating-point sum. A mismatch would make the command exit with 1; the tests show the comparison can fail.

## 4. Speed

| Aircraft | Position reports | Flights | NumPy | Reports per second |
|---|---|---|---|---|
| 100 | 80,430 | 232 | 83.0 ms | 969,484 |
| 300 | 223,836 | 661 | 224.1 ms | 998,834 |
| 1,000 | 736,162 | 2,175 | 1.09 s | 676,514 |
| 2,000 | 1,437,011 | 4,260 | 2.02 s | 710,914 |

Time grows linearly with the number of reports: 24 times more time for 18 times the reports, the measured exponent is 1.1. The rate is between 0.68 and 1.0 million reports a second. The literal implementation took 296.8 ms on the 100-aircraft day and the
NumPy one 106.5 ms in the same run: 2.8 times. In section 1 of the benchmark the NumPy time for the same 100 aircraft is 83.0 ms:
the two timings of the same work differ by 28%, which is the noise of one run on a desktop, so ratios here are good to about 30%.

The speed-up is small, and the likely reason (not measured separately) is that the work is a loop over aircraft with about 800 points each: NumPy calls on arrays of that size cost about as much as the Python loop they replace, and both implementations build a list of points per aircraft. A larger gap would need the points of all aircraft in one array, which is possible and would change the
structure of the code; it was not needed to analyse a million reports a second.

## 5. Reading

| Step | Files | Time | Reports per second |
|---|---|---|---|
| Write gzip trace files | 104 | 371.1 ms | 216,710 |
| Read them from a directory | 104 | 373.1 ms | 215,559 |
| Read them from a tar archive | 104 | 463.4 ms | 173,569 |

Reading and analysing the same 100 aircraft takes 373.1 ms and 83.0 ms: reading is 4.5 times slower than the analysis. The tar stream is a quarter slower than the directory (463.4 against 373.1 ms). At these speeds a day
of real traces is a job of hours, and the place to spend effort would be reading (a faster JSON parser, several processes), not
the analysis.

## What this does not say

Nothing here is about real traffic. The synthetic data shows that the reader, the definition of a flight and the score
agree, that the code is fast enough for a million reports a second and that the two implementations agree; the results of a real
day (how many flights, which airports, how many glitches of which kind) are the next thing to measure. See
[`limitations.md`](limitations.md).
