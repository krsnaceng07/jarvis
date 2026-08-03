"""jarvis.agents.embedded_agent_runner.run.auth_profile_failure_policy — auth-profile failure-policy helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/auth-profile-failure-policy.ts``.

Public surface:

Functions:

- :func:`format_auth_profile_failure_message`
- :func:`resolve_auth_profile_failure_reason`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Auth profile failure reason.
AuthProfileFailureReason = Optional[str]


#: Installable hook for the format-auth-profile-failure-message step.
_FORMAT_AUTH_PROFILE_FAILURE_MESSAGE: Callable[
    [Dict[str, Any]], str
] = lambda _p: "auth profile failure"


def set_format_auth_profile_failure_message_auth_profile_failure_policy_hook(
    hook: Callable[[Dict[str, Any]], str],
) -> None:
    """Install a custom formatAuthProfileFailureMessage hook."""
    global _FORMAT_AUTH_PROFILE_FAILURE_MESSAGE
    _FORMAT_AUTH_PROFILE_FAILURE_MESSAGE = hook


#: Installable hook for the resolve-auth-profile-failure-reason step.
_RESOLVE_AUTH_PROFILE_FAILURE_REASON: Callable[
    [Dict[str, Any]], AuthProfileFailureReason
] = lambda _p: None


def set_resolve_auth_profile_failure_reason_auth_profile_failure_policy_hook(
    hook: Callable[[Dict[str, Any]], AuthProfileFailureReason],
) -> None:
    """Install a custom resolveAuthProfileFailureReason hook."""
    global _RESOLVE_AUTH_PROFILE_FAILURE_REASON
    _RESOLVE_AUTH_PROFILE_FAILURE_REASON = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_auth_profile_failure_message(params: Dict[str, Any]) -> str:
    """Format the auth-profile failure message.

    Mirrors :func:`formatAuthProfileFailureMessage`
    (``auth-profile-failure-policy.ts``).
    """
    return _FORMAT_AUTH_PROFILE_FAILURE_MESSAGE(dict(params or {}))


def resolve_auth_profile_failure_reason(
    params: Dict[str, Any],
) -> AuthProfileFailureReason:
    """Resolve the auth-profile failure reason.

    Mirrors :func:`resolveAuthProfileFailureReason`
    (``auth-profile-failure-policy.ts``).
    """
    return _RESOLVE_AUTH_PROFILE_FAILURE_REASON(dict(params or {}))


__all__ = [
    "AuthProfileFailureReason",
    "format_auth_profile_failure_message",
    "resolve_auth_profile_failure_reason",
    "set_format_auth_profile_failure_message_auth_profile_failure_policy_hook",
    "set_resolve_auth_profile_failure_reason_auth_profile_failure_policy_hook",
]
