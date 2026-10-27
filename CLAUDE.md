# Sales voice assistant

Voice assistant for sales reps on Outlook + Teams.
Plan: `docs/ROADMAP.md`. Background research is kept outside the repo, in `../sales-assistant-notes/`.

## Commands

- `uv run pytest`: fast tests (no LLM, no network). Run after every change.
- `uv run eval`: scores the 30 commands in `backend/evals/commands.yaml` against the real LLM and the fake calendar.
- `uv run app`: serves the chat on http://localhost:8000.

## Conventions

- Use the vocabulary in `GLOSSARY.md` in code, tests and replies: Rep, Meeting, Block, Reschedule, Cancel, Decline, Proposed Action and the rest.
- Tools that change something only build a Proposed Action. The calendar is touched only in `ConfirmationGate.confirm()`.
- Layout: `frontend/` holds the browser pages (HTML/CSS/JS). `backend/app/` holds the Python package `app`, with tests in `backend/tests/`. Settings live in `backend/.env` (git-ignored; template in `backend/.env.example`). Run commands from the repo root.
- New skills go in `backend/app/skills/<name>/` and talk to Microsoft 365 through a Protocol port with a fake implementation for tests.

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five roles: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
