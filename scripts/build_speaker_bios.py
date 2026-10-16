#!/usr/bin/env python3
"""Retrieve the official speaker directory and create a packaged biography snapshot."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

SOURCE_URL = "https://awscommunitydayaus.com/speakers/index.html"
repo = Path(__file__).resolve().parents[1]
request = Request(SOURCE_URL, headers={"User-Agent": "aws-community-day-visitor-guide/1.0"})
with urlopen(request, timeout=30) as response:
    parsed = urlparse(str(response.url))
    if parsed.hostname != "awscommunitydayaus.com" or parsed.path != "/speakers/index.html":
        raise SystemExit("Official speaker directory redirected outside the approved source")
    soup = BeautifulSoup(response.read().decode("utf-8"), "html.parser")

speakers = []
for card in soup.select(".speaker-card"):
    name = card.select_one("h3")
    title = card.select_one(".speaker-title")
    bio = card.select_one(".speaker-bio")
    if name and title and bio:
        speakers.append(
            {
                "name": name.get_text(" ", strip=True),
                "title": title.get_text(" ", strip=True),
                "bio": " ".join(bio.get_text(" ", strip=True).split()),
            }
        )
if len(speakers) < 10:
    raise SystemExit("Official speaker directory did not contain expected speaker entries")

output = {
    "source": SOURCE_URL,
    "retrievedAt": datetime.now(timezone.utc).isoformat(),
    "speakers": speakers,
}
path = repo / "data" / "speaker_bios.json"
path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {len(speakers)} speaker bios to {path}")
