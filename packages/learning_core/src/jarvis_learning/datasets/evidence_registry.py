"""jarvis_learning.datasets.evidence_registry — authentic evidence resolution.

Enforces:
- Every dataset sample must resolve to an authentic, registered record in the evidence store.
- Canonical payload must recompute to the exact SHA-256 digest.
- Revoked evidence is rejected.
- UNTRUSTED evidence is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jarvis_learning.evidence_model import EvidenceTrustLevel, compute_payload_digest
from .canonicalization import canonical_hash


@dataclass(frozen=True, slots=True)
class EvidenceResolutionResult:
    is_authentic: bool
    status: str
    recomputed_digest: str
    trust_level: EvidenceTrustLevel
    is_revoked: bool
    evidence_type: str = ""
    error_detail: str = ""


class EvidenceRegistryResolver:
    """Validates that evidence digests resolve to authentic stored evidence."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def resolve_evidence(self, evidence_digest: str) -> EvidenceResolutionResult:
        """Query storage and verify authenticity of the referenced evidence."""
        if not evidence_digest or len(evidence_digest) != 64:
            return EvidenceResolutionResult(
                is_authentic=False,
                status="INVALID_DIGEST_FORMAT",
                recomputed_digest="",
                trust_level=EvidenceTrustLevel.UNTRUSTED,
                is_revoked=False,
                error_detail="Evidence digest must be a 64-character SHA-256 hex string",
            )

        row = None
        if hasattr(self._db, "get_evidence_record"):
            row = self._db.get_evidence_record(evidence_digest)

        if not row:
            return EvidenceResolutionResult(
                is_authentic=False,
                status="EVIDENCE_NOT_FOUND",
                recomputed_digest="",
                trust_level=EvidenceTrustLevel.UNTRUSTED,
                is_revoked=False,
                error_detail=f"No registered evidence record matches digest {evidence_digest}",
            )

        # Check revocation
        is_revoked = bool(row.get("is_revoked", False))
        if is_revoked:
            return EvidenceResolutionResult(
                is_authentic=False,
                status="EVIDENCE_REVOKED",
                recomputed_digest=evidence_digest,
                trust_level=EvidenceTrustLevel.UNTRUSTED,
                is_revoked=True,
                error_detail="Referenced evidence has been revoked",
            )

        # Recompute digest from payload
        raw_payload = row.get("raw_payload", {})
        canon_digest = canonical_hash(raw_payload) if raw_payload else ""
        if canon_digest == evidence_digest:
            recomputed = canon_digest
        else:
            legacy_digest = compute_payload_digest(raw_payload)
            if legacy_digest == evidence_digest:
                recomputed = legacy_digest
            else:
                recomputed = canon_digest or legacy_digest

        if recomputed != evidence_digest:
            return EvidenceResolutionResult(
                is_authentic=False,
                status="DIGEST_MISMATCH",
                recomputed_digest=recomputed,
                trust_level=EvidenceTrustLevel.UNTRUSTED,
                is_revoked=False,
                error_detail=f"Recomputed digest {recomputed} does not match declared digest {evidence_digest}",
            )

        # Map trust level
        trust_val = row.get("trust_level", "TRUSTED")
        if isinstance(trust_val, EvidenceTrustLevel):
            trust = trust_val
        else:
            trust_str = str(trust_val).upper()
            try:
                trust = EvidenceTrustLevel(trust_str)
            except ValueError:
                trust = EvidenceTrustLevel.UNTRUSTED

        if trust == EvidenceTrustLevel.UNTRUSTED:
            return EvidenceResolutionResult(
                is_authentic=False,
                status="EVIDENCE_UNTRUSTED",
                recomputed_digest=recomputed,
                trust_level=trust,
                is_revoked=False,
                error_detail="Evidence has UNTRUSTED status and cannot be approved for training",
            )

        return EvidenceResolutionResult(
            is_authentic=True,
            status="VERIFIED_AUTHENTIC",
            recomputed_digest=recomputed,
            trust_level=trust,
            is_revoked=False,
            evidence_type=row.get("source", ""),
            error_detail="",
        )

    def resolve_digest(self, evidence_digest: str) -> bool:
        """Return True if evidence digest resolves to authentic registered evidence."""
        return self.resolve_evidence(evidence_digest).is_authentic
