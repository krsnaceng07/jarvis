"""Tests for Google Calendar event lookup and Export bundle packing."""

import datetime
from pathlib import Path
import tempfile
import zipfile

from extensions.google_meet.src.calendar import (
    GoogleCalendarEventDate,
    GoogleMeetCalendarEvent,
    build_google_meet_calendar_day_window,
    choose_best_meet_calendar_event,
    extract_google_meet_uri_from_calendar_event,
)
from extensions.google_meet.src.cli_export import (
    write_export_bundle_to_disk,
)


def test_build_calendar_day_window():
    dt = datetime.datetime(2026, 9, 9, 12, 0, 0, tzinfo=datetime.timezone.utc)
    start_str, end_str = build_google_meet_calendar_day_window(dt)
    assert start_str.startswith("2026-09-09T00:00:00")
    assert end_str.startswith("2026-09-09T23:59:59")


def test_extract_google_meet_uri():
    # 1. From hangout_link
    ev1 = GoogleMeetCalendarEvent(
        hangout_link="https://meet.google.com/abc-defg-hij",
    )
    assert (
        extract_google_meet_uri_from_calendar_event(ev1) == "https://meet.google.com/abc-defg-hij"
    )

    # 2. From conferenceData entry points
    ev2 = GoogleMeetCalendarEvent(
        conference_data={
            "entryPoints": [
                {"entryPointType": "video", "uri": "https://meet.google.com/klm-nopq-rst"}
            ]
        }
    )
    assert (
        extract_google_meet_uri_from_calendar_event(ev2) == "https://meet.google.com/klm-nopq-rst"
    )

    # 3. From location description
    ev3 = GoogleMeetCalendarEvent(
        location="Meeting room https://meet.google.com/uvw-xyza-bcd online",
    )
    assert (
        extract_google_meet_uri_from_calendar_event(ev3) == "https://meet.google.com/uvw-xyza-bcd"
    )


def test_choose_best_calendar_event():
    now = datetime.datetime(2026, 9, 9, 10, 0, 0, tzinfo=datetime.timezone.utc)
    ev_past = GoogleMeetCalendarEvent(
        id="1",
        hangout_link="https://meet.google.com/aaa-bbbb-ccc",
        start=GoogleCalendarEventDate(date_time="2026-09-09T08:00:00Z"),
    )
    ev_close = GoogleMeetCalendarEvent(
        id="2",
        hangout_link="https://meet.google.com/ddd-eeee-fff",
        start=GoogleCalendarEventDate(date_time="2026-09-09T10:15:00Z"),
    )
    ev_future = GoogleMeetCalendarEvent(
        id="3",
        hangout_link="https://meet.google.com/ggg-hhhh-iii",
        start=GoogleCalendarEventDate(date_time="2026-09-09T16:00:00Z"),
    )

    best = choose_best_meet_calendar_event([ev_past, ev_close, ev_future], now)
    assert best is not None
    assert best.id == "2"


def test_export_bundle_writing_dir_and_zip():
    bundle_files = {
        "manifest.json": '{"conferenceRecord": "conf-123"}',
        "summary.md": "# Summary\nMeeting export summary.",
        "attendance.csv": "Participant,Email\nAlice,alice@example.com",
        "attendance.json": '{"total": 1}',
        "transcript.md": "# Transcript\nAlice: Hello world.",
        "artifacts.json": '{"space": "spaces/test"}',
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        dir_path = Path(temp_dir) / "export_folder"
        written_dir = write_export_bundle_to_disk(bundle_files, dir_path, as_zip=False)
        assert written_dir.is_dir()
        assert (written_dir / "manifest.json").exists()
        assert (written_dir / "summary.md").exists()
        assert (written_dir / "attendance.csv").exists()

        zip_target = Path(temp_dir) / "export.zip"
        written_zip = write_export_bundle_to_disk(bundle_files, zip_target, as_zip=True)
        assert written_zip.is_file()
        assert zipfile.is_zipfile(written_zip)
        with zipfile.ZipFile(written_zip, "r") as zf:
            namelist = zf.namelist()
            assert "manifest.json" in namelist
            assert "summary.md" in namelist
            assert "attendance.csv" in namelist
            assert "transcript.md" in namelist
