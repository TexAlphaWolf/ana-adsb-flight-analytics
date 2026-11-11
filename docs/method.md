# Method

## The input

A trace file is one JSON document per aircraft per day, as readsb writes it (usually gzip-compressed, whatever the extension):

| Field | Meaning |
|---|---|
| `icao` | Aircraft address in hex; trimmed and lower-cased |
| `timestamp` | Unix time (seconds) the `trace` offsets are counted from |
| `t` | Aircraft type code (optional) |
| `trace` | List of points |

Each point is a list: `[0]` seconds after `timestamp`, `[1]` latitude, `[2]` longitude, `[3]` barometric altitude in feet, the string
`"ground"` or `null`, `[4]` ground speed in knots (may be `null`), `[5]` track, `[6]` flags (an integer), and more fields that are not
used. Bit 2 of the flags (value 2) marks the first point of a new leg. A point with fewer than 7 items, a non-numeric or
non-finite time, latitude or longitude, a latitude outside -90 to 90, a longitude outside -180 to 180, an altitude that is
neither a number, `"ground"` nor `null`, or flags that are not an integer, is **unusable**: it is counted and dropped.
`--bbox lat0,lon0,lat1,lon1` also drops points outside the rectangle (it does not wrap the antimeridian).

File names must start with `trace_` and end with `.json` or `.json.gz`. A directory is searched recursively; a tar archive is
read as a stream, so a part of an archive that ends early is read as far as it goes (and reported as truncated). Airports come
from an OurAirports `airports.csv` with the columns `ident`, `type`, `name`, `latitude_deg`, `longitude_deg`; rows of type
`large_airport`, `medium_airport` and `small_airport` with a valid position are kept, the first of two equal idents wins, and the
list is sorted by ident.

## The definition of a flight

Both implementations follow these five steps, one aircraft at a time.

1. **Order.** The points are sorted by time and a point with the same time as the one before it is dropped (the first is kept).
2. **Glitches.** The move between two consecutive points is a *jump* when it is longer than `jump_km` and implies a ground speed
   above `max_kt` (the distance is the great-circle one, on a sphere of radius 6,371.0088 km). A point is a *glitch* when the
   move into it and the move out of it are both jumps. All glitches are removed together, and counted.
3. **Legs.** A leg starts at the first point and again at every point where bit 2 of the flags is set, where more than `gap_s`
   seconds have passed since the previous point, or where the move from the previous point is a jump. (Two or more wild points
   in a row are not glitches by step 2: the leg is split before and after them, and the wild stretch is a leg of its own that is
   normally too short to be a flight.)
4. **Flights.** The *airborne* points of a leg are those that are not `"ground"` and have a known altitude. A leg is a flight when
   it has at least `min_air_points` airborne points, the time from the first to the last is at least `min_air_s`, and the great-circle
   distances summed between consecutive airborne points are at least `min_air_km`.
5. **The flight.** It takes off at its first airborne point and lands at its last. The *origin* is the nearest airport within
   `airport_km` of the first airborne point, if the altitude there is at most `low_ft`; the *destination* is the same for the last
   point. Of two equally near airports the first by ident is named. Otherwise the airport is unknown.

For each flight: duration, distance, highest altitude, highest ground speed, and the mean ground speed weighted by time.

## The time weights and the histograms

Each point is weighted by the time to the next point of its leg, at most `weight_cap_s` (the last point of a leg weighs 0). The
altitude histogram adds the weights of the airborne points of flights into bins of `alt_bin_ft` (25 bins, the last one open); the
speed histogram does the same for points with a known ground speed in bins of `speed_bin_kt` (17 bins, the last one open).
The share of airborne time above 24,000 ft is the weight in the bins from 24,000 ft up, over the total.

## The parameters

| Parameter | Option | Default | Meaning |
|---|---|---|---|
| `max_kt` | `--max-kt` | 1200 | Ground speed (kt) above which a move is a jump |
| `jump_km` | `--jump-km` | 2.0 | Shortest move (km) that can be a jump |
| `gap_s` | `--gap-s` | 1800 | Silence (s) that ends a leg |
| `min_air_points` | `--min-air-points` | 10 | Fewest airborne points in a flight |
| `min_air_s` | `--min-air-s` | 300 | Shortest flight (s) |
| `min_air_km` | `--min-air-km` | 10 | Shortest flight (km of ground covered) |
| `airport_km` | `--airport-km` | 8.0 | Farthest an airport can be (km) to be named |
| `low_ft` | `--low-ft` | 3000 | Highest altitude (ft) at which an end of a flight is named after an airport |
| `weight_cap_s` | `--weight-cap-s` | 60 | Most seconds one report counts for |
| `alt_bin_ft` | `--alt-bin-ft` | 2000 | Width of an altitude bin (ft) |
| `speed_bin_kt` | `--speed-bin-kt` | 50 | Width of a ground speed bin (kt) |

## The report

Hours are the UTC hour of the take-off. The busiest airports count departures and arrivals of flights whose airport is named;
routes need both ends named. Types are the `t` codes of the files (`unknown` when absent). Distance and duration are given as
the 10th percentile, median, 90th percentile and longest. The Markdown is a pure function of `report.json`.

## The synthetic day

`generate` places 12 invented airports (`TA01` to `TA12`, at least 90 km apart, in a box of the size of Italy) and a fleet of
aircraft of 7 types (A320, B738, E190, AT76, PC12, SR22, C172, with their own cruise speed, cruise altitude and leg lengths).
Each aircraft makes 1 to 4 legs (1 to 3 for light aircraft): taxi, take-off, climb, cruise along the great circle, descent,
landing, taxi, with irregular sampling (4 to 45 s) and noise in the positions, and the traffic follows a daily curve over UTC hours.
Seven kinds of fault are then injected, at rates per aircraft that make 7 glitches, 3 + 3 traces that start or end in mid-air, 4
holes, 3 repeated-timestamp runs and 2 + 2 decoys per 100 aircraft:

| Fault | What is done | What the truth says |
|---|---|---|
| `glitch` | One airborne point moved 300 to 2,000 km away | The flight is unchanged; 1 glitch |
| `no_start` | The trace begins in mid-air (above 4,000 ft and 70% of the peak) | Take-off is the first remaining point; origin unknown |
| `no_end` | The trace ends in mid-air | Landing is the last remaining point; destination unknown |
| `coverage_gap` | 10 to 25 minutes of airborne points removed (at most 30% of the flight, not the end) | The flight is unchanged |
| `duplicate` | 4 points repeated with the same time and a position 0.01 degrees off | The flight is unchanged |
| `ground_only` | An aircraft that only taxis for 25 minutes | Not a flight |
| `brief` | A 3-minute hop of 12 points around an airport | Not a flight |

A found flight belongs to a true one when it is the same aircraft and the take-offs are within 120 s.
