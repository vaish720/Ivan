from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.core.activity_log import ActivityLog
from app.core.session import Session

PAGES = Path(__file__).parent / "pages"


class ChatIn(BaseModel):
    message: str


def create_app(session: Session, log: ActivityLog, backend: str) -> FastAPI:
    app = FastAPI(title="Sales assistant", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def chat_page():
        return (PAGES / "chat.html").read_text(encoding="utf-8")

    @app.get("/activity", response_class=HTMLResponse)
    def activity_page():
        return (PAGES / "activity.html").read_text(encoding="utf-8")

    @app.get("/api/status")
    def status():
        return {"calendar": backend, "notice": getattr(session._llm, "notice", None)}

    @app.post("/api/chat")
    async def chat(body: ChatIn):
        return asdict(await run_in_threadpool(session.handle, body.message))

    @app.post("/api/proposal/confirm")
    async def confirm():
        return asdict(await run_in_threadpool(session.confirm))

    @app.post("/api/proposal/cancel")
    def cancel():
        return asdict(session.cancel())

    @app.post("/api/new-chat")
    def new_chat():
        session.new_chat()
        return {"ok": True}

    @app.get("/api/activity")
    def activity(limit: int = 200):
        return [asdict(e) for e in log.recent(limit)]

    return app
