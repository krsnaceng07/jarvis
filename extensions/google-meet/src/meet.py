"""Google Meet domain logic for attendance aggregation, artifact extraction, and preflight reports."""

from __future__ import annotations

import asyncio
import datetime
from typing import Any

from jarvis_sdk import Err, Ok, Result

from .drive import export_google_drive_document_text, extract_google_drive_document_id
from .meet_api import (
    GoogleMeetAccessType,
    GoogleMeetArtifactsEntry,
    GoogleMeetArtifactsResult,
    GoogleMeetAttendanceResult,
    GoogleMeetAttendanceRow,
    GoogleMeetConferenceRecord,
    GoogleMeetCreateSpaceResult,
    GoogleMeetEndActiveConferenceResult,
    GoogleMeetEntryPointAccess,
    GoogleMeetLatestConferenceRecordResult,
    GoogleMeetParticipant,
    GoogleMeetParticipantSession,
    GoogleMeetPreflightReport,
    GoogleMeetRecording,
    GoogleMeetSmartNote,
    GoogleMeetSmartNotesListResult,
    GoogleMeetSpace,
    GoogleMeetSpaceConfig,
    GoogleMeetTranscript,
    GoogleMeetTranscriptEntries,
    create_google_meet_space,
    end_google_meet_active_conference,
    fetch_google_meet_space,
    fetch_latest_google_meet_conference_record,
    list_google_meet_participants,
    list_google_meet_participant_sessions,
    list_google_meet_recordings,
    list_google_meet_smart_notes,
    list_google_meet_transcript_entries,
    list_google_meet_transcripts,
    resolve_conference_record_query,
)

__all__ = [
    "GoogleMeetAccessType",
    "GoogleMeetArtifactsEntry",
    "GoogleMeetArtifactsResult",
    "GoogleMeetAttendanceResult",
    "GoogleMeetAttendanceRow",
    "GoogleMeetConferenceRecord",
    "GoogleMeetCreateSpaceResult",
    "GoogleMeetEndActiveConferenceResult",
    "GoogleMeetEntryPointAccess",
    "GoogleMeetLatestConferenceRecordResult",
    "GoogleMeetParticipant",
    "GoogleMeetParticipantSession",
    "GoogleMeetPreflightReport",
    "GoogleMeetRecording",
    "GoogleMeetSmartNote",
    "GoogleMeetSmartNotesListResult",
    "GoogleMeetSpace",
    "GoogleMeetSpaceConfig",
    "GoogleMeetTranscript",
    "GoogleMeetTranscriptEntries",
    "build_google_meet_preflight_report",
    "create_google_meet_space",
    "end_google_meet_active_conference",
    "fetch_google_meet_artifacts",
    "fetch_google_meet_attendance",
    "fetch_google_meet_space",
    "fetch_latest_google_meet_conference_record",
]


def parse_google_meet_timestamp(value: str | None) -> float | None:
    if not value or not value.strip():
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return dt.timestamp() * 1000.0
    except Exception:
        return None


def get_participant_display_name(participant: GoogleMeetParticipant) -> str | None:
    if participant.signedin_user and participant.signedin_user.display_name:
        return participant.signedin_user.display_name
    if participant.anonymous_user and participant.anonymous_user.display_name:
        return participant.anonymous_user.display_name
    if participant.phone_user and participant.phone_user.display_name:
        return participant.phone_user.display_name
    return None


def get_participant_user(participant: GoogleMeetParticipant) -> str | None:
    return participant.signedin_user.user if participant.signedin_user else None


def get_docs_destination_document_id(
    destination: dict[str, Any] | None,
) -> str | None:
    if not destination:
        return None
    return (
        extract_google_drive_document_id(destination.get("document"))
        or extract_google_drive_document_id(destination.get("documentId"))
        or extract_google_drive_document_id(destination.get("file"))
    )


async def attach_document_text(
    *,
    access_token: str,
    resource: Any,
) -> Any:
    dest = getattr(resource, "docs_destination", None)
    doc_id = get_docs_destination_document_id(dest)
    if not doc_id:
        return resource
    try:
        text = await export_google_drive_document_text(
            access_token=access_token,
            document_id=doc_id,
        )
        setattr(resource, "document_text", text)
    except Exception as error:
        setattr(resource, "document_text_error", str(error))
    return resource


def iso_from_ms(value: float | None) -> str | None:
    if value is not None and value > 0:
        return datetime.datetime.fromtimestamp(value / 1000.0, tz=datetime.timezone.utc).isoformat()
    return None


def min_timestamp(values: list[str | None]) -> str | None:
    parsed = [parse_google_meet_timestamp(v) for v in values if v]
    valid = [p for p in parsed if p is not None]
    return iso_from_ms(min(valid)) if valid else None


