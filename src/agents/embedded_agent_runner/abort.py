"""jarvis.agents.embedded_agent_runner.abort — abort detection.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/abort.ts``.

Public surface (mirrors the OpenClaw
source):

- :func:`is_runner_abort_error` —
  detect abort-shaped errors from
  embedded-agent runner dependencies.

Phase 7.0 — focused minimal port.
"""
from __future__ import annotations

from typing import Any


def is_runner_abort_error(err: Any) -> bool:
    """Return ``True`` for ``AbortError``
    objects or lower-level aborted
    messages. Mirrors
    :func:`isRunnerAbortError`
    (``abort.ts:7-19``)."""
    if not err or not isinstance(err, object):
        return False
    name = getattr(err, "name", "")
    if name == "AbortError":
        return True
    message = getattr(err, "message", "")
    if not isinstance(message, str):
        return False
    return "aborted" in message.lower()


__all__ = ["is_runner_abort_error"]
