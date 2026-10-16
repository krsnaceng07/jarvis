"""Agent-to-Agent (A2A) protocol envelope and capability models."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class A2ATaskEnvelope:
    task_id: str
    source_agent: str
    target_agent: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "action": self.action,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


def create_task_envelope(
    source_agent: str,
    target_agent: str,
    action: str,
    payload: dict[str, Any] | None = None,
) -> A2ATaskEnvelope:
    """Create a new A2A task envelope."""
    return A2ATaskEnvelope(
        task_id=f"task_{uuid.uuid4().hex[:12]}",
        source_agent=source_agent,
        target_agent=target_agent,
        action=action,
        payload=payload or {},
        timestamp=time.time(),
    )
