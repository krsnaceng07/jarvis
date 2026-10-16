"""jarvis_learning.training.invariants — Operational Invariant Registry and test evidence framework.

Defines the formal invariants governing the offline training subsystem:
- INV-MEM-001: Process Group Containment
- INV-GPU-001: GPU Failure Classification & Clean-Worker Recycling
- INV-CKPT-001: Crash-Consistent Checkpoint Transaction
- INV-REP-001: Tripartite Reproducibility Contract
- INV-LEASE-001: Supervisor Lease & Split-Brain Prevention
- INV-ORPH-001: Identity-Enveloped Orphan Cleanup
- INV-REV-001: Full Revocation Dependency Graph
- INV-SEC-001: Defense-in-Depth Worker Sandbox
- INV-MAN-001: Signed Backend Manifests & Capability Preflight
- INV-NUM-001: Numerical Stability & Gradient Health
- INV-INP-001: Runtime Input Immutability
- INV-EVAL-001: Statistical Evaluation & Golden Holdout Anti-Tuning
"""

from __future__ import annotations

import enum
import logging
import platform
import sys
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class InvariantEnforcementLevel(enum.StrEnum):
    """Declared enforcement tier for an operational guarantee."""

    HARD_OS_ENFORCED = "HARD_OS_ENFORCED"
    HARD_PROCESS_ENFORCED = "HARD_PROCESS_ENFORCED"
    SOFT_MONITORED = "SOFT_MONITORED"
    PREFLIGHT_ONLY = "PREFLIGHT_ONLY"
    BEST_EFFORT = "BEST_EFFORT"


class TestExecutionClassification(enum.StrEnum):
    """Explicit declaration of test fidelity and runtime reality."""

    MOCKED = "MOCKED"
    SIMULATED = "SIMULATED"
    LOCAL_INTEGRATION = "LOCAL_INTEGRATION"
    REAL_OS_ENFORCEMENT = "REAL_OS_ENFORCEMENT"
    REAL_GPU_HARDWARE = "REAL_GPU_HARDWARE"
    CRASH_INJECTION = "CRASH_INJECTION"
    CROSS_SESSION = "CROSS_SESSION"
    SECURITY_BOUNDARY = "SECURITY_BOUNDARY"


@dataclass(frozen=True, slots=True)
class OperationalInvariant:
    """Formal definition of a subsystem invariant contract."""

    invariant_id: str
    title: str
    description: str
    enforcement_level: InvariantEnforcementLevel
    failure_mode: str
    recovery_behavior: str
    test_ids: tuple[str, ...]


@dataclass(slots=True)
class OperationalTestEvidence:
    """Auditable evidence payload recorded during test execution."""

    test_id: str
    invariant_id: str
    classification: TestExecutionClassification
    timestamp: float = field(default_factory=time.time)
    os_name: str = field(default_factory=platform.system)
    os_version: str = field(default_factory=platform.version)
    python_version: str = field(
        default_factory=lambda: (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )
    )
    passed: bool = True
    failure_classification: str = "NONE"
    evidence_details: dict[str, Any] = field(default_factory=dict)
    artifact_path: str = ""


class OperationalEvidenceLedger:
    """In-memory and persistent ledger tracking verified test evidence."""

    _records: list[OperationalTestEvidence] = []

    @classmethod
    def record(cls, evidence: OperationalTestEvidence) -> None:
        """Append verified test evidence to ledger."""
        cls._records.append(evidence)
        logger.debug(
            "Recorded operational test evidence for [%s] (%s): passed=%s",
            evidence.test_id,
            evidence.classification.value,
            evidence.passed,
        )

    @classmethod
    def get_records(cls) -> list[OperationalTestEvidence]:
        """Fetch all recorded evidence entries."""
        return list(cls._records)

    @classmethod
    def clear(cls) -> None:
        """Reset records (primarily for testing)."""
        cls._records.clear()


GLOBAL_OPERATIONAL_LEDGER = OperationalEvidenceLedger()


