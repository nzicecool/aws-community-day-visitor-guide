# AWS Community Day Australia 2026 Visitor Guide

A source-constrained chat agent for visitors to **AWS Community Day Australia 2026** in Brisbane on **16 October 2026**. It helps attendees find talks, rooms, times, concurrent sessions, and published speaker information.

## What it answers

- Session times, rooms, tracks, descriptions, and speaker names.
- What is on at a given time, including overlapping sessions.
- Where a named session is taking place.
- Brief speaker information from the official speaker directory.
- A public LinkedIn headline and profile URL only where the match is exact-name plus supporting role/headline evidence.

## Source and safety boundaries

- **Programme authority:** [official AWS Community Day Australia 2026 schedule](https://awscommunitydayaus.com/schedule/index.html).
- **Official biographies:** [official speaker directory](https://awscommunitydayaus.com/speakers/index.html).
- **LinkedIn:** the repository stores only high-confidence public profile matches. Ambiguous or unavailable results are explicitly marked unavailable; the agent never guesses a LinkedIn identity.
- The runtime refreshes the approved official schedule at a configurable interval and falls back to `data/schedule.json` if the live source cannot be retrieved safely.
- The agent does not invent venue logistics, room changes, capacity, ticketing facts, transport information, or schedule changes.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export LLM_PROVIDER_URL='https://your-managed-gemini-egress'
export LLM_PROVIDER_KEY='your-key'
export LLM_PROVIDER_PROTOCOL='gemini'
export LLM_PROVIDER_AUTH_STYLE='api-key'
export LLM_MODEL='gemini-3-flash-preview'
python main.py
```

Then send a request to `POST /chat`:

```json
{
  "message": "Where is the WSO2 Agent Manager session?",
  "session_id": "visitor-123"
}
```

## Refreshing curated data

```bash
PYTHONPATH=. .venv/bin/python scripts/build_schedule_snapshot.py
PYTHONPATH=. .venv/bin/python scripts/build_speaker_bios.py
manus-node scripts/enrich_speakers.mjs
```

The LinkedIn enrichment script uses a conservative exact-name-and-context matching rule. It writes no credentials and does not publish unresolved results as profile matches.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
PYTHONPATH=. .venv/bin/pytest -q
```

## Agent Manager / OpenChoreo deployment

See [`deployment/README.md`](deployment/README.md). The deployment uses Agent Manager's managed Gemini binding. No API key is committed to this repository.
