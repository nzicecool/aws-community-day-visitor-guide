from schedule import build_snapshot, parse_schedule_html


SCHEDULE_HTML = """
<div class="schedule-card" id="session-a" data-track="Cloud Corner" data-type="session">
  <div class="schedule-time-block"><span class="time">10:30 - 11:00</span><span class="room">Cloud Corner (Boulevard 2)</span></div>
  <div class="schedule-content">
    <h3>Operating the Agent</h3>
    <div class="schedule-speaker"><span class="speaker-name">Sagar Utekar</span><span class="speaker-company">SRE at Example</span></div>
    <button class="read-more-btn" data-full="A full official description.">Read more</button>
  </div>
</div>
<div class="schedule-card" id="break-a" data-track="all" data-type="break">
  <div class="schedule-time-block"><span class="time">12:00 - 13:00</span><span class="room">Builder’s Mainstage (Auditorium)</span></div>
  <div class="schedule-content"><h3>Lunch &amp; Networking</h3></div>
</div>
"""


def test_parse_schedule_html_extracts_session_details():
    sessions = parse_schedule_html(SCHEDULE_HTML + SCHEDULE_HTML * 5)
    first = sessions[0]
    assert first["id"] == "session-a"
    assert first["track"] == "Cloud Corner"
    assert first["time"] == "10:30 - 11:00"
    assert first["room"] == "Cloud Corner (Boulevard 2)"
    assert first["speakers"] == [{"name": "Sagar Utekar", "eventHeadline": "SRE at Example"}]
    assert first["description"] == "A full official description."


def test_build_snapshot_sets_event_metadata():
    snapshot = build_snapshot(SCHEDULE_HTML + SCHEDULE_HTML * 5, retrieved_at="2026-10-16T00:00:00Z")
    assert snapshot["eventDate"] == "2026-10-16"
    assert snapshot["timezone"] == "Australia/Brisbane"
    assert snapshot["source"].endswith("/schedule/index.html")
    assert len(snapshot["sessions"]) == 12
