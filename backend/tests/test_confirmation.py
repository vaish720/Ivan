from datetime import datetime, timedelta

import pytest

from app.core.activity_log import ActivityLog
from app.core.confirmation import ConfirmationGate, NothingPending, ProposedAction


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 26, 9, 0)

    def __call__(self):
        return self.now


def action(effects: list) -> ProposedAction:
    return ProposedAction(
        kind="cancel",
        tool="propose_cancel",
        args={"meeting_ref": "m1"},
        headline="Cancel meeting",
        details={},
        facts={},
        execute=lambda: effects.append("done") or "Cancelled",
    )


@pytest.fixture
def setup():
    log, clock = ActivityLog(), FakeClock()
    return ConfirmationGate(log, clock), log, clock


def statuses(log):
    return [e.status for e in reversed(log.recent())]


def test_nothing_happens_until_confirmed(setup):
    gate, log, _ = setup
    effects = []
    gate.propose(action(effects))
    assert effects == []
    assert gate.confirm() == "Cancelled"
    assert effects == ["done"]
    assert statuses(log) == ["proposed", "confirmed"]


def test_only_one_pending_and_new_proposal_discards_old(setup):
    gate, log, _ = setup
    first, second = [], []
    gate.propose(action(first))
    gate.propose(action(second))
    gate.confirm()
    assert first == [] and second == ["done"]
    assert statuses(log) == ["proposed", "cancelled", "proposed", "confirmed"]


def test_expires_after_five_minutes(setup):
    gate, log, clock = setup
    effects = []
    gate.propose(action(effects))
    clock.now += timedelta(minutes=5, seconds=1)
    with pytest.raises(NothingPending):
        gate.confirm()
    assert effects == []
    assert statuses(log)[-1] == "expired"


def test_cancel_is_logged_and_clears(setup):
    gate, log, _ = setup
    gate.propose(action([]))
    gate.cancel()
    assert gate.pending() is None
    assert statuses(log)[-1] == "cancelled"


def test_failed_execution_is_logged(setup):
    gate, log, _ = setup
    broken = action([])
    broken.execute = lambda: (_ for _ in ()).throw(RuntimeError("Graph said no"))
    gate.propose(broken)
    with pytest.raises(RuntimeError):
        gate.confirm()
    assert statuses(log)[-1] == "failed"
