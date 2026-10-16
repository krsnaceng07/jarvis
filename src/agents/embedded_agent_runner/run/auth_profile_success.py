"""jarvis.agents.embedded_agent_runner.run.auth_profile_success — mark + report a successful auth-profile binding.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/auth-profile-success.ts``.

Public surface:

Functions:

- :func:`mark_embedded_run_auth_profile_success`
- :func:`report_embedded_run_successful_auth_binding`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Installable hook for the mark-embedded-run-auth-profile-success step.
_MARK_EMBEDDED_RUN_AUTH_PROFILE_SUCCESS: Callable[
    [Dict[str, Any]], None
] = lambda _p: None


def set_mark_embedded_run_auth_profile_success_auth_profile_success_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom markEmbeddedRunAuthProfileSuccess hook."""
    global _MARK_EMBEDDED_RUN_AUTH_PROFILE_SUCCESS
    _MARK_EMBEDDED_RUN_AUTH_PROFILE_SUCCESS = hook


#: Installable hook for the report-embedded-run-successful-auth-binding step.
_REPORT_EMBEDDED_RUN_SUCCESSFUL_AUTH_BINDING: Callable[
    [Dict[str, Any]], None
] = lambda _p: None


def set_report_embedded_run_successful_auth_binding_auth_profile_success_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom reportEmbeddedRunSuccessfulAuthBinding hook."""
    global _REPORT_EMBEDDED_RUN_SUCCESSFUL_AUTH_BINDING
    _REPORT_EMBEDDED_RUN_SUCCESSFUL_AUTH_BINDING = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def mark_embedded_run_auth_profile_success(
    params: Dict[str, Any],
) -> None:
    """Mark an embedded-run auth-profile as successful.

    Mirrors :func:`markEmbeddedRunAuthProfileSuccess`
    (``auth-profile-success.ts``).
    """
    _MARK_EMBEDDED_RUN_AUTH_PROFILE_SUCCESS(dict(params or {}))


def report_embedded_run_successful_auth_binding(
    params: Dict[str, Any],
) -> None:
    """Report a successful auth binding for an embedded run.

    Mirrors :func:`reportEmbeddedRunSuccessfulAuthBinding`
    (``auth-profile-success.ts``).
    """
    _REPORT_EMBEDDED_RUN_SUCCESSFUL_AUTH_BINDING(dict(params or {}))


__all__ = [
    "mark_embedded_run_auth_profile_success",
    "report_embedded_run_successful_auth_binding",
    "set_mark_embedded_run_auth_profile_success_auth_profile_success_hook",
    "set_report_embedded_run_successful_auth_binding_auth_profile_success_hook",
]
