import pytest

from app.core.agent import Agent
from app.core.session import Session
from app.providers.llm import AssistantTurn, FallbackLLM, LLMUnavailable, ToolCall, parse_message
from app.skills.calendar.skill import TOOL_SPECS


class ScriptedLLM:
    """Plays back canned assistant turns and records what it was sent."""

    name = "scripted"

    def __init__(self, *turns: AssistantTurn):
        self.turns = list(turns)
        self.seen: list[list[dict]] = []

    def complete(self, messages, tools):
        self.seen.append(messages)
        return self.turns.pop(0)


def call(name, **args):
    return AssistantTurn("", [ToolCall(f"c-{name}", name, args)])


def say(text):
    return AssistantTurn(text)


@pytest.fixture
def make_session(skill, gate, clock):
    def make(llm):
        return Session(Agent(llm, skill, TOOL_SPECS, "Vaishnavi Soni", clock), gate, skill, llm)

    return make


BOOK_SAM = call(
    "propose_create_meeting", title="Acme / Vaishnavi", start="2026-10-28T16:00", attendee_emails=["sam.carter@acme.example"]
)


def test_proposal_is_returned_as_a_card_and_typed_yes_confirms(make_session, calendar):
    session = make_session(ScriptedLLM(BOOK_SAM, say("Book Acme / Vaishnavi Wed 4 pm? Confirm?")))
    reply = session.handle("book 30 min with Sam from Acme on Wednesday at 4")
    assert reply.proposal["headline"] == "Create Teams meeting"
    assert reply.proposal["details"]["When"] == "Wed 28 Oct, 16:00–16:30"
    done = session.handle("Yes!")
    assert done.text.startswith("Done. Created 'Acme / Vaishnavi'")
    assert done.proposal is None
    assert calendar.sent[-1][0] == "invite"


def test_typed_no_cancels(make_session, calendar):
    session = make_session(ScriptedLLM(BOOK_SAM, say("Confirm?")))
    session.handle("book Sam wed 4")
    assert session.handle("no").text == "OK, I won't do that."
    assert calendar.sent == []


def test_new_request_discards_the_pending_proposal(make_session, gate):
    session = make_session(ScriptedLLM(BOOK_SAM, say("Confirm?"), say("You have 3 meetings tomorrow.")))
    session.handle("book Sam wed 4")
    reply = session.handle("actually what's on tomorrow?")
    assert reply.proposal is None and gate.pending() is None


def test_confirmation_result_is_remembered_for_follow_ups(make_session):
    llm = ScriptedLLM(BOOK_SAM, say("Confirm?"), say("ok"))
    session = make_session(llm)
    session.handle("book Sam wed 4")
    session.handle("yes")
    session.handle("thanks")
    assert any("The Rep confirmed" in str(m.get("content")) for m in llm.seen[-1])


def test_tool_errors_are_fed_back_to_the_model(make_session):
    llm = ScriptedLLM(call("propose_cancel", meeting_ref="m99"), say("Which meeting?"))
    session = make_session(llm)
    session.handle("cancel it")
    tool_message = llm.seen[-1][-1]
    assert tool_message["role"] == "tool" and tool_message["content"].startswith("Error: Unknown meeting reference")


def test_new_chat_forgets_history(make_session):
    llm = ScriptedLLM(say("hi"), say("hello again"))
    session = make_session(llm)
    session.handle("hello")
    session.new_chat()
    session.handle("hello")
    assert [m["role"] for m in llm.seen[-1]] == ["system", "user"]


def test_fallback_switches_once_primary_is_rate_limited():
    class RateLimited:
        name = "groq"

        def complete(self, messages, tools):
            raise LLMUnavailable("groq rate limit reached")

    switches = []
    llm = FallbackLLM(RateLimited(), ScriptedLLM(say("local"), say("local again")), switches.append)
    assert llm.complete([], []).content == "local"
    assert llm.complete([], []).content == "local again"
    assert switches == ["groq rate limit reached"]
    assert llm.notice == "Using the slower local model (groq rate limit reached)."


def test_parse_strips_thinking_and_reads_tool_arguments():
    turn = parse_message(
        {
            "content": "<think>hmm</think>Sure.",
            "tool_calls": [{"id": "x", "function": {"name": "list_calendar", "arguments": '{"start_date": "2026-10-27"}'}}],
        }
    )
    assert turn.content == "Sure."
    assert turn.tool_calls[0].arguments == {"start_date": "2026-10-27"}