def max_timestamp(values: list[str | None]) -> str | None:
    parsed = [parse_google_meet_timestamp(v) for v in values if v]
    valid = [p for p in parsed if p is not None]
    return iso_from_ms(max(valid)) if valid else None


def sum_session_duration_ms(
    sessions: list[GoogleMeetParticipantSession],
    fallback_start: str | None = None,
    fallback_end: str | None = None,
) -> int | None:
    total = 0.0
    for session in sessions:
        start_ms = parse_google_meet_timestamp(session.start_time)
        end_ms = parse_google_meet_timestamp(session.end_time)
        if start_ms is not None and end_ms is not None and end_ms > start_ms:
            total += end_ms - start_ms

    if total > 0:
        return int(total)

    start_ms = parse_google_meet_timestamp(fallback_start)
    end_ms = parse_google_meet_timestamp(fallback_end)
    if start_ms is not None and end_ms is not None and end_ms > start_ms:
        return int(end_ms - start_ms)
    return None


def attendance_merge_key(row: GoogleMeetAttendanceRow) -> str:
    key = row.user or row.display_name or row.participant
    return key.strip().lower()


def sort_sessions(
    sessions: list[GoogleMeetParticipantSession],
) -> list[GoogleMeetParticipantSession]:
    return sorted(
        sessions,
        key=lambda s: parse_google_meet_timestamp(s.start_time) or 0.0,
    )


def decorate_attendance_row(
    row: GoogleMeetAttendanceRow,
    conference_record: GoogleMeetConferenceRecord,
    late_after_minutes: int = 5,
    early_before_minutes: int = 5,
) -> GoogleMeetAttendanceRow:
    sessions = sort_sessions(row.sessions)
    first_join_time = min_timestamp([row.earliest_start_time] + [s.start_time for s in sessions])
    last_leave_time = max_timestamp([row.latest_end_time] + [s.end_time for s in sessions])
    duration_ms = sum_session_duration_ms(sessions, first_join_time, last_leave_time)
    conf_start_ms = parse_google_meet_timestamp(conference_record.start_time)
    conf_end_ms = parse_google_meet_timestamp(conference_record.end_time)
    first_join_ms = parse_google_meet_timestamp(first_join_time)
    last_leave_ms = parse_google_meet_timestamp(last_leave_time)

    late_grace_ms = late_after_minutes * 60 * 1000
    early_grace_ms = early_before_minutes * 60 * 1000

    late_by_ms = (
        int(max(first_join_ms - conf_start_ms, 0))
        if conf_start_ms is not None and first_join_ms is not None
        else None
    )
    early_leave_by_ms = (
        int(max(conf_end_ms - last_leave_ms, 0))
        if conf_end_ms is not None and last_leave_ms is not None
        else None
    )

    is_late = late_by_ms > late_grace_ms if late_by_ms is not None else None
    is_early_leave = early_leave_by_ms > early_grace_ms if early_leave_by_ms is not None else None

    return GoogleMeetAttendanceRow(
        conference_record=row.conference_record,
        participant=row.participant,
        participants=row.participants or [row.participant],
        display_name=row.display_name,
        user=row.user,
        earliest_start_time=first_join_time or row.earliest_start_time,
        latest_end_time=last_leave_time or row.latest_end_time,
        first_join_time=first_join_time,
        last_leave_time=last_leave_time,
        duration_ms=duration_ms,
        late=is_late,
        late_by_ms=late_by_ms if is_late else None,
        early_leave=is_early_leave,
        early_leave_by_ms=early_leave_by_ms if is_early_leave else None,
        sessions=sessions,
    )


def merge_attendance_rows(
    rows: list[GoogleMeetAttendanceRow],
    conference_record: GoogleMeetConferenceRecord,
    merge_duplicate_participants: bool = True,
    late_after_minutes: int = 5,
    early_before_minutes: int = 5,
) -> list[GoogleMeetAttendanceRow]:
    if not merge_duplicate_participants:
        return [
            decorate_attendance_row(
                r,
                conference_record,
                late_after_minutes=late_after_minutes,
                early_before_minutes=early_before_minutes,
            )
            for r in rows
        ]

    grouped: dict[str, GoogleMeetAttendanceRow] = {}
    for row in rows:
        key = attendance_merge_key(row)
        existing = grouped.get(key)
        if not existing:
            grouped[key] = GoogleMeetAttendanceRow(
                conference_record=row.conference_record,
                participant=row.participant,
                participants=[row.participant],
                display_name=row.display_name,
                user=row.user,
                earliest_start_time=row.earliest_start_time,
                latest_end_time=row.latest_end_time,
                sessions=list(row.sessions),
            )
        else:
            merged_participants = list(
                dict.fromkeys((existing.participants or []) + [row.participant])
            )
            existing.participants = merged_participants
            existing.sessions.extend(row.sessions)
            if not existing.display_name:
                existing.display_name = row.display_name
            if not existing.user:
                existing.user = row.user
            existing.earliest_start_time = min_timestamp(
                [existing.earliest_start_time, row.earliest_start_time]
            )
            existing.latest_end_time = max_timestamp(
                [existing.latest_end_time, row.latest_end_time]
            )

    return [
        decorate_attendance_row(
            r,
            conference_record,
            late_after_minutes=late_after_minutes,
            early_before_minutes=early_before_minutes,
        )
        for r in grouped.values()
    ]


