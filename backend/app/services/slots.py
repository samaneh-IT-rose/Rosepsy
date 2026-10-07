"""Pure slot generation (B08) - deterministic and unit-testable.

Weekly rules are local wall-clock windows per ISO weekday; they are
materialized to UTC with the configured clinic timezone. Blocking exceptions
(UTC windows) are subtracted first; then slots of the service duration are
laid from each free window start. Slots starting before `now` are dropped.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def _subtract(
    intervals: list[tuple[datetime, datetime]],
    blocks: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    result = intervals
    for b_start, b_end in blocks:
        nxt: list[tuple[datetime, datetime]] = []
        for s, e in result:
            if b_end <= s or b_start >= e:
                nxt.append((s, e))
                continue
            if b_start > s:
                nxt.append((s, b_start))
            if b_end < e:
                nxt.append((b_end, e))
        result = nxt
    return result


def generate_slots(
    *,
    rules: list[tuple[int, time, time]],
    exceptions: list[tuple[datetime, datetime]],
    duration_minutes: int,
    tz_name: str,
    now: datetime,
    from_date: date,
    to_date: date,
) -> dict[str, list[dict]]:
    """Returns {"YYYY-MM-DD": [{"start": iso, "end": iso}, ...]} sorted."""
    tz = ZoneInfo(tz_name)
    duration = timedelta(minutes=duration_minutes)
    out: dict[str, list[dict]] = {}

    day = from_date
    while day <= to_date:
        windows: list[tuple[datetime, datetime]] = []
        for weekday, r_start, r_end in rules:
            if weekday != day.weekday() or r_end <= r_start:
                continue
            start_utc = datetime.combine(day, r_start, tzinfo=tz).astimezone(UTC)
            end_utc = datetime.combine(day, r_end, tzinfo=tz).astimezone(UTC)
            windows.append((start_utc, end_utc))

        free = _subtract(windows, exceptions)
        slots: list[dict] = []
        for s, e in free:
            cursor = s
            while cursor + duration <= e:
                if cursor >= now:
                    slots.append(
                        {"start": cursor.isoformat(), "end": (cursor + duration).isoformat()}
                    )
                cursor += duration
        if slots:
            out[day.isoformat()] = slots
        day += timedelta(days=1)
    return out
