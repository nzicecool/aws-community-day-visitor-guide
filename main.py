"""AWS Community Day Australia 2026 visitor guide agent."""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from pydantic import BaseModel, Field

from schedule import SCHEDULE_SOURCE_URL, ScheduleCatalog
from speaker_profiles import SpeakerDirectory

app = FastAPI(title="AWS Community Day Australia 2026 Visitor Guide", version="1.0.0")
MODEL = os.getenv("LLM_MODEL", "gemini-3-flash-preview")
TRACER_NAME = "aws-community-day-visitor-guide.gemini"

catalog = ScheduleCatalog()
speakers = SpeakerDirectory()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    session_id: str | None = Field(default=None, max_length=256)


def _redacted_messages(messages: list[dict[str, str]]) -> str:
    """Preserve message roles in telemetry without retaining visitor content."""
    return json.dumps(
        [{"role": item.get("role", "user"), "content": "[redacted]"} for item in messages],
        ensure_ascii=False,
    )


def _read_visible_gemini_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    candidate = candidates[0] if isinstance(candidates, list) and candidates else None
    content = candidate.get("content") if isinstance(candidate, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    text = "".join(
        str(part.get("text", ""))
        for part in parts or []
        if isinstance(part, dict) and part.get("text") and not part.get("thought", False)
    ).strip()
    if not text:
        raise ValueError("Gemini returned no visible response")
    return text


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def generate_response(question: str, schedule_context: str, speaker_context: str) -> tuple[str, int, int]:
    """Call the managed Gemini native endpoint with bounded event data only."""
    base_url = os.getenv("LLM_PROVIDER_URL", "").rstrip("/")
    api_key = os.getenv("LLM_PROVIDER_KEY", "")
    if not base_url or not api_key:
        raise HTTPException(
            status_code=503,
            detail="Agent Manager managed model binding is not available",
        )

    system_prompt = f"""You are the AWS Community Day Australia 2026 Visitor Guide.

Your job is to help attendees find programme items, choose between concurrent sessions, locate rooms, and learn brief speaker details.

Rules:
- Treat the supplied official schedule as the sole authority for titles, times, rooms, tracks, abstracts, speaker assignments, breaks, and event logistics.
- Treat the supplied official speaker directory as the authority for speaker biographies.
- Treat a supplied verified LinkedIn entry as the only authority for LinkedIn details. If no verified entry is supplied, say that a verified LinkedIn profile is unavailable and never infer a profile from the speaker's name.
- When a query asks what is happening "now", use the supplied Brisbane local time. If it is not 16 October 2026, explain that the published programme is for that date and answer only the schedule lookup portion.
- Call out schedule overlaps when relevant. Do not imply a visitor can attend two simultaneous sessions.
- Do not invent ticket, transport, accessibility, venue, capacity, room-change, or timetable-update information. Direct the visitor to the official schedule if the supplied data does not answer the question.
- Keep answers concise and practical. Include the session title, time, and room whenever giving a recommendation or location.
- Do not provide personalised professional, financial, legal, or medical advice.

Official schedule source: {SCHEDULE_SOURCE_URL}

{schedule_context}

{speaker_context}
"""
    endpoint = f"{base_url}/v1beta/models/{quote(MODEL, safe='._-')}:generateContent"
    request_payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": question}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 750},
    }

    tracer = trace.get_tracer(TRACER_NAME)
    with tracer.start_as_current_span(f"chat {MODEL}", kind=SpanKind.CLIENT) as span:
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.system", "gemini")
        span.set_attribute("gen_ai.provider.name", "gemini")
        span.set_attribute("gen_ai.request.model", MODEL)
        span.set_attribute("gen_ai.input.messages", _redacted_messages([{"role": "user", "content": question}]))
        span.set_attribute("event.schedule.source", SCHEDULE_SOURCE_URL)
        try:
            response: httpx.Response | None = None
            for attempt in range(4):
                response = httpx.post(
                    endpoint,
                    json=request_payload,
                    headers={"Content-Type": "application/json", "API-Key": api_key},
                    timeout=60.0,
                )
                if response.status_code != 429 or attempt == 3:
                    response.raise_for_status()
                    break
                try:
                    retry_after = float(response.headers.get("Retry-After", ""))
                except ValueError:
                    retry_after = float(attempt + 1)
                retry_after = min(8.0, max(1.0, retry_after))
                span.add_event(
                    "gen_ai.rate_limit_retry",
                    {"retry_count": attempt + 1, "retry_delay_seconds": retry_after},
                )
                time.sleep(retry_after)
            if response is None:
                raise ValueError("Gemini did not return a response")
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("Gemini returned an invalid response")
            answer = _read_visible_gemini_text(body)
        except httpx.HTTPStatusError as exc:
            is_rate_limited = exc.response.status_code == 429
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "Gemini rate limited" if is_rate_limited else "Gemini request failed"))
            span.set_attribute("error.type", type(exc).__name__)
            raise HTTPException(
                status_code=503 if is_rate_limited else 502,
                detail="Managed Gemini is temporarily rate-limited; please retry shortly."
                if is_rate_limited
                else "Managed Gemini request failed",
            ) from exc
        except (httpx.HTTPError, TypeError, ValueError, KeyError, IndexError) as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "Gemini request failed"))
            span.set_attribute("error.type", type(exc).__name__)
            raise HTTPException(status_code=502, detail="Managed Gemini request failed") from exc

        usage = body.get("usageMetadata") if isinstance(body.get("usageMetadata"), dict) else {}
        input_tokens = _nonnegative_int(usage.get("promptTokenCount"))
        output_tokens = _nonnegative_int(usage.get("candidatesTokenCount"))
        span.set_attribute("gen_ai.response.model", str(body.get("modelVersion") or MODEL))
        span.set_attribute("gen_ai.output.messages", _redacted_messages([{"role": "assistant", "content": answer}]))
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        span.set_status(Status(StatusCode.OK))
        return answer, input_tokens, output_tokens


