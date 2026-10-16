"""Official schedule retrieval, parsing, and bounded model context."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

SCHEDULE_SOURCE_URL = "https://awscommunitydayaus.com/schedule/index.html"
_EXPECTED_HOST = "awscommunitydayaus.com"
_EXPECTED_PATH = "/schedule/index.html"
_EVENT_DATE = "2026-10-16"
_TIMEZONE = "Australia/Brisbane"
_DATA_FILE = Path(__file__).parent / "data" / "schedule.json"


class ScheduleUnavailable(RuntimeError):
    """Raised if no validated official schedule is available."""


def parse_schedule_html(html: str) -> list[dict[str, Any]]:
    """Parse only the published schedule-card elements from the official page."""
    soup = BeautifulSoup(html, "html.parser")
    sessions: list[dict[str, Any]] = []
    for card in soup.select(".schedule-card"):
        title = card.select_one(".schedule-content h3")
        time_block = card.select_one(".schedule-time-block .time")
        room = card.select_one(".schedule-time-block .room")
        if not title or not time_block or not room:
            continue
        speakers = []
        for entry in card.select(".schedule-speaker"):
            name = entry.select_one(".speaker-name")
            company = entry.select_one(".speaker-company")
            if name:
                speakers.append(
                    {
                        "name": name.get_text(" ", strip=True),
                        "eventHeadline": company.get_text(" ", strip=True) if company else "",
                    }
                )
        details = card.select_one(".read-more-btn")
        description = details.get("data-full", "") if details else ""
        if not description:
            description_node = card.select_one(".schedule-description")
            description = description_node.get_text(" ", strip=True) if description_node else ""
        sessions.append(
            {
                "id": card.get("id", ""),
                "type": card.get("data-type", "session"),
                "track": card.get("data-track", "") if card.get("data-track") != "all" else "",
                "time": time_block.get_text(" ", strip=True),
                "room": room.get_text(" ", strip=True),
                "title": title.get_text(" ", strip=True),
                "speakers": speakers,
                "description": " ".join(description.split()),
            }
        )
    if len(sessions) < 10:
        raise ScheduleUnavailable("Official schedule did not contain expected session entries")
    return sessions


def build_snapshot(html: str, retrieved_at: str | None = None) -> dict[str, Any]:
    return {
        "source": SCHEDULE_SOURCE_URL,
        "eventDate": _EVENT_DATE,
        "timezone": _TIMEZONE,
        "retrievedAt": retrieved_at or datetime.now(ZoneInfo("UTC")).isoformat(),
        "sessions": parse_schedule_html(html),
    }


class ScheduleCatalog:
    """Maintains an in-memory official schedule with snapshot fallback."""

    def __init__(self) -> None:
        self._snapshot = self._load_snapshot()
        self._schedule = self._snapshot
        self._last_refresh = 0.0

    @staticmethod
    def _refresh_seconds() -> int:
        try:
            return min(3_600, max(300, int(os.getenv("SCHEDULE_REFRESH_SECONDS", "900"))))
        except ValueError:
            return 900

    @staticmethod
    def _load_snapshot() -> dict[str, Any]:
        try:
            data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ScheduleUnavailable("Packaged schedule snapshot is unavailable") from exc
        if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
            raise ScheduleUnavailable("Packaged schedule snapshot is invalid")
        return data

    def refresh(self) -> None:
        try:
            response = httpx.get(
                SCHEDULE_SOURCE_URL,
                headers={"User-Agent": "aws-community-day-visitor-guide/1.0"},
                follow_redirects=False,
                timeout=20.0,
            )
            if response.status_code != 200:
                raise ScheduleUnavailable(f"Official schedule returned HTTP {response.status_code}")
            parsed = urlparse(str(response.url))
            if parsed.hostname != _EXPECTED_HOST or parsed.path != _EXPECTED_PATH:
                raise ScheduleUnavailable("Official schedule request resolved to an unapproved URL")
            self._schedule = build_snapshot(response.text)
        except (httpx.HTTPError, ScheduleUnavailable):
            self._schedule = self._snapshot
        finally:
            self._last_refresh = time.monotonic()

    def current(self) -> dict[str, Any]:
        if time.monotonic() - self._last_refresh >= self._refresh_seconds():
            self.refresh()
        return self._schedule

    @staticmethod
    def context_for_model(schedule: dict[str, Any], question: str) -> str:
        """Provide every item concisely, with full details only for relevant sessions."""
        now = datetime.now(ZoneInfo(_TIMEZONE)).strftime("%Y-%m-%d %H:%M %Z")
        ignored_terms = {
            "about", "after", "also", "and", "are", "at", "can", "day", "find", "for",
            "from", "give", "happening", "help", "how", "is", "me", "my", "on", "or",
            "tell", "the", "there", "this", "to", "what", "when", "where", "which", "who",
            "with", "would", "you",
        }
        terms = {
            term for term in re.findall(r"[a-z0-9]{3,}", question.lower())
            if term not in ignored_terms
        }
        requested_times = set(re.findall(r"\b\d{1,2}:\d{2}\b", question))
        concise_rows: list[str] = []
        ranked: list[tuple[int, int, dict[str, Any]]] = []
        for index, session in enumerate(schedule["sessions"]):
            speaker_names = "; ".join(
                item["name"] for item in session.get("speakers", [])
            ) or "No speaker published"
            concise_rows.append(
                f"{session['time']} | {session['title']} | {session['room']} | "
                f"{session.get('track') or 'Event programme'} | Speakers: {speaker_names}"
            )
            searchable = " ".join(
                [
                    session.get("title", ""),
                    session.get("room", ""),
                    session.get("track", ""),
                    session.get("description", ""),
                    speaker_names,
                ]
            ).lower()
            score = sum(searchable.count(term) for term in terms)
            score += 20 * sum(time_text in session.get("time", "") for time_text in requested_times)
            if score:
                ranked.append((score, -index, session))

        detailed_rows: list[str] = []
        for _, _, session in sorted(ranked, reverse=True)[:8]:
            speaker_details = "; ".join(
                f"{item['name']} ({item['eventHeadline']})".strip()
                for item in session.get("speakers", [])
            ) or "No speaker published"
            detailed_rows.append(
                " | ".join(
                    [
                        f"Title: {session['title']}",
                        f"Time: {session['time']}",
                        f"Room: {session['room']}",
                        f"Track: {session.get('track') or 'Event programme'}",
                        f"Type: {session.get('type', 'session')}",
                        f"Speakers: {speaker_details}",
                        f"Description: {session.get('description', '')[:350] or 'No description published'}",
                    ]
                )
            )
        return (
            "OFFICIAL SCHEDULE\n"
            f"Event date: {schedule['eventDate']} ({schedule['timezone']}).\n"
            f"Current Brisbane time: {now}.\n"
            "Programme at a glance:\n- " + "\n- ".join(concise_rows)
            + ("\nRelevant detailed entries:\n- " + "\n- ".join(detailed_rows) if detailed_rows else "")
        )
