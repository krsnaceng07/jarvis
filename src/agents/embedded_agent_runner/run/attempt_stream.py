"""jarvis.agents.embedded_agent_runner.run.attempt_stream — install stream guards for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-stream.ts``.

Public surface:

- :func:`install_embedded_attempt_stream_guards`

Phase 7.6d-5 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Embedded-attempt stream-guards shape.
EmbeddedAttemptStreamGuards = Dict[str, Any]


#: Installable hook for the install-stream-guards step.
_INSTALL_STREAM_GUARDS: Callable[[Dict[str, Any]], Any] = lambda _p: {}


def set_install_stream_guards_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom install-stream-guards hook."""
    global _INSTALL_STREAM_GUARDS
    _INSTALL_STREAM_GUARDS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_embedded_attempt_stream_guards(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptStreamGuards:
    """Install the stream guards for an attempt.

    Mirrors :func:`installEmbeddedAttemptStreamGuards`
    (``attempt-stream.ts``).
    """
    guards = _INSTALL_STREAM_GUARDS(dict(input_obj or {}))
    return {
        "guards": guards or {},
        "abortable": (guards or {}).get("abortable"),
    }


__all__ = [
    "EmbeddedAttemptStreamGuards",
    "install_embedded_attempt_stream_guards",
    "set_install_stream_guards_hook",
]
