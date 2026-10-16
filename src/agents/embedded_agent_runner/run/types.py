"""jarvis.agents.embedded_agent_runner.run.types — shared result + attempt types.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/types.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`EmbeddedRunFastModeParam` — Type alias for the fast-mode
  param (bool or lazy resolver).
- :data:`EmbeddedRunAttemptTrajectoryRecorder` — TypedDict for
  the host-owned trajectory recorder.
- :data:`EmbeddedRunAttemptToolTerminalObservation` — TypedDict
  for a tool-terminal observation.
- :data:`EmbeddedRunAttemptToolTerminalResolution` — TypedDict
  for the resolution returned by the observer.
- :data:`EmbeddedRunAttemptToolTerminalObserver` — callable
  type for the terminal observer.
- :data:`EmbeddedRunContextWindowInfo` — TypedDict for the
  context-window info.
- :data:`EmbeddedRunAttemptBase` — TypedDict for the attempt
  base (omits the fields filled in by the run orchestrator).
- :data:`EmbeddedRunAttemptParams` — TypedDict for the
  attempt params (extends the base with sessionFile, context
  engine, etc.).

Phase 7.6a — focused minimal port.

The OpenClaw source is 250+ lines of TypedDict fields plus
re-exports. The Python port keeps the same shape as
TypedDict-subclass dict-style typing so callers can build the
params dict the same way.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Union


#: Fast-mode param shape. Mirrors
#: :data:`EmbeddedRunFastModeParam`` (``types.ts:55``).
EmbeddedRunFastModeParam = Union[bool, Callable[[], Optional[bool]]]


#: Trajectory recorder shape. Mirrors
#: :class:`EmbeddedRunAttemptTrajectoryRecorder``
#: (``types.ts:89-92``).
EmbeddedRunAttemptTrajectoryRecorder = Dict[str, Any]


#: Tool-terminal observation shape. Mirrors
#: :class:`EmbeddedRunAttemptToolTerminalObservation``
#: (``types.ts:57-75``).
EmbeddedRunAttemptToolTerminalObservation = Dict[str, Any]


#: Tool-terminal resolution shape. Mirrors
#: :class:`EmbeddedRunAttemptToolTerminalResolution``
#: (``types.ts:77-82``).
EmbeddedRunAttemptToolTerminalResolution = Dict[str, Any]


#: Tool-terminal observer callable type. Mirrors
#: :class:`EmbeddedRunAttemptToolTerminalObserver``
#: (``types.ts:84-86``).
EmbeddedRunAttemptToolTerminalObserver = Callable[
    [EmbeddedRunAttemptToolTerminalObservation],
    EmbeddedRunAttemptToolTerminalResolution,
]


#: Context-window info shape. Mirrors
#: :class:`EmbeddedRunContextWindowInfo`` (``types.ts:49-53``).
EmbeddedRunContextWindowInfo = Dict[str, Any]


#: Attempt base (omits fields filled by the run orchestrator).
#: Mirrors ``EmbeddedRunAttemptBase`` (``types.ts:36-47``).
EmbeddedRunAttemptBase = Dict[str, Any]


#: Attempt params. Mirrors :class:`EmbeddedRunAttemptParams``
#: (``types.ts:94-...``).
EmbeddedRunAttemptParams = Dict[str, Any]


__all__ = [
    "EmbeddedRunAttemptBase",
    "EmbeddedRunAttemptParams",
    "EmbeddedRunAttemptToolTerminalObservation",
    "EmbeddedRunAttemptToolTerminalResolution",
    "EmbeddedRunAttemptToolTerminalObserver",
    "EmbeddedRunAttemptTrajectoryRecorder",
    "EmbeddedRunContextWindowInfo",
    "EmbeddedRunFastModeParam",
]
