"""Evidence schema, event hash chain, and audit record definitions for Track 2.1.

Implements tamper-evident sequential event hash chaining:
H_n = SHA256(H_{n-1} || event_type || timestamp_mono || payload_json)
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any

from jarvis_learning.hardware.models import HardwareReality, TestVerdict
from jarvis_learning.invariants_p10 import EvidenceLevel


@dataclasses.dataclass(frozen=True)
class ChainedEvent:
    """Individual event in the tamper-evident audit hash chain."""

    sequence: int
    previous_event_hash: str
    event_type: str
    timestamp_mono_ns: int
    payload: dict[str, Any]
    event_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "previous_event_hash": self.previous_event_hash,
            "event_type": self.event_type,
            "timestamp_mono_ns": self.timestamp_mono_ns,
            "payload": self.payload,
            "event_hash": self.event_hash,
        }


class EventHashChain:
    """Maintains an immutable append-only hash chain of laboratory events."""

    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(self) -> None:
        self._events: list[ChainedEvent] = []
        self._last_hash = self.GENESIS_HASH

    @property
    def events(self) -> list[ChainedEvent]:
        return list(self._events)

    @property
    def latest_hash(self) -> str:
        return self._last_hash

    def append_event(self, event_type: str, payload: dict[str, Any]) -> ChainedEvent:
        """Append a new event and compute next hash in the chain."""
        seq = len(self._events)
        mono_ns = time.monotonic_ns()
        payload_serialized = json.dumps(payload, sort_keys=True)

        hasher = hashlib.sha256()
        hasher.update(self._last_hash.encode("utf-8"))
        hasher.update(event_type.encode("utf-8"))
        hasher.update(str(mono_ns).encode("utf-8"))
        hasher.update(payload_serialized.encode("utf-8"))
        event_hash = hasher.hexdigest()

        event = ChainedEvent(
            sequence=seq,
            previous_event_hash=self._last_hash,
            event_type=event_type,
            timestamp_mono_ns=mono_ns,
            payload=payload,
            event_hash=event_hash,
        )
        self._events.append(event)
        self._last_hash = event_hash
        return event

    def verify_integrity(self) -> bool:
        """Audit the entire chain from genesis to head ensuring zero tampering."""
        current_prev = self.GENESIS_HASH
        for event in self._events:
            if event.previous_event_hash != current_prev:
                return False

            payload_serialized = json.dumps(event.payload, sort_keys=True)
            hasher = hashlib.sha256()
            hasher.update(event.previous_event_hash.encode("utf-8"))
            hasher.update(event.event_type.encode("utf-8"))
            hasher.update(str(event.timestamp_mono_ns).encode("utf-8"))
            hasher.update(payload_serialized.encode("utf-8"))
            expected_hash = hasher.hexdigest()

            if event.event_hash != expected_hash:
                return False

            current_prev = event.event_hash

        return True


@dataclasses.dataclass(frozen=True)
class TestExecutionRecord:
    """Individual test case result with evidence level and ground reality classification."""

    test_id: str
    title: str
    category: str
    evidence_level: EvidenceLevel
    hardware_reality: HardwareReality
    verdict: TestVerdict
    duration_ms: float
    raw_details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "title": self.title,
            "category": self.category,
            "evidence_level": self.evidence_level.value,
            "hardware_reality": self.hardware_reality.value,
            "verdict": self.verdict.value,
            "duration_ms": self.duration_ms,
            "raw_details": self.raw_details,
        }


__all__ = ["ChainedEvent", "EventHashChain", "TestExecutionRecord"]
