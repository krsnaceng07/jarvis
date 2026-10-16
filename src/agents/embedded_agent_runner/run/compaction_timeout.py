"""jarvis.agents.embedded_agent_runner.run.compaction_timeout — resolve the compaction timeout.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/compaction-timeout.ts``.

Public surface:

- :func:`resolve_compaction_timeout_ms`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


#: Default compaction timeout (ms). Mirrors the inline default in
#: ``compaction-timeout.ts``.
DEFAULT_COMPACTION_TIMEOUT_MS: int = 180_000


#: Installable hook for the resolve-compaction-timeout-ms step.
_RESOLVE_COMPACTION_TIMEOUT_MS: Callable[
    [Dict[str, Any]], int
] = lambda _p: DEFAULT_COMPACTION_TIMEOUT_MS


def set_resolve_compaction_timeout_ms_compaction_timeout_hook(
    hook: Callable[[Dict[str, Any]], int],
) -> None:
    """Install a custom resolveCompactionTimeoutMs hook."""
    global _RESOLVE_COMPACTION_TIMEOUT_MS
    _RESOLVE_COMPACTION_TIMEOUT_MS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_compaction_timeout_ms(
    params: Optional[Dict[str, Any]] = None,
) -> int:
    """Resolve the compaction timeout in milliseconds.

    Mirrors :func:`resolveCompactionTimeoutMs`
    (``compaction-timeout.ts``).
    """
    return int(
        _RESOLVE_COMPACTION_TIMEOUT_MS(dict(params or {}))
        or DEFAULT_COMPACTION_TIMEOUT_MS
    )


__all__ = [
    "DEFAULT_COMPACTION_TIMEOUT_MS",
    "resolve_compaction_timeout_ms",
    "set_resolve_compaction_timeout_ms_compaction_timeout_hook",
]
