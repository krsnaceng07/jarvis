"""jarvis.plugins.meeting_runtime — Shared meeting plugin runtime, participation modes & node commands.

OpenClaw parity: mirrors
``openclaw-main/src/plugin-sdk/meeting-runtime.ts`` and
``openclaw-main/src/meeting-bot/session-types.ts``.

Features:
- `MeetingParticipationMode`: `"agent"` | `"bidi"` | `"transcribe"`
- `MeetingPluginId`: `"google-meet"` | `"teams-meetings"` | `"zoom-meetings"`
- `MEETING_NODE_COMMANDS`: Dict mapping plugin ID to node Chrome command (`googlemeet.chrome`, `teamsmeetings.chrome`, `zoommeetings.chrome`).
- `MeetingSessionState`: Dataclass tracking active meeting session details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MeetingParticipationMode = Literal["agent", "bidi", "transcribe"]
MeetingPluginId = Literal["google-meet", "teams-meetings", "zoom-meetings"]

MEETING_NODE_COMMANDS: dict[MeetingPluginId, str] = {
    "google-meet": "googlemeet.chrome",
    "teams-meetings": "teamsmeetings.chrome",
    "zoom-meetings": "zoommeetings.chrome",
}


@dataclass
class MeetingSessionState:
    session_id: str
    plugin_id: MeetingPluginId
    meeting_url: str
    mode: MeetingParticipationMode = "agent"
    node_id: str | None = None
    in_call: bool = False
    speech_output_verified: bool = False
    manual_action_required: str | None = None


def resolve_meeting_node_command(plugin_id: str) -> str | None:
    """Resolve the required node Chrome command for a meeting plugin ID."""
    norm = plugin_id.strip().lower()
    return MEETING_NODE_COMMANDS.get(norm)  # type: ignore[arg-type]


__all__ = [
    "MEETING_NODE_COMMANDS",
    "MeetingParticipationMode",
    "MeetingPluginId",
    "MeetingSessionState",
    "resolve_meeting_node_command",
]
