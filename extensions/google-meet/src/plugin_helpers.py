"""Helper routines for Google Meet tool actions and gateway RPC handlers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .calendar import (
    GoogleMeetCalendarLookupResult,
    build_google_meet_calendar_day_window,
    find_google_meet_calendar_event,
    list_google_meet_calendar_events,
)
from .config import GoogleMeetConfig
from .create import (
    create_and_join_meet_from_params,
    create_meet_from_params,
)
from .meet import (
    GoogleMeetArtifactsResult,
    GoogleMeetAttendanceResult,
    GoogleMeetSpace,
    build_google_meet_preflight_report,
    end_google_meet_active_conference,
    fetch_google_meet_artifacts,
    fetch_google_meet_attendance,
    fetch_google_meet_space,
    fetch_latest_google_meet_conference_record,
)
from .oauth import (
    ResolvedGoogleMeetAccessToken,
    resolve_google_meet_access_token,
)

__all__ = [
    "build_google_meet_calendar_day_window",
    "build_google_meet_preflight_report",
    "create_and_join_meet_from_params",
    "create_meet_from_params",
    "end_google_meet_active_conference",
    "execute_google_meet_action",
    "export_google_meet_bundle_from_params",
    "fetch_latest_google_meet_conference_record",
    "fetch_resolved_google_meet_artifacts",
    "fetch_resolved_google_meet_attendance",
    "list_google_meet_calendar_events",
    "resolve_artifact_query_from_params",
    "resolve_google_meet_token_from_params",
    "resolve_meeting_from_params",
    "resolve_space_from_params",
]


def resolve_meeting_input(config: GoogleMeetConfig, value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if config.defaults.meeting and config.defaults.meeting.strip():
        return config.defaults.meeting.strip()
    raise ValueError("Meeting input is required")


async def resolve_google_meet_token_from_params(
    config: GoogleMeetConfig,
    raw: dict[str, Any],
) -> ResolvedGoogleMeetAccessToken:
    return await resolve_google_meet_access_token(
        client_id=raw.get("clientId") or config.oauth.client_id,
        client_secret=raw.get("clientSecret") or config.oauth.client_secret,
        refresh_token=raw.get("refreshToken") or config.oauth.refresh_token,
        access_token=raw.get("accessToken") or config.oauth.access_token,
        expires_at=raw.get("expiresAt")
        if isinstance(raw.get("expiresAt"), int)
        else config.oauth.expires_at,
    )


def wants_calendar_lookup(raw: dict[str, Any]) -> bool:
    return raw.get("today") is True or bool(raw.get("event"))


@dataclass(slots=True)
class ResolvedMeetingResult:
    meeting: str
    calendar_event: GoogleMeetCalendarLookupResult | None = None


async def resolve_meeting_from_params(
    *,
    config: GoogleMeetConfig,
    raw: dict[str, Any],
    access_token: str,
) -> ResolvedMeetingResult:
    if wants_calendar_lookup(raw):
        window = build_google_meet_calendar_day_window() if raw.get("today") is True else {}
        calendar_event = await find_google_meet_calendar_event(
            access_token=access_token,
            calendar_id=raw.get("calendarId"),
            event_query=raw.get("event"),
            time_min=window.get("timeMin"),
            time_max=window.get("timeMax"),
        )
        return ResolvedMeetingResult(
            meeting=calendar_event.meeting_uri,
            calendar_event=calendar_event,
        )
    return ResolvedMeetingResult(meeting=resolve_meeting_input(config, raw.get("meeting")))


@dataclass(slots=True)
class ResolvedSpaceResult:
    meeting: str
    token: ResolvedGoogleMeetAccessToken
    space: GoogleMeetSpace
    calendar_event: GoogleMeetCalendarLookupResult | None = None


async def resolve_space_from_params(
    config: GoogleMeetConfig,
    raw: dict[str, Any],
) -> ResolvedSpaceResult:
    token = await resolve_google_meet_token_from_params(config, raw)
    resolved = await resolve_meeting_from_params(
        config=config,
        raw=raw,
        access_token=token.access_token,
    )
    space = await fetch_google_meet_space(
        access_token=token.access_token,
        meeting=resolved.meeting,
    )
    return ResolvedSpaceResult(
        meeting=resolved.meeting,
        token=token,
        space=space,
        calendar_event=resolved.calendar_event,
    )


@dataclass(slots=True)
class ResolvedArtifactQuery:
    token: ResolvedGoogleMeetAccessToken
    meeting: str | None = None
    calendar_event: GoogleMeetCalendarLookupResult | None = None
    conference_record: str | None = None
    page_size: int | None = None
    include_transcript_entries: bool = True
    include_document_bodies: bool = False
    all_conference_records: bool = False
    merge_duplicate_participants: bool = True
    late_after_minutes: int | None = None
    early_before_minutes: int | None = None


async def resolve_artifact_query_from_params(
    config: GoogleMeetConfig,
    raw: dict[str, Any],
) -> ResolvedArtifactQuery:
    meeting = raw.get("meeting") or config.defaults.meeting
    conference_record = raw.get("conferenceRecord")
    token = await resolve_google_meet_token_from_params(config, raw)

    resolved_meeting: str | None = None
    calendar_event: GoogleMeetCalendarLookupResult | None = None

    if conference_record:
        resolved_meeting = meeting
    elif wants_calendar_lookup(raw):
        res = await resolve_meeting_from_params(
            config=config,
            raw=raw,
            access_token=token.access_token,
        )
        resolved_meeting = res.meeting
        calendar_event = res.calendar_event
    else:
        resolved_meeting = meeting

    if not resolved_meeting and not conference_record:
        raise ValueError("Meeting input, calendar lookup, or conferenceRecord required")

    return ResolvedArtifactQuery(
        token=token,
        meeting=resolved_meeting,
        calendar_event=calendar_event,
        conference_record=conference_record,
        page_size=raw.get("pageSize")
        if isinstance(raw.get("pageSize"), int) and raw["pageSize"] > 0
        else None,
        include_transcript_entries=raw.get("includeTranscriptEntries") is not False,
        include_document_bodies=raw.get("includeDocumentBodies") is True,
        all_conference_records=raw.get("includeAllConferenceRecords") is True,
        merge_duplicate_participants=raw.get("mergeDuplicateParticipants") is not False,
        late_after_minutes=raw.get("lateAfterMinutes")
        if isinstance(raw.get("lateAfterMinutes"), int)
        else None,
        early_before_minutes=raw.get("earlyBeforeMinutes")
        if isinstance(raw.get("earlyBeforeMinutes"), int)
        else None,
    )


async def fetch_resolved_google_meet_artifacts(
    query: ResolvedArtifactQuery,
) -> GoogleMeetArtifactsResult:
    return await fetch_google_meet_artifacts(
        access_token=query.token.access_token,
        meeting=query.meeting,
        conference_record=query.conference_record,
        page_size=query.page_size,
        include_transcript_entries=query.include_transcript_entries,
        include_document_bodies=query.include_document_bodies,
        all_conference_records=query.all_conference_records,
    )


async def fetch_resolved_google_meet_attendance(
    query: ResolvedArtifactQuery,
) -> GoogleMeetAttendanceResult:
    return await fetch_google_meet_attendance(
        access_token=query.token.access_token,
        meeting=query.meeting,
        conference_record=query.conference_record,
        page_size=query.page_size,
        all_conference_records=query.all_conference_records,
        merge_duplicate_participants=query.merge_duplicate_participants,
        late_after_minutes=query.late_after_minutes or 5,
        early_before_minutes=query.early_before_minutes or 5,
    )


async def export_google_meet_bundle_from_params(
    config: GoogleMeetConfig,
    raw: dict[str, Any],
) -> dict[str, Any]:
    from .cli_export import (
        build_google_meet_export_manifest,
        google_meet_export_file_names,
        write_meet_export_bundle,
    )

    resolved = await resolve_artifact_query_from_params(config, raw)
    artifacts_fut = fetch_resolved_google_meet_artifacts(resolved)
    attendance_fut = fetch_resolved_google_meet_attendance(resolved)
    artifacts, attendance = await asyncio.gather(artifacts_fut, attendance_fut)

    calendar_id = raw.get("calendarId")
    request_params: dict[str, Any] = {
        "includeTranscriptEntries": resolved.include_transcript_entries,
        "includeDocumentBodies": resolved.include_document_bodies,
        "allConferenceRecords": resolved.all_conference_records,
        "mergeDuplicateParticipants": resolved.merge_duplicate_participants,
    }
    if resolved.meeting:
        request_params["meeting"] = resolved.meeting
    if resolved.conference_record:
        request_params["conferenceRecord"] = resolved.conference_record
    if resolved.calendar_event and resolved.calendar_event.event.id:
        request_params["calendarEventId"] = resolved.calendar_event.event.id
    if resolved.calendar_event and resolved.calendar_event.event.summary:
        request_params["calendarEventSummary"] = resolved.calendar_event.event.summary
    if calendar_id:
        request_params["calendarId"] = calendar_id
    if resolved.page_size is not None:
        request_params["pageSize"] = resolved.page_size
    if resolved.late_after_minutes is not None:
        request_params["lateAfterMinutes"] = resolved.late_after_minutes
    if resolved.early_before_minutes is not None:
        request_params["earlyBeforeMinutes"] = resolved.early_before_minutes

    token_source = "refresh-token" if resolved.token.refreshed else "cached-access-token"
    if raw.get("dryRun") is True:
        return {
            "dryRun": True,
            "manifest": build_google_meet_export_manifest(
                artifacts=artifacts,
                attendance=attendance,
                files=google_meet_export_file_names(),
                request=request_params,
                token_source=token_source,
                calendar_event=resolved.calendar_event,
            ),
            **({"calendarEvent": resolved.calendar_event} if resolved.calendar_event else {}),
            "tokenSource": token_source,
        }

    output_dir = raw.get("outputDir") or raw.get("output")
    bundle = await write_meet_export_bundle(
        output_dir=output_dir,
        artifacts=artifacts,
        attendance=attendance,
        zip_archive=raw.get("zip") is True,
        request=request_params,
        token_source=token_source,
        calendar_event=resolved.calendar_event,
    )
    return {
        **bundle,
        **({"calendarEvent": resolved.calendar_event} if resolved.calendar_event else {}),
        "tokenSource": token_source,
    }


async def execute_google_meet_action(
    *,
    action_name: str,
    params: dict[str, Any],
    raw_config: dict[str, Any],
    runtime: Any = None,
) -> dict[str, Any]:
    """Unified dispatcher for all 18 google_meet tool actions."""
    from .config import resolve_google_meet_config

    cfg_res = resolve_google_meet_config(raw_config)
    cfg = cfg_res.unwrap() if hasattr(cfg_res, "unwrap") else cfg_res

    action = action_name.lower().replace("_", "-")

    if action == "status":
        if runtime:
            status_res = await runtime.get_status(
                session_id=params.get("sessionId") or params.get("session_id")
            )
            return (
                status_res.unwrap()
                if hasattr(status_res, "unwrap")
                else {"active": False, "session": None}
            )
        return {"active": False, "session": None}

    elif action == "join":
        if not runtime:
            return {"ok": False, "error": "GoogleMeetRuntime unavailable"}
        target = params.get("url") or params.get("target") or params.get("meeting") or ""
        join_res = await runtime.join(
            target=target,
            mode=params.get("mode"),
            transport=params.get("transport"),
            audio_in=params.get("audioIn") or params.get("audio_in"),
            audio_out=params.get("audioOut") or params.get("audio_out"),
            profile=params.get("profile") or params.get("browserProfile"),
            node=params.get("node") or params.get("nodeId"),
        )
        return (
            join_res.unwrap()
            if hasattr(join_res, "unwrap")
            else {"ok": False, "error": str(join_res)}
        )

    elif action == "leave":
        if not runtime:
            return {"ok": False, "error": "GoogleMeetRuntime unavailable"}
        leave_res = await runtime.leave(
            session_id=params.get("sessionId") or params.get("session_id")
        )
        return {"ok": leave_res.is_ok if hasattr(leave_res, "is_ok") else True}

    elif action == "speak":
        if not runtime:
            return {"ok": False, "error": "GoogleMeetRuntime unavailable"}
        text = params.get("text") or params.get("message") or ""
        speak_res = await runtime.speak(
            text=text, session_id=params.get("sessionId") or params.get("session_id")
        )
        return {"ok": speak_res.is_ok if hasattr(speak_res, "is_ok") else True, "text": text}

    elif action == "transcript":
        if not runtime:
            return {"transcript": [], "count": 0}
        trans_res = await runtime.get_transcript(
            session_id=params.get("sessionId") or params.get("session_id"),
            limit=params.get("limit") or 50,
        )
        lines = trans_res.unwrap() if hasattr(trans_res, "unwrap") else []
        return {"transcript": lines, "count": len(lines)}

    elif action == "create":
        from .create import create_google_meet_space

        create_res = await create_google_meet_space(
            config=cfg,
            access_type=params.get("accessType") or params.get("access_type"),
            browser_profile=params.get("profile") or params.get("browserProfile"),
            node_id=params.get("node") or params.get("nodeId"),
        )
        return (
            create_res.unwrap()
            if hasattr(create_res, "unwrap")
            else {"ok": False, "error": str(create_res)}
        )

    elif action in ("resolve-space", "resolve_space"):
        from .meet_api import get_google_meet_space

        target = params.get("target") or params.get("meeting") or params.get("space") or ""
        space_name = target if target.startswith("spaces/") else f"spaces/{target}"
        space_res = await get_google_meet_space(config=cfg, space_name=space_name)
        return (
            space_res.unwrap().to_dict()
            if hasattr(space_res, "unwrap") and hasattr(space_res.unwrap(), "to_dict")
            else {"ok": False}
        )

    elif action in ("end-active-conference", "end_active_conference"):
        from .meet_api import end_active_google_meet_conference

        target = params.get("target") or params.get("meeting") or params.get("space") or ""
        space_name = target if target.startswith("spaces/") else f"spaces/{target}"
        end_res = await end_active_google_meet_conference(config=cfg, space_name=space_name)
        return {"ended": end_res.unwrap() if hasattr(end_res, "unwrap") else True}

    elif action == "preflight":
        from .meet import get_google_meet_preflight_report

        rep_res = await get_google_meet_preflight_report(
            config=cfg, space_name=params.get("target")
        )
        return rep_res.unwrap() if hasattr(rep_res, "unwrap") else {}

    elif action in ("calendar-events", "calendar_events"):
        from .calendar import list_upcoming_calendar_events_with_meet

        if not cfg.oauth or not cfg.oauth.access_token:
            return {"error": "OAuth access token required"}
        events_res = await list_upcoming_calendar_events_with_meet(
            token=cfg.oauth.access_token,
            limit=params.get("limit") or 10,
        )
        return {"events": events_res.unwrap() if hasattr(events_res, "unwrap") else []}

    elif action == "latest":
        resolved = await resolve_artifact_query_from_params(cfg, params)
        latest_rec = await fetch_latest_google_meet_conference_record(
            access_token=resolved.token.access_token,
            meeting=resolved.meeting,
        )
        return (
            latest_rec.to_dict()
            if hasattr(latest_rec, "to_dict")
            else {"conferenceRecord": str(latest_rec)}
        )

    elif action in ("recover-current-tab", "recover_current_tab", "recover-tab", "recover_tab"):
        if runtime:
            rec_res = await runtime.recover_current_tab(params)
            return rec_res if isinstance(rec_res, dict) else {"found": False}
        return {"found": False, "error": "GoogleMeetRuntime unavailable"}

    elif action == "artifacts":
        from .meet import get_google_meet_artifacts

        art_res = await get_google_meet_artifacts(
            config=cfg,
            conference_record_name=params.get("conferenceRecord") or params.get("target"),
        )
        return art_res.unwrap() if hasattr(art_res, "unwrap") else {}

    elif action == "attendance":
        from .meet import get_google_meet_attendance

        att_res = await get_google_meet_attendance(
            config=cfg,
            conference_record_name=params.get("conferenceRecord") or params.get("target"),
        )
        return att_res.unwrap() if hasattr(att_res, "unwrap") else {}

    elif action == "export":
        from .cli_export import generate_export_bundle

        bundle_res = await generate_export_bundle(
            config=cfg,
            conference_record_name=params.get("conferenceRecord")
            or params.get("target")
            or "conferenceRecords/default",
        )
        return bundle_res.unwrap() if hasattr(bundle_res, "unwrap") else {}

    elif action == "doctor":
        from .doctor import run_google_meet_doctor

        doc_res = await run_google_meet_doctor(config=raw_config, fix=params.get("fix", False))
        return doc_res.unwrap() if hasattr(doc_res, "unwrap") else {}

    elif action in ("setup", "setup_status"):
        from .runtime_setup import validate_runtime_setup

        setup_res = await validate_runtime_setup(config=raw_config, node_id=params.get("node"))
        return setup_res.unwrap() if hasattr(setup_res, "unwrap") else {}

    elif action in ("test-speech", "test_speech"):
        from .runtime_probes import run_speech_probe

        probe_res = await run_speech_probe(
            text=params.get("text", "Google Meet audio speech probe test."),
            audio_output_device=params.get("audioOut"),
        )
        return probe_res.unwrap() if hasattr(probe_res, "unwrap") else {}

    elif action in ("test-listen", "test_listen"):
        from .runtime_probes import run_listening_probe

        probe_res = await run_listening_probe(
            duration_seconds=params.get("duration", 5.0),
            audio_input_device=params.get("audioIn"),
        )
        return probe_res.unwrap() if hasattr(probe_res, "unwrap") else {}

    return {"ok": False, "error": f"Unknown action: {action_name}"}
