import pytest
from fastapi import HTTPException

import main


def test_chat_returns_schedule_scoped_response(monkeypatch):
    snapshot = {
        "eventDate": "2026-10-16",
        "timezone": "Australia/Brisbane",
        "sessions": [],
    }
    monkeypatch.setattr(main.catalog, "current", lambda: snapshot)
    monkeypatch.setattr(main.catalog, "context_for_model", lambda _: "SCHEDULE")
    monkeypatch.setattr(main.speakers, "context_for_model", lambda _: "SPEAKERS")
    monkeypatch.setattr(main, "generate_response", lambda *_: ("Cloud Corner at 10:30.", 23, 11))

    response = main.chat(main.ChatRequest(message="Where is Operating the Agent?", session_id="s1"))

    assert response["response"] == "Cloud Corner at 10:30."
    assert response["sessionId"] == "s1"
    assert response["scheduleSource"].endswith("/schedule/index.html")


def test_generate_response_requires_managed_binding(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_URL", raising=False)
    monkeypatch.delenv("LLM_PROVIDER_KEY", raising=False)

    with pytest.raises(HTTPException) as exc:
        main.generate_response("Where is my talk?", "schedule", "speakers")

    assert exc.value.status_code == 503
