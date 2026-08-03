"""jarvis.agents.embedded_agent_runner.run.attempt_transcript_helpers — transcript helpers for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-transcript-helpers.ts``.

Public surface:

Functions:

- :func:`flush_session_manager_transcript`
- :func:`repair_attempt_tool_use_result_pairing`
- :func:`remove_trailing_mid_turn_precheck_assistant_error`
- :func:`normalize_compaction_recovery_transcript_tail`
- :func:`load_attempt_session_entry_after_quota_maintenance` (async)
- :func:`resolve_attempt_trajectory_session_file` (async)
- :func:`resolve_existing_attempt_transcript_state` (async)

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the flush-session-manager-transcript step.
_FLUSH_SESSION_MANAGER_TRANSCRIPT: Callable[
    [Dict[str, Any]], None
] = lambda _p: None


def set_flush_session_manager_transcript_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom flushSessionManagerTranscript hook."""
    global _FLUSH_SESSION_MANAGER_TRANSCRIPT
    _FLUSH_SESSION_MANAGER_TRANSCRIPT = hook


#: Installable hook for the repair-tool-use-result-pairing step.
_REPAIR_TOOL_USE_RESULT_PAIRING: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_repair_attempt_tool_use_result_pairing_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom repairAttemptToolUseResultPairing hook."""
    global _REPAIR_TOOL_USE_RESULT_PAIRING
    _REPAIR_TOOL_USE_RESULT_PAIRING = hook


#: Installable hook for the remove-trailing-mid-turn-precheck-assistant-error step.
_REMOVE_TRAILING_MID_TURN_PRECHECK_ASSISTANT_ERROR: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_remove_trailing_mid_turn_precheck_assistant_error_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom removeTrailingMidTurnPrecheckAssistantError hook."""
    global _REMOVE_TRAILING_MID_TURN_PRECHECK_ASSISTANT_ERROR
    _REMOVE_TRAILING_MID_TURN_PRECHECK_ASSISTANT_ERROR = hook


#: Installable hook for the normalize-compaction-recovery-transcript-tail step.
_NORMALIZE_COMPACTION_RECOVERY_TRANSCRIPT_TAIL: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_normalize_compaction_recovery_transcript_tail_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom normalizeCompactionRecoveryTranscriptTail hook."""
    global _NORMALIZE_COMPACTION_RECOVERY_TRANSCRIPT_TAIL
    _NORMALIZE_COMPACTION_RECOVERY_TRANSCRIPT_TAIL = hook


#: Installable hook for the load-attempt-session-entry-after-quota-maintenance step.
_LOAD_ATTEMPT_SESSION_ENTRY_AFTER_QUOTA_MAINTENANCE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_load_attempt_session_entry_after_quota_maintenance_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom loadAttemptSessionEntryAfterQuotaMaintenance hook."""
    global _LOAD_ATTEMPT_SESSION_ENTRY_AFTER_QUOTA_MAINTENANCE
    _LOAD_ATTEMPT_SESSION_ENTRY_AFTER_QUOTA_MAINTENANCE = hook


#: Installable hook for the resolve-attempt-trajectory-session-file step.
_RESOLVE_ATTEMPT_TRAJECTORY_SESSION_FILE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_resolve_attempt_trajectory_session_file_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom resolveAttemptTrajectorySessionFile hook."""
    global _RESOLVE_ATTEMPT_TRAJECTORY_SESSION_FILE
    _RESOLVE_ATTEMPT_TRAJECTORY_SESSION_FILE = hook


#: Installable hook for the resolve-existing-attempt-transcript-state step.
_RESOLVE_EXISTING_ATTEMPT_TRANSCRIPT_STATE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_resolve_existing_attempt_transcript_state_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom resolveExistingAttemptTranscriptState hook."""
    global _RESOLVE_EXISTING_ATTEMPT_TRANSCRIPT_STATE
    _RESOLVE_EXISTING_ATTEMPT_TRANSCRIPT_STATE = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def flush_session_manager_transcript(
    session_manager: Any,
) -> None:
    """Flush the session-manager transcript.

    Mirrors :func:`flushSessionManagerTranscript`
    (``attempt-transcript-helpers.ts``).
    """
    _FLUSH_SESSION_MANAGER_TRANSCRIPT({"sessionManager": session_manager})


