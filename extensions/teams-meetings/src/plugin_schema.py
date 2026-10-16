"""Tool schema and action definitions for Teams Meetings plugin."""

from __future__ import annotations

from typing import Any

TEAMS_MEETINGS_TOOL_SCHEMA: dict[str, Any] = {
    "name": "teams_meetings",
    "description": (
        "Join Microsoft Teams meetings (work links under teams.microsoft.com/l/meetup-join/... "
        "and consumer links under teams.live.com/meet/...) as a guest in the browser. "
        "Supports join, leave, status, transcript, and speak actions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "join",
                    "leave",
                    "status",
                    "transcript",
                    "speak",
                    "setup",
                    "doctor",
                    "recover_current_tab",
                    "test_speech",
                    "test_listen",
                ],
                "description": "Teams meeting action to perform.",
            },
            "url": {
                "type": "string",
                "description": "Microsoft Teams meeting URL to join or inspect.",
            },
            "target": {
                "type": "string",
                "description": "Alias for url.",
            },
            "mode": {
                "type": "string",
                "enum": ["agent", "bidi", "transcribe"],
                "description": "Audio mode: agent (STT->agent->TTS), bidi (direct voice), or transcribe (observe-only).",
            },
            "transport": {
                "type": "string",
                "enum": ["chrome", "chrome-node"],
                "description": "Participation transport: local chrome or chrome-node host.",
            },
            "text": {
                "type": "string",
                "description": "Text to speak into the meeting.",
            },
            "message": {
                "type": "string",
                "description": "Initial greeting or speech message.",
            },
            "sessionId": {
                "type": "string",
                "description": "Active Teams meeting session ID.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of transcript lines to return.",
            },
            "profile": {
                "type": "string",
                "description": "Browser profile name override.",
            },
            "node": {
                "type": "string",
                "description": "Target node ID for remote execution.",
            },
            "fix": {
                "type": "boolean",
                "description": "Automatically apply fixes during doctor run.",
            },
        },
        "required": ["action"],
    },
}