async def fetch_google_meet_artifacts(
    *,
    access_token: str,
    meeting: str | None = None,
    conference_record: str | None = None,
    page_size: int | None = None,
    include_transcript_entries: bool = True,
    all_conference_records: bool = False,
    include_document_bodies: bool = False,
) -> GoogleMeetArtifactsResult:
    resolved = await resolve_conference_record_query(
        access_token=access_token,
        meeting=meeting,
        conference_record=conference_record,
        page_size=page_size,
        all_conference_records=all_conference_records,
    )

    async def fetch_single_record_artifacts(
        record: GoogleMeetConferenceRecord,
    ) -> GoogleMeetArtifactsEntry:
        participants_fut = list_google_meet_participants(
            access_token=access_token,
            conference_record=record.name,
            page_size=page_size,
        )
        recordings_fut = list_google_meet_recordings(
            access_token=access_token,
            conference_record=record.name,
            page_size=page_size,
        )
        transcripts_fut = list_google_meet_transcripts(
            access_token=access_token,
            conference_record=record.name,
            page_size=page_size,
        )
        smart_notes_fut = list_google_meet_smart_notes(
            access_token=access_token,
            conference_record=record.name,
            page_size=page_size,
        )

        participants, recordings, transcripts = await asyncio.gather(
            participants_fut, recordings_fut, transcripts_fut
        )

        smart_notes: list[GoogleMeetSmartNote] = []
        smart_notes_error: str | None = None
        try:
            smart_notes = await smart_notes_fut
        except Exception as err:
            smart_notes_error = str(err)

        transcript_entries: list[GoogleMeetTranscriptEntries] = []
        if include_transcript_entries:
            for transcript in transcripts:
                try:
                    entries = await list_google_meet_transcript_entries(
                        access_token=access_token,
                        transcript=transcript.name,
                        page_size=page_size,
                    )
                    transcript_entries.append(
                        GoogleMeetTranscriptEntries(
                            transcript=transcript.name,
                            entries=entries,
                        )
                    )
                except Exception as err:
                    transcript_entries.append(
                        GoogleMeetTranscriptEntries(
                            transcript=transcript.name,
                            entries=[],
                            entries_error=str(err),
                        )
                    )

        if include_document_bodies:
            for t in transcripts:
                await attach_document_text(access_token=access_token, resource=t)
            for sn in smart_notes:
                await attach_document_text(access_token=access_token, resource=sn)

        return GoogleMeetArtifactsEntry(
            conference_record=record,
            participants=participants,
            recordings=recordings,
            transcripts=transcripts,
            transcript_entries=transcript_entries,
            smart_notes=smart_notes,
            smart_notes_error=smart_notes_error,
        )

    artifacts = await asyncio.gather(
        *(fetch_single_record_artifacts(r) for r in resolved.conference_records)
    )

    return GoogleMeetArtifactsResult(
        input=resolved.input,
        space=resolved.space,
        conference_records=resolved.conference_records,
        artifacts=list(artifacts),
    )


