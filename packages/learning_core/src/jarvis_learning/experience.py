"""jarvis_learning.experience — core data types for the learning system.

Every interaction that JARVIS can learn from is captured as an
``Experience``.  Multi-step tasks are tracked as a ``TaskEpisode``
composed of individual ``TaskStep`` records with per-step credit
assignment.  Post-reflection insights become ``Lesson`` objects.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────


def generate_id() -> str:
    """Return a UUID4 hex string suitable for primary keys."""
    return uuid.uuid4().hex


def now_ms() -> int:
    """Current UTC time as Unix milliseconds."""
    return int(time.time() * 1000)


# ── Step-level tracking ──────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TaskStep:
    """One step within a multi-step task episode."""

    step_index: int
    tool_name: str
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result_summary: str = ""
    step_outcome: Literal["success", "failure", "partial", "skipped"] = "success"
    verification_status: Literal[
        "verified_success", "verified_failure", "unverified", "false_claim"
    ] = "unverified"
    duration_ms: int = 0
    is_recovery_attempt: bool = False
    caused_final_failure: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON storage."""
        return {
            "step_index": self.step_index,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "tool_result_summary": self.tool_result_summary,
            "step_outcome": self.step_outcome,
            "verification_status": self.verification_status,
            "duration_ms": self.duration_ms,
            "is_recovery_attempt": self.is_recovery_attempt,
            "caused_final_failure": self.caused_final_failure,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskStep:
        """Deserialize from a JSON-parsed dict."""
        return cls(
            step_index=data.get("step_index", 0),
            tool_name=data.get("tool_name", ""),
            tool_args=data.get("tool_args", {}),
            tool_result_summary=data.get("tool_result_summary", ""),
            step_outcome=data.get("step_outcome", "success"),
            verification_status=data.get("verification_status", "unverified"),
            duration_ms=data.get("duration_ms", 0),
            is_recovery_attempt=data.get("is_recovery_attempt", False),
            caused_final_failure=data.get("caused_final_failure", False),
        )


@dataclass(frozen=True, slots=True)
class TaskEpisode:
    """A complete multi-step task execution with per-step credit."""

    episode_id: str
    steps: tuple[TaskStep, ...] = ()
    final_outcome: Literal["success", "failure", "partial"] = "success"
    failure_step_index: int | None = None
    recovery_attempted: bool = False
    recovery_succeeded: bool = False

    @property
    def total_steps(self) -> int:
        """Total number of steps in the episode."""
        return len(self.steps)

    @property
    def unnecessary_steps(self) -> int:
        """Count of steps that were skipped or redundant."""
        return sum(1 for s in self.steps if s.step_outcome == "skipped")

    @property
    def success_rate(self) -> float:
        """Fraction of steps that succeeded."""
        if not self.steps:
            return 0.0
        return sum(1 for s in self.steps if s.step_outcome == "success") / len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON storage."""
        return {
            "episode_id": self.episode_id,
            "steps": [s.to_dict() for s in self.steps],
            "final_outcome": self.final_outcome,
            "failure_step_index": self.failure_step_index,
            "recovery_attempted": self.recovery_attempted,
            "recovery_succeeded": self.recovery_succeeded,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskEpisode:
        """Deserialize from a JSON-parsed dict."""
        steps_raw = data.get("steps", [])
        steps = tuple(TaskStep.from_dict(s) for s in steps_raw)
        return cls(
            episode_id=data.get("episode_id", generate_id()),
            steps=steps,
            final_outcome=data.get("final_outcome", "success"),
            failure_step_index=data.get("failure_step_index"),
            recovery_attempted=data.get("recovery_attempted", False),
            recovery_succeeded=data.get("recovery_succeeded", False),
        )


# ── Core experience record ───────────────────────────────────


@dataclass(frozen=True, slots=True)
class Experience:
    """A complete learning experience from one JARVIS interaction."""

    id: str
    created_at: int
    session_id: str
    agent_id: str
    task_id: str = ""
    user_input: str = ""
    interpreted_intent: str = ""
    context_summary: str = ""
    plan: str = ""
    reasoning_summary: str = ""
    selected_tool: str = ""
    tool_arguments: str = ""
    tool_result: str = ""
    success: bool = False
    failure_type: str = ""
    error: str = ""
    user_feedback: str = ""
    implicit_feedback: str = ""
    reward_score: float = 0.0
    reflection: str = ""
    learned_lesson: str = ""
    reusable_strategy: str = ""
    confidence: float = 0.5
    approved_for_training: bool = False
    source_type: str = "llm_inferred"
    verification_status: str = "unverified"
    episode: TaskEpisode | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for SQLite storage."""
        result: dict[str, Any] = {
            "id": self.id,
            "created_at": self.created_at,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "user_input": self.user_input,
            "interpreted_intent": self.interpreted_intent,
            "context_summary": self.context_summary,
            "plan": self.plan,
            "reasoning_summary": self.reasoning_summary,
            "selected_tool": self.selected_tool,
            "tool_arguments": self.tool_arguments,
            "tool_result": self.tool_result,
            "success": self.success,
            "failure_type": self.failure_type,
            "error": self.error,
            "user_feedback": self.user_feedback,
            "implicit_feedback": self.implicit_feedback,
            "reward_score": self.reward_score,
            "reflection": self.reflection,
            "learned_lesson": self.learned_lesson,
            "reusable_strategy": self.reusable_strategy,
            "confidence": self.confidence,
            "approved_for_training": self.approved_for_training,
            "source_type": self.source_type,
            "verification_status": self.verification_status,
        }
        if self.episode is not None:
            result["episode"] = json.dumps(self.episode.to_dict())
        else:
            result["episode"] = ""
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Experience:
        """Deserialize from a SQLite row dict."""
        episode_raw = data.get("episode", "")
        episode: TaskEpisode | None = None
        if episode_raw and isinstance(episode_raw, str):
            episode = TaskEpisode.from_dict(json.loads(episode_raw))
        elif isinstance(episode_raw, dict):
            episode = TaskEpisode.from_dict(episode_raw)
        return cls(
            id=data["id"],
            created_at=data["created_at"],
            session_id=data.get("session_id", ""),
            agent_id=data.get("agent_id", ""),
            task_id=data.get("task_id", ""),
            user_input=data.get("user_input", ""),
            interpreted_intent=data.get("interpreted_intent", ""),
            context_summary=data.get("context_summary", ""),
            plan=data.get("plan", ""),
            reasoning_summary=data.get("reasoning_summary", ""),
            selected_tool=data.get("selected_tool", ""),
            tool_arguments=data.get("tool_arguments", ""),
            tool_result=data.get("tool_result", ""),
            success=bool(data.get("success", False)),
            failure_type=data.get("failure_type", ""),
            error=data.get("error", ""),
            user_feedback=data.get("user_feedback", ""),
            implicit_feedback=data.get("implicit_feedback", ""),
            reward_score=float(data.get("reward_score", 0.0)),
            reflection=data.get("reflection", ""),
            learned_lesson=data.get("learned_lesson", ""),
            reusable_strategy=data.get("reusable_strategy", ""),
            confidence=float(data.get("confidence", 0.5)),
            approved_for_training=bool(data.get("approved_for_training", False)),
            source_type=data.get("source_type", "llm_inferred"),
            verification_status=data.get("verification_status", "unverified"),
            episode=episode,
        )


# ── Post-reflection lesson ───────────────────────────────────


@dataclass(frozen=True, slots=True)
class Lesson:
    """A generalizable insight extracted from experience reflection."""

    id: str
    experience_id: str
    created_at: int
    summary: str
    generalizable: bool = False
    applicable_intents: tuple[str, ...] = ()
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "id": self.id,
            "experience_id": self.experience_id,
            "created_at": self.created_at,
            "summary": self.summary,
            "generalizable": self.generalizable,
            "applicable_intents": json.dumps(list(self.applicable_intents)),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Lesson:
        """Deserialize from a dict."""
        intents = data.get("applicable_intents", "[]")
        if isinstance(intents, str):
            intents = json.loads(intents)
        return cls(
            id=data["id"],
            experience_id=data.get("experience_id", ""),
            created_at=data["created_at"],
            summary=data["summary"],
            generalizable=bool(data.get("generalizable", False)),
            applicable_intents=tuple(intents),
            confidence=float(data.get("confidence", 0.5)),
        )
