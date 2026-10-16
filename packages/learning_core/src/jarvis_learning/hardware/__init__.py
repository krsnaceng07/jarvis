"""Hardware discovery, resource governors, and laboratory validation for Track 2.1."""

from __future__ import annotations

from jarvis_learning.hardware.device_discovery import DiscoveredDevice, LayeredDiscoveryEngine
from jarvis_learning.hardware.device_probe import DeviceProbeEngine
from jarvis_learning.hardware.evidence_integrity import (
    EvidenceIntegritySealer,
    L5QualificationChecklist,
)
from jarvis_learning.hardware.evidence_schema import (
    ChainedEvent,
    EventHashChain,
    TestExecutionRecord,
)
from jarvis_learning.hardware.fault_injection import FaultInjectionResult, GPUFaultInjector
from jarvis_learning.hardware.governance_reference import GovernanceReferenceModel
from jarvis_learning.hardware.gpu_lab_harness import GPULabConfig, GPULabHarness, GPULabReport
from jarvis_learning.hardware.memory_probe import ActiveVoiceHeadroomProber, MemoryProbeEngine
from jarvis_learning.hardware.models import (
    DeviceType,
    DirectMLCapability,
    EvidenceLevel,
    FallbackReason,
    HardwareReality,
    LabSafetyLimits,
    MemoryAccounting,
    TelemetryQuality,
    TestVerdict,
)
from jarvis_learning.hardware.permissions import PermissionInspector, PermissionProfile
from jarvis_learning.hardware.provenance import ProvenanceValue
from jarvis_learning.hardware.recovery_validator import (
    HardwareSnapshot,
    RecoveryAuditReport,
    RecoveryValidator,
)
from jarvis_learning.hardware.resource_lease import (
    LeasePriority,
    ResourceLease,
    ResourceLeaseManager,
)
from jarvis_learning.hardware.run_lock import (
    LabRunConflictError,
    RunLockPayload,
    SingleInstanceRunLock,
)
from jarvis_learning.hardware.safe_stress import SafeStressEngine, StressRunSummary
from jarvis_learning.hardware.telemetry import HardwareTelemetrySample, TelemetryCollector
from jarvis_learning.hardware.telemetry_quality import TelemetryQualityValidator
from jarvis_learning.hardware.thermal_monitor import (
    ThermalAction,
    ThermalMonitor,
    ThermalState,
    ThermalThresholds,
)
from jarvis_learning.hardware.thermal_observer import ThermalObservationReport, ThermalObserver
from jarvis_learning.hardware.thermal_replay import ThermalReplayEngine, ThermalReplayReport
from jarvis_learning.hardware.vram_governor import (
    VRAMAction,
    VRAMGovernor,
    VRAMMetrics,
    VRAMState,
    VRAMThresholds,
)

__all__ = [
    "ActiveVoiceHeadroomProber",
    "ChainedEvent",
    "DeviceProbeEngine",
    "DeviceType",
    "DirectMLCapability",
    "DiscoveredDevice",
    "EventHashChain",
    "EvidenceIntegritySealer",
    "EvidenceLevel",
    "FallbackReason",
    "FaultInjectionResult",
    "GPULabConfig",
    "GPULabHarness",
    "GPULabReport",
    "GPUFaultInjector",
    "GovernanceReferenceModel",
    "HardwareReality",
    "HardwareSnapshot",
    "HardwareTelemetrySample",
    "L5QualificationChecklist",
    "LabRunConflictError",
    "LabSafetyLimits",
    "LayeredDiscoveryEngine",
    "LeasePriority",
    "MemoryAccounting",
    "MemoryProbeEngine",
    "PermissionInspector",
    "PermissionProfile",
    "ProvenanceValue",
    "RecoveryAuditReport",
    "RecoveryValidator",
    "ResourceLease",
    "ResourceLeaseManager",
    "RunLockPayload",
    "SafeStressEngine",
    "SingleInstanceRunLock",
    "StressRunSummary",
    "TelemetryCollector",
    "TelemetryQuality",
    "TelemetryQualityValidator",
    "TestExecutionRecord",
    "TestVerdict",
    "ThermalAction",
    "ThermalMonitor",
    "ThermalObservationReport",
    "ThermalObserver",
    "ThermalReplayEngine",
    "ThermalReplayReport",
    "ThermalState",
    "ThermalThresholds",
    "VRAMAction",
    "VRAMGovernor",
    "VRAMMetrics",
    "VRAMState",
    "VRAMThresholds",
]
