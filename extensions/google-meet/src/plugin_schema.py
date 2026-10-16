"""Google Meet plugin configuration and tool parameter schemas."""

from __future__ import annotations

from typing import Any

from .config import resolve_google_meet_config


class GoogleMeetConfigSchema:
    @staticmethod
    def parse(value: Any) -> Any:
        return resolve_google_meet_config(value)


google_meet_config_schema = GoogleMeetConfigSchema()
GOOGLE_MEET_CONFIG_SCHEMA = google_meet_config_schema

GOOGLE_MEET_TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "join",
                "create",
                "status",
                "transcript",
                "setup_status",
                "resolve_space",
                "preflight",
                "latest",
                "calendar_events",
                "artifacts",
                "attendance",
                "export",
                "recover_current_tab",
                "leave",
                "end_active_conference",
                "speak",
                "test_speech",
                "test_listen",
            ],
            "description": (
                "Google Meet action to run. create creates and joins by default; "
                "pass join=false to only mint a URL. After a timeout or unclear "
                "browser state, call recover_current_tab before retrying join."
            ),
        },
        "join": {
            "type": "boolean",
            "description": "For action=create, set false to create the URL without joining.",
        },
        "accessType": {
            "type": "string",
            "enum": ["OPEN", "TRUSTED", "RESTRICTED"],
            "description": "For action=create with Google Meet OAuth, configure who can join without knocking.",
        },
        "entryPointAccess": {
            "type": "string",
            "enum": ["ALL", "CREATOR_APP_ONLY"],
            "description": "For action=create with Google Meet OAuth, configure allowed join entry points.",
        },
        "url": {
            "type": "string",
            "description": "Explicit https://meet.google.com/... URL",
        },
        "transport": {
            "type": "string",
            "enum": ["chrome", "chrome-node", "twilio"],
            "description": "Join transport",
        },
        "mode": {
            "type": "string",
            "enum": ["agent", "bidi", "transcribe"],
            "description": (
                "Join mode. agent uses realtime transcription, the configured JARVIS agent, "
                "and regular TTS. bidi uses the realtime voice model directly. transcribe joins observe-only."
            ),
        },
        "dialInNumber": {
            "type": "string",
            "description": (
                "Meet dial-in phone number for Twilio. Required for Twilio unless "
                "twilio.defaultDialInNumber is configured; Meet URLs cannot be dialed directly."
            ),
        },
        "pin": {
            "type": "string",
            "description": "Meet phone PIN for Twilio; # is appended if omitted",
        },
        "dtmfSequence": {
            "type": "string",
            "description": "Explicit DTMF sequence for Twilio",
        },
        "sessionId": {
            "type": "string",
            "description": "Meet session ID",
        },
        "sinceIndex": {
            "type": "integer",
            "minimum": 0,
            "description": "For transcript, resume from the previous response's nextIndex.",
        },
        "message": {
            "type": "string",
            "description": "Realtime instructions to speak now",
        },
        "timeoutMs": {
            "type": "integer",
            "minimum": 1,
            "description": "Probe timeout in milliseconds",
        },
        "meeting": {
            "type": "string",
            "description": "Meet URL, meeting code, or spaces/{id}",
        },
        "today": {
            "type": "boolean",
            "description": "For latest, artifacts, or attendance, find a Meet link on today's calendar.",
        },
        "event": {
            "type": "string",
            "description": "For latest, artifacts, or attendance, find a matching Calendar event.",
        },
        "calendarId": {
            "type": "string",
            "description": "Calendar id for today/event lookup",
        },
        "conferenceRecord": {
            "type": "string",
            "description": "Meet conferenceRecords/{id} resource name or id",
        },
        "pageSize": {
            "type": "integer",
            "minimum": 1,
            "description": "Meet API page size for list actions",
        },
        "includeTranscriptEntries": {
            "type": "boolean",
            "description": "For artifacts, include structured transcript entries",
        },
        "includeDocumentBodies": {
            "type": "boolean",
            "description": "For artifacts/export, export linked transcript and smart-note Google Docs text through Drive.",
        },
        "outputDir": {
            "type": "string",
            "description": "For export, output directory",
        },
        "zip": {
            "type": "boolean",
            "description": "For export, also write a .zip archive",
        },
        "dryRun": {
            "type": "boolean",
            "description": "For export, return the manifest without writing files.",
        },
        "includeAllConferenceRecords": {
            "type": "boolean",
            "description": "For artifacts, attendance, or export with meeting input, fetch all conference records instead of only the latest.",
        },
        "mergeDuplicateParticipants": {
            "type": "boolean",
            "description": "For attendance, merge duplicate participant resources.",
        },
        "lateAfterMinutes": {
            "type": "integer",
            "minimum": 1,
            "description": "For attendance, mark participants late after this many minutes.",
        },
        "earlyBeforeMinutes": {
            "type": "integer",
            "minimum": 1,
            "description": "For attendance, mark early leavers before this many minutes.",
        },
        "accessToken": {
            "type": "string",
            "description": "Access token override",
        },
        "refreshToken": {
            "type": "string",
            "description": "Refresh token override",
        },
        "clientId": {
            "type": "string",
            "description": "OAuth client id override",
        },
        "clientSecret": {
            "type": "string",
            "description": "OAuth client secret override",
        },
        "expiresAt": {
            "type": "number",
            "description": "Cached access token expiry ms",
        },
    },
    "required": ["action"],
}
