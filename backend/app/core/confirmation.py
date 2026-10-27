"""The confirmation gate: changes wait as a Proposed Action until the Rep confirms.

At most one Proposed Action waits at a time. It expires after five minutes, and
proposing a new one discards the old one.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import count
from typing import Any, Literal

from app.core.activity_log import ActivityLog

ActionKind = Literal["create", "reschedule", "cancel", "decline"]
Clock = Callable[[], datetime]
TTL = timedelta(minutes=5)


class NothingPending(Exception):
    pass


@dataclass
class ProposedAction:
    kind: ActionKind
    tool: str
    args: dict
    headline: str  # e.g. "Create Teams meeting"
    details: dict[str, str]  # label -> value, shown on the card
    facts: dict[str, Any]  # structured description, used by evals
    execute: Callable[[], str]  # performs the change, returns a one-line result
    warnings: list[str] = field(default_factory=list)
    id: str = ""
    created_at: datetime | None = None

    def card(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "headline": self.headline,
            "details": self.details,
            "warnings": self.warnings,
        }


class ConfirmationGate:
    def __init__(self, log: ActivityLog, clock: Clock, ttl: timedelta = TTL):
        self._log = log
        self._clock = clock
        self._ttl = ttl
        self._ids = count(1)
        self._pending: ProposedAction | None = None

    def propose(self, action: ProposedAction) -> ProposedAction:
        self.discard("replaced by a new proposal")
        action.id = f"pa-{next(self._ids)}"
        action.created_at = self._clock()
        self._pending = action
        self._log.record(action.tool, action.args, "proposed", action.headline, action.id)
        return action

    def pending(self) -> ProposedAction | None:
        action = self._pending
        if action is not None and self._clock() - action.created_at > self._ttl:
            self._log.record(action.tool, action.args, "expired", "not confirmed within 5 minutes", action.id)
            self._pending = None
        return self._pending

    def confirm(self) -> str:
        action = self.pending()
        if action is None:
            raise NothingPending()
        self._pending = None
        try:
            result = action.execute()
        except Exception as exc:
            self._log.record(action.tool, action.args, "failed", str(exc), action.id)
            raise
        self._log.record(action.tool, action.args, "confirmed", result, action.id)
        return result

    def cancel(self) -> ProposedAction:
        action = self.pending()
        if action is None:
            raise NothingPending()
        self._pending = None
        self._log.record(action.tool, action.args, "cancelled", "cancelled by the Rep", action.id)
        return action

    def discard(self, reason: str) -> None:
        action = self.pending()
        if action is not None:
            self._pending = None
            self._log.record(action.tool, action.args, "cancelled", reason, action.id)
