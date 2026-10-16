"""Cryptographic EvidenceReference model for provenance and auditability.

Ensures that observations, verifications, and state transitions cite concrete,
hash-verified artifacts and records rather than relying on model assertions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
import hashlib
from typing import Any


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Immutable pointer to an audited piece of empirical evidence."""

    evidence_id: str
    evidence_type: str  # e.g., "FILE_HASH", "SQLITE_RECORD", "PROCESS_OUTPUT", "DOM_SNAPSHOT"
    sha256_digest: str
    uri: str
    captured_at_utc: str
    source_node_id: str | None = None
    source_task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def verify_bytes(self, content: bytes) -> bool:
        """Verify that raw bytes match the recorded SHA-256 digest."""
        computed = hashlib.sha256(content).hexdigest()
        return computed.lower() == self.sha256_digest.lower()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceReference:
        return cls(
            evidence_id=data["evidence_id"],
            evidence_type=data["evidence_type"],
            sha256_digest=data["sha256_digest"],
            uri=data["uri"],
            captured_at_utc=data.get(
                "captured_at_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
            source_node_id=data.get("source_node_id"),
            source_task_id=data.get("source_task_id"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create_from_content(
        cls,
        evidence_id: str,
        evidence_type: str,
        content: bytes | str,
        uri: str,
        source_node_id: str | None = None,
        source_task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceReference:
        """Helper to create an evidence record directly from content bytes or string."""
        raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
        digest = hashlib.sha256(raw_bytes).hexdigest()
        return cls(
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            sha256_digest=digest,
            uri=uri,
            captured_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            source_node_id=source_node_id,
            source_task_id=source_task_id,
            metadata=metadata or {},
        )


__all__ = ["EvidenceReference"]
