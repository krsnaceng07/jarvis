"""jarvis.types.microsoft_teams_sdk — type stub for the Microsoft Teams SDK.

OpenClaw parity: mirrors
``openclaw-main/src/types/microsoft-teams-sdk.d.ts``.

Phase 8.1b — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


#: Placeholder type alias for the Teams activity envelope.
TeamsActivity = Dict[str, Any]

#: Placeholder type alias for the Teams bot client.
TeamsBotClient = Any

#: Placeholder type alias for the Teams conversation reference.
TeamsConversationReference = Dict[str, Any]

#: Placeholder type alias for the Teams turn context.
TeamsTurnContext = Any


__all__ = [
    "TeamsActivity",
    "TeamsBotClient",
    "TeamsConversationReference",
    "TeamsTurnContext",
]
