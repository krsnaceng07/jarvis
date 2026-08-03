"""jarvis.agents.embedded_agent_runner.run.attempt_abort_settle_timeout — resolve the embedded abort-settle timeout.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.abort-settle-timeout.ts``.

Public surface:

- :func:`resolve_embedded_abort_settle_timeout_ms`

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Default abort-settle timeout (ms). Mirrors the inline default in
#: ``attempt.abort-settle-timeout.ts``.
DEFAULT_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS: int = 5_000


#: Installable hook for the resolve-embedded-abort-settle-timeout step.
_RESOLVE_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS: Callable[
    [Dict[str, Any]], int
] = lambda _p: DEFAULT_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS


def set_resolve_embedded_abort_settle_timeout_ms_hook(
    hook: Callable[[Dict[str, Any]], int],
) -> None:
    """Install a custom resolveEmbeddedAbortSettleTimeoutMs hook."""
    global _RESOLVE_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS
    _RESOLVE_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_embedded_abort_settle_timeout_ms(
    params: Optional[Dict[str, Any]] = None,
) -> int:
    """Resolve the embedded abort-settle timeout in milliseconds.

    Mirrors :func:`resolveEmbeddedAbortSettleTimeoutMs`
    (``attempt.abort-settle-timeout.ts``).
    """
    return int(
        _RESOLVE_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS(dict(params or {}))
        or DEFAULT_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS
    )


__all__ = [
    "DEFAULT_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS",
    "resolve_embedded_abort_settle_timeout_ms",
    "set_resolve_embedded_abort_settle_timeout_ms_hook",
]
