"""jarvis_learning.datasets.lineage — full sample traceability.

Every training sample carries a ``SampleLineage`` that traces it back
to the original experience, tool call, session, and model that
produced it.  This enables debugging bad model behavior:

    bad prediction → training sample → experience → tool call → session
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..experience import now_ms


@dataclass(frozen=True, slots=True)
class SampleLineage:
    """Traces a training sample back to its origin."""

    sample_id: str
    experience_id: str
    episode_id: str = ""
    step_index: int | None = None
    source_session_id: str = ""
    source_timestamp: int = 0
    source_tool_call_id: str = ""
    source_agent_id: str = ""
    source_model_id: str = ""
    created_by: str = "dataset_builder"
    approval_reason: str = ""
    rejection_reason: str = ""

    def trace_path(self) -> str:
        """Human-readable trace: sample → experience → session."""
        parts = [f"sample:{self.sample_id}"]
        if self.experience_id:
            parts.append(f"exp:{self.experience_id}")
        if self.episode_id:
            parts.append(f"ep:{self.episode_id}")
        if self.step_index is not None:
            parts.append(f"step:{self.step_index}")
        if self.source_session_id:
            parts.append(f"session:{self.source_session_id}")
        return " ← ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "experience_id": self.experience_id,
            "episode_id": self.episode_id,
            "step_index": self.step_index,
            "source_session_id": self.source_session_id,
            "source_timestamp": self.source_timestamp,
            "source_tool_call_id": self.source_tool_call_id,
            "source_agent_id": self.source_agent_id,
            "source_model_id": self.source_model_id,
            "created_by": self.created_by,
            "approval_reason": self.approval_reason,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SampleLineage:
        return cls(
            sample_id=d.get("sample_id", ""),
            experience_id=d.get("experience_id", ""),
            episode_id=d.get("episode_id", ""),
            step_index=d.get("step_index"),
            source_session_id=d.get("source_session_id", ""),
            source_timestamp=d.get("source_timestamp", 0),
            source_tool_call_id=d.get("source_tool_call_id", ""),
            source_agent_id=d.get("source_agent_id", ""),
            source_model_id=d.get("source_model_id", ""),
            created_by=d.get("created_by", "dataset_builder"),
            approval_reason=d.get("approval_reason", ""),
            rejection_reason=d.get("rejection_reason", ""),
        )

    @classmethod
    def from_experience(
        cls,
        sample_id: str,
        experience_id: str,
        *,
        session_id: str = "",
        agent_id: str = "",
        episode_id: str = "",
        step_index: int | None = None,
        created_by: str = "dataset_builder",
        approval_reason: str = "",
    ) -> SampleLineage:
        """Build lineage from an Experience's fields."""
        return cls(
            sample_id=sample_id,
            experience_id=experience_id,
            episode_id=episode_id,
            step_index=step_index,
            source_session_id=session_id,
            source_timestamp=now_ms(),
            source_agent_id=agent_id,
            created_by=created_by,
            approval_reason=approval_reason,
        )
