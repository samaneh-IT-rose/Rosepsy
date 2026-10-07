from datetime import date, datetime, timedelta, timezone

from app.services.slots import generate_slots

TZ = "Asia/Tehran"
FAKE_NOW = datetime(2025, 6, 10, 12, 0, tzinfo=timezone.utc)  # a Tuesday


def test_two_fitting_slots_in_90min_window():
    slots = generate_slots(
        rules=[(0, __import__("datetime").time(9, 0), __import__("datetime").time(10, 30))],
        exceptions=[],
        duration_minutes=45,
        tz_name=TZ,
        now=FAKE_NOW,
        from_date=date(2025, 6, 16),  # next Monday
        to_date=date(2025, 6, 16),
    )
    starts = [s["start"] for s in slots["2025-06-16"]]
    # 09:00 and 09:45 local == 05:30 and 06:15 UTC
    assert starts == ["2025-06-16T05:30:00+00:00", "2025-06-16T06:15:00+00:00"]


def test_slot_must_fit_entirely():
    slots = generate_slots(
        rules=[(0, __import__("datetime").time(9, 0), __import__("datetime").time(10, 0))],
        exceptions=[],
        duration_minutes=45,
        tz_name=TZ,
        now=FAKE_NOW,
        from_date=date(2025, 6, 16),
        to_date=date(2025, 6, 16),
    )
    # 09:00 fits; 09:45 would end 10:30 > window end -> excluded
    assert len(slots["2025-06-16"]) == 1


def test_exception_splits_window():
    slots = generate_slots(
        rules=[(0, __import__("datetime").time(9, 0), __import__("datetime").time(12, 0))],
        exceptions=[
            (
                datetime(2025, 6, 16, 6, 30, tzinfo=timezone.utc),   # 10:00 local
                datetime(2025, 6, 16, 7, 30, tzinfo=timezone.utc),   # 11:00 local
            )
        ],
        duration_minutes=60,
        tz_name=TZ,
        now=FAKE_NOW,
        from_date=date(2025, 6, 16),
        to_date=date(2025, 6, 16),
    )
    starts = [s["start"] for s in slots["2025-06-16"]]
    # free: 09-10 and 11-12 -> slots at 09:00 and 11:00 local
    assert starts == ["2025-06-16T05:30:00+00:00", "2025-06-16T07:30:00+00:00"]


def test_past_slots_dropped():
    # fake now = Monday 09:30 local -> 06:00 UTC
    now = datetime(2025, 6, 16, 6, 0, tzinfo=timezone.utc)
    slots = generate_slots(
        rules=[(0, __import__("datetime").time(9, 0), __import__("datetime").time(10, 30))],
        exceptions=[],
        duration_minutes=45,
        tz_name=TZ,
        now=now,
        from_date=date(2025, 6, 16),
        to_date=date(2025, 6, 16),
    )
    starts = [s["start"] for s in slots["2025-06-16"]]
    assert starts == ["2025-06-16T06:15:00+00:00"]  # 09:00 local is past -> dropped


def test_full_day_leave_empties_date():
    slots = generate_slots(
        rules=[(0, __import__("datetime").time(9, 0), __import__("datetime").time(17, 0))],
        exceptions=[
            (
                datetime(2025, 6, 15, 20, 30, tzinfo=timezone.utc),  # Mon 00:00 local
                datetime(2025, 6, 16, 20, 30, tzinfo=timezone.utc),  # Tue 00:00 local
            )
        ],
        duration_minutes=60,
        tz_name=TZ,
        now=FAKE_NOW,
        from_date=date(2025, 6, 16),
        to_date=date(2025, 6, 16),
    )
    assert "2025-06-16" not in slots


def test_wrong_weekday_produces_nothing():
    slots = generate_slots(
        rules=[(2, __import__("datetime").time(9, 0), __import__("datetime").time(10, 0))],
        exceptions=[],
        duration_minutes=30,
        tz_name=TZ,
        now=FAKE_NOW,
        from_date=date(2025, 6, 16),  # Monday; rule is Wednesday
        to_date=date(2025, 6, 16),
    )
    assert slots == {}
