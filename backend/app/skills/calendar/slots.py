"""Finding a Slot: a free window in the Rep's working hours long enough for a Meeting."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.skills.calendar.model import Interval, WorkingHours

LEAD_TIME = timedelta(minutes=15)
STEP = timedelta(minutes=15)
HORIZON_WORKING_DAYS = 5


def _round_up(moment: datetime, step: timedelta) -> datetime:
    floor = moment.replace(minute=0, second=0, microsecond=0)
    while floor < moment:
        floor += step
    return floor


def find_slots(
    busy: list[Interval],
    hours: WorkingHours,
    duration: timedelta,
    now: datetime,
    search_start: date | None = None,
    search_end: date | None = None,
    limit: int = 3,
) -> list[Interval]:
    """Earliest non-overlapping Slots, never in the past and never within LEAD_TIME of now.

    Without an explicit search_end, looks across the next HORIZON_WORKING_DAYS working days.
    """
    tz = ZoneInfo(hours.timezone)
    now = now.astimezone(tz)
    earliest = _round_up(now + LEAD_TIME, STEP)
    day = search_start or now.date()
    working_days_seen = 0
    slots: list[Interval] = []

    while len(slots) < limit:
        if search_end is not None and day > search_end:
            break
        if search_end is None and working_days_seen >= HORIZON_WORKING_DAYS:
            break
        if day.weekday() in hours.days:
            working_days_seen += 1
            day_start = datetime.combine(day, hours.start, tz)
            day_end = datetime.combine(day, hours.end, tz)
            candidate = _round_up(max(day_start, earliest), STEP)
            while candidate + duration <= day_end and len(slots) < limit:
                proposal = Interval(candidate, candidate + duration)
                blocker = next((b for b in busy if b.overlaps(proposal)), None)
                if blocker is None:
                    slots.append(proposal)
                    candidate = proposal.end
                else:
                    candidate = _round_up(blocker.end.astimezone(tz), STEP)
        day += timedelta(days=1)

    return slots