def repair_attempt_tool_use_result_pairing(
    params: Dict[str, Any],
) -> Any:
    """Repair the tool-use/result pairing in the attempt transcript.

    Mirrors :func:`repairAttemptToolUseResultPairing`
    (``attempt-transcript-helpers.ts``).
    """
    return _REPAIR_TOOL_USE_RESULT_PAIRING(dict(params or {}))


def remove_trailing_mid_turn_precheck_assistant_error(
    params: Dict[str, Any],
) -> Any:
    """Remove the trailing mid-turn precheck assistant error.

    Mirrors :func:`removeTrailingMidTurnPrecheckAssistantError`
    (``attempt-transcript-helpers.ts``).
    """
    return _REMOVE_TRAILING_MID_TURN_PRECHECK_ASSISTANT_ERROR(
        dict(params or {})
    )


def normalize_compaction_recovery_transcript_tail(
    params: Dict[str, Any],
) -> Any:
    """Normalize the compaction-recovery transcript tail.

    Mirrors :func:`normalizeCompactionRecoveryTranscriptTail`
    (``attempt-transcript-helpers.ts``).
    """
    return _NORMALIZE_COMPACTION_RECOVERY_TRANSCRIPT_TAIL(
        dict(params or {})
    )


async def load_attempt_session_entry_after_quota_maintenance(
    params: Dict[str, Any],
) -> Any:
    """Load the attempt session entry after quota maintenance.

    Mirrors :func:`loadAttemptSessionEntryAfterQuotaMaintenance`
    (``attempt-transcript-helpers.ts``).
    """
    return await _maybe_await(
        _LOAD_ATTEMPT_SESSION_ENTRY_AFTER_QUOTA_MAINTENANCE(
            dict(params or {})
        )
    )


async def resolve_attempt_trajectory_session_file(
    params: Dict[str, Any],
) -> Any:
    """Resolve the attempt trajectory session file.

    Mirrors :func:`resolveAttemptTrajectorySessionFile`
    (``attempt-transcript-helpers.ts``).
    """
    return await _maybe_await(
        _RESOLVE_ATTEMPT_TRAJECTORY_SESSION_FILE(dict(params or {}))
    )


async def resolve_existing_attempt_transcript_state(
    params: Dict[str, Any],
) -> Any:
    """Resolve the existing attempt transcript state.

    Mirrors :func:`resolveExistingAttemptTranscriptState`
    (``attempt-transcript-helpers.ts``).
    """
    return await _maybe_await(
        _RESOLVE_EXISTING_ATTEMPT_TRANSCRIPT_STATE(dict(params or {}))
    )


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "flush_session_manager_transcript",
    "load_attempt_session_entry_after_quota_maintenance",
    "normalize_compaction_recovery_transcript_tail",
    "remove_trailing_mid_turn_precheck_assistant_error",
    "repair_attempt_tool_use_result_pairing",
    "resolve_attempt_trajectory_session_file",
    "resolve_existing_attempt_transcript_state",
    "set_flush_session_manager_transcript_hook",
    "set_load_attempt_session_entry_after_quota_maintenance_hook",
    "set_normalize_compaction_recovery_transcript_tail_hook",
    "set_remove_trailing_mid_turn_precheck_assistant_error_hook",
    "set_repair_attempt_tool_use_result_pairing_hook",
    "set_resolve_attempt_trajectory_session_file_hook",
    "set_resolve_existing_attempt_transcript_state_hook",
]
