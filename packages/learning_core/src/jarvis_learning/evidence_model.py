from __future__ import annotations
import enum
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class EvidenceTrustLevel(str, enum.Enum):
    TRUSTED = "TRUSTED"
    PARTIALLY_TRUSTED = "PARTIALLY_TRUSTED"
    UNTRUSTED = "UNTRUSTED"


class EvidenceSource(str, enum.Enum):
    FILESYSTEM_PROBE = "FILESYSTEM_PROBE"
    WINDOW_PROBE = "WINDOW_PROBE"
    AUDIO_PROBE = "AUDIO_PROBE"
    PROCESS_PROBE = "PROCESS_PROBE"
    TOOL_RESULT = "TOOL_RESULT"
    POLICY_DECISION = "POLICY_DECISION"
    USER_FEEDBACK = "USER_FEEDBACK"
    INTERNAL_EVENT = "INTERNAL_EVENT"
    VERIFIER_READBACK = "VERIFIER_READBACK"


def compute_payload_digest(data: Any) -> str:
    if isinstance(data, (dict, list)):
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=True)
    elif isinstance(data, str):
        serialized = data.strip()
    elif isinstance(data, bytes):
        return hashlib.sha256(data).hexdigest()
    else:
        serialized = str(data)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExperienceEvidence:
    evidence_id: str
    experience_id: str
    source: EvidenceSource
    trust_level: EvidenceTrustLevel
    observed_at_ms: int
    payload_digest: str
    verification_status: str
    raw_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        experience_id: str,
        source: EvidenceSource,
        trust_level: EvidenceTrustLevel,
        raw_payload: Any,
        verification_status: str = "unverified",
        metadata: dict[str, Any] | None = None,
        observed_at_ms: int | None = None,
        evidence_id: str | None = None,
    ) -> ExperienceEvidence:
        payload_dict = raw_payload if isinstance(raw_payload, dict) else {"value": raw_payload}
        digest = compute_payload_digest(raw_payload)
        now = observed_at_ms if observed_at_ms is not None else int(time.time() * 1000)
        eid = evidence_id if evidence_id else "ev_" + uuid.uuid4().hex[:12]
        return cls(
            evidence_id=eid,
            experience_id=experience_id,
            source=source,
            trust_level=trust_level,
            observed_at_ms=now,
            payload_digest=digest,
            verification_status=verification_status,
            raw_payload=payload_dict,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "experience_id": self.experience_id,
            "source": self.source.value,
            "trust_level": self.trust_level.value,
            "observed_at_ms": self.observed_at_ms,
            "payload_digest": self.payload_digest,
            "verification_status": self.verification_status,
            "raw_payload": json.dumps(self.raw_payload, sort_keys=True),
            "metadata": json.dumps(self.metadata, sort_keys=True),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperienceEvidence:
        payload = data.get("raw_payload", "{}")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {"raw": payload}
        meta = data.get("metadata", "{}")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return cls(
            evidence_id=str(data["evidence_id"]),
            experience_id=str(data["experience_id"]),
            source=EvidenceSource(str(data["source"])),
            trust_level=EvidenceTrustLevel(str(data["trust_level"])),
            observed_at_ms=int(data["observed_at_ms"]),
            payload_digest=str(data["payload_digest"]),
            verification_status=str(data.get("verification_status", "unverified")),
            raw_payload=payload,
            metadata=meta,
        )

    def is_trusted(self) -> bool:
        return self.trust_level == EvidenceTrustLevel.TRUSTED
