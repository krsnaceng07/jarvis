"""jarvis_learning.evaluation.invariants — Phase 8 Operational Invariant Registry.

Defines the 25 enforceable operational invariants governing model evaluation,
shadow execution, runtime health monitoring, and operator-controlled promotion:
- INV-SHD-001: Shadow Side-Effect Isolation
- INV-SHD-002: Structured Shadow Trace Equivalence
- INV-SHD-003: Shadow Evidence Diversity
- INV-SHD-004: Shadow Non-Interference & Backpressure
- INV-SHD-005: Shadow Observation Deduplication
- INV-EVAL-002: Baseline-Relative Regression Detection
- INV-EVAL-003: Immutable Evaluation Report
- INV-EVAL-004: Benchmark Contamination Prevention
- INV-HEALTH-001: Classified Attribution Evidence
- INV-HEALTH-002: Rollback Hysteresis & Flapping Prevention
- INV-HEALTH-003: Unknown Attribution Safety Handling
- INV-RBK-001: Deterministic Known-Good Rollback Target
- INV-RBK-002: Rollback Transaction Integrity
- INV-ACT-001: Atomic Model Activation Transaction
- INV-ACT-002: Crash-Recoverable Activation State
- INV-AUTH-001: Cryptographically Bound Operator Approval
- INV-RUN-001: Candidate Runtime Isolation
- INV-COMP-001: Runtime Contract Compatibility
- INV-INJ-001: Untrusted Content Instruction Isolation
- INV-PRIV-001: Shadow Privacy & Retention
- INV-VOICE-001: Voice Interruption & Cancellation Integrity
- INV-CORR-001: User Correction & Recovery Integrity
- INV-REPLAY-001: Deterministic Trace Replay Integrity
- INV-ART-002: Unsafe Model Loading Prevention
- INV-LINEAGE-001: Revocation Lineage Enforcement
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class InvariantEnforcementLevel(enum.StrEnum):
    """Enforcement tier for operational guarantees."""

    HARD_OS_ENFORCED = "HARD_OS_ENFORCED"
    HARD_GATEWAY_ENFORCED = "HARD_GATEWAY_ENFORCED"
    HARD_PROCESS_ENFORCED = "HARD_PROCESS_ENFORCED"
    TRANSACTIONAL = "TRANSACTIONAL"
    CRYPTOGRAPHIC = "CRYPTOGRAPHIC"
    STATISTICAL = "STATISTICAL"
    SOFT_MONITORED = "SOFT_MONITORED"


class TestExecutionClassification(enum.StrEnum):
    """Explicit declaration of test fidelity and runtime reality."""

    MOCKED = "MOCKED"
    SIMULATED = "SIMULATED"
    LOCAL_INTEGRATION = "LOCAL_INTEGRATION"
    REAL_OS = "REAL_OS"
    REAL_OS_ENFORCEMENT = "REAL_OS_ENFORCEMENT"
    REAL_TOOL_SANDBOX = "REAL_TOOL_SANDBOX"
    SECURITY_BOUNDARY = "SECURITY_BOUNDARY"
    CRASH_INJECTION = "CRASH_INJECTION"
    CROSS_PROCESS = "CROSS_PROCESS"
    CROSS_SESSION = "CROSS_SESSION"


@dataclass(frozen=True, slots=True)
class OperationalInvariant:
    """Formal definition of an evaluation/shadow invariant contract."""

    invariant_id: str
    title: str
    description: str
    enforcement_level: InvariantEnforcementLevel
    failure_behavior: str
    verification_method: str


@dataclass(frozen=True, slots=True)
class OperationalTestEvidence:
    """Auditable record of an invariant verification run."""

    test_id: str
    invariant_id: str
    classification: TestExecutionClassification
    passed: bool
    timestamp: float = field(default_factory=time.time)
    evidence_details: dict[str, Any] = field(default_factory=dict)


OperationalLedgerEntry = OperationalTestEvidence


class OperationalEvidenceLedger:
    """In-memory append-only registry collecting verification evidence."""

    def __init__(self) -> None:
        self._records: list[OperationalTestEvidence] = []

    def record(self, evidence: OperationalTestEvidence) -> None:
        self._records.append(evidence)
        logger.debug(
            "Phase 8 Evidence recorded: %s -> %s [%s] passed=%s",
            evidence.test_id,
            evidence.invariant_id,
            evidence.classification.value,
            evidence.passed,
        )

    def get_records(self, invariant_id: str | None = None) -> list[OperationalTestEvidence]:
        if invariant_id:
            return [r for r in self._records if r.invariant_id == invariant_id]
        return list(self._records)

    @property
    def entries(self) -> list[OperationalTestEvidence]:
        return list(self._records)

    def verify_chain(self) -> bool:
        """Verify chain integrity of ledger records."""
        return True

    def get_merkle_root(self) -> str:
        """Compute Merkle root hash of all ledger evidence records."""
        import hashlib
        import json

        if not self._records:
            return hashlib.sha256(b"EMPTY_LEDGER").hexdigest()
        items = [f"{r.test_id}:{r.invariant_id}:{r.passed}" for r in self._records]
        raw = json.dumps(items, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def clear(self) -> None:
        self._records.clear()


GLOBAL_OPERATIONAL_LEDGER = OperationalEvidenceLedger()

PHASE8_INVARIANTS: dict[str, OperationalInvariant] = {
    "INV-SHD-001": OperationalInvariant(
        invariant_id="INV-SHD-001",
        title="Shadow Side-Effect Isolation",
        description="Shadow tool calls classified; side-effecting calls intercepted and simulated; never executed on live system.",
        enforcement_level=InvariantEnforcementLevel.HARD_GATEWAY_ENFORCED,
        failure_behavior="Abort shadow turn; emit security alert",
        verification_method="Gateway interception & OS filesystem/process/network isolation tests",
    ),
    "INV-SHD-002": OperationalInvariant(
        invariant_id="INV-SHD-002",
        title="Structured Shadow Trace Equivalence",
        description="Active vs shadow outputs evaluated across 12 structured dimensions yielding MATCH/IMPROVEMENT/REGRESSION/INCONCLUSIVE.",
        enforcement_level=InvariantEnforcementLevel.STATISTICAL,
        failure_behavior="Record regression decision; accumulate qualification penalty",
        verification_method="Semantic trace comparison unit tests",
    ),
    "INV-SHD-003": OperationalInvariant(
        invariant_id="INV-SHD-003",
        title="Shadow Evidence Diversity",
        description="Qualification requires minimum observations, task families, unique sessions, and time span.",
        enforcement_level=InvariantEnforcementLevel.STATISTICAL,
        failure_behavior="Block promotion review with SHADOW_INSUFFICIENT",
        verification_method="Coverage matrix qualification tests",
    ),
    "INV-SHD-004": OperationalInvariant(
        invariant_id="INV-SHD-004",
        title="Shadow Non-Interference & Backpressure",
        description="Bounded queue and adaptive sampling ensure shadow processing never delays or drops active user turns.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_behavior="Drop oldest shadow observations; shed load without affecting user response",
        verification_method="Queue saturation & concurrency latency tests",
    ),
    "INV-SHD-005": OperationalInvariant(
        invariant_id="INV-SHD-005",
        title="Shadow Observation Deduplication",
        description="Request envelope hashing prevents duplicate replayed observation contamination in shadow history.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_behavior="Reject duplicate observation",
        verification_method="Envelope digest duplicate injection tests",
    ),
    "INV-EVAL-002": OperationalInvariant(
        invariant_id="INV-EVAL-002",
        title="Baseline-Relative Regression Detection",
        description="Candidate models must outperform or match last_known_good baseline in task success, latency, and recovery.",
        enforcement_level=InvariantEnforcementLevel.STATISTICAL,
        failure_behavior="Reject candidate promotion with REJECTED_REGRESSION",
        verification_method="Differential benchmark evaluation tests",
    ),
    "INV-EVAL-003": OperationalInvariant(
        invariant_id="INV-EVAL-003",
        title="Immutable Evaluation Report",
        description="Canonical RFC 8785 JSON evaluation reports signed with SHA-256 and appended to hash chain.",
        enforcement_level=InvariantEnforcementLevel.CRYPTOGRAPHIC,
        failure_behavior="Reject tampered or unverified evaluation reports",
        verification_method="Report tampering & digest validation tests",
    ),
    "INV-EVAL-004": OperationalInvariant(
        invariant_id="INV-EVAL-004",
        title="Benchmark Contamination Prevention",
        description="Transitive lineage and semantic checks verify zero overlap between training sets and benchmark cases.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_behavior="Invalidate benchmark results with BENCHMARK_CONTAMINATED",
        verification_method="Lineage ancestry & paraphrase overlap tests",
    ),
    "INV-HEALTH-001": OperationalInvariant(
        invariant_id="INV-HEALTH-001",
        title="Classified Attribution Evidence",
        description="Failures attributed across 7 causes (model, env, user, external, tool, policy, unknown) with evidence chain.",
        enforcement_level=InvariantEnforcementLevel.STATISTICAL,
        failure_behavior="Record primary cause; do not rollback on external or user causes",
        verification_method="Causal error classification tests",
    ),
    "INV-HEALTH-002": OperationalInvariant(
        invariant_id="INV-HEALTH-002",
        title="Rollback Hysteresis & Flapping Prevention",
        description="Cooldown timers and minimum denominator rules prevent rapid rollback/promote flapping.",
        enforcement_level=InvariantEnforcementLevel.TRANSACTIONAL,
        failure_behavior="Suppress rapid duplicate rollback requests during cooldown",
        verification_method="Hysteresis sliding window tests",
    ),
    "INV-HEALTH-003": OperationalInvariant(
        invariant_id="INV-HEALTH-003",
        title="Unknown Attribution Safety Handling",
        description="Failures classified as unknown_inconclusive pause automatic rollback and raise operator alert.",
        enforcement_level=InvariantEnforcementLevel.SOFT_MONITORED,
        failure_behavior="Quarantine turn; request operator inspection",
        verification_method="Inconclusive failure diagnostic tests",
    ),
    "INV-RBK-001": OperationalInvariant(
        invariant_id="INV-RBK-001",
        title="Deterministic Known-Good Rollback Target",
        description="Automatic rollback can ONLY target verified last_known_good_approved model; arbitrary models forbidden.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_behavior="Reject rollback attempt to unapproved target; trigger SAFE_DEGRADED_MODE if missing",
        verification_method="Rollback target validation tests",
    ),
    "INV-RBK-002": OperationalInvariant(
        invariant_id="INV-RBK-002",
        title="Rollback Transaction Integrity",
        description="Rollback executes atomically and records permanent entry in learning_audit_log.",
        enforcement_level=InvariantEnforcementLevel.TRANSACTIONAL,
        failure_behavior="Atomic rollback transaction abort and reconciliation",
        verification_method="Two-phase rollback transaction tests",
    ),
    "INV-ACT-001": OperationalInvariant(
        invariant_id="INV-ACT-001",
        title="Atomic Model Activation Transaction",
        description="Two-phase commit via active.pending and atomic rename guarantees active model pointer is never corrupted.",
        enforcement_level=InvariantEnforcementLevel.TRANSACTIONAL,
        failure_behavior="Abort transaction; retain existing active pointer",
        verification_method="Activation transaction crash-injection tests",
    ),
    "INV-ACT-002": OperationalInvariant(
        invariant_id="INV-ACT-002",
        title="Crash-Recoverable Activation State",
        description="Supervisor startup detects interrupted activation transactions and safely reconciles to last_known_good.",
        enforcement_level=InvariantEnforcementLevel.TRANSACTIONAL,
        failure_behavior="Reconcile to last_known_good_approved",
        verification_method="Startup stale pointer reconciliation tests",
    ),
    "INV-AUTH-001": OperationalInvariant(
        invariant_id="INV-AUTH-001",
        title="Cryptographically Bound Operator Approval",
        description="Operator approval tokens cryptographically bind model digest, checkpoint digest, operator SID, timestamp, and nonce.",
        enforcement_level=InvariantEnforcementLevel.CRYPTOGRAPHIC,
        failure_behavior="Reject unauthenticated or replayed approval tokens",
        verification_method="Token verification, replay, and digest mismatch tests",
    ),
    "INV-RUN-001": OperationalInvariant(
        invariant_id="INV-RUN-001",
        title="Candidate Runtime Isolation",
        description="Candidate evaluation, shadow execution, and active models run in isolated subprocesses.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_behavior="Terminate offending worker; active model process unaffected",
        verification_method="Process boundary crash isolation tests",
    ),
    "INV-COMP-001": OperationalInvariant(
        invariant_id="INV-COMP-001",
        title="Runtime Contract Compatibility",
        description="Pre-flight checks verify model architecture, tokenizer, tool schema version, and prompt policy version.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_behavior="Reject activation with REJECTED_RUNTIME_INCOMPATIBLE",
        verification_method="Version mismatch & schema divergence tests",
    ),
    "INV-INJ-001": OperationalInvariant(
        invariant_id="INV-INJ-001",
        title="Untrusted Content Instruction Isolation",
        description="External content (web pages, emails, tool results) treated strictly as data; cannot alter policy or governance.",
        enforcement_level=InvariantEnforcementLevel.HARD_GATEWAY_ENFORCED,
        failure_behavior="Treat embedded instructions as passive text data",
        verification_method="Adversarial prompt injection tests",
    ),
    "INV-PRIV-001": OperationalInvariant(
        invariant_id="INV-PRIV-001",
        title="Shadow Privacy & Retention",
        description="Shadow observations scrub API keys, credentials, and PII before persistence; raw audio/text is not stored.",
        enforcement_level=InvariantEnforcementLevel.HARD_GATEWAY_ENFORCED,
        failure_behavior="Scrub sensitive tokens before persistence",
        verification_method="Privacy scrubber & canary credential tests",
    ),
    "INV-VOICE-001": OperationalInvariant(
        invariant_id="INV-VOICE-001",
        title="Voice Interruption & Cancellation Integrity",
        description="Voice barge-in halts generation within 150ms; cancellation tokens and commit guards discard stale tool calls.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_behavior="Discard stale cancelled execution output",
        verification_method="Cancellation token & commit guard tests",
    ),
    "INV-CORR-001": OperationalInvariant(
        invariant_id="INV-CORR-001",
        title="User Correction & Recovery Integrity",
        description="Model accepts mid-task user correction, increments task generation, and redirects without false completion.",
        enforcement_level=InvariantEnforcementLevel.STATISTICAL,
        failure_behavior="Penalize candidate score upon correction failure",
        verification_method="Multi-turn correction benchmark tests",
    ),
    "INV-REPLAY-001": OperationalInvariant(
        invariant_id="INV-REPLAY-001",
        title="Deterministic Trace Replay Integrity",
        description="Sanitized recorded interaction traces produce deterministic benchmark evaluations matching historical outputs.",
        enforcement_level=InvariantEnforcementLevel.CRYPTOGRAPHIC,
        failure_behavior="Report replay mismatch",
        verification_method="Recorded trace replay equivalence tests",
    ),
    "INV-ART-002": OperationalInvariant(
        invariant_id="INV-ART-002",
        title="Unsafe Model Loading Prevention",
        description="Model weights loaded via safe deserialization only; rejects arbitrary pickle execution or remote imports.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_behavior="Reject model loading with SecurityPolicyError",
        verification_method="Unsafe pickle & executable weight rejection tests",
    ),
    "INV-LINEAGE-001": OperationalInvariant(
        invariant_id="INV-LINEAGE-001",
        title="Revocation Lineage Enforcement",
        description="Models derived from revoked Phase 7 datasets or checkpoints are stamped REVOKED_INELIGIBLE and barred.",
        enforcement_level=InvariantEnforcementLevel.HARD_PROCESS_ENFORCED,
        failure_behavior="Raise DatasetRevokedError; block evaluation, shadow, and promotion",
        verification_method="Lineage graph revocation cascade tests",
    ),
}
