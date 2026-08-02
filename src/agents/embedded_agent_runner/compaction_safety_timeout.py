"""jarvis.agents.embedded_agent_runner.compaction_safety_timeout — compaction timeout.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compaction-safety-timeout.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`EMBEDDED_COMPACTION_TIMEOUT_MS` —
  the default compaction timeout
  (180 seconds).
- :func:`resolve_compaction_timeout_ms` —
  resolve the compaction timeout
  from config (defaults to
  :data:`EMBEDDED_COMPACTION_TIMEOUT_MS`).
- :func:`compact_with_safety_timeout` —
  wrap a compaction call with a
  safety timeout + abort cleanup.
- :func:`compact_context_engine_with_safety_timeout` —
  wrap a plugin-owned
  ``ContextEngine.compact`` call
  with the same safety timeout.

Phase 7.2a — focused minimal port.
The OpenClaw source's
``withTimeout`` helper from
:mod:`node-host/with-timeout.js`
lands in 7.2b+ (when the node-host
helpers are ported); the Python
port uses :func:`asyncio.wait_for`
for the focused minimal version."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional


_LOG = logging.getLogger(
    "jarvis.agents.embedded_agent_runner.compaction_safety_timeout"
)


#: The default compaction timeout
#: (180 seconds). Mirrors
#: :data:`EMBEDDED_COMPACTION_TIMEOUT_MS`
#: (``compaction-safety-timeout.ts:10``).
EMBEDDED_COMPACTION_TIMEOUT_MS: int = 180_000


def _as_abort_error(reason: Any) -> BaseException:
    """Build an abort-shaped error.
    Mirrors
    :func:`abortErrorFromSignal`
    (``compaction-safety-timeout.ts:12-18`).
    """
    if isinstance(reason, BaseException):
        return reason
    return asyncio.CancelledError()


def _finite_seconds_to_ms(
    value: Any,
    floor_seconds: bool = True,
) -> Optional[int]:
    """Coerce ``value`` (seconds) to
    milliseconds. Mirrors
    :func:`finiteSecondsToTimerSafeMilliseconds`
    from
    ``@openclaw/normalization-core/number-coercion``.
    """
    if not isinstance(value, (int, float)):
        return None
    if value != value:  # NaN
        return None
    seconds = max(0.0, float(value))
    if floor_seconds:
        seconds = int(seconds)
    return int(seconds * 1000)


def resolve_compaction_timeout_ms(config: Optional[dict] = None) -> int:
    """Resolve the compaction timeout
    from config. Mirrors
    :func:`resolveCompactionTimeoutMs`
    (``compaction-safety-timeout.ts:20-26`).
    """
    agents = (config or {}).get("agents", {})
    if not isinstance(agents, dict):
        agents = {}
    defaults = agents.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    compaction = defaults.get("compaction", {})
    if not isinstance(compaction, dict):
        compaction = {}
    timeout_seconds = compaction.get("timeoutSeconds")
    return (
        _finite_seconds_to_ms(timeout_seconds, floor_seconds=True)
        or EMBEDDED_COMPACTION_TIMEOUT_MS
    )


async def compact_with_safety_timeout(
    compact: Callable[[Optional[Any]], Awaitable[Any]],
    timeout_ms: int = EMBEDDED_COMPACTION_TIMEOUT_MS,
    abort_signal: Optional[Any] = None,
    on_cancel: Optional[Callable[[], Any]] = None,
) -> Any:
    """Wrap a compaction call with a
    safety timeout + abort cleanup.
    Mirrors
    :func:`compactWithSafetyTimeout`
    (``compaction-safety-timeout.ts:28-100`).

    Phase 7.2a — focused minimal port
    using :func:`asyncio.wait_for`
    (the OpenClaw source's
    ``withTimeout`` helper lands
    in 7.2b+).
    """
    canceled = False
    cancel_state = {"called": False}

    def _cancel() -> None:
        if cancel_state["called"]:
            return
        cancel_state["called"] = True
        if on_cancel is not None:
            try:
                on_cancel()
            except Exception:
                # Best-effort
                # cancellation hook.
                pass

    async def _runner() -> Any:
        if abort_signal is not None and getattr(
            abort_signal, "aborted", False
        ):
            _cancel()
            raise _as_abort_error(
                getattr(abort_signal, "reason", None)
            )
        return await compact(abort_signal)

    try:
        return await asyncio.wait_for(
            _runner(), timeout=timeout_ms / 1000
        )
    except asyncio.TimeoutError:
        _cancel()
        raise RuntimeError("Compaction timed out") from None


async def compact_context_engine_with_safety_timeout(
    context_engine: Any,
    params: Any,
    timeout_ms: int = EMBEDDED_COMPACTION_TIMEOUT_MS,
    abort_signal: Optional[Any] = None,
) -> Any:
    """Wrap a plugin-owned
    :func:`ContextEngine.compact`
    call with the same safety
    timeout. Mirrors
    :func:`compactContextEngineWithSafetyTimeout`
    (``compaction-safety-timeout.ts:125-138`).
    """
    compact_fn = getattr(context_engine, "compact", None)
    if not callable(compact_fn):
        raise TypeError(
            "context_engine must have a callable compact method"
        )
    return await compact_with_safety_timeout(
        lambda compact_abort_signal: compact_fn(
            compact_abort_signal
            if compact_abort_signal
            else params
        ),
        timeout_ms=timeout_ms,
        abort_signal=abort_signal,
    )


__all__ = [
    "EMBEDDED_COMPACTION_TIMEOUT_MS",
    "compact_context_engine_with_safety_timeout",
    "compact_with_safety_timeout",
    "resolve_compaction_timeout_ms",
]
