# Benchmark

Run on Linux x86_64, 12 CPUs, Python 3.14.10; seed 1; each time is the median of 5 runs (at most 2 for the literal implementation); command `bench --sizes 100,300,1000,2000 --ref-aircraft 100 --repeat 5 --draws 25 --seeds 20 --out /out`.

## 1. Analysing traces: NumPy against the literal implementation

| Aircraft | Position reports | Flights | NumPy | Reports per second |
|---|---|---|---|---|
| 100 | 80,430 | 232 | 83.0 ms | 969,484 |
| 300 | 223,836 | 661 | 224.1 ms | 998,834 |
| 1,000 | 736,162 | 2,175 | 1.09 s | 676,514 |
| 2,000 | 1,437,011 | 4,260 | 2.02 s | 710,914 |

The literal implementation took 296.8 ms on 100 aircraft (80,430 reports), the NumPy one 106.5 ms: 2.8x.

## 2. Reading

| Step | Files | Time | Reports per second |
|---|---|---|---|
| Write gzip trace files | 104 | 371.1 ms | 216,710 |
| Read them from a directory | 104 | 373.1 ms | 215,559 |
| Read them from a tar archive | 104 | 463.4 ms | 173,569 |

## 3. Accuracy against the truth

20 generated days of 200 aircraft (seeds 1 to 20): 8,692 of 8,692 true flights found, 0 extra; origin correct for 8,692, destination for 8,692; distance error median 0.0000%, 95th percentile 0.0000%, largest 0.01%; glitches 280 injected, 280 removed.

| Fault | Injected | Handled | Missed |
|---|---|---|---|
| Position thrown far away | 280 | 280 | 0 |
| Trace starts in mid-air | 120 | 120 | 0 |
| Trace ends in mid-air | 120 | 120 | 0 |
| Hole in the coverage | 160 | 160 | 0 |
| Repeated timestamps | 120 | 120 | 0 |
| Only on the ground (not a flight) | 80 | 80 | 0 |
| Brief hop (not a flight) | 80 | 80 | 0 |

## 4. Agreement

26 comparisons (generated and spoiled traffic, random parameters): 31,259 values compared, largest relative difference 1.5e-15 (tolerance 1e-09). All agree.
