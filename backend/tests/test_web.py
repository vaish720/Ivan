from fastapi.testclient import TestClient

from app.core.agent import Agent
from app.core.session import Session
from app.skills.calendar.skill import TOOL_SPECS
from app.web.routes import create_app
from tests.test_session import BOOK_SAM, ScriptedLLM, say


def test_chat_confirm_and_activity_over_http(skill, gate, log, clock):
    llm = ScriptedLLM(BOOK_SAM, say("Book it? Confirm?"))
    session = Session(Agent(llm, skill, TOOL_SPECS, "Vaishnavi Soni", clock), gate, skill, llm)
    client = TestClient(create_app(session, log, "fake"))

    assert "Sales Assistant" in client.get("/").text
    assert "Activity Log" in client.get("/activity").text

    reply = client.post("/api/chat", json={"message": "book Sam wed 4"}).json()
    assert reply["proposal"]["headline"] == "Create Teams meeting"

    done = client.post("/api/proposal/confirm").json()
    assert done["text"].startswith("Done.") and done["proposal"] is None

    statuses = [e["status"] for e in client.get("/api/activity").json()]
    assert statuses[:2] == ["confirmed", "proposed"]
