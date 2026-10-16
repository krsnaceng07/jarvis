"""Google Meet REST API client for spaces, conferences, participants, and artifacts."""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar
import httpx

from jarvis_sdk import Err, Ok, Result

from .google_api_errors import google_api_error

GOOGLE_MEET_API_ORIGIN = "https://meet.googleapis.com"
GOOGLE_MEET_API_BASE_URL = f"{GOOGLE_MEET_API_ORIGIN}/v2"
GOOGLE_MEET_URL_HOST = "meet.google.com"
GOOGLE_MEET_API_HOST = "meet.googleapis.com"
GOOGLE_MEET_REQUEST_TIMEOUT_MS = 30000

GOOGLE_MEET_MEDIA_SCOPE = "https://www.googleapis.com/auth/meetings.conference.media.readonly"
GOOGLE_MEET_SPACE_SCOPE = "https://www.googleapis.com/auth/meetings.space.readonly"
GOOGLE_MEET_SPACE_CREATED_SCOPE = "https://www.googleapis.com/auth/meetings.space.created"
GOOGLE_MEET_SPACE_SETTINGS_SCOPE = "https://www.googleapis.com/auth/meetings.space.settings"

GoogleMeetAccessType = Literal["OPEN", "TRUSTED", "RESTRICTED"]
GoogleMeetEntryPointAccess = Literal["ALL", "CREATOR_APP_ONLY"]


@dataclass(slots=True)
class GoogleMeetSpaceConfig:
    access_type: GoogleMeetAccessType | None = None
    entry_point_access: GoogleMeetEntryPointAccess | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GoogleMeetSpace:
    name: str
    meeting_code: str | None = None
    meeting_uri: str | None = None
    active_conference: dict[str, Any] | None = None
    config: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "meetingCode": self.meeting_code,
            "meetingUri": self.meeting_uri,
            "activeConference": self.active_conference,
            "config": self.config,
        }


@dataclass(slots=True)
class GoogleMeetPreflightReport:
    input: str
    resolved_space_name: str
    has_active_conference: bool
    preview_acknowledged: bool
    token_source: Literal["cached-access-token", "refresh-token"]
    blockers: list[str]
    meeting_code: str | None = None
    meeting_uri: str | None = None


@dataclass(slots=True)
class GoogleMeetCreateSpaceResult:
    space: GoogleMeetSpace
    meeting_uri: str


@dataclass(slots=True)
class GoogleMeetEndActiveConferenceResult:
    space: str
    ended: bool = True


@dataclass(slots=True)
class GoogleMeetConferenceRecord:
    name: str
    space: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    expire_time: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "space": self.space,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "expireTime": self.expire_time,
        }


@dataclass(slots=True)
class GoogleMeetParticipantUser:
    user: str | None = None
    display_name: str | None = None


@dataclass(slots=True)
class GoogleMeetParticipant:
    name: str
    earliest_start_time: str | None = None
    latest_end_time: str | None = None
    signedin_user: GoogleMeetParticipantUser | None = None
    anonymous_user: GoogleMeetParticipantUser | None = None
    phone_user: GoogleMeetParticipantUser | None = None


@dataclass(slots=True)
class GoogleMeetParticipantSession:
    name: str
    start_time: str | None = None
    end_time: str | None = None


@dataclass(slots=True)
class GoogleMeetRecording:
    name: str
    start_time: str | None = None
    end_time: str | None = None
    drive_destination: dict[str, Any] | None = None


@dataclass(slots=True)
class GoogleMeetTranscript:
    name: str
    start_time: str | None = None
    end_time: str | None = None
    docs_destination: dict[str, Any] | None = None
    document_text: str | None = None
    document_text_error: str | None = None


@dataclass(slots=True)
class GoogleMeetTranscriptEntry:
    name: str
    participant: str | None = None
    text: str | None = None
    language_code: str | None = None
    start_time: str | None = None
    end_time: str | None = None


@dataclass(slots=True)
class GoogleMeetTranscriptEntries:
    transcript: str
    entries: list[GoogleMeetTranscriptEntry]
    entries_error: str | None = None


@dataclass(slots=True)
class GoogleMeetSmartNote:
    name: str
    start_time: str | None = None
    end_time: str | None = None
    docs_destination: dict[str, Any] | None = None
    document_text: str | None = None
    document_text_error: str | None = None


