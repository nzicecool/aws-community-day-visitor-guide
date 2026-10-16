"""Read official speaker biographies and verified public LinkedIn profile details."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parent / "data"
_PROFILES_FILE = _DATA_DIR / "speaker_profiles.json"
_BIOS_FILE = _DATA_DIR / "speaker_bios.json"


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


class SpeakerDirectory:
    def __init__(self) -> None:
        self._profiles = self._load_list(_PROFILES_FILE, "profiles")
        self._bios = self._load_list(_BIOS_FILE, "speakers")
        self._profiles_by_name = {
            _normalise(str(profile.get("name", ""))): profile for profile in self._profiles
        }

    @staticmethod
    def _load_list(path: Path, key: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        values = data.get(key, []) if isinstance(data, dict) else []
        return [value for value in values if isinstance(value, dict)]

    @property
    def count(self) -> int:
        return len(self._profiles)

    def context_for_model(self, question: str) -> str:
        """Return official biographical material only for explicitly named speakers."""
        question_normalised = _normalise(question)
        matched = [
            bio for bio in self._bios
            if _normalise(str(bio.get("name", ""))) in question_normalised
        ]
        directory = "; ".join(
            f"{bio.get('name', '')} — {bio.get('title', '')}" for bio in self._bios
        )
        if not matched:
            return (
                "OFFICIAL SPEAKER DIRECTORY\n"
                "Published speakers and titles: " + directory + "\n"
                "No speaker biography is included unless the visitor names the speaker explicitly. "
                "No unverified LinkedIn profile should be claimed."
            )

        entries = []
        for bio in matched:
            name = str(bio.get("name", ""))
            profile = self._profiles_by_name.get(_normalise(name))
            entry = [
                f"Name: {name}",
                f"Official event title: {bio.get('title', '')}",
                f"Official event biography: {bio.get('bio', '')}",
            ]
            if profile:
                entry.extend(
                    [
                        f"Verified public LinkedIn headline: {profile.get('headline', '')}",
                        f"Verified LinkedIn profile: {profile.get('profileUrl', '')}",
                    ]
                )
            else:
                entry.append("Verified public LinkedIn profile: unavailable; do not guess one.")
            entries.append(" | ".join(entry))
        return "OFFICIAL SPEAKER DIRECTORY\n- " + "\n- ".join(entries)
