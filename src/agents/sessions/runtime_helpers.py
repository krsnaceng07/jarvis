"""jarvis.agents.sessions.runtime_helpers — small runtime helpers.

The OpenClaw source's
``agent-session-execution.ts`` +
``agent-session-inspection.ts`` import
several small helpers from
``@openclaw/ai/internal/runtime`` +
``llm/utils/``:

- :func:`is_context_overflow` —
  classifies an assistant error as a
  context overflow.
- :func:`classify_rate_limit_window` —
  returns a short / long-window hint
  for a rate-limit error.
- :func:`is_retryable_assistant_error` —
  returns ``True`` for retryable
  errors (overloaded, rate limit,
  server errors).
- :func:`sleep` — cancellable async
  sleep with an ``AbortSignal``.

The Python port ships its own
conservative implementations here so
the modules can be imported without
the OpenClaw runtime package.

Phase 6.12e — STUB. The per-provider
heuristics land in Phase 6.13+ (the
per-model context-window + per-error
classifier table is large).
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional


def is_context_overflow(message: Any, context_window: int) -> bool:
    """Whether the error indicates a
    context overflow (model was given
    more tokens than its window can
    hold). Mirrors ``isContextOverflow``
    (``@openclaw/ai/internal/runtime``).

    Phase 6.12e — STUB. The OpenClaw
    source's provider-specific check
    lands in Phase 6.13+. The Python
    port returns ``True`` when the
    ``errorMessage`` contains the
    canonical "context" or
    "maximum context length" phrases.
    """
    if not isinstance(message, dict):
        msg = getattr(message, "error_message", None) or getattr(
            message, "errorMessage", None
        )
    else:
        msg = message.get("errorMessage") or message.get("error_message")
    if not msg:
        return False
    msg_lower = str(msg).lower()
    if context_window <= 0:
        return False
    return (
        "context" in msg_lower
        or "context_length" in msg_lower
        or "context length" in msg_lower
        or "maximum context" in msg_lower
    )


def classify_rate_limit_window(error_message: str) -> dict:
    """Classify a rate-limit error as
    short-window (seconds) or
    long-window (minutes). Mirrors
    ``classifyRateLimitWindow``
    (``llm/utils/rate-limit-window.js``).

    Returns
    -------
    dict
        ``{"kind": "none" | "short" |
        "long", "retryAfterSeconds"?: float}``
    """
    if not error_message:
        return {"kind": "none"}
    msg_lower = str(error_message).lower()
    # Short-window signals.
    if "rate limit" in msg_lower or "ratelimit" in msg_lower:
        if "requests per minute" in msg_lower or "rpm" in msg_lower:
            return {"kind": "short", "retryAfterSeconds": 30.0}
        if "tokens per minute" in msg_lower or "tpm" in msg_lower:
            return {"kind": "short", "retryAfterSeconds": 30.0}
        if "per second" in msg_lower:
            return {"kind": "short", "retryAfterSeconds": 5.0}
        return {"kind": "short", "retryAfterSeconds": 30.0}
    # Long-window signals (daily / monthly
    # quotas).
    if "quota" in msg_lower or "limit exceeded" in msg_lower:
        return {"kind": "long", "retryAfterSeconds": 3600.0}
    return {"kind": "none"}


def is_retryable_assistant_error(message: Any) -> bool:
    """Whether the assistant error is
    retryable. Mirrors
    ``isRetryableAssistantError``
    (``llm/utils/retry.js``).

    Phase 6.12e — STUB. The OpenClaw
    source's full classifier lands in
    Phase 6.13+. The Python port
    returns ``True`` for the canonical
    retryable phrases.
    """
    if isinstance(message, dict):
        stop_reason = message.get("stopReason") or message.get("stop_reason")
        err = message.get("errorMessage") or message.get("error_message")
    else:
        stop_reason = getattr(message, "stop_reason", None)
        err = getattr(message, "error_message", None) or getattr(
            message, "errorMessage", None
        )
    if stop_reason != "error" or not err:
        return False
    err_lower = str(err).lower()
    retryable_phrases = (
        "rate limit",
        "ratelimit",
        "overloaded",
        "timeout",
        "timed out",
        "server error",
        "internal server error",
        "service unavailable",
        "temporarily unavailable",
        "try again",
        "429",
        "500",
        "502",
        "503",
        "504",
    )
    return any(phrase in err_lower for phrase in retryable_phrases)


async def sleep(delay_ms: int, signal: Optional[Any] = None) -> None:
    """Async sleep for ``delay_ms``
    milliseconds. Mirrors ``sleep``
    (``utils/sleep.js``).

    When ``signal`` is an object with an
    ``aborted`` attribute, raises
    :class:`asyncio.CancelledError` on
    abort (mirroring the OpenClaw source's
    behaviour).
    """
    if delay_ms <= 0:
        return
    try:
        await asyncio.wait_for(asyncio.sleep(delay_ms / 1000), timeout=delay_ms / 1000)
    except asyncio.TimeoutError:
        pass
    if signal is not None and getattr(signal, "aborted", False):
        raise asyncio.CancelledError("Sleep aborted")


__all__ = [
    "classify_rate_limit_window",
    "is_context_overflow",
    "is_retryable_assistant_error",
    "sleep",
]
