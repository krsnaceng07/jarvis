"""TaskFocusManager with focus stack and antecedent pronoun resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import re
from typing import Any


@dataclass
class FocusRecord:
    """Record of a task's activation on the focus stack."""

    task_id: str
    focused_at_utc: str
    entities: dict[str, Any] = field(
        default_factory=dict
    )  # e.g. {"file": "report.pdf", "url": "youtube.com"}


class TaskFocusManager:
    """Manages the active task focus stack and resolves ambiguous pronouns ('it', 'that')."""

    def __init__(self) -> None:
        self._focus_stack: list[str] = []
        self._task_entities: dict[str, dict[str, Any]] = {}
        self._history: list[FocusRecord] = []

    def push_focus(self, task_id: str, entities: dict[str, Any] | None = None) -> None:
        """Set task_id as the primary focus, pushing previous focus down the stack."""
        if task_id in self._focus_stack:
            self._focus_stack.remove(task_id)
        self._focus_stack.append(task_id)

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        ents = dict(entities or {})
        if task_id in self._task_entities:
            self._task_entities[task_id].update(ents)
        else:
            self._task_entities[task_id] = ents

        self._history.append(
            FocusRecord(
                task_id=task_id, focused_at_utc=now_utc, entities=dict(self._task_entities[task_id])
            )
        )

    def pop_focus(self) -> str | None:
        """Pop the current focused task from the top of the stack and return it."""
        if not self._focus_stack:
            return None
        popped = self._focus_stack.pop()
        return popped

    def current_focus(self) -> str | None:
        """Return the task_id at the top of the focus stack, or None if empty."""
        return self._focus_stack[-1] if self._focus_stack else None

    def list_focus_stack(self) -> list[str]:
        """Return a copy of the focus stack from bottom to top."""
        return list(self._focus_stack)

    def register_entities(self, task_id: str, entities: dict[str, Any]) -> None:
        """Attach identifiable entities (files, URLs, processes) to a task context."""
        if task_id not in self._task_entities:
            self._task_entities[task_id] = {}
        self._task_entities[task_id].update(entities)

    def get_entities(self, task_id: str) -> dict[str, Any]:
        return dict(self._task_entities.get(task_id, {}))

    def resolve_antecedent(self, text: str) -> tuple[str | None, str | None]:
        """Resolve pronouns ('it', 'that', 'the file', 'the video') to a task and entity.

        Returns:
            Tuple of (task_id, entity_name_or_value)
        """
        lower = text.lower().strip()
        has_pronoun = bool(re.search(r"\b(it|that|this|them)\b", lower))

        # Check entity keywords
        has_video_ref = bool(re.search(r"\b(video|youtube|song|music|stream)\b", lower))
        has_file_ref = bool(re.search(r"\b(file|document|doc|pdf|script|report|code)\b", lower))

        top_task = self.current_focus()

        # If a specific entity keyword is mentioned, search focus stack top-down
        for tid in reversed(self._focus_stack):
            ents = self._task_entities.get(tid, {})
            if has_video_ref:
                for k, v in ents.items():
                    if any(
                        w in str(k).lower() or w in str(v).lower()
                        for w in ("video", "youtube", "media")
                    ):
                        return tid, str(v)
            if has_file_ref:
                for k, v in ents.items():
                    if any(
                        w in str(k).lower() or w in str(v).lower()
                        for w in ("file", "path", "document", "pdf")
                    ):
                        return tid, str(v)

        # Fallback to top of focus stack if pronouns are present
        if has_pronoun and top_task:
            return top_task, None

        return top_task, None


__all__ = ["FocusRecord", "TaskFocusManager"]
