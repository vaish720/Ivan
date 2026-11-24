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

    page = client.get("/").text
    assert "Sales Assistant" in page and '<script src="/static/voice.js">' in page
    assert "Activity Log" in client.get("/activity").text
    voice = client.get("/static/voice.js")
    assert voice.status_code == 200 and "const Voice" in voice.text

    reply = client.post("/api/chat", json={"message": "book Sam wed 4"}).json()
    assert reply["proposal"]["headline"] == "Create Teams meeting"

    done = client.post("/api/proposal/confirm").json()
    assert done["text"].startswith("Done.") and done["proposal"] is None

    statuses = [e["status"] for e in client.get("/api/activity").json()]
    assert statuses[:2] == ["confirmed", "proposed"]