@dataclass(slots=True)
class GoogleMeetArtifactsEntry:
    conference_record: GoogleMeetConferenceRecord
    participants: list[GoogleMeetParticipant]
    recordings: list[GoogleMeetRecording]
    transcripts: list[GoogleMeetTranscript]
    transcript_entries: list[GoogleMeetTranscriptEntries]
    smart_notes: list[GoogleMeetSmartNote]
    smart_notes_error: str | None = None


@dataclass(slots=True)
class GoogleMeetArtifactsResult:
    conference_records: list[GoogleMeetConferenceRecord]
    artifacts: list[GoogleMeetArtifactsEntry]
    input: str | None = None
    space: GoogleMeetSpace | None = None


@dataclass(slots=True)
class GoogleMeetLatestConferenceRecordResult:
    input: str
    space: GoogleMeetSpace
    conference_record: GoogleMeetConferenceRecord | None = None


@dataclass(slots=True)
class GoogleMeetAttendanceRow:
    conference_record: str
    participant: str
    sessions: list[GoogleMeetParticipantSession]
    participants: list[str] | None = None
    display_name: str | None = None
    user: str | None = None
    earliest_start_time: str | None = None
    latest_end_time: str | None = None
    first_join_time: str | None = None
    last_leave_time: str | None = None
    duration_ms: int | None = None
    late: bool | None = None
    late_by_ms: int | None = None
    early_leave: bool | None = None
    early_leave_by_ms: int | None = None


@dataclass(slots=True)
class GoogleMeetAttendanceResult:
    conference_records: list[GoogleMeetConferenceRecord]
    attendance: list[GoogleMeetAttendanceRow]
    input: str | None = None
    space: GoogleMeetSpace | None = None


@dataclass(slots=True)
class GoogleMeetSmartNotesListResult:
    smart_notes: list[GoogleMeetSmartNote]
    smart_notes_error: str | None = None


def normalize_google_meet_space_name(input_val: str) -> str:
    trimmed = input_val.strip()
    if not trimmed:
        raise ValueError("Meeting input is required")
    if trimmed.startswith("spaces/"):
        suffix = trimmed[len("spaces/") :].strip()
        if not suffix:
            raise ValueError("spaces/ input must include a meeting code or space id")
        return f"spaces/{suffix}"
    if trimmed.lower().startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(trimmed)
        if parsed.hostname != GOOGLE_MEET_URL_HOST:
            raise ValueError(f"Expected a {GOOGLE_MEET_URL_HOST} URL, received {parsed.hostname}")
        segments = [s.strip() for s in parsed.path.split("/") if s.strip()]
        if not segments:
            raise ValueError("Google Meet URL did not include a meeting code")
        return f"spaces/{segments[0]}"
    return f"spaces/{trimmed}"


def encode_space_name_for_path(name: str) -> str:
    return "/".join(urllib.parse.quote(segment, safe="") for segment in name.split("/"))


def encode_resource_name_for_path(name: str) -> str:
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("Google Meet resource name is required")
    return "/".join(urllib.parse.quote(segment, safe="") for segment in trimmed.split("/"))


def normalize_conference_record_name(input_val: str) -> str:
    trimmed = input_val.strip()
    if not trimmed:
        raise ValueError("Conference record is required")
    return trimmed if trimmed.startswith("conferenceRecords/") else f"conferenceRecords/{trimmed}"


def append_query(url: str, query: dict[str, Any] | None = None) -> str:
    if not query:
        return url
    clean_query = {k: str(v) for k, v in query.items() if v is not None}
    if not clean_query:
        return url
    parsed = urllib.parse.urlparse(url)
    existing_qs = urllib.parse.parse_qs(parsed.query)
    for k, v in clean_query.items():
        existing_qs[k] = [v]
    new_query = urllib.parse.urlencode(existing_qs, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


async def request_google_meet_api(
    *,
    access_token: str,
    path: str,
    query: dict[str, Any] | None = None,
    method: str = "GET",
    body: str | None = None,
    audit_context: str = "google-meet.api",
) -> httpx.Response:
    url = append_query(f"{GOOGLE_MEET_API_BASE_URL}/{path}", query)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=GOOGLE_MEET_REQUEST_TIMEOUT_MS / 1000.0) as client:
        return await client.request(
            method=method,
            url=url,
            headers=headers,
            content=body.encode("utf-8") if body is not None else None,
        )


