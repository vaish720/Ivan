# Sales voice assistant

A voice assistant for sales reps that works across Outlook and Teams. It is being built in phases, and **Phase 0** is a text chat that manages the Rep's calendar. Changes always wait for the Rep to confirm them.

- Plan: [docs/ROADMAP.md](docs/ROADMAP.md)
- Terms: [GLOSSARY.md](GLOSSARY.md)
- Decisions: [docs/adr/](docs/adr/)

## Run it

You need [uv](https://docs.astral.sh/uv/). It installs Python 3.11 for the project.

```sh
cp .env.example .env      # then add GROQ_API_KEY (free at console.groq.com)
uv sync
uv run app                # http://localhost:8000
```

The app starts on a **sample calendar** with a made-up week, so no Microsoft account is needed. To use a real Outlook calendar:
1. Register an Entra app.
2. Set `CALENDAR_BACKEND=graph`, `ENTRA_CLIENT_ID` and `ENTRA_TENANT_ID` in `.env`.
3. Run the app. A browser window opens for you to sign in.

## Things to try

- "What's on tomorrow?"
- "Find 45 minutes with Priya next week"
- "Book 30 min with Sam from Acme on Wednesday at 4"
- "Move my 3 pm tomorrow to 5" (the sample week has two Meetings at 3 pm, so the assistant asks which one)
- "Decline the team retro and say I'm with a client"

Every change appears as a card with **Confirm** and **Cancel** buttons. You can also type "yes" or "no". The **Activity Log** page lists everything the assistant read or did.

## Test

```sh
uv run pytest             # fast tests, no LLM, no network
uv run eval               # the 30 test commands against the real LLM (needs GROQ_API_KEY)
uv run eval --only 6      # a single command
```

Phase 0 is finished when `uv run eval` scores at least 90%.

## Layout

```
frontend/                what runs in the browser
  chat.html              the chat page (http://localhost:8000)
  activity.html          the Activity Log page
backend/                 the Python app
  app/
    main.py              starting point for `uv run app`
    web/routes.py        the HTTP API the pages call
    core/                coordinator (agent), confirmation gate, Activity Log, session
    providers/           LLM clients (Groq, Ollama) behind one interface
    skills/calendar/     calendar tools, Slot finding, fake calendar, Outlook (Graph) calendar
    graph/               Microsoft sign-in (MSAL)
    evals/               the scorer behind `uv run eval`
  evals/commands.yaml    the 30 test commands
  tests/                 pytest
```

Run every command from the repo root.
