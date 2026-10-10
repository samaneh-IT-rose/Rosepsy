"""Geo helpers for B40 (pure functions, deterministic tests).

- haversine_km: great-circle distance between two coordinates.
- is_open_now: evaluates a branch working_hours JSON of the shape
  {"0": [["09:00","17:00"]], ...} keyed by ISO weekday; None input means
  "unknown hours" (not closed).
"""

from datetime import time
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def _parse_hhmm(value: str) -> time | None:
    try:
        parts = value.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError, AttributeError):
        return None


def is_open_now(
    working_hours: dict | None, weekday_iso: int, local_time: time
) -> bool | None:
    """bool per defined hours; None when the branch has no hours data."""
    if not working_hours:
        return None
    windows = working_hours.get(str(weekday_iso))
    if not windows:
        return False
    for window in windows:
        if not isinstance(window, (list, tuple)) or len(window) != 2:
            continue
        start = _parse_hhmm(str(window[0]))
        end = _parse_hhmm(str(window[1]))
        if start and end and start <= local_time < end:
            return True
    return False
