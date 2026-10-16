"""Version, contract, and digest compatibility handshake.

Enforces INV-P10-COMP-001: Incompatible host/worker/runtime contracts or digest
mismatches must prevent worker startup.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any


class WorkerIncompatibleError(RuntimeError):
    """Raised when worker and host fail compatibility handshake."""


@dataclasses.dataclass(frozen=True)
class CompatibilityHandshake:
    """Handshake contract payload containing runtime versions and component digests."""

    host_version: str
    worker_version: str
    protocol_version: str
    event_schema_version: str
    tool_registry_digest: str
    sandbox_policy_digest: str
    runtime_contract_digest: str
    capability_manifest_digest: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def compute_digest(self) -> str:
        payload = self.to_dict()
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclasses.dataclass(frozen=True)
class HandshakeResult:
    """Result of evaluating mutual handshake compatibility."""

    compatible: bool
    rejection_reason: str | None = None
    mismatched_fields: list[str] = dataclasses.field(default_factory=list)
    handshake_digest: str = ""


def verify_compatibility_handshake(
    host_handshake: CompatibilityHandshake,
    worker_handshake: CompatibilityHandshake,
    raise_on_mismatch: bool = True,
) -> HandshakeResult:
    """Verify mutual compatibility between host and worker contracts.

    Enforces INV-P10-COMP-001: any mismatch in protocol, event schema,
    tool registry, sandbox policy, or runtime contract halts worker admission.
    """
    mismatches: list[str] = []

    # Protocol version must match exactly
    if host_handshake.protocol_version != worker_handshake.protocol_version:
        mismatches.append(
            f"protocol_version: host={host_handshake.protocol_version} vs worker={worker_handshake.protocol_version}"
        )

    # Event schema version must match exactly
    if host_handshake.event_schema_version != worker_handshake.event_schema_version:
        mismatches.append(
            f"event_schema_version: host={host_handshake.event_schema_version} vs worker={worker_handshake.event_schema_version}"
        )

    # Tool registry digest must match exactly
    if host_handshake.tool_registry_digest != worker_handshake.tool_registry_digest:
        mismatches.append("tool_registry_digest mismatch")

    # Sandbox policy digest must match exactly
    if host_handshake.sandbox_policy_digest != worker_handshake.sandbox_policy_digest:
        mismatches.append("sandbox_policy_digest mismatch")

    # Runtime contract digest must match exactly
    if host_handshake.runtime_contract_digest != worker_handshake.runtime_contract_digest:
        mismatches.append("runtime_contract_digest mismatch")

    if mismatches:
        reason = f"WORKER_INCOMPATIBLE: {'; '.join(mismatches)}"
        if raise_on_mismatch:
            raise WorkerIncompatibleError(reason)
        return HandshakeResult(
            compatible=False,
            rejection_reason=reason,
            mismatched_fields=mismatches,
            handshake_digest=host_handshake.compute_digest(),
        )

    return HandshakeResult(
        compatible=True,
        rejection_reason=None,
        mismatched_fields=[],
        handshake_digest=host_handshake.compute_digest(),
    )
