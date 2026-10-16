"""jarvis_learning.evaluation — Model Evaluation, Shadow Promotion, and Health Monitoring.

Phase 8 production evaluation subsystem adhering to all 25 operational invariants.
"""

from .attribution import (
    FailureAttributionEngine,
    FailureAttributionEvidence,
    FailureCause,
    RollbackDecision,
    RollbackHysteresisController,
)
from .event_bus import (
    CanonicalEventBus,
    EventCallback,
    SubscriptionHandle,
    get_global_event_bus,
    reset_global_event_bus,
)
from .event_envelope import (
    CanonicalEventEnvelope,
    CanonicalEventType,
    EventPriority,
    create_event_envelope,
)
from .priority_queue import (
    DroppedEventRecord,
    PriorityShadowQueue,
    SamplingCompletenessMetrics,
    ShadowEventBusAdapter,
)
from .browser_boundary import (
    BrowserTabMetadata,
    VirtualBrowserState,
)
from .recovery_manager import (
    PromotionTransactionState,
    ReconciliationReport,
    TransactionalRecoveryManager,
)
from .sandbox_policy import (
    NetworkAccessBlockedError,
    SecurityPolicyViolationError,
    WorkerResourceQuota,
    assert_worker_environment_safe,
    check_outbound_network_allowed,
    create_sanitized_environment,
    verify_sanitized_environment,
)
from .tool_registry import (
    CANONICAL_TOOL_REGISTRY,
    CentralToolRegistry,
    SideEffectLevel,
    ToolCategory,
    ToolContractDefinition,
)
from .benchmark import (
    AgentBenchmarkTrace,
    BenchmarkAgent,
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRunner,
    BenchmarkSuiteResult,
)
from .domain_benchmarks import (
    BaselineRegressionResult,
    BaselineRelativeRegressionDetector,
    BenchmarkContaminationChecker,
    BenchmarkContaminationError,
    BenchmarkDomain,
    CanonicalEvaluationReport,
    CategoryGatingResult,
    CategorySafetyGate,
    ContaminationCheckResult,
)
from .invariants import (
    GLOBAL_OPERATIONAL_LEDGER,
    InvariantEnforcementLevel,
    OperationalInvariant,
    OperationalLedgerEntry,
    PHASE8_INVARIANTS,
    TestExecutionClassification,
)
from .promotion_machine import (
    AuthorizationError,
    ModelActivationTransaction,
    OperatorApprovalToken,
    OperatorAuthorizationValidator,
    PromotionLifecycleManager,
    PromotionState,
)
from .regression import (
    RegressionGate,
    RegressionResult,
)
from .shadow_executor import (
    ShadowDiversityRequirements,
    ShadowEvidenceDiversityGate,
    ShadowExecutor,
    ShadowMetrics,
    ShadowNonInterferenceQueue,
    StructuredShadowTraceComparison,
)
from .tool_gateway import (
    CanonicalRequestEnvelope,
    ShadowToolSimulator,
    SimulatedToolResult,
    StateSnapshotSanitizer,
    TOOL_SENSITIVITY_REGISTRY,
    ToolSensitivityClass,
)
from .voice_evaluator import (
    CancellationToken,
    CorrectionEvaluationHarness,
    RecordedTraceTurn,
    TaskGenerationContext,
    TraceReplayHarness,
    UntrustedContentFilter,
    VoiceInterruptionHarness,
)

__all__ = [
    # Event Bus & Canonical Envelope
    "CanonicalEventEnvelope",
    "CanonicalEventType",
    "EventPriority",
    "create_event_envelope",
    "CanonicalEventBus",
    "EventCallback",
    "SubscriptionHandle",
    "get_global_event_bus",
    "reset_global_event_bus",
    "PriorityShadowQueue",
    "DroppedEventRecord",
    "SamplingCompletenessMetrics",
    "ShadowEventBusAdapter",
    # Tool Registry & Governance
    "ToolCategory",
    "SideEffectLevel",
    "ToolContractDefinition",
    "CANONICAL_TOOL_REGISTRY",
    "CentralToolRegistry",
    # Sandbox & Security Policy
    "SecurityPolicyViolationError",
    "NetworkAccessBlockedError",
    "WorkerResourceQuota",
    "create_sanitized_environment",
    "verify_sanitized_environment",
    "assert_worker_environment_safe",
    "check_outbound_network_allowed",
    # Browser Boundary
    "BrowserTabMetadata",
    "VirtualBrowserState",
    # Recovery Manager & Transaction Lifecycle
    "PromotionTransactionState",
    "ReconciliationReport",
    "TransactionalRecoveryManager",
    # Invariants
    "PHASE8_INVARIANTS",
    "GLOBAL_OPERATIONAL_LEDGER",
    "InvariantEnforcementLevel",
    "OperationalInvariant",
    "OperationalLedgerEntry",
    "TestExecutionClassification",
    # Tool Gateway
    "ToolSensitivityClass",
    "TOOL_SENSITIVITY_REGISTRY",
    "CanonicalRequestEnvelope",
    "ShadowToolSimulator",
    "SimulatedToolResult",
    "StateSnapshotSanitizer",
    # Shadow Executor
    "StructuredShadowTraceComparison",
    "ShadowDiversityRequirements",
    "ShadowEvidenceDiversityGate",
    "ShadowNonInterferenceQueue",
    "ShadowExecutor",
    "ShadowMetrics",
    # Domain Benchmarks
    "BenchmarkDomain",
    "BenchmarkContaminationChecker",
    "BenchmarkContaminationError",
    "ContaminationCheckResult",
    "CanonicalEvaluationReport",
    "CategorySafetyGate",
    "CategoryGatingResult",
    "BaselineRelativeRegressionDetector",
    "BaselineRegressionResult",
    # Attribution & Hysteresis
    "FailureCause",
    "FailureAttributionEvidence",
    "FailureAttributionEngine",
    "RollbackDecision",
    "RollbackHysteresisController",
    # Promotion Machine
    "PromotionState",
    "OperatorApprovalToken",
    "OperatorAuthorizationValidator",
    "ModelActivationTransaction",
    "PromotionLifecycleManager",
    "AuthorizationError",
    # Voice & Behavioral
    "CancellationToken",
    "TaskGenerationContext",
    "VoiceInterruptionHarness",
    "CorrectionEvaluationHarness",
    "UntrustedContentFilter",
    "TraceReplayHarness",
    "RecordedTraceTurn",
    # Legacy Benchmarks
    "BenchmarkCase",
    "BenchmarkResult",
    "BenchmarkRunner",
    "BenchmarkSuiteResult",
    "AgentBenchmarkTrace",
    "BenchmarkAgent",
    "RegressionGate",
    "RegressionResult",
]
