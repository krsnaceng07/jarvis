"""jarvis.types.agent_sessions — type stub for OpenClaw's agent-sessions SDK.

OpenClaw parity: mirrors
``openclaw-main/src/types/agent-sessions.d.ts``.

Phase 8.1b — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


#: Placeholder type alias for the agent-sessions SDK record shape.
AgentSessionRecord = Dict[str, Any]

#: Placeholder type alias for the agent-sessions list response.
AgentSessionListResponse = List[AgentSessionRecord]

#: Placeholder type alias for the agent-sessions count response.
AgentSessionCountResponse = Dict[str, int]


__all__ = [
    "AgentSessionRecord",
    "AgentSessionListResponse",
    "AgentSessionCountResponse",
]
