"""jarvis.agents.embedded_agent_runner.post_compaction_loop_guard — post-compaction loop guard.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/post-compaction-loop-guard.ts``.

Public surface (mirrors the OpenClaw
source):

- :func:`create_post_compaction_loop_guard` —
  build a stateful post-compaction
  loop detector for one embedded
  run.
- :class:`PostCompactionLoopPersistedError` —
  error raised when the guard
  aborts a run.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from jarvis.config.types_tools import ToolLoopPostCompactionGuardConfig



_LOG = logging.getLogger(
    "jarvis.agents.embedded_agent_runner.post_compaction_loop_guard"
)


#: The default window size (the
#: number of attempts to observe
#: after compaction). Mirrors
#: :data:`DEFAULT_WINDOW_SIZE`
#: (``post-compaction-loop-guard.ts:15``).
DEFAULT_WINDOW_SIZE: int = 3


def _as_positive_int(
    value: Optional[int], fallback: int
) -> int:
    """Coerce ``value`` to a positive
    integer, falling back to
    ``fallback`` when invalid.
    Mirrors :func:`asPositiveInt`
    (``post-compaction-loop-guard.ts:48-53``)."""
    if not isinstance(value, int) or value <= 0:
        return fallback
    return value


def _build_verdict_from_history(
    call: dict,
    matches_count: int,
    armed_after: bool,
    remaining_attempts: int,
    window_size: int,
) -> dict:
    """Build a "should abort" verdict
    when the loop persists. Mirrors
    the OpenClaw source's abort
    verdict block."""
    tool_name = call.get("toolName", "unknown")
    return {
        "shouldAbort": True,
        "armed": armed_after,
        "remainingAttempts": remaining_attempts,
        "detector": "compaction_loop_persisted",
        "count": matches_count,
        "toolName": tool_name,
        "message": (
            f"CRITICAL: tool {tool_name} repeated "
            f"{matches_count} times with identical arguments "
            f"and identical results within {window_size} "
            f"attempts after auto-compaction. The compaction "
            f"did not break the loop. Aborting to prevent "
            f"runaway resource use."
        ),
    }


def _build_normal_verdict(
    armed_after: bool, remaining_attempts: int
) -> dict:
    """Build a "don't abort" verdict.
    Mirrors the OpenClaw source's
    normal verdict block."""
    return {
        "shouldAbort": False,
        "armed": armed_after,
        "remainingAttempts": remaining_attempts,
    }


def create_post_compaction_loop_guard(
    config: Optional[ToolLoopPostCompactionGuardConfig] = None,
    options: Optional[dict] = None,
) -> dict:
    """Build a stateful post-compaction
    loop detector for one embedded
    run. Mirrors
    :func:`createPostCompactionLoopGuard`
    (``post-compaction-loop-guard.ts:56-119`).

    The returned guard has three
    methods:
    - ``armPostCompaction()`` — arm
      the guard for a fresh post-
      compaction window.
    - ``observe(call)`` — record a
      tool call. Returns a verdict
      with ``shouldAbort`` /
      ``armed`` / ``remainingAttempts``
      (and an extra ``detector`` /
      ``count`` / ``toolName`` /
      ``message`` when ``shouldAbort``
      is True).
    - ``snapshot()`` — return a
      snapshot of the armed state.
    """
    options = options or {}
    config = config or {}
    state: dict = {
        "enabled": bool(options.get("enabled", True)),
        "windowSize": _as_positive_int(
            config.get("windowSize")
            if isinstance(config, dict)
            else None,
            DEFAULT_WINDOW_SIZE,
        ),
        "remainingAttempts": 0,
        "history": [],
    }

    def arm_post_compaction() -> None:
        state["remainingAttempts"] = state["windowSize"]
        state["history"] = []
        if state["enabled"]:
            _LOG.info(
                f"post-compaction guard armed for "
                f"{state['windowSize']} attempts"
            )

    def observe(call: dict) -> dict:
        if not state["enabled"]:
            return _build_normal_verdict(False, 0)
        if state["remainingAttempts"] <= 0:
            return _build_normal_verdict(False, 0)
        state["remainingAttempts"] -= 1
        state["history"].append(call)
        armed_after = state["remainingAttempts"] > 0
        # Compare full tool name +
        # args + result. Repeated
        # args alone can be
        # legitimate polling;
        # identical results after
        # compaction prove the
        # compression did not
        # change the loop.
        matches = [
            entry
            for entry in state["history"]
            if entry.get("toolName") == call.get("toolName")
            and entry.get("argsHash") == call.get("argsHash")
            and entry.get("resultHash") == call.get("resultHash")
        ]
        if len(matches) >= state["windowSize"]:
            _LOG.error(
                f"post-compaction loop persisted: "
                f"tool={call.get('toolName')} repeated "
                f"{len(matches)} times with identical "
                f"args+result post-compaction"
            )
            return _build_verdict_from_history(
                call=call,
                matches_count=len(matches),
                armed_after=armed_after,
                remaining_attempts=state["remainingAttempts"],
                window_size=state["windowSize"],
            )
        return _build_normal_verdict(
            armed_after, state["remainingAttempts"]
        )

    def snapshot() -> dict:
        return {
            "armed": state["remainingAttempts"] > 0,
            "remainingAttempts": state["remainingAttempts"],
        }

    return {
        "armPostCompaction": arm_post_compaction,
        "observe": observe,
        "snapshot": snapshot,
    }


class PostCompactionLoopPersistedError(Exception):
    """Error raised when the
    post-compaction loop guard aborts
    a run. Mirrors
    :class:`PostCompactionLoopPersistedError`
    (``post-compaction-loop-guard.ts:122-150``)."""

    def __init__(
        self,
        message: str,
        details: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.name = "PostCompactionLoopPersistedError"
        if details is None:
            details = {}
        self.detector = details.get(
            "detector", "compaction_loop_persisted"
        )
        self.count = details.get("count", 0)
        self.tool_name = details.get("toolName", "")

    @classmethod
    def from_verdict(
        cls, verdict: dict
    ) -> "PostCompactionLoopPersistedError":
        """Build an error from a guard
        verdict. Mirrors
        :func:`PostCompactionLoopPersistedError.fromVerdict`
        (``post-compaction-loop-guard.ts:142-150``)."""
        return cls(
            verdict.get("message", "loop persisted"),
            {
                "detector": verdict.get(
                    "detector", "compaction_loop_persisted"
                ),
                "count": verdict.get("count", 0),
                "toolName": verdict.get("toolName", ""),
            },
        )


__all__ = [
    "DEFAULT_WINDOW_SIZE",
    "PostCompactionLoopPersistedError",
    "create_post_compaction_loop_guard",
]
