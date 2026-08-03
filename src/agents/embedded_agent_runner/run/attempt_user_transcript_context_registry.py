"""jarvis.agents.embedded_agent_runner.run.attempt_user_transcript_context_registry — create the user-transcript context registry.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.user-transcript-context-registry.ts``.

Public surface:

- :func:`create_user_transcript_context_registry`

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: User transcript context registry.
UserTranscriptContextRegistry = Dict[str, Any]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_user_transcript_context_registry() -> UserTranscriptContextRegistry:
    """Create the user-transcript context registry.

    Mirrors :func:`createUserTranscriptContextRegistry`
    (``attempt.user-transcript-context-registry.ts``).
    """
    return {
        "by_session": {},
        "active_session": None,
    }


__all__ = [
    "UserTranscriptContextRegistry",
    "create_user_transcript_context_registry",
]
