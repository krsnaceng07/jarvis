"""Phase 10 Operational Invariants & Evidence Registry.

Defines the 17 formal invariants (INV-P10-HW-001 through INV-P10-LIM-001),
evidence levels (L0 to L8), risk classifications, and operational evidence ledger.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import time
from typing import Any


class EvidenceLevel(enum.Enum):
    """Hierarchy of test and validation evidence levels."""

    L0_STATIC = "L0_STATIC"
    L1_UNIT_MOCK = "L1_UNIT_MOCK"
    L2_IN_PROCESS_INTEGRATION = "L2_IN_PROCESS_INTEGRATION"
    L3_REAL_SUBPROCESS = "L3_REAL_SUBPROCESS"
    L4_REAL_WINDOWS_API = "L4_REAL_WINDOWS_API"
    L5_REAL_HARDWARE = "L5_REAL_HARDWARE"
    L6_REAL_REBOOT_SESSION = "L6_REAL_REBOOT_SESSION"
    L7_DEDICATED_POWER_LOSS = "L7_DEDICATED_POWER_LOSS"
    L8_HOSTILE_BOUNDARY = "L8_HOSTILE_BOUNDARY"


class RiskClassification(enum.Enum):
    """Risk domain for Phase 10 operational areas."""

    RESOURCE_PERFORMANCE = "RESOURCE_PERFORMANCE"
    DATA_INTEGRITY_RECOVERY = "DATA_INTEGRITY_RECOVERY"
    SECURITY_BOUNDARY = "SECURITY_BOUNDARY"
    REAL_TIME_RUNTIME = "REAL_TIME_RUNTIME"
    GOVERNANCE_OPERATOR = "GOVERNANCE_OPERATOR"


@dataclasses.dataclass(frozen=True)
class Phase10Invariant:
    """Formal Phase 10 invariant definition."""

    invariant_id: str
    title: str
    description: str
    risk_class: RiskClassification
    required_evidence_level: EvidenceLevel
    stop_ship_on_breach: bool = True


PHASE10_INVARIANTS: dict[str, Phase10Invariant] = {
    "INV-P10-HW-001": Phase10Invariant(
        invariant_id="INV-P10-HW-001",
        title="Evidence-Backed Hardware Claims",
        description="Hardware capability claims must be evidence-backed and capability-specific, never assumed.",
        risk_class=RiskClassification.RESOURCE_PERFORMANCE,
        required_evidence_level=EvidenceLevel.L5_REAL_HARDWARE,
    ),
    "INV-P10-HW-002": Phase10Invariant(
        invariant_id="INV-P10-HW-002",
        title="Active Runtime Resource Reservation",
        description="Resource governors must reserve guaranteed capacity and headroom for the active JARVIS runtime.",
        risk_class=RiskClassification.RESOURCE_PERFORMANCE,
        required_evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    ),
    "INV-P10-HW-003": Phase10Invariant(
        invariant_id="INV-P10-HW-003",
        title="Thermal Throttling Hysteresis",
        description="Thermal throttling must use hysteresis (>=82C pause, <=75C resume) and sustained observation duration.",
        risk_class=RiskClassification.RESOURCE_PERFORMANCE,
        required_evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    ),
    "INV-P10-REC-001": Phase10Invariant(
        invariant_id="INV-P10-REC-001",
        title="Durable Transaction Non-Loss",
        description="No acknowledged durable transaction may be silently lost within the tested failure class.",
        risk_class=RiskClassification.DATA_INTEGRITY_RECOVERY,
        required_evidence_level=EvidenceLevel.L3_REAL_SUBPROCESS,
    ),
    "INV-P10-REC-002": Phase10Invariant(
        invariant_id="INV-P10-REC-002",
        title="Uncommitted Artifact Isolation",
        description="Uncommitted partial artifacts must never become active or corrupt existing state.",
        risk_class=RiskClassification.DATA_INTEGRITY_RECOVERY,
        required_evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    ),
    "INV-P10-SBX-001": Phase10Invariant(
        invariant_id="INV-P10-SBX-001",
        title="Pre-Launch Sandbox Verification",
        description="Required sandbox guarantees must be established and verified before any restricted worker launch.",
        risk_class=RiskClassification.SECURITY_BOUNDARY,
        required_evidence_level=EvidenceLevel.L4_REAL_WINDOWS_API,
    ),
    "INV-P10-SBX-002": Phase10Invariant(
        invariant_id="INV-P10-SBX-002",
        title="Fail-Closed Sandbox Policy",
        description="Sandbox setup failure must fail closed (deny launch) for restricted workers.",
        risk_class=RiskClassification.SECURITY_BOUNDARY,
        required_evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    ),
    "INV-P10-SBX-003": Phase10Invariant(
        invariant_id="INV-P10-SBX-003",
        title="Accurate Enforcement Level Reporting",
        description="Application-level restrictions must never be reported or certified as OS-level enforcement.",
        risk_class=RiskClassification.SECURITY_BOUNDARY,
        required_evidence_level=EvidenceLevel.L4_REAL_WINDOWS_API,
    ),
    "INV-P10-RT-001": Phase10Invariant(
        invariant_id="INV-P10-RT-001",
        title="Active Path Non-Interference",
        description="No learning-sidecar failure, queue backlog, or IPC delay may delay active voice/tool execution.",
        risk_class=RiskClassification.REAL_TIME_RUNTIME,
        required_evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    ),
    "INV-P10-RT-002": Phase10Invariant(
        invariant_id="INV-P10-RT-002",
        title="Stale Generation Discard",
        description="Stale task-generation or cancelled-turn results must never affect current runtime state.",
        risk_class=RiskClassification.REAL_TIME_RUNTIME,
        required_evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    ),
    "INV-P10-RT-003": Phase10Invariant(
        invariant_id="INV-P10-RT-003",
        title="Truthful Failure Attribution",
        description="Real user workflow failures must be recorded without false-success or ungrounded attribution.",
        risk_class=RiskClassification.REAL_TIME_RUNTIME,
        required_evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    ),
    "INV-P10-OPS-001": Phase10Invariant(
        invariant_id="INV-P10-OPS-001",
        title="Detached Dashboard Control Plane",
        description="Operator dashboard unavailability must not block, pause, or alter active runtime or learning workers.",
        risk_class=RiskClassification.GOVERNANCE_OPERATOR,
        required_evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    ),
    "INV-P10-OPS-002": Phase10Invariant(
        invariant_id="INV-P10-OPS-002",
        title="Cryptographic Anti-Replay Tokens",
        description="Approval tokens must be cryptographically signed, single-use (nonce), time-bound, and candidate-bound.",
        risk_class=RiskClassification.GOVERNANCE_OPERATOR,
        required_evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    ),
    "INV-P10-RB-001": Phase10Invariant(
        invariant_id="INV-P10-RB-001",
        title="Classified Atomic Rollback",
        description="Rollback must restore a verified known-good artifact and correct pointer atomically within target class SLO.",
        risk_class=RiskClassification.GOVERNANCE_OPERATOR,
        required_evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    ),
    "INV-P10-CAP-001": Phase10Invariant(
        invariant_id="INV-P10-CAP-001",
        title="Attested Capability Transparency",
        description="The system must expose actual verified capability levels, never assumed or simulated capabilities.",
        risk_class=RiskClassification.GOVERNANCE_OPERATOR,
        required_evidence_level=EvidenceLevel.L0_STATIC,
    ),
    "INV-P10-COMP-001": Phase10Invariant(
        invariant_id="INV-P10-COMP-001",
        title="Runtime Contract Compatibility Handshake",
        description="Incompatible host/worker/runtime contracts or digest mismatches must prevent worker startup.",
        risk_class=RiskClassification.GOVERNANCE_OPERATOR,
        required_evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    ),
    "INV-P10-LIM-001": Phase10Invariant(
        invariant_id="INV-P10-LIM-001",
        title="Enforceable Resource & Execution Limits",
        description="Every worker operation must execute under strictly enforceable resource, time, and retry limits.",
        risk_class=RiskClassification.RESOURCE_PERFORMANCE,
        required_evidence_level=EvidenceLevel.L3_REAL_SUBPROCESS,
    ),
}


@dataclasses.dataclass(frozen=True)
class Phase10EvidenceRecord:
    """Tamper-evident record of an operational validation test."""

    record_id: str
    scenario_id: str
    invariant_id: str
    evidence_level: EvidenceLevel
    passed: bool
    details: dict[str, Any]
    timestamp_ns: int = dataclasses.field(default_factory=time.time_ns)
    record_digest: str = ""

    def compute_digest(self) -> str:
        payload = {
            "record_id": self.record_id,
            "scenario_id": self.scenario_id,
            "invariant_id": self.invariant_id,
            "evidence_level": self.evidence_level.value,
            "passed": self.passed,
            "details": self.details,
            "timestamp_ns": self.timestamp_ns,
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class Phase10EvidenceLedger:
    """Ledger recording Phase 10 scenario verification evidence."""

    def __init__(self) -> None:
        self._records: list[Phase10EvidenceRecord] = []

    def record(
        self,
        scenario_id: str,
        invariant_id: str,
        evidence_level: EvidenceLevel,
        passed: bool,
        details: dict[str, Any] | None = None,
    ) -> Phase10EvidenceRecord:
        record_id = f"P10-EV-{len(self._records) + 1:04d}"
        rec = Phase10EvidenceRecord(
            record_id=record_id,
            scenario_id=scenario_id,
            invariant_id=invariant_id,
            evidence_level=evidence_level,
            passed=passed,
            details=details or {},
        )
        digest = rec.compute_digest()
        sealed_rec = dataclasses.replace(rec, record_digest=digest)
        self._records.append(sealed_rec)
        return sealed_rec

    @property
    def records(self) -> list[Phase10EvidenceRecord]:
        return list(self._records)

    def verify_integrity(self) -> bool:
        for r in self._records:
            if r.record_digest != r.compute_digest():
                return False
        return True


_GLOBAL_P10_LEDGER = Phase10EvidenceLedger()


def get_p10_evidence_ledger() -> Phase10EvidenceLedger:
    return _GLOBAL_P10_LEDGER
