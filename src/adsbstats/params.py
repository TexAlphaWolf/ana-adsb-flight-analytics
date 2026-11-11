"""The thresholds that define a flight, in one place."""

from __future__ import annotations

from dataclasses import dataclass

ALT_BINS = 25  # 0-2,000 ft ... 48,000 ft and above
SPEED_BINS = 17  # 0-50 kt ... 800 kt and above
KM_PER_NM = 1.852


@dataclass(frozen=True)
class Params:
    max_kt: float = 1200.0  # a move faster than this between two points is a jump, not flight
    jump_km: float = 2.0  # ... and only if it covers at least this much ground
    gap_s: float = 1800.0  # a silence longer than this ends a leg
    min_air_points: int = 10  # a flight has at least this many airborne points ...
    min_air_s: float = 300.0  # ... lasts at least this long ...
    min_air_km: float = 10.0  # ... and covers at least this much ground
    airport_km: float = 8.0  # an airport within this distance of the first / last airborne point ...
    low_ft: float = 3000.0  # ... counts as origin / destination if the aircraft was below this altitude there
    weight_cap_s: float = 60.0  # a point stands for at most this many seconds in the time histograms
    alt_bin_ft: float = 2000.0
    speed_bin_kt: float = 50.0
