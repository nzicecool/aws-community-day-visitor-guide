import pytest
import httpx
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


def test_generate_response_retries_a_rate_limited_gemini_request(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code, body, headers=None):
            self.status_code = status_code
            self._body = body
            self.headers = headers or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                request = httpx.Request("POST", "https://example.test")
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError("request failed", request=request, response=response)

        def json(self):
            return self._body

    responses = iter(
        [
            FakeResponse(429, {}, {"Retry-After": "1"}),
            FakeResponse(
                200,
                {
                    "candidates": [{"content": {"parts": [{"text": "Cloud Corner at 10:30."}]}}],
                    "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 5},
                },
            ),
        ]
    )
    sleeps = []
    monkeypatch.setenv("LLM_PROVIDER_URL", "https://example.test")
    monkeypatch.setenv("LLM_PROVIDER_KEY", "test-key")
    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(main.time, "sleep", sleeps.append)

    answer, input_tokens, output_tokens = main.generate_response("What is on?", "schedule", "speakers")

    assert answer == "Cloud Corner at 10:30."
    assert (input_tokens, output_tokens) == (7, 5)
    assert sleeps == [1.0]
