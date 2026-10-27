"""The coordinator: understands the Rep's request and calls skill tools via the LLM."""

from collections.abc import Callable
from datetime import datetime, timedelta

from app.providers.llm import LLM
from app.skills.calendar.skill import CalendarSkill

MAX_STEPS = 8
MAX_TURNS = 10  # about 20 Rep/assistant messages

SYSTEM_PROMPT = """You are the scheduling assistant for {rep_name}, a sales rep ("the Rep"). You manage the Rep's Outlook calendar. Replies will be read aloud later, so keep them short and conversational: one to three sentences, no markdown tables.

Now: {now} ({tz}).
Upcoming dates:
{dates}

Words:
- A Meeting has other attendees. A Block (focus time, out of office) has none.
- New Meetings are Teams meetings unless the Rep says in person. Default length is 30 minutes.

Rules:
1. To act on an existing Meeting, call list_calendar for that day first and use its reference (m1, m2...). If more than one Meeting could match ("my 3 pm" with two at 3 pm), ask which one. Never guess.
2. To find a person, call search_contacts. If several people match, ask which one. Never guess. Clients are invited by email; if you have no email for a Client, ask for it.
3. If the Rep gives no exact time ("tomorrow afternoon", "next week"), call find_slots in that window and propose the earliest option. Afternoon is 12:00-18:00, morning 09:00-12:00.
4. If there's no title, use "<Contact first name> / {rep_first}" or "<Company> - <topic>" when a company or topic is known. Don't ask just for a title.
5. Only the organiser can Reschedule or Cancel. If the Rep wants to move or drop a Meeting someone else organises, offer to Decline it, with a note suggesting the new time if they want it moved.
6. You can only change a single occurrence of a recurring Meeting. If asked to change the whole series, say you can't do that yet and offer to change just this one.
7. propose_* tools never change anything: they create a Proposed Action the Rep must confirm. After proposing, summarise it in one sentence, mention any warnings, and ask the Rep to confirm. Never say it is done.
8. There is no undo. Notes to attendees must never mention you or AI.
9. If a tool returns an error, fix the call or explain the problem to the Rep."""


def _dates(now: datetime) -> str:
    return "\n".join(
        f"- {(now + timedelta(days=i)):%a %d %b} = {(now + timedelta(days=i)):%Y-%m-%d}"
        + (" (today)" if i == 0 else " (tomorrow)" if i == 1 else "")
        for i in range(10)
    )


class Agent:
    def __init__(self, llm: LLM, skill: CalendarSkill, tool_specs: list[dict], rep_name: str,
                 clock: Callable[[], datetime]):
        self._llm = llm
        self._skill = skill
        self._tool_specs = tool_specs
        self._rep_name = rep_name
        self._clock = clock
        self._turns: list[list[dict]] = []

    def reset(self) -> None:
        self._turns.clear()

    def note(self, text: str) -> None:
        """Record something that happened outside the LLM (e.g. the Rep confirmed) in the conversation."""
        self._remember([{"role": "assistant", "content": text}])

    def _system(self) -> dict:
        now = self._skill.now()
        return {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                rep_name=self._rep_name,
                rep_first=self._rep_name.split()[0],
                now=f"{now:%A %d %B %Y, %H:%M}",
                tz=now.tzinfo,
                dates=_dates(now),
            ),
        }

    def _remember(self, turn: list[dict]) -> None:
        self._turns.append(turn)
        del self._turns[:-MAX_TURNS]

    def respond(self, text: str) -> str:
        turn: list[dict] = [{"role": "user", "content": text}]
        history = [m for t in self._turns for m in t]
        for _ in range(MAX_STEPS):
            reply = self._llm.complete([self._system(), *history, *turn], self._tool_specs)
            turn.append(reply.as_message())
            if not reply.tool_calls:
                self._remember(turn)
                return reply.content or "Sorry, I didn't catch that."
            for call in reply.tool_calls:
                result = self._skill.call(call.name, call.arguments)
                turn.append({"role": "tool", "tool_call_id": call.id, "content": result})
        self._remember(turn)
        return "Sorry, I couldn't finish that. Could you say it a different way?"
