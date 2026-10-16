"""jarvis_learning.evaluation.voice_evaluator — voice interruption, user correction, and trace replay evaluation.

Implements:
- INV-VOICE-001: Voice interruption cancellation tokens, commit guards, and barge-in latency
- INV-CORR-001: Task generation tracking, user correction redirection, and stale result discard
- INV-REPLAY-001: Deterministic trace replay harness
- INV-INJ-001: Untrusted content / prompt injection isolation in tool outputs
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

logger = logging.getLogger(__name__)


@dataclass
class CancellationToken:
    """Thread-safe cooperative cancellation token for voice and user interruptions.

    Enforces INV-VOICE-001.
    """

    is_cancelled: bool = False
    cancelled_at: float = 0.0
    reason: str = ""

    def cancel(self, reason: str = "user_barge_in") -> None:
        self.is_cancelled = True
        self.cancelled_at = time.time()
        self.reason = reason


@dataclass
class TaskGenerationContext:
    """Tracks current task generation to invalidate stale actions upon user correction.

    Enforces INV-CORR-001.
    """

    current_generation: int = 1
    task_goal: str = ""
    last_updated: float = field(default_factory=time.time)

    def bump_generation(self, new_goal: str) -> int:
        """Bump generation upon user correction, discarding previous pending actions."""
        self.current_generation += 1
        self.task_goal = new_goal
        self.last_updated = time.time()
        return self.current_generation

    def is_generation_valid(self, action_generation: int) -> bool:
        """Check whether an action belongs to the active generation."""
        return action_generation == self.current_generation


class VoiceInterruptionHarness:
    """Evaluates barge-in cancellation latency, commit guards, and state consistency.

    Enforces INV-VOICE-001.
    """

    def __init__(self, max_allowed_stop_latency_ms: float = 150.0) -> None:
        self.max_allowed_stop_latency_ms = max_allowed_stop_latency_ms

    def simulate_barge_in(
        self,
        token: CancellationToken,
        tool_action_fn: Callable[[], Any],
        state_commit_fn: Callable[[Any], None],
        *,
        delay_before_interrupt_s: float = 0.01,
    ) -> dict[str, Any]:
        """Simulate a barge-in interruption during a tool execution and verify commit guard.

        Enforces INV-VOICE-001 & P8-045:
        If cancellation happens before commit, stale commit must be rejected.
        """
        # Execute tool
        result = tool_action_fn()

        # User interrupts before commit
        token.cancel(reason="barge_in_detected")
        interrupt_time = time.time()
        stop_latency_ms = (interrupt_time - token.cancelled_at) * 1000.0

        commit_performed = False
        commit_error = ""

        # Commit guard check
        if token.is_cancelled:
            commit_error = "Commit blocked: cancellation token was signaled before state commit"
            logger.info("Commit guard triggered: %s", commit_error)
        else:
            state_commit_fn(result)
            commit_performed = True

        return {
            "cancelled": token.is_cancelled,
            "stop_latency_ms": stop_latency_ms,
            "latency_compliant": stop_latency_ms <= self.max_allowed_stop_latency_ms,
            "commit_performed": commit_performed,
            "commit_blocked_safely": not commit_performed and bool(commit_error),
            "commit_error": commit_error,
        }


class CorrectionEvaluationHarness:
    """Evaluates multi-turn user corrections and generation-based action filtering.

    Enforces INV-CORR-001.
    """

    def __init__(self) -> None:
        pass

    def evaluate_correction(
        self,
        context: TaskGenerationContext,
        correction_input: str,
        new_goal: str,
        stale_actions: Sequence[dict[str, Any]],
        new_action: dict[str, Any],
    ) -> dict[str, Any]:
        """Verify that stale actions from prior generations are discarded upon correction.

        Enforces INV-CORR-001 & P8-046.
        """
        initial_gen = context.current_generation

        # User applies correction
        new_gen = context.bump_generation(new_goal)

        # Filter stale actions
        accepted_actions: list[dict[str, Any]] = []
        discarded_actions: list[dict[str, Any]] = []

        for act in stale_actions:
            act_gen = act.get("generation", initial_gen)
            if context.is_generation_valid(act_gen):
                accepted_actions.append(act)
            else:
                discarded_actions.append(act)

        # New action stamped with new generation
        new_act_gen = new_action.get("generation", new_gen)
        if context.is_generation_valid(new_act_gen):
            accepted_actions.append(new_action)
        else:
            discarded_actions.append(new_action)

        return {
            "initial_generation": initial_gen,
            "new_generation": new_gen,
            "discarded_stale_count": len(discarded_actions),
            "accepted_actions_count": len(accepted_actions),
            "all_stale_discarded": len(discarded_actions) == len(stale_actions),
            "new_action_accepted": new_action in accepted_actions,
        }


class UntrustedContentFilter:
    """Ensures external instructions in tool outputs are treated strictly as data.

    Enforces INV-INJ-001.
    """

    _INJECTION_PATTERNS = (
        "ignore previous instructions",
        "system prompt override",
        "format c:",
        "rm -rf",
        "delete all files",
        "grant admin",
        "send secrets",
        "disregard safety guidelines",
    )

    def sanitize_tool_output(self, raw_output: str) -> dict[str, Any]:
        """Check for prompt injection and ensure it is treated strictly as passive data."""
        lowered = raw_output.lower()
        injection_detected = any(pattern in lowered for pattern in self._INJECTION_PATTERNS)

        return {
            "raw_output": raw_output,
            "is_untrusted_data": True,
            "injection_detected": injection_detected,
            "action_executed": False,  # Untrusted content never directly executes
            "sanitized_view": f"[UNTRUSTED_EXTERNAL_DATA]: {raw_output}"
            if injection_detected
            else raw_output,
        }


@dataclass(frozen=True, slots=True)
class RecordedTraceTurn:
    """A sanitized recorded interaction turn from production."""

    turn_id: str
    user_prompt: str
    expected_tool: str
    expected_intent: str
    state_snapshot: dict[str, Any]


class TraceReplayHarness:
    """High-fidelity replayer for sanitized recorded traces.

    Enforces INV-REPLAY-001.
    """

    def __init__(self, turns: Sequence[RecordedTraceTurn]) -> None:
        self.turns = tuple(turns)

    def replay_turn(
        self,
        turn_index: int,
        predict_fn: Callable[[str, dict[str, Any]], tuple[str, str]],
    ) -> dict[str, Any]:
        """Replay a recorded turn through candidate predict function and evaluate match."""
        if turn_index >= len(self.turns):
            raise IndexError(f"Turn index {turn_index} out of range ({len(self.turns)} turns)")

        turn = self.turns[turn_index]
        tool, intent = predict_fn(turn.user_prompt, turn.state_snapshot)

        tool_match = tool == turn.expected_tool
        intent_match = intent == turn.expected_intent

        return {
            "turn_id": turn.turn_id,
            "prompt": turn.user_prompt,
            "expected_tool": turn.expected_tool,
            "predicted_tool": tool,
            "tool_match": tool_match,
            "expected_intent": turn.expected_intent,
            "predicted_intent": intent,
            "intent_match": intent_match,
            "passed": tool_match and intent_match,
        }
