"""jarvis.agents.embedded_agent_runner.run.attempt_tool_base_prepare — prepare the tool base for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-tool-base-prepare.ts``.

Public surface:

- :func:`prepare_embedded_attempt_tool_base`

Phase 7.6d-5 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Embedded-attempt tool-base shape.
EmbeddedAttemptToolBase = Dict[str, Any]


#: Installable hook for the tool-base-prepare step.
_PREPARE_TOOL_BASE: Callable[[Dict[str, Any]], Any] = lambda _p: {}


def set_prepare_tool_base_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom prepare-tool-base hook."""
    global _PREPARE_TOOL_BASE
    _PREPARE_TOOL_BASE = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepare_embedded_attempt_tool_base(
    params: Dict[str, Any],
) -> EmbeddedAttemptToolBase:
    """Prepare the tool base for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptToolBase`
    (``attempt-tool-base-prepare.ts``).
    """
    prepared = _PREPARE_TOOL_BASE(dict(params or {}))
    if not isinstance(prepared, dict):
        prepared = {}
    return {
        "toolBase": prepared,
        "toolSearchTargetTranscriptProjections": prepared.get(
            "toolSearchTargetTranscriptProjections"
        ),
    }


__all__ = [
    "EmbeddedAttemptToolBase",
    "prepare_embedded_attempt_tool_base",
    "set_prepare_tool_base_hook",
]