@app.get("/health")
def health() -> dict[str, Any]:
    schedule = catalog.current()
    return {
        "status": "ok",
        "agent": "aws-community-day-visitor-guide",
        "eventDate": schedule["eventDate"],
        "timezone": schedule["timezone"],
        "scheduleEntries": len(schedule["sessions"]),
        "verifiedSpeakerProfiles": speakers.count,
        "scheduleSource": SCHEDULE_SOURCE_URL,
        "model": MODEL,
        "managedModelConfigured": bool(
            os.getenv("LLM_PROVIDER_URL") and os.getenv("LLM_PROVIDER_KEY")
        ),
    }


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    tracer = trace.get_tracer("aws-community-day-visitor-guide.agent")
    with tracer.start_as_current_span("invoke_agent", kind=SpanKind.INTERNAL) as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")
        span.set_attribute("gen_ai.agent.name", "aws-community-day-visitor-guide")
        span.set_attribute("gen_ai.request.model", MODEL)
        span.set_attribute("gen_ai.input.messages", _redacted_messages([{"role": "user", "content": request.message}]))
        span.set_attribute("event.schedule.source", SCHEDULE_SOURCE_URL)
        try:
            schedule = catalog.current()
            answer, input_tokens, output_tokens = generate_response(
                request.message,
                catalog.context_for_model(schedule),
                speakers.context_for_model(request.message),
            )
        except HTTPException as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc.detail)))
            raise

        span.set_attribute("gen_ai.output.messages", _redacted_messages([{"role": "assistant", "content": answer}]))
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        span.set_status(Status(StatusCode.OK))
        return {
            "response": answer,
            "sessionId": request.session_id,
            "model": MODEL,
            "scheduleSource": SCHEDULE_SOURCE_URL,
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