async def fetch_google_meet_json(
    *,
    access_token: str,
    path: str,
    query: dict[str, Any] | None = None,
    audit_context: str,
    error_prefix: str,
) -> dict[str, Any]:
    response = await request_google_meet_api(
        access_token=access_token,
        path=path,
        query=query,
        audit_context=audit_context,
    )
    if response.status_code >= 400:
        raise await google_api_error(
            response=response,
            prefix=error_prefix,
            scopes=[GOOGLE_MEET_MEDIA_SCOPE],
        )
    try:
        return response.json()
    except Exception as err:
        raise ValueError(f"{error_prefix} response JSON malformed: {err}") from err


T = TypeVar("T")


async def list_google_meet_collection(
    *,
    access_token: str,
    path: str,
    collection_key: str,
    query: dict[str, Any] | None = None,
    max_items: int | None = None,
    audit_context: str,
    error_prefix: str,
    transform: Any = None,
) -> list[Any]:
    items: list[Any] = []
    page_token: str | None = None
    while True:
        req_query = dict(query or {})
        if page_token:
            req_query["pageToken"] = page_token
        payload = await fetch_google_meet_json(
            access_token=access_token,
            path=path,
            query=req_query,
            audit_context=audit_context,
            error_prefix=error_prefix,
        )
        raw_items = payload.get(collection_key)
        if raw_items is None:
            page_items = []
        elif not isinstance(raw_items, list):
            raise ValueError(f"Google Meet {error_prefix} response had non-array {collection_key}")
        else:
            page_items = [transform(i) if transform else i for i in raw_items]

        if max_items is not None:
            remaining = max(max_items - len(items), 0)
            items.extend(page_items[:remaining])
            if len(items) >= max_items:
                break
        else:
            items.extend(page_items)

        next_page = payload.get("nextPageToken")
        page_token = str(next_page) if isinstance(next_page, str) and next_page.strip() else None
        if not page_token:
            break

    return items


def parse_space_payload(payload: dict[str, Any]) -> GoogleMeetSpace:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Google Meet space response was missing name")
    return GoogleMeetSpace(
        name=name,
        meeting_code=payload.get("meetingCode"),
        meeting_uri=payload.get("meetingUri"),
        active_conference=payload.get("activeConference"),
        config=payload.get("config"),
    )


async def fetch_google_meet_space(
    *,
    access_token: str,
    meeting: str,
) -> GoogleMeetSpace:
    name = normalize_google_meet_space_name(meeting)
    response = await request_google_meet_api(
        access_token=access_token,
        path=encode_space_name_for_path(name),
        audit_context="google-meet.spaces.get",
    )
    if response.status_code >= 400:
        raise await google_api_error(
            response=response,
            prefix="Google Meet spaces.get",
            scopes=[GOOGLE_MEET_SPACE_SCOPE],
        )
    return parse_space_payload(response.json())


async def create_google_meet_space(
    *,
    access_token: str,
    config: dict[str, Any] | None = None,
) -> GoogleMeetCreateSpaceResult:
    body = json.dumps({"config": config}) if config else "{}"
    scopes = (
        [GOOGLE_MEET_SPACE_CREATED_SCOPE, GOOGLE_MEET_SPACE_SETTINGS_SCOPE]
        if config
        else [GOOGLE_MEET_SPACE_CREATED_SCOPE]
    )
    response = await request_google_meet_api(
        access_token=access_token,
        path="spaces",
        method="POST",
        body=body,
        audit_context="google-meet.spaces.create",
    )
    if response.status_code >= 400:
        raise await google_api_error(
            response=response,
            prefix="Google Meet spaces.create",
            scopes=scopes,
        )
    space = parse_space_payload(response.json())
    if not space.meeting_uri:
        raise ValueError("Google Meet spaces.create response was missing meetingUri")
    return GoogleMeetCreateSpaceResult(space=space, meeting_uri=space.meeting_uri)


