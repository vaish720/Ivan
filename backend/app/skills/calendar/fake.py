"""An in-memory calendar that behaves like Outlook, seeded with a sample week.

The week is always built relative to "today", so requests like "tomorrow" keep working.
It deliberately contains the hard cases: two Meetings at 3 pm on the same day, two
Colleagues called Raj, a weekly Series, Blocks, and Meetings the Rep attends but does
not organise.
"""

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from itertools import count
from zoneinfo import ZoneInfo

from app.skills.calendar.model import CalendarEvent, Contact, Interval, NewMeeting, WorkingHours

RAJ_MEHTA = Contact("Raj Mehta", "raj.mehta@contoso.example", "colleague", "Contoso")
RAJ_KUMAR = Contact("Raj Kumar", "raj.kumar@contoso.example", "colleague", "Contoso")
PRIYA = Contact("Priya Shah", "priya.shah@contoso.example", "colleague", "Contoso")
ANANYA = Contact("Ananya Rao", "ananya.rao@contoso.example", "colleague", "Contoso")
SAM = Contact("Sam Carter", "sam.carter@acme.example", "client", "Acme")
LENA = Contact("Lena Ortiz", "lena.ortiz@globex.example", "client", "Globex")
TOM = Contact("Tom Becker", "tom.becker@initech.example", "client", "Initech")

DIRECTORY = [RAJ_MEHTA, RAJ_KUMAR, PRIYA, ANANYA, SAM, LENA, TOM]


def working_days_from(today: date, n: int) -> list[date]:
    days, d = [], today
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


class FakeCalendar:
    def __init__(self, rep: Contact, timezone: str = "Asia/Kolkata", now: datetime | None = None):
        self._rep = rep
        self._tz = ZoneInfo(timezone)
        self._hours = WorkingHours(frozenset(range(5)), time(9), time(18), timezone)
        self._ids = count(1)
        self.sent: list[tuple[str, str, str]] = []  # (kind, title, note): what attendees were sent
        today = (now or datetime.now(self._tz)).astimezone(self._tz).date()
        self._events: dict[str, CalendarEvent] = {}
        self._extra_busy: dict[str, list[Interval]] = {}
        self._seed(working_days_from(today, 7))

    # --- seed --------------------------------------------------------------------------

    def _at(self, d: date, hh: int, mm: int = 0) -> datetime:
        return datetime.combine(d, time(hh, mm), self._tz)

    def _add(self, d, start, end, title, organiser=None, attendees=(), teams=True, series=""):
        organiser = organiser or self._rep
        event = CalendarEvent(
            id=f"evt-{next(self._ids)}",
            title=title,
            start=self._at(d, *start),
            end=self._at(d, *end),
            organiser=organiser,
            attendees=list(attendees),
            is_organiser=organiser == self._rep,
            is_teams=teams and bool(attendees),
            join_url="https://teams.microsoft.com/l/meetup-join/fake" if teams and attendees else "",
            series_id=series,
        )
        self._events[event.id] = event

    def _seed(self, d: list[date]) -> None:
        first = self._rep.name.split()[0]
        self._add(d[0], (10, 0), (10, 30), "Weekly pipeline sync", attendees=[PRIYA, ANANYA], series="series-pipeline")
        self._add(d[0], (16, 0), (16, 30), "Acme onboarding check-in", attendees=[SAM])
        self._add(d[1], (9, 0), (11, 0), "Focus time", teams=False)
        self._add(d[1], (15, 0), (15, 30), "Acme pricing call", attendees=[SAM])
        self._add(d[1], (15, 0), (16, 0), "Q4 forecast review", organiser=PRIYA, attendees=[PRIYA, RAJ_MEHTA])
        self._add(d[2], (11, 0), (11, 45), "Globex discovery", attendees=[LENA])
        self._add(d[2], (14, 0), (14, 30), f"1:1 Raj / {first}", organiser=RAJ_MEHTA, attendees=[RAJ_MEHTA])
        self._add(d[3], (10, 0), (10, 30), "Raj Kumar sync", attendees=[RAJ_KUMAR])
        self._add(d[3], (13, 0), (18, 0), "Out of office", teams=False)
        self._add(d[4], (16, 0), (17, 0), "Team retro", organiser=PRIYA, attendees=[PRIYA, ANANYA, RAJ_KUMAR])
        self._add(d[5], (10, 0), (10, 30), "Weekly pipeline sync", attendees=[PRIYA, ANANYA], series="series-pipeline")
        self._add(d[6], (12, 0), (12, 30), "Initech follow-up", attendees=[TOM])
        self._extra_busy = {
            RAJ_MEHTA.email: [Interval(self._at(d[1], 13), self._at(d[1], 15))],
            PRIYA.email: [Interval(self._at(d[2], 9), self._at(d[2], 12))],
        }

    # --- CalendarPort ------------------------------------------------------------------

    def rep(self) -> Contact:
        return self._rep

    def working_hours(self) -> WorkingHours:
        return self._hours

    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        window = Interval(start, end)
        return sorted((e for e in self._events.values() if e.interval.overlaps(window)), key=lambda e: e.start)

    def get_event(self, event_id: str) -> CalendarEvent | None:
        return self._events.get(event_id)

    def busy_times(self, emails: list[str], start: datetime, end: datetime) -> dict[str, list[Interval]]:
        window = Interval(start, end)
        result: dict[str, list[Interval]] = {}
        for email in emails:
            contact = next((c for c in DIRECTORY if c.email == email), None)
            if contact is None or contact.kind == "client":
                result[email] = []
                continue
            busy = [e.interval for e in self._events.values() if contact in e.attendees or e.organiser == contact]
            busy += self._extra_busy.get(email, [])
            result[email] = sorted((b for b in busy if b.overlaps(window)), key=lambda b: b.start)
        return result

    def search_contacts(self, query: str) -> list[Contact]:
        q = query.strip().lower()
        return [c for c in DIRECTORY if q in c.name.lower() or q in c.email.lower() or q == c.company.lower()]

    def create_meeting(self, meeting: NewMeeting) -> CalendarEvent:
        event = CalendarEvent(
            id=f"evt-{next(self._ids)}",
            title=meeting.title,
            start=meeting.start,
            end=meeting.end,
            organiser=self._rep,
            attendees=list(meeting.attendees),
            is_organiser=True,
            is_teams=meeting.is_teams,
            join_url="https://teams.microsoft.com/l/meetup-join/fake" if meeting.is_teams else "",
        )
        self._events[event.id] = event
        self.sent.append(("invite", event.title, ""))
        return event

    def reschedule(self, event_id: str, start: datetime, end: datetime, note: str = "") -> CalendarEvent:
        event = self._require(event_id)
        updated = replace(event, start=start, end=end)
        self._events[event_id] = updated
        self.sent.append(("update", event.title, note))
        return updated

    def cancel(self, event_id: str, note: str = "") -> None:
        event = self._require(event_id)
        del self._events[event_id]
        self.sent.append(("cancellation", event.title, note))

    def decline(self, event_id: str, note: str = "") -> None:
        event = self._require(event_id)
        del self._events[event_id]
        self.sent.append(("decline", event.title, note))

    def _require(self, event_id: str) -> CalendarEvent:
        event = self._events.get(event_id)
        if event is None:
            raise KeyError(f"No event {event_id}")
        return event
