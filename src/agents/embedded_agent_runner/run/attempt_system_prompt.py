"""jarvis.agents.embedded_agent_runner.run.attempt_system_prompt — build the system prompt for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-system-prompt.ts``.

Public surface:

- :func:`build_attempt_system_prompt`

Phase 7.6h-1 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from ..system_prompt import build_embedded_system_prompt


def _normalize_attempt_system_prompt_params(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalize attempt-system-prompt params for the default hook.

    The public prepare step passes a wrapper with ``params`` plus
    ``runtimeInfo`` and ``identity``. The default builder wants the
    flattened embedded-system-prompt params shape.
    """
    if not isinstance(params, dict):
        return {}
    params = dict(params or {})
    nested = params.get("params")
    if isinstance(nested, dict):
        normalized = dict(nested)
        if "runtimeInfo" in params:
            normalized["runtimeInfo"] = params["runtimeInfo"]
        if "identity" in params:
            normalized["identity"] = params["identity"]
        return normalized
    return params


def _default_build_attempt_system_prompt(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "text": build_embedded_system_prompt(
            _normalize_attempt_system_prompt_params(dict(params or {}))
        ),
        "report": {},
    }


#: Installable hook for the build-attempt-system-prompt step.
_BUILD_ATTEMPT_SYSTEM_PROMPT: Callable[
    [Dict[str, Any]], Any
] = _default_build_attempt_system_prompt


def set_build_attempt_system_prompt_hook(
    hook: Callable[[Dict[str, Any]], Any] | None,
) -> None:
    """Install a custom buildAttemptSystemPrompt hook."""
    global _BUILD_ATTEMPT_SYSTEM_PROMPT
    _BUILD_ATTEMPT_SYSTEM_PROMPT = (
        _default_build_attempt_system_prompt
        if hook is None
        else hook
    )


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