async def end_google_meet_active_conference(
    *,
    access_token: str,
    meeting: str,
) -> GoogleMeetEndActiveConferenceResult:
    resolved = await fetch_google_meet_space(
        access_token=access_token,
        meeting=meeting,
    )
    space = resolved.name
    response = await request_google_meet_api(
        access_token=access_token,
        path=f"{encode_space_name_for_path(space)}:endActiveConference",
        method="POST",
        body="{}",
        audit_context="google-meet.spaces.endActiveConference",
    )
    if response.status_code >= 400:
        raise await google_api_error(
            response=response,
            prefix="Google Meet spaces.endActiveConference",
            scopes=[GOOGLE_MEET_SPACE_CREATED_SCOPE],
        )
    return GoogleMeetEndActiveConferenceResult(space=space, ended=True)


def parse_conference_record_payload(payload: dict[str, Any]) -> GoogleMeetConferenceRecord:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Google Meet conference record response was missing name")
    return GoogleMeetConferenceRecord(
        name=name,
        space=payload.get("space"),
        start_time=payload.get("startTime"),
        end_time=payload.get("endTime"),
        expire_time=payload.get("expireTime"),
    )


async def fetch_google_meet_conference_record(
    *,
    access_token: str,
    conference_record: str,
) -> GoogleMeetConferenceRecord:
    name = normalize_conference_record_name(conference_record)
    payload = await fetch_google_meet_json(
        access_token=access_token,
        path=encode_resource_name_for_path(name),
        audit_context="google-meet.conferenceRecords.get",
        error_prefix="Google Meet conferenceRecords.get",
    )
    return parse_conference_record_payload(payload)


async def list_google_meet_conference_records(
    *,
    access_token: str,
    meeting: str | None = None,
    page_size: int | None = None,
    max_items: int | None = None,
) -> list[GoogleMeetConferenceRecord]:
    filt = f'space.name = "{normalize_google_meet_space_name(meeting)}"' if meeting else None
    query: dict[str, Any] = {}
    if page_size:
        query["pageSize"] = page_size
    if filt:
        query["filter"] = filt

    return await list_google_meet_collection(
        access_token=access_token,
        path="conferenceRecords",
        collection_key="conferenceRecords",
        query=query,
        max_items=max_items,
        audit_context="google-meet.conferenceRecords.list",
        error_prefix="Google Meet conferenceRecords.list",
        transform=parse_conference_record_payload,
    )


async def fetch_latest_google_meet_conference_record(
    *,
    access_token: str,
    meeting: str,
) -> GoogleMeetLatestConferenceRecordResult:
    space = await fetch_google_meet_space(
        access_token=access_token,
        meeting=meeting,
    )
    records = await list_google_meet_conference_records(
        access_token=access_token,
        meeting=space.name,
        page_size=1,
        max_items=1,
    )
    return GoogleMeetLatestConferenceRecordResult(
        input=meeting,
        space=space,
        conference_record=records[0] if records else None,
    )


def parse_participant_user(raw: Any) -> GoogleMeetParticipantUser | None:
    if not isinstance(raw, dict):
        return None
    return GoogleMeetParticipantUser(
        user=raw.get("user"),
        display_name=raw.get("displayName"),
    )


def parse_participant_payload(payload: dict[str, Any]) -> GoogleMeetParticipant:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Google Meet participant response was missing name")
    return GoogleMeetParticipant(
        name=name,
        earliest_start_time=payload.get("earliestStartTime"),
        latest_end_time=payload.get("latestEndTime"),
        signedin_user=parse_participant_user(payload.get("signedinUser")),
        anonymous_user=parse_participant_user(payload.get("anonymousUser")),
        phone_user=parse_participant_user(payload.get("phoneUser")),
    )


async def list_google_meet_participants(
    *,
    access_token: str,
    conference_record: str,
    page_size: int | None = None,
) -> list[GoogleMeetParticipant]:
    parent = normalize_conference_record_name(conference_record)
    query = {"pageSize": page_size} if page_size else {}
    return await list_google_meet_collection(
        access_token=access_token,
        path=f"{encode_resource_name_for_path(parent)}/participants",
        collection_key="participants",
        query=query,
        audit_context="google-meet.conferenceRecords.participants.list",
        error_prefix="Google Meet conferenceRecords.participants.list",
        transform=parse_participant_payload,
    )


