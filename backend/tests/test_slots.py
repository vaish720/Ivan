from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.skills.calendar.model import Interval, WorkingHours
from app.skills.calendar.slots import find_slots

TZ = ZoneInfo("Asia/Kolkata")
HOURS = WorkingHours(days=frozenset(range(5)), start=time(9), end=time(18), timezone="Asia/Kolkata")
HALF_HOUR = timedelta(minutes=30)


def at(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)


MONDAY = date(2026, 10, 26)
FRIDAY = date(2026, 10, 30)


def test_first_slot_is_start_of_working_day():
    slots = find_slots([], HOURS, HALF_HOUR, now=at(MONDAY, 8))
    assert slots[0] == Interval(at(MONDAY, 9), at(MONDAY, 9, 30))


def test_never_starts_within_15_minutes_and_aligns_to_quarter_hour():
    slots = find_slots([], HOURS, HALF_HOUR, now=at(MONDAY, 10, 50))
    assert slots[0].start == at(MONDAY, 11, 15)


def test_skips_busy_time():
    busy = [Interval(at(MONDAY, 9), at(MONDAY, 10))]
    slots = find_slots(busy, HOURS, HALF_HOUR, now=at(MONDAY, 8))
    assert slots[0].start == at(MONDAY, 10)


def test_skips_weekend_after_friday_close():
    slots = find_slots([], HOURS, HALF_HOUR, now=at(FRIDAY, 17, 45))
    assert slots[0].start == at(date(2026, 11, 2), 9)


def test_returns_distinct_non_overlapping_options_earliest_first():
    slots = find_slots([], HOURS, HALF_HOUR, now=at(MONDAY, 8), limit=3)
    assert [s.start for s in slots] == [at(MONDAY, 9), at(MONDAY, 9, 30), at(MONDAY, 10)]


def test_honours_requested_search_window():
    slots = find_slots(
        [], HOURS, HALF_HOUR, now=at(MONDAY, 8), search_start=date(2026, 10, 28), search_end=date(2026, 10, 28)
    )
    assert slots[0].start == at(date(2026, 10, 28), 9)
    assert all(s.start.date() == date(2026, 10, 28) for s in slots)


def test_gives_up_after_five_working_days_when_fully_booked():
    busy = [Interval(at(MONDAY, 0), at(date(2026, 11, 3), 0))]
    assert find_slots(busy, HOURS, HALF_HOUR, now=at(MONDAY, 8)) == []


def test_meeting_must_fit_before_end_of_day():
    busy = [Interval(at(MONDAY, 9), at(MONDAY, 17, 30))]
    slots = find_slots(busy, HOURS, timedelta(minutes=45), now=at(MONDAY, 8))
    assert slots[0].start == at(date(2026, 10, 27), 9)
