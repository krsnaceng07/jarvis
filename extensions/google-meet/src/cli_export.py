"""Export bundle generator for Google Meet artifacts and attendance.

Bundles transcripts, smart notes, attendance CSV/Markdown, and metadata manifest
into a zip file or a destination directory.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any
import zipfile

from jarvis_sdk import Err, Ok, Result

from .config import GoogleMeetResolvedConfig
from .drive import export_drive_file_text
from .google_api_errors import GoogleApiError
from .meet import fetch_google_meet_artifacts, get_google_meet_attendance


def format_attendance_csv(attendance: dict[str, Any]) -> str:
    """Format attendance summary records as CSV text."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Participant Name",
            "Email",
            "Role",
            "Earliest Join Time",
            "Latest Leave Time",
            "Total Duration (Seconds)",
            "Total Duration (Minutes)",
            "Joined Late",
            "Left Early",
            "Session Count",
        ]
    )

    participants = attendance.get("participants", [])
    for p in participants:
        writer.writerow(
            [
                p.get("displayName", ""),
                p.get("email", ""),
                p.get("role", ""),
                p.get("earliestStartTime", ""),
                p.get("latestEndTime", ""),
                p.get("totalDurationSeconds", 0),
                round(p.get("totalDurationSeconds", 0) / 60.0, 1),
                "Yes" if p.get("joinedLate") else "No",
                "Yes" if p.get("leftEarly") else "No",
                p.get("sessionCount", 1),
            ]
        )

    return output.getvalue()


def format_attendance_markdown(attendance: dict[str, Any]) -> str:
    """Format attendance summary records as Markdown table."""
    lines: list[str] = [
        "# Google Meet Attendance Summary",
        "",
        f"- **Meeting Space:** `{attendance.get('space', '')}`",
        f"- **Conference Record:** `{attendance.get('conferenceRecord', '')}`",
        f"- **Start Time:** {attendance.get('startTime', 'Unknown')}",
        f"- **End Time:** {attendance.get('endTime', 'Ongoing / Unknown')}",
        f"- **Total Participants:** {attendance.get('totalParticipants', 0)}",
        "",
        "| Participant | Email | Role | First Joined | Last Left | Duration | Late | Left Early |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for p in attendance.get("participants", []):
        duration_mins = round(p.get("totalDurationSeconds", 0) / 60.0, 1)
        name = p.get("displayName", "Unknown")
        email = p.get("email", "")
        role = p.get("role", "ATTENDEE")
        first_join = p.get("earliestStartTime", "")
        last_left = p.get("latestEndTime", "Still in call")
        late = "⚠️ Yes" if p.get("joinedLate") else "No"
        early = "⚠️ Yes" if p.get("leftEarly") else "No"
        lines.append(
            f"| {name} | {email} | {role} | {first_join} | {last_left} | {duration_mins} min | {late} | {early} |"
        )

    return "\n".join(lines) + "\n"


async def generate_export_bundle(
    *,
    config: GoogleMeetResolvedConfig,
    conference_record_name: str,
    include_drive_content: bool = True,
) -> Result[dict[str, Any], GoogleApiError]:
    """Gather all artifacts, text exports, and attendance data into an in-memory export bundle."""
    # 1. Fetch artifacts and attendance
    artifacts_res = await fetch_google_meet_artifacts(
        config=config,
        conference_record_name=conference_record_name,
    )
    if not artifacts_res.is_ok:
        return Err(artifacts_res.error)
    artifacts_data = artifacts_res.unwrap()

    attendance_res = await get_google_meet_attendance(
        config=config,
        conference_record_name=conference_record_name,
    )
    if not attendance_res.is_ok:
        return Err(attendance_res.error)
    attendance_data = attendance_res.unwrap()

    files: dict[str, str | bytes] = {}

    # Manifest
    manifest = {
        "conferenceRecord": conference_record_name,
        "space": artifacts_data.get("space"),
        "startTime": artifacts_data.get("startTime"),
        "endTime": artifacts_data.get("endTime"),
        "attendanceSummary": {
            "totalParticipants": attendance_data.get("totalParticipants", 0),
        },
        "transcriptsCount": len(artifacts_data.get("transcripts", [])),
        "recordingsCount": len(artifacts_data.get("recordings", [])),
        "smartNotes": artifacts_data.get("smartNotes"),
    }
    files["manifest.json"] = json.dumps(manifest, indent=2)

    # Attendance CSV & MD
    files["attendance.csv"] = format_attendance_csv(attendance_data)
    files["attendance.md"] = format_attendance_markdown(attendance_data)

    # Drive text fetching if requested
    token = config.oauth.access_token if config.oauth else None
    if include_drive_content and token:
        # Transcripts
        transcripts: list[dict[str, Any]] = artifacts_data.get("transcripts", [])
        for i, t in enumerate(transcripts):
            drive_doc_id = t.get("documentId")
            if drive_doc_id:
                content_res = await export_drive_file_text(token=token, file_id=drive_doc_id)
                if content_res.is_ok:
                    files[f"transcript_{i + 1}_{drive_doc_id}.txt"] = content_res.unwrap()

        # Smart notes
        smart_notes = artifacts_data.get("smartNotes")
        if smart_notes and smart_notes.get("documentId"):
            notes_doc_id = smart_notes["documentId"]
            notes_res = await export_drive_file_text(token=token, file_id=notes_doc_id)
            if notes_res.is_ok:
                files[f"smart_notes_{notes_doc_id}.txt"] = notes_res.unwrap()

    return Ok(
        {
            "manifest": manifest,
            "attendance": attendance_data,
            "artifacts": artifacts_data,
            "files": files,
        }
    )


def write_export_bundle_to_disk(
    bundle_files: dict[str, str | bytes],
    output_path: Path,
    as_zip: bool = False,
) -> Path:
    """Write export bundle files to a directory or a .zip archive."""
    if as_zip:
        zip_file_path = (
            output_path if output_path.suffix == ".zip" else output_path.with_suffix(".zip")
        )
        zip_file_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_file_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_name, content in bundle_files.items():
                if isinstance(content, str):
                    zf.writestr(file_name, content.encode("utf-8"))
                else:
                    zf.writestr(file_name, content)
        return zip_file_path
    else:
        output_path.mkdir(parents=True, exist_ok=True)
        for file_name, content in bundle_files.items():
            dest = output_path / file_name
            if isinstance(content, str):
                dest.write_text(content, encoding="utf-8")
            else:
                dest.write_bytes(content)
        return output_path
