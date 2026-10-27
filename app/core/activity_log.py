"""The Activity Log: everything the assistant read or did on the Rep's behalf.

Append-only. Stores tool arguments and a short result summary, never message bodies.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

Status = Literal["ok", "failed", "proposed", "confirmed", "cancelled", "expired", "notice"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    tool TEXT NOT NULL,
    args TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    proposal_id TEXT
)
"""


@dataclass(frozen=True)
class Entry:
    id: int
    at: str
    tool: str
    args: dict
    status: str
    summary: str
    proposal_id: str | None


class ActivityLog:
    def __init__(self, path: Path | str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute(SCHEMA)
        self._db.commit()

    def record(
        self, tool: str, args: dict, status: Status, summary: str = "", proposal_id: str | None = None
    ) -> int:
        cur = self._db.execute(
            "INSERT INTO activity (at, tool, args, status, summary, proposal_id) VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                tool,
                json.dumps(args, default=str),
                status,
                summary,
                proposal_id,
            ),
        )
        self._db.commit()
        return cur.lastrowid

    def recent(self, limit: int = 200) -> list[Entry]:
        rows = self._db.execute(
            "SELECT id, at, tool, args, status, summary, proposal_id FROM activity ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [Entry(r[0], r[1], r[2], json.loads(r[3]), r[4], r[5], r[6]) for r in rows]