def parse_participant_session_payload(payload: dict[str, Any]) -> GoogleMeetParticipantSession:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Google Meet participant session response was missing name")
    return GoogleMeetParticipantSession(
        name=name,
        start_time=payload.get("startTime"),
        end_time=payload.get("endTime"),
    )


async def list_google_meet_participant_sessions(
    *,
    access_token: str,
    participant: str,
    page_size: int | None = None,
) -> list[GoogleMeetParticipantSession]:
    query = {"pageSize": page_size} if page_size else {}
    return await list_google_meet_collection(
        access_token=access_token,
        path=f"{encode_resource_name_for_path(participant)}/participantSessions",
        collection_key="participantSessions",
        query=query,
        audit_context="google-meet.conferenceRecords.participants.participantSessions.list",
        error_prefix="Google Meet conferenceRecords.participants.participantSessions.list",
        transform=parse_participant_session_payload,
    )


def parse_recording_payload(payload: dict[str, Any]) -> GoogleMeetRecording:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Google Meet recording response was missing name")
    return GoogleMeetRecording(
        name=name,
        start_time=payload.get("startTime"),
        end_time=payload.get("endTime"),
        drive_destination=payload.get("driveDestination"),
    )


async def list_google_meet_recordings(
    *,
    access_token: str,
    conference_record: str,
    page_size: int | None = None,
) -> list[GoogleMeetRecording]:
    parent = normalize_conference_record_name(conference_record)
    query = {"pageSize": page_size} if page_size else {}
    return await list_google_meet_collection(
        access_token=access_token,
        path=f"{encode_resource_name_for_path(parent)}/recordings",
        collection_key="recordings",
        query=query,
        audit_context="google-meet.conferenceRecords.recordings.list",
        error_prefix="Google Meet conferenceRecords.recordings.list",
        transform=parse_recording_payload,
    )


def parse_transcript_payload(payload: dict[str, Any]) -> GoogleMeetTranscript:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Google Meet transcript response was missing name")
    return GoogleMeetTranscript(
        name=name,
        start_time=payload.get("startTime"),
        end_time=payload.get("endTime"),
        docs_destination=payload.get("docsDestination"),
    )


async def list_google_meet_transcripts(
    *,
    access_token: str,
    conference_record: str,
    page_size: int | None = None,
) -> list[GoogleMeetTranscript]:
    parent = normalize_conference_record_name(conference_record)
    query = {"pageSize": page_size} if page_size else {}
    return await list_google_meet_collection(
        access_token=access_token,
        path=f"{encode_resource_name_for_path(parent)}/transcripts",
        collection_key="transcripts",
        query=query,
        audit_context="google-meet.conferenceRecords.transcripts.list",
        error_prefix="Google Meet conferenceRecords.transcripts.list",
        transform=parse_transcript_payload,
    )


def parse_transcript_entry_payload(payload: dict[str, Any]) -> GoogleMeetTranscriptEntry:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Google Meet transcript entry response was missing name")
    return GoogleMeetTranscriptEntry(
        name=name,
        participant=payload.get("participant"),
        text=payload.get("text"),
        language_code=payload.get("languageCode"),
        start_time=payload.get("startTime"),
        end_time=payload.get("endTime"),
    )


async def list_google_meet_transcript_entries(
    *,
    access_token: str,
    transcript: str,
    page_size: int | None = None,
) -> list[GoogleMeetTranscriptEntry]:
    query = {"pageSize": page_size} if page_size else {}
    return await list_google_meet_collection(
        access_token=access_token,
        path=f"{encode_resource_name_for_path(transcript)}/entries",
        collection_key="transcriptEntries",
        query=query,
        audit_context="google-meet.conferenceRecords.transcripts.entries.list",
        error_prefix="Google Meet conferenceRecords.transcripts.entries.list",
        transform=parse_transcript_entry_payload,
    )


def parse_smart_note_payload(payload: dict[str, Any]) -> GoogleMeetSmartNote:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Google Meet smart note response was missing name")
    return GoogleMeetSmartNote(
        name=name,
        start_time=payload.get("startTime"),
        end_time=payload.get("endTime"),
        docs_destination=payload.get("docsDestination"),
    )


