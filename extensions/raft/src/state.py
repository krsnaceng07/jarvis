"""Raft distributed consensus state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["leader", "follower", "candidate"]


@dataclass(slots=True)
class LogEntry:
    term: int
    index: int
    data: Any


@dataclass(slots=True)
class RaftNodeState:
    node_id: str
    current_term: int = 0
    voted_for: str | None = None
    role: Role = "follower"
    log: list[LogEntry] = field(default_factory=list)
    commit_index: int = 0
    last_applied: int = 0

    def append_log(self, data: Any) -> LogEntry:
        index = len(self.log) + 1
        entry = LogEntry(term=self.current_term, index=index, data=data)
        self.log.append(entry)
        return entry
