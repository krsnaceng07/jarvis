"""Hardened resume cursor model for Track 3.5 client runtime.

Enforces Invariant T35-13: Durable Cursor Independence.
A resume cursor must NOT depend on an obsolete transport connection identifier.
New connections resume authorized subscriptions using journal identity and global sequence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ResumeCursor:
    """Persistent client resume cursor decoupled from ephemeral connection IDs."""

    journal_id: str
    global_seq: int  # Authoritative rowid in EventStore
    subscription_id: str  # Scope of subscription (e.g. session_id or task_id)
    aggregate_versions: dict[str, int] = field(
        default_factory=dict
    )  # {task_id: last_seen_aggregate_version}
    cursor_generation: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "journalId": self.journal_id,
            "globalSeq": self.global_seq,
            "subscriptionId": self.subscription_id,
            "aggregateVersions": dict(self.aggregate_versions),
            "cursorGeneration": self.cursor_generation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResumeCursor:
        return cls(
            journal_id=str(data.get("journalId", "")),
            global_seq=int(data.get("globalSeq", 0)),
            subscription_id=str(data.get("subscriptionId", "")),
            aggregate_versions=dict(data.get("aggregateVersions", {})),
            cursor_generation=int(data.get("cursorGeneration", 1)),
        )

    def advance(
        self, global_seq: int, task_id: str | None = None, aggregate_version: int | None = None
    ) -> ResumeCursor:
        """Return new cursor advanced to next global sequence number."""
        new_aggs = dict(self.aggregate_versions)
        if task_id and aggregate_version is not None:
            new_aggs[task_id] = max(new_aggs.get(task_id, 0), aggregate_version)
        return ResumeCursor(
            journal_id=self.journal_id,
            global_seq=max(self.global_seq, global_seq),
            subscription_id=self.subscription_id,
            aggregate_versions=new_aggs,
            cursor_generation=self.cursor_generation,
        )


class CursorStore:
    """Durable client-side cursor persistence."""

    def __init__(self, file_path: Path | None = None) -> None:
        self.file_path = file_path
        self._memory_cache: dict[str, ResumeCursor] = {}
        if self.file_path and self.file_path.exists():
            self._load()

    def save_cursor(self, cursor: ResumeCursor) -> None:
        self._memory_cache[cursor.subscription_id] = cursor
        if self.file_path:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                raw = {k: v.to_dict() for k, v in self._memory_cache.items()}
                json.dump(raw, f)

    def get_cursor(self, subscription_id: str) -> ResumeCursor | None:
        return self._memory_cache.get(subscription_id)

    def _load(self) -> None:
        if not self.file_path or not self.file_path.exists():
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    self._memory_cache[k] = ResumeCursor.from_dict(v)
        except Exception:
            self._memory_cache = {}


__all__ = ["ResumeCursor", "CursorStore"]
