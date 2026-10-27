# Sales Voice Assistant

A personal assistant that manages a sales rep's Outlook calendar, mail and Teams through voice and chat, acting only with the rep's confirmation.

## People

**Rep**:
The salesperson the assistant works for; their calendar, mail and reminders are the ones being managed.
_Avoid_: User, employee, salesperson

**Contact**:
Anyone a Rep meets, messages or calls; either a Colleague or a Client.
_Avoid_: Person, participant

**Colleague**:
A Contact inside the Rep's own organisation, whose availability can be checked.
_Avoid_: Internal user, coworker

**Client**:
A Contact outside the Rep's organisation, invited by email address; their availability cannot be seen.
_Avoid_: Customer, external, prospect

## Calendar

**Meeting**:
A calendar event on the Rep's calendar with at least one other attendee.
_Avoid_: Event, appointment, call

**Block**:
A calendar event with no other attendees, such as focus time or out-of-office; shown in the Rep's day but never treated as a Meeting.
_Avoid_: Hold, busy time

**Teams meeting**:
A Meeting that carries a Teams join link; the default kind of Meeting the assistant creates.
_Avoid_: Online meeting, call

**Organiser**:
The person who owns a Meeting; only the Organiser can Reschedule or Cancel it.
_Avoid_: Owner, host

**Occurrence**:
A single instance of a recurring Meeting.
_Avoid_: Instance

**Series**:
The whole set of Occurrences of a recurring Meeting.
_Avoid_: Recurrence, recurring meeting

**Slot**:
A free window in the Rep's working hours long enough for a requested Meeting.
_Avoid_: Free time, availability

**Clash**:
An overlap between a proposed Meeting time and an existing Meeting or Block, or a time when an invited Colleague is busy.
_Avoid_: Conflict, double-booking

## Actions

**Reschedule**:
Move a Meeting the Rep organises to a new time; attendees receive the update.
_Avoid_: Move, shift, push

**Cancel**:
Remove a Meeting the Rep organises; attendees receive a cancellation.
_Avoid_: Delete, remove

**Decline**:
Remove the Rep from a Meeting someone else organises; the Organiser is told.
_Avoid_: Delete, reject, leave

**Proposed Action**:
A change the assistant intends to make, shown to the Rep in full and executed only after the Rep confirms it.
_Avoid_: Draft, pending action, suggestion

**Activity Log**:
The record of everything the assistant read or did on the Rep's behalf, including what was proposed, confirmed, cancelled, expired or failed.
_Avoid_: Audit trail, history
