"""jarvis.agents.embedded_agent_runner.run.attempt_system_prompt — build the system prompt for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-system-prompt.ts``.

Public surface:

- :func:`build_attempt_system_prompt`

Phase 7.6h-1 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the build-attempt-system-prompt step.
_BUILD_ATTEMPT_SYSTEM_PROMPT: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {"text": "", "report": {}}


def set_build_attempt_system_prompt_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildAttemptSystemPrompt hook."""
    global _BUILD_ATTEMPT_SYSTEM_PROMPT
    _BUILD_ATTEMPT_SYSTEM_PROMPT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_attempt_system_prompt(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the system prompt for an attempt.

    Mirrors :func:`buildAttemptSystemPrompt`
    (``attempt-system-prompt.ts``).
    """
    built = _BUILD_ATTEMPT_SYSTEM_PROMPT(dict(params or {}))
    if not isinstance(built, dict):
        built = {}
    return {
        "text": built.get("text"),
        "report": built.get("report") or {},
    }


__all__ = [
    "build_attempt_system_prompt",
    "set_build_attempt_system_prompt_hook",
]
