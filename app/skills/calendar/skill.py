"""The calendar skill: the tools the coordinator can call.

Reading tools answer straight away. Changing tools never touch the calendar: they
build a Proposed Action and hand it to the confirmation gate.
"""

import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.activity_log import ActivityLog
from app.core.confirmation import ConfirmationGate, ProposedAction
from app.skills.calendar.model import CalendarEvent, Contact, Interval, NewMeeting
from app.skills.calendar.port import CalendarPort
from app.skills.calendar.slots import LEAD_TIME, find_slots

DEFAULT_MINUTES = 30
_FILLER = {"from", "the", "and", "with", "guy", "lady", "person", "client", "colleague", "team", "someone"}


class ToolError(Exception):
    """A problem the coordinator should explain to the Rep or fix and retry."""


def _fmt_day(d: datetime) -> str:
    return d.strftime("%a %d %b")


def _fmt_range(start: datetime, end: datetime) -> str:
    return f"{_fmt_day(start)}, {start:%H:%M}–{end:%H:%M}"


def _who(c: Contact) -> str:
    if c.kind == "client":
        return f"{c.name} ({c.company or 'client'}, client)" if c.name != c.email else f"{c.email} (client)"
    return c.name


class CalendarSkill:
    def __init__(self, calendar: CalendarPort, gate: ConfirmationGate, log: ActivityLog, clock: Callable[[], datetime]):
        self._cal = calendar
        self._gate = gate
        self._log = log
        self._clock = clock
        self._refs: dict[str, str] = {}  # short ref (m1) -> event id, for this conversation
        self._proposed_this_turn = False

    # --- helpers -----------------------------------------------------------------------

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self._cal.working_hours().timezone)

    def now(self) -> datetime:
        return self._clock().astimezone(self.tz)

    def reset_conversation(self) -> None:
        self._refs.clear()

    def begin_turn(self) -> None:
        """Called once per Rep request: only one Proposed Action may be made per request."""
        self._proposed_this_turn = False

    def _ref_for(self, event: CalendarEvent) -> str:
        for ref, event_id in self._refs.items():
            if event_id == event.id:
                return ref
        ref = f"m{len(self._refs) + 1}"
        self._refs[ref] = event.id
        return ref

    def _event(self, ref: str) -> CalendarEvent:
        event_id = self._refs.get(ref.strip())
        event = self._cal.get_event(event_id) if event_id else None
        if event is None:
            raise ToolError(f"Unknown meeting reference '{ref}'. Call list_calendar first and use its m-numbers.")
        return event

    def _parse_start(self, value: str) -> datetime:
        try:
            moment = datetime.fromisoformat(value.strip())
        except ValueError:
            raise ToolError(f"Can't read start time '{value}'. Use local ISO format like 2026-10-28T15:00.")
        moment = moment.replace(tzinfo=self.tz) if moment.tzinfo is None else moment.astimezone(self.tz)
        if moment < self.now() + LEAD_TIME:
            raise ToolError("That time is in the past or less than 15 minutes away. Pick a later time.")
        return moment

    def _parse_day(self, value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            raise ToolError(f"Can't read date '{value}'. Use YYYY-MM-DD.")

    def _resolve_attendees(self, emails: list[str]) -> list[Contact]:
        rep_domain = self._cal.rep().email.split("@")[-1].lower()
        people = []
        for email in emails:
            email = email.strip().lower()
            if "@" not in email:
                raise ToolError(f"'{email}' isn't an email address. Use search_contacts to find the person first.")
            known = [c for c in self._cal.search_contacts(email) if c.email.lower() == email]
            if known:
                people.append(known[0])
            elif email.split("@")[-1] == rep_domain:
                raise ToolError(f"No colleague with address {email}. Use search_contacts to find the right person.")
            else:
                people.append(Contact(email, email, "client"))
        return people

    def _describe(self, e: CalendarEvent) -> str:
        if not e.is_meeting:
            kind = "Block"
        else:
            role = "you organise" if e.is_organiser else f"organised by {e.organiser.name}"
            kind = f"Meeting, {role}" + (", Teams" if e.is_teams else ", in person")
        if e.is_occurrence:
            kind += ", part of a weekly series"
        line = f"{self._ref_for(e)} | {_fmt_range(e.start, e.end)} | {e.title} | {kind}"
        if e.attendees:
            line += " | with " + ", ".join(_who(a) for a in e.attendees)
        return line

    def _clashes(self, slot: Interval, attendees: list[Contact], ignore: CalendarEvent | None = None) -> list[str]:
        warnings = []
        for e in self._cal.list_events(slot.start, slot.end):
            if ignore is None or e.id != ignore.id:
                warnings.append(f"Clashes with {e.title} ({e.start:%H:%M}–{e.end:%H:%M})")
        colleagues = [a for a in attendees if a.kind == "colleague"]
        busy = self._cal.busy_times([c.email for c in colleagues], slot.start, slot.end)
        for c in colleagues:
            own = [b for b in busy.get(c.email, []) if ignore is None or b != ignore.interval]
            if any(b.overlaps(slot) for b in own):
                warnings.append(f"{c.name} is busy then")
        if warnings:
            alt = self._next_free(slot, attendees, ignore)
            if alt:
                warnings.append(f"Next free slot: {_fmt_range(alt.start, alt.end)}")
        return warnings

    def _busy(self, attendees: list[Contact], start: datetime, end: datetime, ignore=None) -> list[Interval]:
        busy = [e.interval for e in self._cal.list_events(start, end) if ignore is None or e.id != ignore.id]
        colleagues = [a.email for a in attendees if a.kind == "colleague"]
        for intervals in self._cal.busy_times(colleagues, start, end).values():
            busy += [b for b in intervals if ignore is None or b != ignore.interval]
        return busy

    def _next_free(self, wanted: Interval, attendees, ignore=None) -> Interval | None:
        """The first free Slot starting at or after the time the Rep asked for."""
        busy = self._busy(attendees, wanted.start, wanted.start + timedelta(days=14), ignore)
        search_from = max(self.now(), wanted.start - LEAD_TIME)
        slots = find_slots(busy, self._cal.working_hours(), wanted.end - wanted.start, search_from, limit=1)
        return slots[0] if slots else None

    # --- reading tools -----------------------------------------------------------------

    def list_calendar(self, start_date: str, end_date: str | None = None) -> str:
        first = self._parse_day(start_date)
        last = self._parse_day(end_date) or first
        start = datetime.combine(first, datetime.min.time(), self.tz)
        end = datetime.combine(last + timedelta(days=1), datetime.min.time(), self.tz)
        events = self._cal.list_events(start, end)
        if not events:
            return f"Nothing on the calendar from {first} to {last}."
        return "\n".join(self._describe(e) for e in events)

    def _find_contacts(self, query: str) -> list[Contact]:
        """Whole query first; if that finds nobody, people matching every word ("Lena Globex")."""
        found = self._cal.search_contacts(query)
        if found:
            return found
        words = [w for w in re.findall(r"[\w.@'-]+", query.lower()) if len(w) > 2 and w not in _FILLER]
        matches = [set(self._cal.search_contacts(w)) for w in words]
        matches = [m for m in matches if m]
        if not matches:
            return []
        common = set.intersection(*matches)
        return sorted(common or set.union(*matches), key=lambda c: c.name)

    def find_meetings(self, text: str) -> str:
        """Upcoming Meetings and Blocks (next 14 days) whose title, people or company match every word of text."""
        words = [w for w in re.findall(r"[\w.@'-]+", text.lower()) if len(w) > 2 and w not in _FILLER]
        now = self.now()
        hits = []
        for e in self._cal.list_events(now, now + timedelta(days=14)):
            haystack = " ".join([e.title, e.organiser.name, *(f"{a.name} {a.email} {a.company}" for a in e.attendees)]).lower()
            if words and all(w in haystack for w in words):
                hits.append(e)
        if not hits:
            return f"No upcoming meetings match '{text}' in the next 14 days."
        return "\n".join(self._describe(e) for e in hits)

    def search_contacts(self, query: str) -> str:
        found = self._find_contacts(query)
        if not found:
            return (f"No contacts match '{query}'. If the Rep already gave an email address, use it as-is; "
                    "otherwise ask them for one.")
        lines = [f"{c.name} <{c.email}> {c.kind}" + (f", {c.company}" if c.company else "") for c in found]
        if len(found) > 1:
            lines.insert(0, f"{len(found)} matches - ask the Rep which one they mean:")
        return "\n".join(lines)

    def find_slots(
        self,
        duration_minutes: int = DEFAULT_MINUTES,
        attendee_emails: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        attendees = self._resolve_attendees(attendee_emails or [])
        duration = timedelta(minutes=int(duration_minutes))
        first = self._parse_day(start_date) or self.now().date()
        last = self._parse_day(end_date)
        start = datetime.combine(first, datetime.min.time(), self.tz)
        busy = self._busy(attendees, start, start + timedelta(days=21))
        slots = find_slots(busy, self._cal.working_hours(), duration, self.now(), first, last, limit=3)
        clients = [_who(a) for a in attendees if a.kind == "client"]
        note = f"\nNote: can't see availability for {', '.join(clients)}; only the Rep and colleagues were checked." if clients else ""
        if not slots:
            return "No free slot in working hours in that range." + note
        return "\n".join(f"Option {i}: {_fmt_range(s.start, s.end)} (start {s.start:%Y-%m-%dT%H:%M})" for i, s in enumerate(slots, 1)) + note

    # --- changing tools (each builds a Proposed Action) ----------------------------------

    def propose_create_meeting(
        self,
        title: str,
        start: str,
        attendee_emails: list[str],
        duration_minutes: int = DEFAULT_MINUTES,
        teams: bool = True,
    ) -> str:
        if not attendee_emails:
            raise ToolError("A meeting needs at least one attendee. Ask the Rep who it's with.")
        attendees = self._resolve_attendees(attendee_emails)
        begin = self._parse_start(start)
        end = begin + timedelta(minutes=int(duration_minutes))
        meeting = NewMeeting(title.strip() or "Meeting", begin, end, attendees, bool(teams))
        args = {"title": meeting.title, "start": start, "attendee_emails": attendee_emails,
                "duration_minutes": duration_minutes, "teams": teams}

        def execute() -> str:
            created = self._cal.create_meeting(meeting)
            return f"Created '{created.title}' {_fmt_range(created.start, created.end)}; invites sent."

        action = ProposedAction(
            kind="create",
            tool="propose_create_meeting",
            args=args,
            headline="Create Teams meeting" if meeting.is_teams else "Create in-person meeting",
            details={
                "Title": meeting.title,
                "When": _fmt_range(begin, end),
                "With": ", ".join(_who(a) for a in attendees),
                "Teams link": "Yes" if meeting.is_teams else "No (in person)",
            },
            facts={"kind": "create", "title": meeting.title, "start": begin, "end": end,
                   "attendees": sorted(a.email for a in attendees), "is_teams": meeting.is_teams},
            execute=execute,
            warnings=self._clashes(Interval(begin, end), attendees),
        )
        self._gate.propose(action)
        return self._proposed_reply(action)

    def propose_reschedule(self, meeting_ref: str, new_start: str, duration_minutes: int | None = None, note: str = "",
                           whole_series: bool = False) -> str:
        if whole_series:
            raise ToolError("Changing a whole Series isn't supported yet. Tell the Rep, and offer to change just one occurrence.")
        event = self._event(meeting_ref)
        if not event.is_organiser:
            raise ToolError(
                f"The Rep doesn't organise '{event.title}' ({event.organiser.name} does), so it can't be moved. "
                "Offer to decline it with a note suggesting the new time instead (propose_decline)."
            )
        begin = self._parse_start(new_start)
        length = timedelta(minutes=int(duration_minutes)) if duration_minutes else event.end - event.start
        end = begin + length
        args = {"meeting_ref": meeting_ref, "event_id": event.id, "new_start": new_start,
                "duration_minutes": duration_minutes, "note": note}

        def execute() -> str:
            moved = self._cal.reschedule(event.id, begin, end, note)
            return f"Rescheduled '{moved.title}' to {_fmt_range(moved.start, moved.end)}; attendees updated."

        details = {"Meeting": event.title, "From": _fmt_range(event.start, event.end), "To": _fmt_range(begin, end)}
        if event.is_occurrence:
            details["Scope"] = "This occurrence only"
        if note:
            details["Note to attendees"] = note
        action = ProposedAction(
            kind="reschedule", tool="propose_reschedule", args=args, headline="Reschedule meeting",
            details=details,
            facts={"kind": "reschedule", "title": event.title, "start": begin, "end": end, "note": note},
            execute=execute,
            warnings=self._clashes(Interval(begin, end), event.attendees, ignore=event),
        )
        self._gate.propose(action)
        return self._proposed_reply(action)

    def propose_cancel(self, meeting_ref: str, note: str = "", whole_series: bool = False) -> str:
        if whole_series:
            raise ToolError("Changing a whole Series isn't supported yet. Tell the Rep, and offer to change just one occurrence.")
        event = self._event(meeting_ref)
        if not event.is_organiser:
            raise ToolError(
                f"The Rep doesn't organise '{event.title}' ({event.organiser.name} does), so it can't be cancelled. "
                "Offer to decline it instead (propose_decline)."
            )
        args = {"meeting_ref": meeting_ref, "event_id": event.id, "note": note}

        def execute() -> str:
            self._cal.cancel(event.id, note)
            return f"Cancelled '{event.title}'" + ("; attendees notified." if event.is_meeting else ".")

        details = {"Meeting": event.title, "When": _fmt_range(event.start, event.end)}
        if event.attendees:
            details["Attendees told"] = ", ".join(_who(a) for a in event.attendees)
        if event.is_occurrence:
            details["Scope"] = "This occurrence only"
        if note:
            details["Note to attendees"] = note
        action = ProposedAction(
            kind="cancel", tool="propose_cancel", args=args,
            headline="Cancel meeting" if event.is_meeting else "Remove block",
            details=details, facts={"kind": "cancel", "title": event.title, "start": event.start, "note": note},
            execute=execute,
        )
        self._gate.propose(action)
        return self._proposed_reply(action)

    def propose_decline(self, meeting_ref: str, note: str = "", whole_series: bool = False) -> str:
        if whole_series:
            raise ToolError("Changing a whole Series isn't supported yet. Tell the Rep, and offer to change just one occurrence.")
        event = self._event(meeting_ref)
        if event.is_organiser:
            raise ToolError(f"The Rep organises '{event.title}'; use propose_cancel instead of declining.")
        args = {"meeting_ref": meeting_ref, "event_id": event.id, "note": note}

        def execute() -> str:
            self._cal.decline(event.id, note)
            return f"Declined '{event.title}'; {event.organiser.name} has been told."

        details = {"Meeting": event.title, "When": _fmt_range(event.start, event.end), "Organiser": event.organiser.name}
        if event.is_occurrence:
            details["Scope"] = "This occurrence only"
        if note:
            details["Note to organiser"] = note
        action = ProposedAction(
            kind="decline", tool="propose_decline", args=args, headline="Decline meeting",
            details=details, facts={"kind": "decline", "title": event.title, "start": event.start, "note": note},
            execute=execute,
        )
        self._gate.propose(action)
        return self._proposed_reply(action)

    @staticmethod
    def _proposed_reply(action: ProposedAction) -> str:
        text = f"Proposed Action ready: {action.headline}. " + "; ".join(f"{k}: {v}" for k, v in action.details.items())
        if action.warnings:
            text += ". Warnings: " + "; ".join(action.warnings)
        return text + ". It is NOT done yet: tell the Rep briefly and ask them to confirm."

    # --- tool registry -----------------------------------------------------------------

    def tools(self) -> dict[str, Callable[..., str]]:
        return {
            "list_calendar": self.list_calendar,
            "find_meetings": self.find_meetings,
            "search_contacts": self.search_contacts,
            "find_slots": self.find_slots,
            "propose_create_meeting": self.propose_create_meeting,
            "propose_reschedule": self.propose_reschedule,
            "propose_cancel": self.propose_cancel,
            "propose_decline": self.propose_decline,
        }

    def call(self, name: str, args: dict) -> str:
        tool = self.tools().get(name)
        if tool is None:
            return f"Error: unknown tool {name}"
        if name.startswith("propose_") and self._proposed_this_turn:
            message = ("Only one change can wait for confirmation at a time and one is already proposed. "
                       "Ask the Rep to confirm it first; offer the next change after that.")
            self._log.record(name, args, "failed", message)
            return f"Error: {message}"
        args = {k: v for k, v in args.items() if v is not None}  # models send null for "not given"
        try:
            result = tool(**args)
        except ToolError as exc:
            self._log.record(name, args, "failed", str(exc))
            return f"Error: {exc}"
        except TypeError as exc:
            self._log.record(name, args, "failed", str(exc))
            return f"Error: bad arguments for {name}: {exc}"
        if name.startswith("propose_"):
            self._proposed_this_turn = True
        else:
            self._log.record(name, args, "ok", result.splitlines()[0][:200])
        return result


TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "list_calendar",
            "description": "List Meetings and Blocks on the Rep's calendar between two dates (inclusive). Each line starts with a reference like m3 to use in other tools.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD; omit for a single day"},
                },
                "required": ["start_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_meetings",
            "description": "Find upcoming Meetings (next 14 days) by title, attendee name or company, e.g. 'Globex discovery' or 'Raj Kumar'. Use this when the Rep names a Meeting without saying which day.",
            "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": "Find Colleagues and Clients by name, email or company. If several match, ask the Rep which one.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_slots",
            "description": "Find the earliest free Slots in working hours for the Rep and any colleague attendees. Defaults to the next 5 working days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_minutes": {"type": "integer", "default": 30},
                    "attendee_emails": {"type": "array", "items": {"type": "string"}},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, earliest day to search"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, last day to search"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_create_meeting",
            "description": "Propose a new Meeting organised by the Rep. Does not create it: the Rep must confirm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "Local time, ISO format e.g. 2026-10-28T15:00"},
                    "attendee_emails": {"type": "array", "items": {"type": "string"}},
                    "duration_minutes": {"type": "integer", "default": 30},
                    "teams": {"type": "boolean", "default": True, "description": "false only if the Rep says in person"},
                },
                "required": ["title", "start", "attendee_emails"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_reschedule",
            "description": "Propose moving a Meeting or Block the Rep organises (single occurrence only). Does not move it: the Rep must confirm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "meeting_ref": {"type": "string", "description": "Reference from list_calendar, e.g. m3"},
                    "new_start": {"type": "string", "description": "Local time, ISO format"},
                    "duration_minutes": {"type": "integer", "description": "Only if the length changes"},
                    "note": {"type": "string", "description": "Optional note the Rep dictated"},
                    "whole_series": {"type": "boolean", "description": "true if the Rep asked to change every occurrence of a recurring Meeting"},
                },
                "required": ["meeting_ref", "new_start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_cancel",
            "description": "Propose cancelling a Meeting the Rep organises, or removing a Block (single occurrence only). The Rep must confirm.",
            "parameters": {
                "type": "object",
                "properties": {"meeting_ref": {"type": "string"}, "note": {"type": "string"}, "whole_series": {"type": "boolean", "description": "true if the Rep asked to change every occurrence of a recurring Meeting"}},
                "required": ["meeting_ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_decline",
            "description": "Propose declining a Meeting someone else organises; use the note to suggest a new time if the Rep wants it moved. The Rep must confirm.",
            "parameters": {
                "type": "object",
                "properties": {"meeting_ref": {"type": "string"}, "note": {"type": "string"}, "whole_series": {"type": "boolean", "description": "true if the Rep asked to change every occurrence of a recurring Meeting"}},
                "required": ["meeting_ref"],
            },
        },
    },
]


def _allow_null_for_optional(specs: list[dict]) -> None:
    """Models often send null for an optional field; Groq rejects that unless the schema allows it."""
    for spec in specs:
        params = spec["function"]["parameters"]
        for name, prop in params.get("properties", {}).items():
            if name not in params.get("required", []):
                prop["type"] = [prop["type"], "null"]


_allow_null_for_optional(TOOL_SPECS)
