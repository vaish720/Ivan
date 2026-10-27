"""Scores the coordinator on evals/commands.yaml against the fake calendar and a real LLM.

Usage: uv run eval [--only N] [--provider groq|ollama]
"""

import argparse
import json
import sys
import time as clock_time
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from tzlocal import get_localzone_name

from app.config import get_settings
from app.core.activity_log import ActivityLog
from app.main import build_llm, build_session
from app.skills.calendar.fake import FakeCalendar, working_days_from
from app.skills.calendar.model import Contact

COMMANDS = Path("evals/commands.yaml")
RESULTS = Path("evals/results")
PASS_MARK = 0.9


@dataclass
class Outcome:
    passed: bool
    got: str
    why: str
    reply: str


def eval_now(tz: ZoneInfo) -> datetime:
    today = datetime.now(tz).date()
    monday = today - timedelta(days=today.weekday())
    return datetime.combine(monday, time(8, 30), tz)


def resolve_at(value: str, days, tz: ZoneInfo) -> datetime:
    day, hhmm = value.split()
    return datetime.combine(days[int(day[1:])], time.fromisoformat(hhmm), tz)


def judge(case: dict, reply, days, tz) -> Outcome:
    expected = case["expect"] if isinstance(case["expect"], list) else [case["expect"]]
    facts = reply.proposal and reply.proposal_facts
    if facts:
        got = facts["kind"]
    elif "?" in reply.text:
        got = "clarify"
    else:
        got = "answer"
    if got == "clarify" and "answer" in expected and "clarify" not in expected:
        got = "answer"  # a reading answer that ends with "anything else?" is still an answer
    if got not in expected:
        return Outcome(False, got, f"expected {'/'.join(expected)}", reply.text)

    problems = []
    if got == "answer":
        text = reply.text.lower()
        problems += [f"missing '{m}'" for m in case.get("mentions", []) if m.lower() not in text]
        if case.get("mentions_any") and not any(m.lower() in text for m in case["mentions_any"]):
            problems.append(f"none of {case['mentions_any']}")
    if facts:
        if "meeting" in case and case["meeting"].lower() not in facts["title"].lower():
            problems.append(f"acted on '{facts['title']}'")
        if "at" in case and facts["start"] != resolve_at(case["at"], days, tz):
            problems.append(f"start {facts['start']:%a %H:%M}")
        if "minutes" in case and (facts["end"] - facts["start"]) != timedelta(minutes=case["minutes"]):
            problems.append(f"length {(facts['end'] - facts['start']).seconds // 60} min")
        if "attendees" in case and facts.get("attendees") != sorted(a.lower() for a in case["attendees"]):
            problems.append(f"attendees {facts.get('attendees')}")
        if "teams" in case and facts.get("is_teams") != case["teams"]:
            problems.append(f"teams={facts.get('is_teams')}")
        if "note_contains" in case and case["note_contains"].lower() not in (facts.get("note") or "").lower():
            problems.append(f"note '{facts.get('note')}'")
    return Outcome(not problems, got, "; ".join(problems), reply.text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", type=int, help="run a single case by number (1-based)")
    parser.add_argument("--provider", choices=["groq", "ollama"])
    args = parser.parse_args()

    settings = get_settings()
    if args.provider:
        settings = settings.model_copy(update={"llm_provider": args.provider})
    tz = ZoneInfo(get_localzone_name())
    now = eval_now(tz)
    days = working_days_from(now.date(), 7)
    rep = Contact(settings.rep_name, settings.rep_email.lower(), "colleague", "Contoso")
    cases = yaml.safe_load(COMMANDS.read_text(encoding="utf-8"))
    numbered = list(enumerate(cases, 1))
    if args.only:
        numbered = [numbered[args.only - 1]]

    results = []
    print(f"Eval: {len(numbered)} commands, LLM provider {settings.llm_provider}, clock {now:%a %d %b %H:%M}\n")
    for n, case in numbered:
        log = ActivityLog()
        llm = build_llm(settings, log)
        session = build_session(settings, FakeCalendar(rep, str(tz), now=now), log, clock=lambda: now, llm=llm)
        started = clock_time.monotonic()
        reply = session.handle(case["say"])
        pending = session.gate.pending()
        reply.proposal_facts = pending.facts if pending else None
        outcome = judge(case, reply, days, tz)
        seconds = clock_time.monotonic() - started
        mark = "PASS" if outcome.passed else "FAIL"
        print(f"{mark} {n:>2}. {case['say']}  [{outcome.got}, {seconds:.1f}s]")
        if not outcome.passed:
            print(f"        {outcome.why}\n        reply: {outcome.reply[:160]}")
        results.append({"n": n, "say": case["say"], "passed": outcome.passed, "got": outcome.got,
                        "why": outcome.why, "reply": outcome.reply, "seconds": round(seconds, 1),
                        "llm": getattr(llm, "name", settings.llm_provider)})

    score = sum(r["passed"] for r in results) / len(results)
    print(f"\nScore: {sum(r['passed'] for r in results)}/{len(results)} = {score:.0%} (exit check: {PASS_MARK:.0%})")
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}-{settings.llm_provider}.json"
    out.write_text(json.dumps({"score": score, "results": results}, indent=2), encoding="utf-8")
    print(f"Saved {out}")
    sys.exit(0 if score >= PASS_MARK or args.only else 1)
