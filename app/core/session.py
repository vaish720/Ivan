"""One conversation with the Rep: routes messages, confirmations and new chats."""

from dataclasses import dataclass

from app.core.agent import Agent
from app.core.confirmation import ConfirmationGate, NothingPending
from app.providers.llm import LLMError
from app.skills.calendar.skill import CalendarSkill

YES = {"yes", "y", "yeah", "yep", "yes please", "confirm", "ok", "okay", "go ahead", "do it", "sure"}
NO = {"no", "n", "nope", "no thanks", "cancel", "stop", "don't", "dont", "never mind"}


@dataclass
class Reply:
    text: str
    proposal: dict | None = None
    notice: str | None = None


class Session:
    def __init__(self, agent: Agent, gate: ConfirmationGate, skill: CalendarSkill, llm=None):
        self.agent = agent
        self.gate = gate
        self.skill = skill
        self._llm = llm

    def _reply(self, text: str) -> Reply:
        pending = self.gate.pending()
        return Reply(text, pending.card() if pending else None, getattr(self._llm, "notice", None))

    def handle(self, text: str) -> Reply:
        said = text.strip().lower().rstrip(".!")
        if self.gate.pending() is not None:
            if said in YES:
                return self.confirm()
            if said in NO:
                return self.cancel()
        self.gate.discard("the Rep moved on to a new request")
        try:
            answer = self.agent.respond(text)
        except LLMError as exc:
            answer = f"I couldn't reach the language model, so nothing was changed. ({exc})"
        return self._reply(answer)

    def confirm(self) -> Reply:
        try:
            result = self.gate.confirm()
        except NothingPending:
            return self._reply("There's nothing waiting for confirmation. It may have expired after 5 minutes.")
        except Exception as exc:  # the calendar refused the change
            self.agent.note(f"(The change failed: {exc})")
            return self._reply(f"Outlook refused that change: {exc}")
        self.agent.note(f"(The Rep confirmed. {result})")
        return self._reply(f"Done. {result}")

    def cancel(self) -> Reply:
        try:
            self.gate.cancel()
        except NothingPending:
            return self._reply("There's nothing waiting for confirmation.")
        self.agent.note("(The Rep said no, so nothing was changed.)")
        return self._reply("OK, I won't do that.")

    def new_chat(self) -> None:
        self.gate.discard("the Rep started a new chat")
        self.agent.reset()
        self.skill.reset_conversation()
