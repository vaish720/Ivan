"""Calendar domain types. Terms follow GLOSSARY.md."""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Literal

ContactKind = Literal["colleague", "client"]


@dataclass(frozen=True)
class Contact:
    name: str
    email: str
    kind: ContactKind
    company: str = ""


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass
class CalendarEvent:
    """Anything on the Rep's calendar: a Meeting or a Block."""

    id: str
    title: str
    start: datetime
    end: datetime
    organiser: Contact
    attendees: list[Contact] = field(default_factory=list)
    is_organiser: bool = False
    is_teams: bool = False
    join_url: str = ""
    series_id: str = ""  # set when this is an Occurrence of a Series

    @property
    def is_meeting(self) -> bool:
        """A Meeting has at least one other attendee; otherwise it is a Block."""
        return len(self.attendees) > 0

    @property
    def is_occurrence(self) -> bool:
        return bool(self.series_id)

    @property
    def interval(self) -> Interval:
        return Interval(self.start, self.end)


@dataclass(frozen=True)
class WorkingHours:
    days: frozenset[int]  # 0 = Monday … 6 = Sunday
    start: time
    end: time
    timezone: str  # IANA name


@dataclass(frozen=True)
class NewMeeting:
    title: str
    start: datetime
    end: datetime
    attendees: list[Contact]
    is_teams: bool = True
