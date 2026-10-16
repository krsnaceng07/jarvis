"""Reef flow packet delivery, receipts, and audit trail."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FlowPacket:
    flow_id: str = field(default_factory=lambda: f"flow_{uuid.uuid4().hex[:10]}")
    sender_id: str = ""
    recipient_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def compute_hash(self) -> str:
        s = f"{self.flow_id}:{self.sender_id}:{self.recipient_id}:{self.timestamp}"
        return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class FlowReceipt:
    flow_id: str
    recipient_id: str
    status: str = "delivered"
    receipt_time: float = field(default_factory=time.time)
