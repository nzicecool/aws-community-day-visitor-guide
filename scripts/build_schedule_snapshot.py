#!/usr/bin/env python3
"""Retrieve the official programme and create the packaged schedule snapshot."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from schedule import SCHEDULE_SOURCE_URL, build_snapshot

repo = Path(__file__).resolve().parents[1]
request = Request(SCHEDULE_SOURCE_URL, headers={"User-Agent": "aws-community-day-visitor-guide/1.0"})
with urlopen(request, timeout=30) as response:
    final_url = str(response.url)
    parsed = urlparse(final_url)
    if parsed.hostname != "awscommunitydayaus.com" or parsed.path != "/schedule/index.html":
        raise SystemExit("Official schedule URL redirected outside the approved source")
    snapshot = build_snapshot(
        response.read().decode("utf-8"),
        retrieved_at=datetime.now(timezone.utc).isoformat(),
    )

output = repo / "data" / "schedule.json"
output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {len(snapshot['sessions'])} schedule entries to {output}")
