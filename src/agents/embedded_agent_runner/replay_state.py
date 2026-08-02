"""jarvis.agents.embedded_agent_runner.replay_state — embedded-run replay state.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/replay-state.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`EmbeddedRunReplayState` — TypedDict for the run replay
  state.
- :data:`EmbeddedRunReplayMetadata` — TypedDict for the compact
  replay metadata persisted with run results.
- :func:`create_embedded_run_replay_state` — create a normalized
  replay state from partial caller metadata.
- :func:`merge_embedded_run_replay_state` — merge replay state
  monotonically (unsafe observations cannot be cleared).
- :func:`observe_replay_metadata` — apply result metadata to the
  current replay state.
- :func:`replay_metadata_from_state` — convert internal state
  into the compact metadata persisted with run results.

Phase 7.5a — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


#: Embedded-run replay state. Mirrors
#: :class:`EmbeddedRunReplayState`` (``replay-state.ts:4-7``).
EmbeddedRunReplayState = Dict[str, bool]


#: Compact replay metadata persisted with run results. Mirrors
#: :class:`EmbeddedRunReplayMetadata`` (``replay-state.ts:10-13``).
EmbeddedRunReplayMetadata = Dict[str, bool]


def create_embedded_run_replay_state(
    state: Optional[Dict[str, Any]] = None,
) -> EmbeddedRunReplayState:
    """Create a normalized replay state from partial caller metadata.

    Mirrors :func:`createEmbeddedRunReplayState``
    (``replay-state.ts:16-23``).
    """
    return {
        "replayInvalid": bool(state and state.get("replayInvalid") is True),
        "hadPotentialSideEffects": bool(
            state and state.get("hadPotentialSideEffects") is True
        ),
    }


def merge_embedded_run_replay_state(
    current: EmbeddedRunReplayState,
    next_state: Optional[Dict[str, Any]] = None,
) -> EmbeddedRunReplayState:
    """Merge replay state monotonically.

    Mirrors :func:`mergeEmbeddedRunReplayState``
    (``replay-state.ts:26-38``).
    """
    if not next_state:
        return current
    return {
        "replayInvalid": (
            current.get("replayInvalid", False)
            or next_state.get("replayInvalid") is True
        ),
        "hadPotentialSideEffects": (
            current.get("hadPotentialSideEffects", False)
            or next_state.get("hadPotentialSideEffects") is True
        ),
    }


def observe_replay_metadata(
    current: EmbeddedRunReplayState,
    metadata: Optional[Dict[str, Any]] = None,
) -> EmbeddedRunReplayState:
    """Apply result metadata to the current replay state.

    Mirrors :func:`observeReplayMetadata``
    (``replay-state.ts:41-57``).
    """
    if not metadata:
        # Missing metadata means the caller cannot prove replay
        # safety. Treat as side-effectful.
        return merge_embedded_run_replay_state(
            current,
            {"replayInvalid": True, "hadPotentialSideEffects": True},
        )
    return merge_embedded_run_replay_state(
        current,
        {
            "replayInvalid": not metadata.get("replaySafe", False),
            "hadPotentialSideEffects": bool(
                metadata.get("hadPotentialSideEffects", False)
            ),
        },
    )


def replay_metadata_from_state(
    state: EmbeddedRunReplayState,
) -> EmbeddedRunReplayMetadata:
    """Convert internal state into the compact metadata shape.

    Mirrors :func:`replayMetadataFromState``
    (``replay-state.ts:60-65``).
    """
    return {
        "hadPotentialSideEffects": bool(state.get("hadPotentialSideEffects", False)),
        "replaySafe": (
            not state.get("replayInvalid", False)
            and not state.get("hadPotentialSideEffects", False)
        ),
    }


__all__ = [
    "EmbeddedRunReplayMetadata",
    "EmbeddedRunReplayState",
    "create_embedded_run_replay_state",
    "merge_embedded_run_replay_state",
    "observe_replay_metadata",
    "replay_metadata_from_state",
]
