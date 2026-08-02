"""jarvis.agents.embedded_agent_runner.failure_signal — failure-signal resolution.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/failure-signal.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`FAILURE_SIGNAL_CODES` —
  the canonical failure-signal
  codes.
- :func:`resolve_failure_signal_code` —
  validate a code against the
  canonical list.
- :func:`resolve_embedded_run_failure_signal` —
  build a failure-signal block
  from a tool error.

Phase 7.0 — focused minimal port.
The full :func:`isExecLikeToolName`
helper lands in 7.4+ (when
:mod:`tool_error_summary` is ported).
"""
from __future__ import annotations

from typing import Any, Optional

from .types import EmbeddedRunFailureSignal


#: The canonical failure-signal codes.
#: Mirrors
#: :data:`FAILURE_SIGNAL_CODES`
#: (``failure-signal.ts:14``).
FAILURE_SIGNAL_CODES: tuple = (
    "SYSTEM_RUN_DENIED",
    "INVALID_REQUEST",
)


def resolve_failure_signal_code(
    value: Optional[str],
) -> Optional[str]:
    """Validate ``value`` against the
    canonical list. Mirrors
    :func:`resolveFailureSignalCode`
    (``failure-signal.ts:16-25``)."""
    if not value:
        return None
    for code in FAILURE_SIGNAL_CODES:
        if value == code:
            return code
    return None


def _is_exec_like_tool_name(name: Optional[str]) -> bool:
    """Focused minimal port of
    :func:`isExecLikeToolName`
    (``tool-error-summary.ts``). The
    full helper lands in 7.4+.

    The OpenClaw source marks the
    following tools as exec-like:
    ``bash``, ``exec``, ``run``,
    ``shell``, ``process``,
    ``command``.
    """
    if not name:
        return False
    lowered = name.lower()
    return lowered in (
        "bash",
        "exec",
        "run",
        "shell",
        "process",
        "command",
    )


def _normalize_optional_string(value: Any) -> Optional[str]:
    """Coerce ``value`` to a stripped
    string, or ``None`` if it isn't a
    non-empty string. Mirrors
    :func:`normalizeOptionalString`."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def resolve_embedded_run_failure_signal(
    params: dict,
) -> Optional[EmbeddedRunFailureSignal]:
    """Build a failure-signal block
    from the last exec-like tool
    error. Mirrors
    :func:`resolveEmbeddedRunFailureSignal`
    (``failure-signal.ts:28-52`).

    Returns ``None`` when the trigger
    isn't ``"cron"`` or the last
    tool error isn't an exec-like
    tool with a recognised
    failure-signal code.
    """
    if params.get("trigger") != "cron":
        return None
    last_tool_error = params.get("lastToolError")
    if not last_tool_error or not isinstance(last_tool_error, dict):
        return None
    tool_name = last_tool_error.get("toolName")
    if not _is_exec_like_tool_name(tool_name):
        return None
    code = resolve_failure_signal_code(
        _normalize_optional_string(last_tool_error.get("errorCode"))
    )
    if not code:
        return None
    message = (
        _normalize_optional_string(last_tool_error.get("error"))
        or code
    )
    return {
        "kind": "execution_denied",
        "source": "tool",
        "toolName": tool_name,
        "code": code,
        "message": message,
        "fatalForCron": True,
    }


__all__ = [
    "FAILURE_SIGNAL_CODES",
    "resolve_embedded_run_failure_signal",
    "resolve_failure_signal_code",
]