async def list_google_meet_smart_notes(
    *,
    access_token: str,
    conference_record: str,
    page_size: int | None = None,
) -> list[GoogleMeetSmartNote]:
    parent = normalize_conference_record_name(conference_record)
    query = {"pageSize": page_size} if page_size else {}
    return await list_google_meet_collection(
        access_token=access_token,
        path=f"{encode_resource_name_for_path(parent)}/smartNotes",
        collection_key="smartNotes",
        query=query,
        audit_context="google-meet.conferenceRecords.smartNotes.list",
        error_prefix="Google Meet conferenceRecords.smartNotes.list",
        transform=parse_smart_note_payload,
    )


@dataclass(slots=True)
class ResolvedConferenceRecordQuery:
    conference_records: list[GoogleMeetConferenceRecord]
    input: str | None = None
    space: GoogleMeetSpace | None = None


async def resolve_conference_record_query(
    *,
    access_token: str,
    meeting: str | None = None,
    conference_record: str | None = None,
    page_size: int | None = None,
    all_conference_records: bool = False,
) -> ResolvedConferenceRecordQuery:
    if conference_record and conference_record.strip():
        rec = await fetch_google_meet_conference_record(
            access_token=access_token,
            conference_record=conference_record.strip(),
        )
        return ResolvedConferenceRecordQuery(
            input=conference_record.strip(),
            conference_records=[rec],
        )
    if not meeting or not meeting.strip():
        raise ValueError("Meeting input or conference record is required")

    space = await fetch_google_meet_space(
        access_token=access_token,
        meeting=meeting.strip(),
    )
    records = await list_google_meet_conference_records(
        access_token=access_token,
        meeting=space.name,
        page_size=page_size if all_conference_records else 1,
        max_items=None if all_conference_records else 1,
    )
    return ResolvedConferenceRecordQuery(
        input=meeting.strip(),
        space=space,
        conference_records=records,
    )


async def get_google_meet_space(
    *,
    config: Any = None,
    access_token: str | None = None,
    space_name: str,
) -> Result[GoogleMeetSpace, Any]:
    token = access_token or (
        config.oauth.access_token if config and hasattr(config, "oauth") and config.oauth else None
    )
    if not token:
        return Err("OAuth access token required.")
    try:
        space = await fetch_google_meet_space(access_token=token, meeting=space_name)
        return Ok(space)
    except Exception as e:
        return Err(e)


async def get_active_google_meet_conference(
    *,
    config: Any = None,
    access_token: str | None = None,
    space_name: str,
) -> Result[GoogleMeetConferenceRecord | None, Any]:
    space_res = await get_google_meet_space(
        config=config, access_token=access_token, space_name=space_name
    )
    if not space_res.is_ok:
        return space_res
    space = space_res.unwrap()
    if space.active_conference and isinstance(space.active_conference, dict):
        conf_name = space.active_conference.get("conferenceRecord")
        if conf_name:
            token = access_token or (
                config.oauth.access_token
                if config and hasattr(config, "oauth") and config.oauth
                else None
            )
            if token:
                try:
                    conf = await fetch_google_meet_conference_record(
                        access_token=token, conference_record=conf_name
                    )
                    return Ok(conf)
                except Exception:
                    return Ok(GoogleMeetConferenceRecord(name=conf_name, space=space.name))
    return Ok(None)


async def get_latest_google_meet_conference_for_space(
    *,
    config: Any = None,
    access_token: str | None = None,
    space_name: str,
) -> Result[GoogleMeetConferenceRecord | None, Any]:
    token = access_token or (
        config.oauth.access_token if config and hasattr(config, "oauth") and config.oauth else None
    )
    if not token:
        return Err("OAuth access token required.")
    try:
        records = await list_google_meet_conference_records(
            access_token=token, meeting=space_name, max_items=1
        )
        return Ok(records[0] if records else None)
    except Exception as e:
        return Err(e)


async def end_active_google_meet_conference(
    *,
    config: Any = None,
    access_token: str | None = None,
    space_name: str,
) -> Result[bool, Any]:
    token = access_token or (
        config.oauth.access_token if config and hasattr(config, "oauth") and config.oauth else None
    )
    if not token:
        return Err("OAuth access token required.")
    try:
        res = await end_google_meet_active_conference(access_token=token, meeting=space_name)
        return Ok(res.ended)
    except Exception as e:
        return Err(e)
