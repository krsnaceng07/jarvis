"""jarvis.agents.embedded_agent_runner.transcript_runtime_state — runtime transcript target.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/transcript-runtime-state.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`RuntimeTranscriptScope` — TypedDict for the runtime
  transcript scope.
- :data:`RuntimeTranscriptTarget` — TypedDict for the resolved
  runtime transcript target.
- :func:`resolve_runtime_transcript_read_target` — resolve the
  runtime transcript target for read/probe operations.
- :func:`persist_runtime_transcript_state_mutation` — persist an
  append or migration rewrite for a resolved runtime transcript.

Phase 7.5a — focused minimal port.

The OpenClaw source is tightly coupled to the session-accessor
layer. The Python port keeps the public surface but delegates
the heavy resolution + persistence to installable hooks so the
host can plug in the real session-accessor layer as it lands.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List


#: Runtime transcript scope shape. Mirrors
#: :data:`SessionTranscriptRuntimeScope`` from
#: ``config/sessions/session-accessor.js``.
RuntimeTranscriptScope = Dict[str, Any]


#: Resolved runtime transcript target shape. Mirrors
#: :data:`SessionTranscriptRuntimeTarget`` from
#: ``config/sessions/session-accessor.js``.
RuntimeTranscriptTarget = Dict[str, Any]


#: Resolve hook. The host installs the real
#: :func:`resolveSessionTranscriptRuntimeReadTarget`` when the
#: session-accessor layer lands. The default returns a stub
#: target with an empty session file.
_RESOLVE_RUNTIME_TRANSCRIPT_READ_TARGET: Callable[
    [RuntimeTranscriptScope], Awaitable[RuntimeTranscriptTarget]
] = (
    lambda _scope: _default_resolve_runtime_transcript_target()
)


def _default_resolve_runtime_transcript_target() -> RuntimeTranscriptTarget:
    return {
        "sessionFile": "",
        "sessionKey": None,
        "agentId": None,
        "sessionId": "",
    }


def set_resolve_runtime_transcript_read_target(
    hook: Callable[
        [RuntimeTranscriptScope], Awaitable[RuntimeTranscriptTarget]
    ],
) -> None:
    """Install a custom resolve-runtime-transcript-read-target hook."""
    global _RESOLVE_RUNTIME_TRANSCRIPT_READ_TARGET
    _RESOLVE_RUNTIME_TRANSCRIPT_READ_TARGET = hook


async def resolve_runtime_transcript_read_target(
    scope: RuntimeTranscriptScope,
) -> RuntimeTranscriptTarget:
    """Resolve the runtime transcript target for read/probe operations.

    Mirrors :func:`resolveRuntimeTranscriptReadTarget``
    (``transcript-runtime-state.ts:19-23``).
    """
    return await _RESOLVE_RUNTIME_TRANSCRIPT_READ_TARGET(scope)


#: Persist hook. The host installs the real
#: :func:`persistTranscriptStateMutation`` when the transcript
#: file-state layer lands. The default returns ``None`` (no-op).
_PERSIST_RUNTIME_TRANSCRIPT_STATE_MUTATION: Callable[
    [Dict[str, Any]], Awaitable[None]
] = (
    lambda _params: _default_persist_noop()
)


async def _default_persist_noop() -> None:
    return None


def set_persist_runtime_transcript_state_mutation(
    hook: Callable[[Dict[str, Any]], Awaitable[None]],
) -> None:
    """Install a custom persist-runtime-transcript-state-mutation hook."""
    global _PERSIST_RUNTIME_TRANSCRIPT_STATE_MUTATION
    _PERSIST_RUNTIME_TRANSCRIPT_STATE_MUTATION = hook


async def persist_runtime_transcript_state_mutation(
    *,
    appended_entries: List[Dict[str, Any]],
    state: Dict[str, Any],
    target: RuntimeTranscriptTarget,
) -> None:
    """Persist an append or migration rewrite for a resolved runtime transcript.

    Mirrors :func:`persistRuntimeTranscriptStateMutation``
    (``transcript-runtime-state.ts:28-37``).
    """
    await _PERSIST_RUNTIME_TRANSCRIPT_STATE_MUTATION(
        {
            "appendedEntries": appended_entries,
            "state": state,
            "target": target,
        }
    )


__all__ = [
    "RuntimeTranscriptScope",
    "RuntimeTranscriptTarget",
    "persist_runtime_transcript_state_mutation",
    "resolve_runtime_transcript_read_target",
    "set_persist_runtime_transcript_state_mutation",
    "set_resolve_runtime_transcript_read_target",
]
