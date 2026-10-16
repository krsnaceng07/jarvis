"""Conversation session container tracking active tasks, focus, and turns."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Conversation:
    """Session container tracking conversation state, turn history, and task focus."""

    conversation_id: str
    session_id: str
    channel: str
    user_id: str
    active_task_ids: list[str] = field(default_factory=list)
    current_focus_task_id: str | None = None
    turn_ids: list[str] = field(default_factory=list)
    created_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    updated_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_turn(self, turn_id: str) -> Conversation:
        """Append turn ID and update timestamp."""
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        new_turns = list(self.turn_ids)
        if turn_id not in new_turns:
            new_turns.append(turn_id)
        return replace(self, turn_ids=new_turns, updated_at_utc=now_utc)

    def with_task(self, task_id: str, set_focus: bool = True) -> Conversation:
        """Register task ID and optionally set it as current focus."""
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        new_tasks = list(self.active_task_ids)
        if task_id not in new_tasks:
            new_tasks.append(task_id)
        focus = task_id if set_focus else self.current_focus_task_id
        return replace(
            self,
            active_task_ids=new_tasks,
            current_focus_task_id=focus,
            updated_at_utc=now_utc,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Conversation:
        return cls(
            conversation_id=data["conversation_id"],
            session_id=data["session_id"],
            channel=data["channel"],
            user_id=data["user_id"],
            active_task_ids=list(data.get("active_task_ids", [])),
            current_focus_task_id=data.get("current_focus_task_id"),
            turn_ids=list(data.get("turn_ids", [])),
            created_at_utc=data.get(
                "created_at_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
            updated_at_utc=data.get(
                "updated_at_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
            metadata=data.get("metadata", {}),
        )


__all__ = ["Conversation"]
