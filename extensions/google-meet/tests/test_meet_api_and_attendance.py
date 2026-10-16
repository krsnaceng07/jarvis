"""Tests for Meet API parsing, attendance calculations, and export formatting."""

from extensions.google_meet.src.cli_export import (
    format_attendance_csv,
    format_attendance_markdown,
)


def test_attendance_csv_and_markdown_formatting():
    attendance_data = {
        "space": "spaces/abc-defg-hij",
        "conferenceRecord": "conferenceRecords/conf-123",
        "startTime": "2026-09-09T10:00:00Z",
        "endTime": "2026-09-09T11:00:00Z",
        "totalParticipants": 2,
        "participants": [
            {
                "displayName": "Alice Smith",
                "email": "alice@example.com",
                "role": "HOST",
                "earliestStartTime": "2026-09-09T10:00:05Z",
                "latestEndTime": "2026-09-09T11:00:00Z",
                "totalDurationSeconds": 3595,
                "joinedLate": False,
                "leftEarly": False,
                "sessionCount": 1,
            },
            {
                "displayName": "Bob Jones",
                "email": "bob@example.com",
                "role": "ATTENDEE",
                "earliestStartTime": "2026-09-09T10:15:00Z",
                "latestEndTime": "2026-09-09T10:45:00Z",
                "totalDurationSeconds": 1800,
                "joinedLate": True,
                "leftEarly": True,
                "sessionCount": 1,
            },
        ],
    }

    csv_text = format_attendance_csv(attendance_data)
    assert "Alice Smith,alice@example.com,HOST" in csv_text
    assert "Bob Jones,bob@example.com,ATTENDEE" in csv_text
    assert "Yes" in csv_text

    md_text = format_attendance_markdown(attendance_data)
    assert "# Google Meet Attendance Summary" in md_text
    assert "| Alice Smith |" in md_text
    assert "| Bob Jones |" in md_text
    assert "⚠️ Yes" in md_text
