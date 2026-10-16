"""Cryptographic integrity sealing and strict 10-point L5 qualification gate.

Guarantees tamper detection via SHA-256 digest, operator attestation via HMAC-SHA256,
and strictly prevents simulation or replay results from being mislabeled as L5_REAL_HARDWARE.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
from typing import Any

from jarvis_learning.invariants_p10 import EvidenceLevel


@dataclasses.dataclass(frozen=True)
class L5QualificationChecklist:
    """Strict 10-point qualification gate for claiming L5_REAL_HARDWARE evidence."""

    physical_device_detected: bool
    actual_driver_queried: bool
    actual_workload_executed: bool
    actual_telemetry_observed: bool
    zero_mocks_used: bool
    raw_samples_retained: bool
    monotonic_timing_captured: bool
    environment_fingerprint_captured: bool
    recovery_snapshot_recorded: bool
    reproducible: bool

    @property
    def is_l5_qualified(self) -> bool:
        """All 10 conditions must simultaneously be True to qualify for L5."""
        return (
            self.physical_device_detected
            and self.actual_driver_queried
            and self.actual_workload_executed
            and self.actual_telemetry_observed
            and self.zero_mocks_used
            and self.raw_samples_retained
            and self.monotonic_timing_captured
            and self.environment_fingerprint_captured
            and self.recovery_snapshot_recorded
            and self.reproducible
        )

    def determine_effective_level(self) -> EvidenceLevel:
        """Dynamically compute honest evidence classification."""
        if self.is_l5_qualified:
            return EvidenceLevel.L5_REAL_HARDWARE
        if self.physical_device_detected and self.actual_driver_queried:
            return EvidenceLevel.L4_REAL_WINDOWS_API
        if self.actual_workload_executed:
            return EvidenceLevel.L3_REAL_SUBPROCESS
        return EvidenceLevel.L2_IN_PROCESS_INTEGRATION

    def to_dict(self) -> dict[str, bool]:
        return dataclasses.asdict(self)


class EvidenceIntegritySealer:
    """Computes SHA-256 local integrity digests and HMAC-SHA256 operator attestation."""

    @staticmethod
    def compute_sha256_digest(manifest_dict: dict[str, Any]) -> str:
        """Compute SHA-256 digest over normalized JSON (excluding signature block)."""
        clean_copy = {k: v for k, v in manifest_dict.items() if k != "attestation"}
        serialized = json.dumps(clean_copy, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def sign_attestation(
        digest: str,
        operator_secret: bytes,
        operator_id: str = "JARVIS_OPERATOR",
    ) -> dict[str, str]:
        """Generate an HMAC-SHA256 operator attestation block."""
        signature = hmac.new(operator_secret, digest.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "operator_id": operator_id,
            "algorithm": "HMAC-SHA256",
            "integrity_digest": digest,
            "signature": signature,
        }

    @staticmethod
    def verify_attestation(
        manifest_dict: dict[str, Any],
        operator_secret: bytes,
    ) -> bool:
        """Verify that manifest integrity digest and HMAC-SHA256 signature match."""
        attestation = manifest_dict.get("attestation")
        if not attestation or not isinstance(attestation, dict):
            return False

        computed_digest = EvidenceIntegritySealer.compute_sha256_digest(manifest_dict)
        if computed_digest != attestation.get("integrity_digest"):
            return False

        expected_sig = hmac.new(
            operator_secret, computed_digest.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_sig, attestation.get("signature", ""))


__all__ = ["EvidenceIntegritySealer", "L5QualificationChecklist"]
