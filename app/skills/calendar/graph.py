"""The Rep's real Outlook calendar through Microsoft Graph (delegated permissions).

Graph limitation: updating an event has no message field, so a note on a
Reschedule is not sent. Cancel and Decline notes are sent.
"""

from datetime import datetime, time, timezone
from functools import cached_property
from zoneinfo import ZoneInfo, available_timezones

import httpx
from tzlocal.windows_tz import win_tz

from app.graph.auth import GraphAuth
from app.skills.calendar.model import CalendarEvent, Contact, Interval, NewMeeting, WorkingHours

GRAPH = "https://graph.microsoft.com/v1.0"
EVENT_FIELDS = "id,subject,start,end,organizer,attendees,isOrganizer,isOnlineMeeting,onlineMeeting,seriesMasterId,isCancelled"
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
BUSY = {"busy", "oof", "tentative", "workingElsewhere"}


def _utc(dt: datetime) -> dict:
    return {"dateTime": dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"}


def _parse_utc(value: dict) -> datetime:
    return datetime.fromisoformat(value["dateTime"][:26]).replace(tzinfo=timezone.utc)


def _iana(name: str) -> str:
    return name if name in available_timezones() else win_tz.get(name, "UTC")


class GraphCalendar:
    def __init__(self, auth: GraphAuth):
        self._auth = auth

    # --- http --------------------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {self._auth.token()}", "Prefer": 'outlook.timezone="UTC"'}
        url = path if path.startswith("http") else GRAPH + path
        response = httpx.request(method, url, headers=headers, timeout=30, **kwargs)
        if response.status_code >= 400:
            try:
                message = response.json()["error"]["message"]
            except Exception:
                message = response.text[:200]
            raise RuntimeError(f"Outlook error {response.status_code}: {message}")
        return response.json() if response.content else {}

    # --- mapping -----------------------------------------------------------------------

    @cached_property
    def _rep(self) -> Contact:
        me = self._request("GET", "/me?$select=displayName,mail,userPrincipalName,companyName")
        return Contact(me["displayName"], (me.get("mail") or me["userPrincipalName"]).lower(), "colleague",
                       me.get("companyName") or "")

    def _contact(self, address: dict, company: str = "") -> Contact:
        email = (address.get("address") or "").lower()
        rep_domain = self._rep.email.split("@")[-1]
        kind = "colleague" if email.endswith("@" + rep_domain) else "client"
        return Contact(address.get("name") or email, email, kind, company)

    def _event(self, raw: dict) -> CalendarEvent:
        tz = ZoneInfo(self.working_hours().timezone)
        organiser = self._contact(raw["organizer"]["emailAddress"])
        others = [self._contact(a["emailAddress"]) for a in raw.get("attendees", [])]
        if organiser.email != self._rep.email:
            others.insert(0, organiser)
        others = [c for i, c in enumerate(others) if c.email != self._rep.email and c not in others[:i]]
        return CalendarEvent(
            id=raw["id"],
            title=raw.get("subject") or "(no title)",
            start=_parse_utc(raw["start"]).astimezone(tz),
            end=_parse_utc(raw["end"]).astimezone(tz),
            organiser=organiser,
            attendees=others,
            is_organiser=bool(raw.get("isOrganizer")),
            is_teams=bool(raw.get("isOnlineMeeting")),
            join_url=(raw.get("onlineMeeting") or {}).get("joinUrl", ""),
            series_id=raw.get("seriesMasterId") or "",
        )

    # --- CalendarPort ------------------------------------------------------------------

    def rep(self) -> Contact:
        return self._rep

    @cached_property
    def _hours(self) -> WorkingHours:
        hours = self._request("GET", "/me/mailboxSettings")["workingHours"]
        return WorkingHours(
            days=frozenset(DAYS.index(d) for d in hours["daysOfWeek"]),
            start=time.fromisoformat(hours["startTime"][:8]),
            end=time.fromisoformat(hours["endTime"][:8]),
            timezone=_iana(hours["timeZone"]["name"]),
        )

    def working_hours(self) -> WorkingHours:
        return self._hours

    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        params = {"startDateTime": _utc(start)["dateTime"], "endDateTime": _utc(end)["dateTime"],
                  "$select": EVENT_FIELDS, "$top": "100", "$orderby": "start/dateTime"}
        page = self._request("GET", "/me/calendarView", params=params)
        raw = list(page.get("value", []))
        while "@odata.nextLink" in page:
            page = self._request("GET", page["@odata.nextLink"])
            raw += page.get("value", [])
        return [self._event(r) for r in raw if not r.get("isCancelled")]

    def get_event(self, event_id: str) -> CalendarEvent | None:
        try:
            return self._event(self._request("GET", f"/me/events/{event_id}?$select={EVENT_FIELDS}"))
        except RuntimeError:
            return None

    def busy_times(self, emails: list[str], start: datetime, end: datetime) -> dict[str, list[Interval]]:
        if not emails:
            return {}
        body = {"schedules": emails, "startTime": _utc(start), "endTime": _utc(end), "availabilityViewInterval": 15}
        result: dict[str, list[Interval]] = {e: [] for e in emails}
        for schedule in self._request("POST", "/me/calendar/getSchedule", json=body).get("value", []):
            result[schedule["scheduleId"].lower()] = [
                Interval(_parse_utc(i["start"]), _parse_utc(i["end"]))
                for i in schedule.get("scheduleItems", []) if i.get("status") in BUSY
            ]
        return result

    def search_contacts(self, query: str) -> list[Contact]:
        params = {"$search": f'"{query}"', "$top": "10", "$select": "displayName,scoredEmailAddresses,companyName"}
        people = self._request("GET", "/me/people", params=params).get("value", [])
        return [
            self._contact({"name": p["displayName"], "address": p["scoredEmailAddresses"][0]["address"]},
                          p.get("companyName") or "")
            for p in people if p.get("scoredEmailAddresses")
        ]

    def create_meeting(self, meeting: NewMeeting) -> CalendarEvent:
        body = {
            "subject": meeting.title,
            "start": _utc(meeting.start),
            "end": _utc(meeting.end),
            "attendees": [{"emailAddress": {"address": a.email, "name": a.name}, "type": "required"}
                          for a in meeting.attendees],
        }
        if meeting.is_teams:
            body |= {"isOnlineMeeting": True, "onlineMeetingProvider": "teamsForBusiness"}
        return self._event(self._request("POST", "/me/events", json=body))

    def reschedule(self, event_id: str, start: datetime, end: datetime, note: str = "") -> CalendarEvent:
        return self._event(self._request("PATCH", f"/me/events/{event_id}", json={"start": _utc(start), "end": _utc(end)}))

    def cancel(self, event_id: str, note: str = "") -> None:
        event = self.get_event(event_id)
        if event is not None and not event.is_meeting:
            self._request("DELETE", f"/me/events/{event_id}")  # a Block has nobody to notify
        else:
            self._request("POST", f"/me/events/{event_id}/cancel", json={"comment": note})

    def decline(self, event_id: str, note: str = "") -> None:
        self._request("POST", f"/me/events/{event_id}/decline", json={"comment": note, "sendResponse": True})
