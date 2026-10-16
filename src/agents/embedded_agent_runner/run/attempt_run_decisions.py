"""jarvis.agents.embedded_agent_runner.run.attempt_run_decisions — resolve run-level decisions for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.run-decisions.ts``.

Public surface:

Functions:

- :func:`resolve_embedded_attempt_session_write_lock_options`
- :func:`resolve_attempt_stream_auth_profile_id`
- :func:`resolve_unknown_tool_guard_threshold`
- :func:`should_run_llm_output_hooks_for_attempt`
- :func:`resolve_attempt_tool_policy_message_provider`

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


#: Loop-detection shape.
LoopDetection = Dict[str, Any]


#: Installable hook for the resolve-embedded-attempt-session-write-lock-options step.
_RESOLVE_EMBEDDED_ATTEMPT_SESSION_WRITE_LOCK_OPTIONS: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_resolve_embedded_attempt_session_write_lock_options_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveEmbeddedAttemptSessionWriteLockOptions hook."""
    global _RESOLVE_EMBEDDED_ATTEMPT_SESSION_WRITE_LOCK_OPTIONS
    _RESOLVE_EMBEDDED_ATTEMPT_SESSION_WRITE_LOCK_OPTIONS = hook


#: Installable hook for the resolve-attempt-stream-auth-profile-id step.
_RESOLVE_ATTEMPT_STREAM_AUTH_PROFILE_ID: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_resolve_attempt_stream_auth_profile_id_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveAttemptStreamAuthProfileId hook."""
    global _RESOLVE_ATTEMPT_STREAM_AUTH_PROFILE_ID
    _RESOLVE_ATTEMPT_STREAM_AUTH_PROFILE_ID = hook


#: Installable hook for the resolve-unknown-tool-guard-threshold step.
_RESOLVE_UNKNOWN_TOOL_GUARD_THRESHOLD: Callable[
    [Dict[str, Any]], Any
] = lambda _p: 0


def set_resolve_unknown_tool_guard_threshold_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveUnknownToolGuardThreshold hook."""
    global _RESOLVE_UNKNOWN_TOOL_GUARD_THRESHOLD
    _RESOLVE_UNKNOWN_TOOL_GUARD_THRESHOLD = hook


#: Installable hook for the should-run-llm-output-hooks-for-attempt step.
_SHOULD_RUN_LLM_OUTPUT_HOOKS_FOR_ATTEMPT: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_should_run_llm_output_hooks_for_attempt_run_decisions_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldRunLlmOutputHooksForAttempt hook."""
    global _SHOULD_RUN_LLM_OUTPUT_HOOKS_FOR_ATTEMPT
    _SHOULD_RUN_LLM_OUTPUT_HOOKS_FOR_ATTEMPT = hook


#: Installable hook for the resolve-attempt-tool-policy-message-provider step.
_RESOLVE_ATTEMPT_TOOL_POLICY_MESSAGE_PROVIDER: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_resolve_attempt_tool_policy_message_provider_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveAttemptToolPolicyMessageProvider hook."""
    global _RESOLVE_ATTEMPT_TOOL_POLICY_MESSAGE_PROVIDER
    _RESOLVE_ATTEMPT_TOOL_POLICY_MESSAGE_PROVIDER = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_embedded_attempt_session_write_lock_options(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve the embedded-attempt session-write-lock options.

    Mirrors :func:`resolveEmbeddedAttemptSessionWriteLockOptions`
    (``attempt.run-decisions.ts``).
    """
    return _RESOLVE_EMBEDDED_ATTEMPT_SESSION_WRITE_LOCK_OPTIONS(
        dict(params or {})
    )


def resolve_attempt_stream_auth_profile_id(
    params: Dict[str, Any],
) -> Optional[str]:
    """Resolve the attempt stream auth-profile id.

    Mirrors :func:`resolveAttemptStreamAuthProfileId`
    (``attempt.run-decisions.ts``).
    """
    return _RESOLVE_ATTEMPT_STREAM_AUTH_PROFILE_ID(dict(params or {}))


def resolve_unknown_tool_guard_threshold(
    loop_detection: Optional[LoopDetection] = None,
) -> int:
    """Resolve the unknown-tool guard threshold.

    Mirrors :func:`resolveUnknownToolGuardThreshold`
    (``attempt.run-decisions.ts``).
    """
    return int(
        _RESOLVE_UNKNOWN_TOOL_GUARD_THRESHOLD(
            {"loopDetection": loop_detection}
        )
        or 0
    )


def should_run_llm_output_hooks_for_attempt(
    params: Dict[str, Any],
) -> bool:
    """Return True when llm_output hooks should run for this attempt.

    Mirrors :func:`shouldRunLlmOutputHooksForAttempt`
    (``attempt.run-decisions.ts``).
    """
    return _SHOULD_RUN_LLM_OUTPUT_HOOKS_FOR_ATTEMPT(dict(params or {}))


def resolve_attempt_tool_policy_message_provider(
    params: Dict[str, Any],
) -> Any:
    """Resolve the attempt tool-policy message provider.

    Mirrors :func:`resolveAttemptToolPolicyMessageProvider`
    (``attempt.run-decisions.ts``).
    """
    return _RESOLVE_ATTEMPT_TOOL_POLICY_MESSAGE_PROVIDER(dict(params or {}))


__all__ = [
    "LoopDetection",
    "resolve_attempt_stream_auth_profile_id",
    "resolve_attempt_tool_policy_message_provider",
    "resolve_embedded_attempt_session_write_lock_options",
    "resolve_unknown_tool_guard_threshold",
    "set_resolve_attempt_stream_auth_profile_id_hook",
    "set_resolve_attempt_tool_policy_message_provider_hook",
    "set_resolve_embedded_attempt_session_write_lock_options_hook",
    "set_resolve_unknown_tool_guard_threshold_hook",
    "set_should_run_llm_output_hooks_for_attempt_run_decisions_hook",
    "should_run_llm_output_hooks_for_attempt",
]
