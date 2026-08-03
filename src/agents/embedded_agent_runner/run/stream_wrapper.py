"""jarvis.agents.embedded_agent_runner.run.stream_wrapper — generic StreamFn wrapper helper.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/stream-wrapper.ts``.

Public surface:

- :func:`wrap_stream_fn`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: StreamFn shape.
StreamFn = Any


#: Installable hook for the wrap-stream-fn step.
_WRAP_STREAM_FN: Callable[
    [Dict[str, Any]], Any
] = lambda p: p.get("baseFn")


def set_wrap_stream_fn_stream_wrapper_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom wrapStreamFn hook."""
    global _WRAP_STREAM_FN
    _WRAP_STREAM_FN = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def wrap_stream_fn(base_fn: StreamFn) -> StreamFn:
    """Wrap a StreamFn.

    Mirrors :func:`wrapStreamFn` (``stream-wrapper.ts``).
    """
    return _WRAP_STREAM_FN({"baseFn": base_fn})


__all__ = [
    "StreamFn",
    "set_wrap_stream_fn_stream_wrapper_hook",
    "wrap_stream_fn",
]
