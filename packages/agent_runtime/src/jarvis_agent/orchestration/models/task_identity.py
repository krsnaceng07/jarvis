"""Composite TaskIdentity for lineage, generation, and epoch tracking.

Prevents context confusion when multiple tasks overlap or pronouns ("it", "that")
are used across multiple active lines of work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskIdentity:
    """Composite, immutable identity fingerprint of a task execution context."""

    task_id: str
    conversation_id: str
    session_id: str
    root_task_id: str
    turn_id: str
    creation_event_id: str
    parent_task_id: str | None = None
    generation: int = 1
    lifecycle_epoch: int = 1

    @property
    def is_root(self) -> bool:
        return self.parent_task_id is None or self.task_id == self.root_task_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskIdentity:
        return cls(
            task_id=data["task_id"],
            conversation_id=data["conversation_id"],
            session_id=data["session_id"],
            root_task_id=data.get("root_task_id", data["task_id"]),
            turn_id=data["turn_id"],
            creation_event_id=data.get("creation_event_id", ""),
            parent_task_id=data.get("parent_task_id"),
            generation=data.get("generation", 1),
            lifecycle_epoch=data.get("lifecycle_epoch", 1),
        )


__all__ = ["TaskIdentity"]
