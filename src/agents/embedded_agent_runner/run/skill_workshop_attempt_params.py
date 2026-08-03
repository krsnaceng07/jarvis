"""jarvis.agents.embedded_agent_runner.run.skill_workshop_attempt_params — skill-workshop attempt-params helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/skill-workshop-attempt-params.ts``.

Public surface:

- :func:`resolve_skill_workshop_attempt_params`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the resolve-skill-workshop-attempt-params step.
_RESOLVE_SKILL_WORKSHOP_ATTEMPT_PARAMS: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_resolve_skill_workshop_attempt_params_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveSkillWorkshopAttemptParams hook."""
    global _RESOLVE_SKILL_WORKSHOP_ATTEMPT_PARAMS
    _RESOLVE_SKILL_WORKSHOP_ATTEMPT_PARAMS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_skill_workshop_attempt_params(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve the skill-workshop attempt-params.

    Mirrors :func:`resolveSkillWorkshopAttemptParams`
    (``skill-workshop-attempt-params.ts``).
    """
    return _RESOLVE_SKILL_WORKSHOP_ATTEMPT_PARAMS(dict(params or {}))


__all__ = [
    "resolve_skill_workshop_attempt_params",
    "set_resolve_skill_workshop_attempt_params_hook",
]