# Canonical Operational Invariants
INVARIANTS: dict[str, OperationalInvariant] = {
    "INV-MEM-001": OperationalInvariant(
        invariant_id="INV-MEM-001",
        title="Process Group Containment",
        description="Worker and all descendants (children, grandchildren) are bound to Windows Job Object; escaping process tree is impossible.",
        enforcement_level=InvariantEnforcementLevel.HARD_OS_ENFORCED,
        failure_mode="WORKER_RESOURCE_EXCEEDED",
        recovery_behavior="OS terminates entire process tree; supervisor survives; zero orphans left.",
        test_ids=("test_p7_41", "test_p7_61", "test_p7_126"),
    ),
    "INV-GPU-001": OperationalInvariant(
        invariant_id="INV-GPU-001",
        title="GPU Failure Classification & Clean-Worker Recycling",
        description="GPU failures are classified into 8 distinct categories. Serious CUDA crashes terminate worker process without in-process state reuse.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_mode="GPU_OOM_FATAL",
        recovery_behavior="Supervisor destroys corrupted child process; restarts clean worker with adjusted batch size or aborts safely.",
        test_ids=(
            "test_p7_43",
            "test_p7_45",
            "test_p7_62",
            "test_p7_63",
            "test_p7_64",
            "test_p7_65",
            "test_p7_69",
            "test_p7_127",
        ),
    ),
    "INV-CKPT-001": OperationalInvariant(
        invariant_id="INV-CKPT-001",
        title="Crash-Consistent Checkpoint Transaction",
        description="Checkpoints follow a 9-state atomic transaction protocol. Incomplete or corrupted files are quarantined.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_mode="CHECKPOINT_CORRUPT",
        recovery_behavior="Corrupted checkpoints moved to _quarantine/; abandoned staging purged automatically on startup.",
        test_ids=(
            "test_p7_29",
            "test_p7_30",
            "test_p7_31",
            "test_p7_46",
            "test_p7_47",
            "test_p7_48",
            "test_p7_50",
            "test_p7_70",
            "test_p7_78",
        ),
    ),
    "INV-REP-001": OperationalInvariant(
        invariant_id="INV-REP-001",
        title="Tripartite Reproducibility Contract",
        description="Three separate cryptographic identities: RunIdentity (unique attempt), ExecutionFingerprint (22+ facts), and ResumeCompatibilityFingerprint.",
        enforcement_level=InvariantEnforcementLevel.PREFLIGHT_ONLY,
        failure_mode="REPRODUCIBILITY_MISMATCH",
        recovery_behavior="Preflight blocks incompatible run configurations before resource allocation.",
        test_ids=(
            "test_p7_33",
            "test_p7_34",
            "test_p7_51",
            "test_p7_52",
            "test_p7_53",
            "test_p7_79",
            "test_p7_84",
        ),
    ),
    "INV-LEASE-001": OperationalInvariant(
        invariant_id="INV-LEASE-001",
        title="Supervisor Lease & Split-Brain Prevention",
        description="Supervisor must hold active, unexpired atomic lease with monotonic heartbeats. Two supervisors cannot train the same job.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_mode="SPLIT_BRAIN_BLOCKED",
        recovery_behavior="Competing supervisor rejected; worker aborts if lease heartbeat is lost.",
        test_ids=(
            "test_p7_10",
            "test_p7_55",
            "test_p7_112",
            "test_p7_113",
            "test_p7_114",
            "test_p7_115",
            "test_p7_128",
            "test_p7_129",
        ),
    ),
    "INV-ORPH-001": OperationalInvariant(
        invariant_id="INV-ORPH-001",
        title="Identity-Enveloped Orphan Cleanup",
        description="Workers carry cryptographic identity envelopes (worker_id, nonce, timestamp). Cleanup only kills verified matching envelopes.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_mode="ORPHAN_DETECTED",
        recovery_behavior="Stale worker processes killed safely without PID reuse mistakes or killing unrelated tasks.",
        test_ids=("test_p7_56", "test_p7_85", "test_p7_86", "test_p7_87", "test_p7_88"),
    ),
    "INV-REV-001": OperationalInvariant(
        invariant_id="INV-REV-001",
        title="Full Revocation Dependency Graph",
        description="Revoking a dataset propagates downstream through DAG: Dataset -> Snapshot -> Run -> Checkpoint -> Model -> Evaluation -> Export.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_mode="REVOKED_INELIGIBLE",
        recovery_behavior="All derived artifacts stamped REVOKED_INELIGIBLE; blocked from training, evaluation, export, or deployment.",
        test_ids=(
            "test_p7_03",
            "test_p7_04",
            "test_p7_57",
            "test_p7_89",
            "test_p7_90",
            "test_p7_91",
            "test_p7_92",
            "test_p7_93",
            "test_p7_130",
        ),
    ),
    "INV-SEC-001": OperationalInvariant(
        invariant_id="INV-SEC-001",
        title="Defense-in-Depth Worker Sandbox",
        description="Workers execute with scrubbed environment, scratch-only write access, and OS/socket level network denial. Proxies alone are not considered security boundaries.",
        enforcement_level=InvariantEnforcementLevel.HARD_OS_ENFORCED,
        failure_mode="SECURITY_VIOLATION",
        recovery_behavior="Worker terminated immediately; security incident logged to audit ledger.",
        test_ids=("test_p7_58", "test_p7_59", "test_p7_94", "test_p7_101", "test_p7_131"),
    ),
    "INV-MAN-001": OperationalInvariant(
        invariant_id="INV-MAN-001",
        title="Signed Backend Manifests & Capability Preflight",
        description="Backends declare signed manifests with capability flags and entrypoints. Unregistered or untrusted backends are rejected at preflight.",
        enforcement_level=InvariantEnforcementLevel.PREFLIGHT_ONLY,
        failure_mode="UNTRUSTED_BACKEND_REJECTED",
        recovery_behavior="Preflight blocks execution before worker child launch.",
        test_ids=("test_p7_60", "test_p7_124"),
    ),
    "INV-NUM-001": OperationalInvariant(
        invariant_id="INV-NUM-001",
        title="Numerical Stability & Gradient Health",
        description="Runtime monitors loss, gradients, and weights for NaN, Inf, explosion, nonfinite parameters, and stagnation. No model with numerical faults can become a candidate.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_mode="NUMERICAL_INSTABILITY",
        recovery_behavior="Execution halted; model barred from candidate status; pre-failure checkpoint retained.",
        test_ids=(
            "test_p7_106",
            "test_p7_107",
            "test_p7_108",
            "test_p7_109",
            "test_p7_110",
            "test_p7_111",
        ),
    ),
    "INV-INP-001": OperationalInvariant(
        invariant_id="INV-INP-001",
        title="Runtime Input Immutability",
        description="Datasets and configs are snapshotted read-only and periodically hash-verified during training execution. Mid-run mutations trigger immediate abort.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_mode="INTEGRITY_VIOLATION",
        recovery_behavior="Job aborted; tamper incident recorded in audit log.",
        test_ids=(
            "test_p7_02",
            "test_p7_06",
            "test_p7_116",
            "test_p7_117",
            "test_p7_118",
            "test_p7_119",
        ),
    ),
    "INV-EVAL-001": OperationalInvariant(
        invariant_id="INV-EVAL-001",
        title="Statistical Evaluation & Golden Holdout Anti-Tuning",
        description="Wilson score confidence intervals, multi-class decision outcomes, zero-tolerance safety triggers, and rate-limited, read-only golden holdout access with aggregate-only metrics.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_mode="SAFETY_REJECTION",
        recovery_behavior="Unsafe models rejected unconditionally (REJECTED_SAFETY); golden holdout tuning prevented.",
        test_ids=(
            "test_p7_07",
            "test_p7_39",
            "test_p7_40",
            "test_p7_102",
            "test_p7_105",
            "test_p7_132",
        ),
    ),
}
