"""jarvis.agents.embedded_agent_runner.run.abortable — wrap a value in an abortable handle.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/abortable.ts``.

Public surface:

- :func:`make_abortable`
- :func:`is_aborted`
- :func:`abort`
- :func:`await_abortable`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional


#: Abortable handle shape.
Abortable = Dict[str, Any]


#: Process-local abortable registry.
_ABORTABLES: Dict[str, "Abortable"] = {}


def _next_handle_id() -> str:
    global _NEXT_HANDLE_ID
    _NEXT_HANDLE_ID += 1
    return f"abortable-{_NEXT_HANDLE_ID}"


_NEXT_HANDLE_ID: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def make_abortable(value: Any) -> Abortable:
    """Wrap ``value`` in an abortable handle.

    Mirrors :func:`makeAbortable` (``abortable.ts``).
    """
    handle_id = _next_handle_id()
    handle: Abortable = {
        "id": handle_id,
        "value": value,
        "aborted": False,
    }
    _ABORTABLES[handle_id] = handle
    return handle


def is_aborted(handle: Any) -> bool:
    """Return True when ``handle`` is aborted.

    Mirrors :func:`isAborted` (``abortable.ts``).
    """
    if not isinstance(handle, dict):
        return False
    return bool(handle.get("aborted"))


def abort(handle: Any) -> None:
    """Abort the given ``handle``.

    Mirrors :func:`abort` (``abortable.ts``).
    """
    if isinstance(handle, dict):
        handle["aborted"] = True


async def await_abortable(
    handle: Any,
    timeout_ms: Optional[int] = None,
) -> Any:
    """Await the value of ``handle``, returning None when aborted.

    Mirrors :func:`awaitAbortable` (``abortable.ts``).
    """
    if not isinstance(handle, dict):
        return None
    value = handle.get("value")
    if asyncio.iscoroutine(value):
        if timeout_ms is not None and timeout_ms > 0:
            try:
                return await asyncio.wait_for(value, timeout=timeout_ms / 1000)
            except asyncio.TimeoutError:
                return None
        return await value
    return value


__all__ = [
    "Abortable",
    "abort",
    "await_abortable",
    "is_aborted",
    "make_abortable",
]