async def fetch_google_meet_attendance(
    *,
    access_token: str,
    meeting: str | None = None,
    conference_record: str | None = None,
    page_size: int | None = None,
    all_conference_records: bool = False,
    merge_duplicate_participants: bool = True,
    late_after_minutes: int = 5,
    early_before_minutes: int = 5,
) -> GoogleMeetAttendanceResult:
    resolved = await resolve_conference_record_query(
        access_token=access_token,
        meeting=meeting,
        conference_record=conference_record,
        page_size=page_size,
        all_conference_records=all_conference_records,
    )

    all_rows: list[GoogleMeetAttendanceRow] = []
    for record in resolved.conference_records:
        participants = await list_google_meet_participants(
            access_token=access_token,
            conference_record=record.name,
            page_size=page_size,
        )

        async def fetch_participant_row(
            p: GoogleMeetParticipant,
        ) -> GoogleMeetAttendanceRow:
            sessions = await list_google_meet_participant_sessions(
                access_token=access_token,
                participant=p.name,
                page_size=page_size,
            )
            return GoogleMeetAttendanceRow(
                conference_record=record.name,
                participant=p.name,
                display_name=get_participant_display_name(p),
                user=get_participant_user(p),
                earliest_start_time=p.earliest_start_time,
                latest_end_time=p.latest_end_time,
                sessions=sessions,
            )

        rows = await asyncio.gather(*(fetch_participant_row(p) for p in participants))
        merged = merge_attendance_rows(
            list(rows),
            record,
            merge_duplicate_participants=merge_duplicate_participants,
            late_after_minutes=late_after_minutes,
            early_before_minutes=early_before_minutes,
        )
        all_rows.extend(merged)

    return GoogleMeetAttendanceResult(
        input=resolved.input,
        space=resolved.space,
        conference_records=resolved.conference_records,
        attendance=all_rows,
    )


def build_google_meet_preflight_report(
    *,
    input: str,
    space: GoogleMeetSpace,
    preview_acknowledged: bool,
    token_source: str,
) -> GoogleMeetPreflightReport:
    blockers: list[str] = []
    if not preview_acknowledged:
        blockers.append(
            "Set preview.enrollmentAcknowledged=true after confirming your Cloud project, OAuth principal, and meeting participants are enrolled in the Google Workspace Developer Preview Program."
        )
    return GoogleMeetPreflightReport(
        input=input,
        resolved_space_name=space.name,
        meeting_code=space.meeting_code,
        meeting_uri=space.meeting_uri,
        has_active_conference=bool(space.active_conference),
        preview_acknowledged=preview_acknowledged,
        token_source="refresh-token" if token_source == "refresh-token" else "cached-access-token",
        blockers=blockers,
    )


async def get_google_meet_artifacts(
    *,
    config: Any = None,
    access_token: str | None = None,
    meeting: str | None = None,
    conference_record_name: str | None = None,
    conference_record: str | None = None,
    **kwargs: Any,
) -> Result[dict[str, Any], Any]:
    token = access_token or (
        config.oauth.access_token if config and hasattr(config, "oauth") and config.oauth else None
    )
    if not token:
        return Err("OAuth access token required.")
    record = conference_record_name or conference_record
    try:
        res = await fetch_google_meet_artifacts(
            access_token=token,
            meeting=meeting,
            conference_record=record,
            **kwargs,
        )
        return Ok(res.to_dict() if hasattr(res, "to_dict") else vars(res))
    except Exception as e:
        return Err(e)


async def get_google_meet_attendance(
    *,
    config: Any = None,
    access_token: str | None = None,
    meeting: str | None = None,
    conference_record_name: str | None = None,
    conference_record: str | None = None,
    late_threshold_seconds: int = 300,
    early_leave_threshold_seconds: int = 300,
    **kwargs: Any,
) -> Result[dict[str, Any], Any]:
    token = access_token or (
        config.oauth.access_token if config and hasattr(config, "oauth") and config.oauth else None
    )
    if not token:
        return Err("OAuth access token required.")
    record = conference_record_name or conference_record
    try:
        res = await fetch_google_meet_attendance(
            access_token=token,
            meeting=meeting,
            conference_record=record,
            late_after_minutes=max(1, int(late_threshold_seconds / 60)),
            early_before_minutes=max(1, int(early_leave_threshold_seconds / 60)),
            **kwargs,
        )
        return Ok(res.to_dict() if hasattr(res, "to_dict") else vars(res))
    except Exception as e:
        return Err(e)


async def get_google_meet_preflight_report(
    *,
    config: Any = None,
    space_name: str | None = None,
    input: str | None = None,
    **kwargs: Any,
) -> Result[dict[str, Any], Any]:
    token = (
        config.oauth.access_token if config and hasattr(config, "oauth") and config.oauth else None
    )
    target_space = space_name or input or "spaces/default"
    try:
        space = None
        if token and space_name:
            space = await fetch_google_meet_space(access_token=token, name=space_name)
        if not space:
            code = target_space.replace("spaces/", "")
            space = GoogleMeetSpace(
                name=target_space, meeting_code=code, meeting_uri=f"https://meet.google.com/{code}"
            )
        report = build_google_meet_preflight_report(
            input=target_space,
            space=space,
            preview_acknowledged=bool(
                config.preview.enrollment_acknowledged
                if config and hasattr(config, "preview")
                else False
            ),
            token_source="cached-access-token" if token else "none",
        )
        return Ok(vars(report))
    except Exception as e:
        return Err(e)
