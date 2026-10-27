import re

from tests.conftest import TZ


def ref_of(listing: str, title: str) -> str:
    line = next(l for l in listing.splitlines() if title in l)
    return line.split(" | ")[0]


def test_listing_shows_both_3pm_meetings_with_roles(skill):
    out = skill.list_calendar("2026-10-27")
    assert "Acme pricing call | Meeting, you organise, Teams" in out
    assert "Q4 forecast review | Meeting, organised by Priya Shah" in out
    assert "Focus time | Block" in out
    assert re.match(r"m\d+ \| Tue 27 Oct, 09:00–11:00", out.splitlines()[0])


def test_two_rajs_means_ask_which(skill):
    out = skill.search_contacts("Raj")
    assert out.startswith("2 matches - ask the Rep which one")
    assert "raj.mehta@contoso.example" in out and "raj.kumar@contoso.example" in out


def test_create_waits_for_confirmation(skill, calendar, gate):
    reply = skill.call(
        "propose_create_meeting",
        {"title": "Acme / Vaishnavi", "start": "2026-10-28T16:00", "attendee_emails": ["sam.carter@acme.example"]},
    )
    assert "NOT done yet" in reply
    assert not [e for e in calendar.list_events(*_day(28)) if e.title == "Acme / Vaishnavi"]
    gate.confirm()
    created = [e for e in calendar.list_events(*_day(28)) if e.title == "Acme / Vaishnavi"]
    assert created and created[0].is_teams and created[0].is_organiser
    assert calendar.sent[-1] == ("invite", "Acme / Vaishnavi", "")


def test_clash_warns_but_does_not_block(skill, gate):
    skill.call(
        "propose_create_meeting",
        {"title": "Raj catch-up", "start": "2026-10-27T15:00", "attendee_emails": ["raj.mehta@contoso.example"]},
    )
    warnings = gate.pending().warnings
    assert "Clashes with Acme pricing call (15:00–15:30)" in warnings
    assert "Raj Mehta is busy then" in warnings
    assert "Next free slot: Tue 27 Oct, 16:00–16:30" in warnings


def test_cannot_move_a_meeting_someone_else_organises(skill, gate):
    ref = ref_of(skill.list_calendar("2026-10-27"), "Q4 forecast review")
    reply = skill.call("propose_reschedule", {"meeting_ref": ref, "new_start": "2026-10-27T17:00"})
    assert reply.startswith("Error:") and "decline" in reply
    assert gate.pending() is None


def test_decline_with_note_for_someone_elses_meeting(skill, calendar, gate):
    ref = ref_of(skill.list_calendar("2026-10-27"), "Q4 forecast review")
    skill.call("propose_decline", {"meeting_ref": ref, "note": "Could we do 5 pm instead?"})
    gate.confirm()
    assert calendar.sent[-1] == ("decline", "Q4 forecast review", "Could we do 5 pm instead?")


def test_cannot_decline_own_meeting(skill):
    ref = ref_of(skill.list_calendar("2026-10-27"), "Acme pricing call")
    assert "propose_cancel" in skill.call("propose_decline", {"meeting_ref": ref})


def test_cancel_one_occurrence_leaves_the_rest_of_the_series(skill, calendar, gate):
    ref = ref_of(skill.list_calendar("2026-10-26"), "Weekly pipeline sync")
    skill.call("propose_cancel", {"meeting_ref": ref})
    assert gate.pending().details["Scope"] == "This occurrence only"
    gate.confirm()
    remaining = [e for e in calendar.list_events(*_day(26, 14)) if e.title == "Weekly pipeline sync"]
    assert len(remaining) == 1 and remaining[0].start.day == 2


def test_reschedule_ignores_the_meetings_own_slot(skill, gate):
    ref = ref_of(skill.list_calendar("2026-10-27"), "Acme pricing call")
    skill.call("propose_reschedule", {"meeting_ref": ref, "new_start": "2026-10-27T15:15"})
    assert all("Acme pricing call" not in w for w in gate.pending().warnings)


def test_rejects_times_in_the_past(skill):
    reply = skill.call(
        "propose_create_meeting",
        {"title": "x", "start": "2026-10-26T08:00", "attendee_emails": ["sam.carter@acme.example"]},
    )
    assert "past" in reply


def test_unknown_colleague_address_is_rejected_but_clients_are_accepted(skill, gate):
    bad = skill.call(
        "propose_create_meeting",
        {"title": "x", "start": "2026-10-28T16:00", "attendee_emails": ["raj@contoso.example"]},
    )
    assert "search_contacts" in bad
    skill.call(
        "propose_create_meeting",
        {"title": "Hooli intro", "start": "2026-10-28T16:00", "attendee_emails": ["gavin@hooli.example"]},
    )
    assert gate.pending().facts["attendees"] == ["gavin@hooli.example"]


def test_find_slots_checks_colleagues_and_flags_clients(skill):
    out = skill.find_slots(30, ["raj.mehta@contoso.example", "sam.carter@acme.example"], "2026-10-27", "2026-10-27")
    assert out.startswith("Option 1: Tue 27 Oct, 11:00–11:30")
    assert "can't see availability for Sam Carter" in out


def test_reads_are_logged_without_bodies(skill, log):
    skill.call("list_calendar", {"start_date": "2026-10-27"})
    entry = log.recent()[0]
    assert entry.tool == "list_calendar" and entry.status == "ok"


def _day(d: int, span_days: int = 1):
    from datetime import datetime, timedelta

    start = datetime(2026, 10, d, tzinfo=TZ)
    return start, start + timedelta(days=span_days)


def test_whole_series_changes_are_refused(skill, gate):
    ref = ref_of(skill.list_calendar("2026-10-26"), "Weekly pipeline sync")
    reply = skill.call("propose_cancel", {"meeting_ref": ref, "whole_series": True})
    assert "isn't supported yet" in reply and gate.pending() is None


def test_only_one_proposal_per_request(skill, gate):
    listing = skill.list_calendar("2026-10-26", "2026-11-03")
    first, second = [ref_of(listing, t) for t in ("Acme pricing call", "Globex discovery")]
    skill.begin_turn()
    skill.call("propose_cancel", {"meeting_ref": first})
    reply = skill.call("propose_cancel", {"meeting_ref": second})
    assert reply.startswith("Error: Only one change")
    assert gate.pending().facts["title"] == "Acme pricing call"
    skill.begin_turn()
    assert "NOT done yet" in skill.call("propose_cancel", {"meeting_ref": second})


def test_contact_search_matches_name_and_company_words(skill):
    assert "lena.ortiz@globex.example" in skill.search_contacts("Lena Globex")
    assert "lena.ortiz@globex.example" in skill.search_contacts("Lena from Globex")
    assert "sam.carter@acme.example" in skill.search_contacts("the Acme guy")


def test_find_meetings_by_name_across_the_coming_days(skill):
    out = skill.find_meetings("Globex discovery")
    assert "Wed 28 Oct, 11:00–11:45 | Globex discovery" in out
    assert "Raj Kumar sync" in skill.find_meetings("Raj Kumar")
    assert skill.find_meetings("Hooli").startswith("No upcoming meetings")
