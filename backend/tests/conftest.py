from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.activity_log import ActivityLog
from app.core.confirmation import ConfirmationGate
from app.skills.calendar.fake import FakeCalendar
from app.skills.calendar.model import Contact
from app.skills.calendar.skill import CalendarSkill

TZ = ZoneInfo("Asia/Kolkata")
MONDAY_0830 = datetime(2026, 10, 26, 8, 30, tzinfo=TZ)  # d0 = Mon 26 Oct, d1 = Tue 27 Oct ...
REP = Contact("Vaishnavi Soni", "vaishnavi@contoso.example", "colleague", "Contoso")


class Clock:
    def __init__(self, now: datetime = MONDAY_0830):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def calendar():
    return FakeCalendar(REP, "Asia/Kolkata", now=MONDAY_0830)


@pytest.fixture
def log():
    return ActivityLog()


@pytest.fixture
def gate(log, clock):
    return ConfirmationGate(log, clock)


@pytest.fixture
def skill(calendar, gate, log, clock):
    return CalendarSkill(calendar, gate, log, clock)
