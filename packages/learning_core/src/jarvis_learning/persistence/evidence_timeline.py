"""Chronological event hash chain for tamper-evident reboot persistence audit trails.

Guarantees integrity of forensic timelines across arming, reboot boundaries, and verification:
- Genesis hash: H_0 = SHA256(transaction_id || pre_boot_session_id)
- Chained hashes: H_n = SHA256(H_{n-1} || sequence || event_name || timestamp || payload)
- Full cryptographic chain verification detects retroactive edits, insertions, or deletions.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any


@dataclasses.dataclass(frozen=True)
class TimelineEvent:
    """Individual immutably chained event in the reboot timeline."""

    sequence: int
    event_name: str
    timestamp_utc: str
    timestamp_epoch: float
    payload: dict[str, Any]
    prev_hash: str
    current_hash: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimelineEvent:
        return cls(
            sequence=int(data["sequence"]),
            event_name=str(data["event_name"]),
            timestamp_utc=str(data["timestamp_utc"]),
            timestamp_epoch=float(data["timestamp_epoch"]),
            payload=dict(data.get("payload", {})),
            prev_hash=str(data["prev_hash"]),
            current_hash=str(data["current_hash"]),
        )


class EvidenceTimeline:
    """Chronological tamper-evident hash-chained event logger."""

    def __init__(self, transaction_id: str, pre_boot_session_id: str) -> None:
        self.transaction_id = transaction_id
        self.pre_boot_session_id = pre_boot_session_id
        # Genesis hash H_0
        genesis_src = f"GENESIS:{transaction_id}:{pre_boot_session_id}".encode("utf-8")
        self.genesis_hash = hashlib.sha256(genesis_src).hexdigest()
        self.events: list[TimelineEvent] = []

    @property
    def latest_hash(self) -> str:
        if not self.events:
            return self.genesis_hash
        return self.events[-1].current_hash

    def record_event(self, event_name: str, payload: dict[str, Any] | None = None) -> TimelineEvent:
        """Append an event to the chronological hash chain."""
        seq = len(self.events) + 1
        prev_h = self.latest_hash
        now_epoch = time.time()
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))
        p = payload or {}

        # Canonical payload serialization
        payload_json = json.dumps(p, sort_keys=True)
        chain_input = f"{prev_h}:{seq}:{event_name}:{now_utc}:{payload_json}".encode("utf-8")
        curr_h = hashlib.sha256(chain_input).hexdigest()

        event = TimelineEvent(
            sequence=seq,
            event_name=event_name,
            timestamp_utc=now_utc,
            timestamp_epoch=now_epoch,
            payload=p,
            prev_hash=prev_h,
            current_hash=curr_h,
        )
        self.events.append(event)
        return event

    def verify_chain(self) -> tuple[bool, str]:
        """Verify unbroken cryptographic integrity of the entire timeline."""
        expected_prev = self.genesis_hash
        for i, ev in enumerate(self.events):
            if ev.sequence != i + 1:
                return (
                    False,
                    f"Sequence discontinuity at index {i}: expected {i + 1}, got {ev.sequence}",
                )

            if ev.prev_hash != expected_prev:
                return (
                    False,
                    f"Broken link at sequence {ev.sequence}: prev_hash {ev.prev_hash} != {expected_prev}",
                )

            payload_json = json.dumps(ev.payload, sort_keys=True)
            chain_input = f"{ev.prev_hash}:{ev.sequence}:{ev.event_name}:{ev.timestamp_utc}:{payload_json}".encode(
                "utf-8"
            )
            recomputed = hashlib.sha256(chain_input).hexdigest()
            if recomputed != ev.current_hash:
                return (
                    False,
                    f"Hash tampering at sequence {ev.sequence}: expected {ev.current_hash}, computed {recomputed}",
                )

            expected_prev = ev.current_hash

        return True, "Hash chain is cryptographically intact"

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "pre_boot_session_id": self.pre_boot_session_id,
            "genesis_hash": self.genesis_hash,
            "event_count": len(self.events),
            "latest_hash": self.latest_hash,
            "events": [ev.to_dict() for ev in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceTimeline:
        timeline = cls(
            transaction_id=str(data["transaction_id"]),
            pre_boot_session_id=str(data["pre_boot_session_id"]),
        )
        for ev_data in data.get("events", []):
            timeline.events.append(TimelineEvent.from_dict(ev_data))
        return timeline


__all__ = ["EvidenceTimeline", "TimelineEvent"]
