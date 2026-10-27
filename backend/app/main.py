"""Wires the app together and serves it on localhost:8000."""

from collections.abc import Callable
from datetime import datetime, timezone

import uvicorn
from tzlocal import get_localzone_name

from app.config import Settings, get_settings
from app.core.activity_log import ActivityLog
from app.core.agent import Agent
from app.core.confirmation import ConfirmationGate
from app.core.session import Session
from app.providers.llm import GROQ_BASE_URL, FallbackLLM, OpenAICompatibleLLM, Patient
from app.skills.calendar.model import Contact
from app.skills.calendar.port import CalendarPort
from app.skills.calendar.skill import TOOL_SPECS, CalendarSkill


def build_calendar(settings: Settings) -> CalendarPort:
    if settings.calendar_backend == "graph":
        from app.graph.auth import GraphAuth
        from app.skills.calendar.graph import GraphCalendar

        auth = GraphAuth(settings.entra_client_id, settings.entra_tenant_id, settings.data_dir / "msal_cache.bin")
        auth.token()  # sign in now, before the server starts
        return GraphCalendar(auth)
    from app.skills.calendar.fake import FakeCalendar

    domain_company = settings.rep_email.split("@")[-1].split(".")[0].title()
    rep = Contact(settings.rep_name, settings.rep_email.lower(), "colleague", domain_company)
    return FakeCalendar(rep, get_localzone_name())


def build_llm(settings: Settings, log: ActivityLog, fallback: bool = True):
    ollama = OpenAICompatibleLLM("ollama", settings.ollama_base_url, settings.ollama_model)
    if settings.llm_provider == "ollama":
        return ollama
    groq = Patient(OpenAICompatibleLLM("groq", GROQ_BASE_URL, settings.groq_model, settings.groq_api_key))
    if not fallback:
        return groq
    return FallbackLLM(groq, ollama, lambda reason: log.record("llm", {"switched_to": "ollama"}, "notice", reason))


def build_session(settings: Settings, calendar: CalendarPort, log: ActivityLog,
                  clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc), llm=None) -> Session:
    gate = ConfirmationGate(log, clock)
    skill = CalendarSkill(calendar, gate, log, clock)
    llm = llm or build_llm(settings, log)
    agent = Agent(llm, skill, TOOL_SPECS, calendar.rep().name, clock)
    return Session(agent, gate, skill, llm)


def run() -> None:
    from app.web.routes import create_app

    settings = get_settings()
    log = ActivityLog(settings.data_dir / "activity.db")
    calendar = build_calendar(settings)
    session = build_session(settings, calendar, log)
    print(f"Sales assistant: http://localhost:8000  (calendar: {settings.calendar_backend}, LLM: {settings.llm_provider})")
    uvicorn.run(create_app(session, log, settings.calendar_backend), host="127.0.0.1", port=8000, log_level="warning")
