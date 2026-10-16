"""jarvis.agents.embedded_agent_runner.run.attempt_startup — prepare skills + diagnostics for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-startup.ts``.

Public surface:

Functions:

- :func:`prepare_embedded_attempt_skills`
- :func:`start_embedded_attempt_diagnostics`

Phase 7.6d-6 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Embedded-attempt skills shape.
EmbeddedAttemptSkills = Dict[str, Any]


#: Embedded-attempt diagnostics shape.
EmbeddedAttemptDiagnostics = Dict[str, Any]


#: Emit-diagnostic run-completed callback.
EmitDiagnosticRunCompleted = Callable[[Dict[str, Any]], None]


#: Installable hook for the prepare-skills step.
_PREPARE_SKILLS: Callable[[Dict[str, Any]], Any] = lambda _p: None


def set_prepare_skills_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom prepare-skills hook."""
    global _PREPARE_SKILLS
    _PREPARE_SKILLS = hook


#: Installable hook for the start-diagnostics step.
_START_DIAGNOSTICS: Callable[[Dict[str, Any]], Any] = lambda _p: {}


def set_start_diagnostics_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom start-diagnostics hook."""
    global _START_DIAGNOSTICS
    _START_DIAGNOSTICS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepare_embedded_attempt_skills(
    params: Dict[str, Any],
) -> EmbeddedAttemptSkills:
    """Prepare the skills for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptSkills`
    (``attempt-startup.ts``).
    """
    skills = _PREPARE_SKILLS(dict(params or {}))
    return {
        "skills": skills or {},
        "skillNames": (skills or {}).get("skillNames") or [],
    }


def start_embedded_attempt_diagnostics(
    params: Dict[str, Any],
) -> EmbeddedAttemptDiagnostics:
    """Start the attempt diagnostics.

    Mirrors :func:`startEmbeddedAttemptDiagnostics`
    (``attempt-startup.ts``).
    """
    started = _START_DIAGNOSTICS(dict(params or {}))
    if not isinstance(started, dict):
        started = {}
    return {
        "runTrace": started.get("runTrace"),
        "diagnosticTrace": started.get("diagnosticTrace"),
    }


__all__ = [
    "EmitDiagnosticRunCompleted",
    "EmbeddedAttemptDiagnostics",
    "EmbeddedAttemptSkills",
    "prepare_embedded_attempt_skills",
    "set_prepare_skills_hook",
    "set_start_diagnostics_hook",
    "start_embedded_attempt_diagnostics",
]
