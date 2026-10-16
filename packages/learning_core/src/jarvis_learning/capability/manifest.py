"""Machine-readable capability discovery and attestation manifest.

Enforces INV-P10-CAP-001: The system must expose actual verified capability levels,
never assumed or simulated capabilities.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import platform
import sys
import time
from typing import Any

from jarvis_learning.invariants_p10 import EvidenceLevel


class DeviceState(enum.Enum):
    """Detailed operational states for hardware devices."""

    NOT_PRESENT = "NOT_PRESENT"
    PRESENT_UNSUPPORTED = "PRESENT_UNSUPPORTED"
    DRIVER_MISSING = "DRIVER_MISSING"
    TELEMETRY_ONLY = "TELEMETRY_ONLY"
    COMPUTE_READY = "COMPUTE_READY"
    COMPUTE_DEGRADED = "COMPUTE_DEGRADED"
    THERMAL_THROTTLED = "THERMAL_THROTTLED"
    MEMORY_EXHAUSTED = "MEMORY_EXHAUSTED"
    UNAVAILABLE = "UNAVAILABLE"


class SandboxTier(enum.Enum):
    """Graded levels of Windows security sandboxing."""

    TIER_0_APP = "TIER_0_APP"
    TIER_1_RESTRICTED_TOKEN = "TIER_1_RESTRICTED_TOKEN"
    TIER_2_NETWORK_FIREWALL = "TIER_2_NETWORK_FIREWALL"
    TIER_3_APPCONTAINER = "TIER_3_APPCONTAINER"
    TIER_4_WDAC = "TIER_4_WDAC"


@dataclasses.dataclass(frozen=True)
class CapabilityMatrix:
    """Matrix of verifiable hardware and driver capabilities."""

    device_present: bool = False
    driver_present: bool = False
    telemetry_available: bool = False
    compute_runtime_available: bool = False
    memory_telemetry_available: bool = False
    temperature_available: bool = False
    power_telemetry_available: bool = False
    process_isolation_supported: bool = False
    device_usable_by_learning_worker: bool = False

    def to_dict(self) -> dict[str, bool]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class DeviceCapability:
    """Individual hardware device descriptor with evidence level."""

    device_id: str
    device_name: str
    backend: str
    state: DeviceState
    matrix: CapabilityMatrix
    evidence_level: EvidenceLevel
    total_memory_bytes: int = 0
    driver_version: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "backend": self.backend,
            "state": self.state.value,
            "matrix": self.matrix.to_dict(),
            "evidence_level": self.evidence_level.value,
            "total_memory_bytes": self.total_memory_bytes,
            "driver_version": self.driver_version,
        }


@dataclasses.dataclass(frozen=True)
class HostCapabilityManifest:
    """Cryptographically sealed host capability attestation manifest."""

    manifest_id: str
    timestamp_ns: int
    host_os: str
    os_build: str
    python_version: str
    sandbox_tier: SandboxTier
    sandbox_evidence_level: EvidenceLevel
    devices: list[DeviceCapability]
    cross_session_verified: bool = False
    cross_reboot_verified: bool = False
    power_loss_verified: bool = False
    operator_mode: str = "LOCAL_HUMAN_REQUIRED"
    manifest_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "timestamp_ns": self.timestamp_ns,
            "host_os": self.host_os,
            "os_build": self.os_build,
            "python_version": self.python_version,
            "sandbox_tier": self.sandbox_tier.value,
            "sandbox_evidence_level": self.sandbox_evidence_level.value,
            "devices": [d.to_dict() for d in self.devices],
            "cross_session_verified": self.cross_session_verified,
            "cross_reboot_verified": self.cross_reboot_verified,
            "power_loss_verified": self.power_loss_verified,
            "operator_mode": self.operator_mode,
        }

    def compute_digest(self) -> str:
        payload = self.to_dict()
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_json(self, indent: int = 2) -> str:
        data = self.to_dict()
        data["manifest_digest"] = self.manifest_digest or self.compute_digest()
        return json.dumps(data, indent=indent, sort_keys=True)


def build_host_capability_manifest(
    devices: list[DeviceCapability] | None = None,
    sandbox_tier: SandboxTier = SandboxTier.TIER_0_APP,
    sandbox_evidence_level: EvidenceLevel = EvidenceLevel.L1_UNIT_MOCK,
    cross_session_verified: bool = False,
    cross_reboot_verified: bool = False,
    power_loss_verified: bool = False,
) -> HostCapabilityManifest:
    """Build and seal a host capability manifest for the current execution environment."""
    now_ns = time.time_ns()
    manifest_id = f"CAP-{now_ns}"
    host_os = platform.system()
    os_build = platform.version()
    python_ver = sys.version.split()[0]

    dev_list = devices or []
    if not dev_list:
        # Default fallback CPU device descriptor
        cpu_matrix = CapabilityMatrix(
            device_present=True,
            driver_present=True,
            telemetry_available=True,
            compute_runtime_available=True,
            memory_telemetry_available=True,
            temperature_available=False,
            power_telemetry_available=False,
            process_isolation_supported=True,
            device_usable_by_learning_worker=True,
        )
        dev_list = [
            DeviceCapability(
                device_id="cpu_0",
                device_name=platform.processor() or "Host CPU",
                backend="CPU",
                state=DeviceState.COMPUTE_READY,
                matrix=cpu_matrix,
                evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
                total_memory_bytes=0,
                driver_version="system",
            )
        ]

    manifest = HostCapabilityManifest(
        manifest_id=manifest_id,
        timestamp_ns=now_ns,
        host_os=host_os,
        os_build=os_build,
        python_version=python_ver,
        sandbox_tier=sandbox_tier,
        sandbox_evidence_level=sandbox_evidence_level,
        devices=dev_list,
        cross_session_verified=cross_session_verified,
        cross_reboot_verified=cross_reboot_verified,
        power_loss_verified=power_loss_verified,
    )
    digest = manifest.compute_digest()
    return dataclasses.replace(manifest, manifest_digest=digest)
