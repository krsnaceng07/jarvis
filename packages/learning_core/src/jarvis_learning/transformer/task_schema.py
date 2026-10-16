"""Task schema definitions for Transformer task heads."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """Standardized learning task record for tokenization and task heads."""

    task_id: str
    task_type: str  # "tool_policy", "outcome_prediction", "causal_lm"
    input_text: str
    target_label: int | str | float | None = None
    session_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskRecord:
        return cls(
            task_id=str(data["task_id"]),
            task_type=str(data["task_type"]),
            input_text=str(data["input_text"]),
            target_label=data.get("target_label"),
            session_id=str(data.get("session_id", "")),
            metadata=dict(data.get("metadata", {})),
        )
