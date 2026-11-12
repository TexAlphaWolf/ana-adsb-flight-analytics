# Flight analysis

Source: demo day (synthetic, 150 aircraft, seed 1). adsbstat 1.1.0.

## Totals

| What | Value |
|---|---|
| Aircraft | 156 |
| Position reports | 115,347 |
| Glitches removed | 11 |
| Legs (stretches of one trace) | 337 |
| Flights | 331 |
| Distance flown | 189,615 km |
| Time in the air | 349.0 h |
| Origin unknown | 4 |
| Destination unknown | 4 |
| Already in the air when the day began (origin unknown, first 10 minutes) | 0 |
| Still in the air when the day ended (destination unknown, last 10 minutes) | 0 |
| Round trips (same airport at both ends) | 0 |

## Flights

| | 10th percentile | Median | 90th percentile | Longest |
|---|---|---|---|---|
| Distance (km) | 304 | 522 | 913 | 1,077 |
| Duration (min) | 35 | 57 | 85 | 314 |

Mean ground speed 298 kt (per flight, weighted by time). Busiest hour for take-offs: 19:00 UTC (28 flights). Share of airborne time above 24,000 ft: 36.1%.

## Take-offs by hour (UTC)

| Hour | 00 | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Flights | 5 | 3 | 5 | 4 | 5 | 8 | 10 | 14 | 20 | 11 | 15 | 21 | 14 | 22 | 17 | 23 | 19 | 21 | 17 | 28 | 18 | 21 | 10 | 0 |

## Busiest airports

| Airport | Name | Departures | Arrivals | Movements |
|---|---|---|---|---|
| TA07 | Test Airport 07 | 33 | 34 | 67 |
| TA12 | Test Airport 12 | 33 | 32 | 65 |
| TA03 | Test Airport 03 | 31 | 30 | 61 |
| TA04 | Test Airport 04 | 28 | 31 | 59 |
| TA08 | Test Airport 08 | 29 | 30 | 59 |
| TA05 | Test Airport 05 | 27 | 30 | 57 |
| TA01 | Test Airport 01 | 27 | 29 | 56 |
| TA11 | Test Airport 11 | 25 | 29 | 54 |
| TA06 | Test Airport 06 | 27 | 25 | 52 |
| TA09 | Test Airport 09 | 24 | 22 | 46 |

## Busiest routes

| Route | Flights |
|---|---|
| TA12 to TA07 | 8 |
| TA12 to TA04 | 7 |
| TA07 to TA03 | 6 |
| TA03 to TA05 | 5 |
| TA04 to TA12 | 5 |
| TA05 to TA11 | 5 |
| TA06 to TA03 | 5 |
| TA06 to TA07 | 5 |
| TA07 to TA01 | 5 |
| TA07 to TA12 | 5 |

## Aircraft types

| Type | Flights |
|---|---|
| B738 | 103 |
| A320 | 81 |
| E190 | 75 |
| AT76 | 38 |
| C172 | 17 |
| PC12 | 12 |
| SR22 | 5 |

## Against the truth

331 of 331 true flights found (recall 100.00%), 0 extra (precision 100.00%), of which 0 come from aircraft that never flew. Origin named correctly for 331 of 331, destination for 331. Distance: total error 0.000%, median error 0.0000%, largest 0.01%. Take-off time error: median 0.0 s, largest 0.0 s. Glitches: 11 injected, 11 removed.

| Fault | Injected | Handled |
|---|---|---|
| Position thrown far away | 11 | 11 |
| Trace starts in mid-air | 4 | 4 |
| Trace ends in mid-air | 4 | 4 |
| Hole in the coverage | 6 | 6 |
| Repeated timestamps | 4 | 4 |
| Only on the ground (not a flight) | 3 | 3 |
| Brief hop (not a flight) | 3 | 3 |
