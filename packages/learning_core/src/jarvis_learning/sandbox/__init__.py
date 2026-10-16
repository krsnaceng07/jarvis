"""Windows security boundary enforcement and hostile test harness for Phase 10 and Track 2.3."""

from __future__ import annotations

from jarvis_learning.sandbox.boundary_validator import (
    AttackOutcomeStatus,
    AttackTestResult,
    AttackVector,
    HostileBoundaryValidator,
)
from jarvis_learning.sandbox.broker_guard import BrokerGuard, CapabilityBroker
from jarvis_learning.sandbox.code_guard import CodeGuard
from jarvis_learning.sandbox.credential_guard import CredentialGuard
from jarvis_learning.sandbox.device_guard import DeviceGuard
from jarvis_learning.sandbox.evidence_sealer import EventHashChain, SandboxEvidenceSealer
from jarvis_learning.sandbox.filesystem_guard import FilesystemGuard
from jarvis_learning.sandbox.handle_isolator import HandleIsolator
from jarvis_learning.sandbox.hostile_matrix import HostileAttackMatrix
from jarvis_learning.sandbox.ipc_guard import IpcGuard
from jarvis_learning.sandbox.models import (
    BoundaryVerdict,
    EnforcementMechanism,
    ForensicDiffRecord,
    HostileProbeResult,
    IntegrityLevel,
    SeverityLevel,
    TokenDifferential,
    TokenStateSnapshot,
    VectorFamily,
)
from jarvis_learning.sandbox.network_guard import NetworkGuard
from jarvis_learning.sandbox.persistence_guard import PersistenceGuard
from jarvis_learning.sandbox.qualification import (
    SandboxQualificationEvaluator,
    SandboxQualificationGate,
)
from jarvis_learning.sandbox.resource_guard import ResourceGuard
from jarvis_learning.sandbox.restricted_launcher import RestrictedProcessLauncher
from jarvis_learning.sandbox.sandbox_lab_harness import SandboxValidationHarness
from jarvis_learning.sandbox.sandbox_oracle import (
    CANONICAL_EXPECTATIONS,
    OracleVectorExpectation,
    SandboxReferenceOracle,
)
from jarvis_learning.sandbox.sandbox_tier import (
    EnforcementClassification,
    SandboxAttestation,
    SandboxPolicyEngine,
    SandboxPolicySpec,
    SandboxSetupError,
    SandboxTier,
)
from jarvis_learning.sandbox.win32_job import Win32JobObjectEngine
from jarvis_learning.sandbox.win32_token import Win32TokenEngine
from jarvis_learning.sandbox.windows_tokens import (
    WindowsJobObjectConfig,
    WindowsTokenConfig,
    WorkerLaunchContext,
)

__all__ = [
    "AttackOutcomeStatus",
    "AttackTestResult",
    "AttackVector",
    "BoundaryVerdict",
    "BrokerGuard",
    "CANONICAL_EXPECTATIONS",
    "CapabilityBroker",
    "CodeGuard",
    "CredentialGuard",
    "DeviceGuard",
    "EnforcementClassification",
    "EnforcementMechanism",
    "EventHashChain",
    "FilesystemGuard",
    "ForensicDiffRecord",
    "HandleIsolator",
    "HostileAttackMatrix",
    "HostileBoundaryValidator",
    "HostileProbeResult",
    "IntegrityLevel",
    "IpcGuard",
    "NetworkGuard",
    "OracleVectorExpectation",
    "PersistenceGuard",
    "ResourceGuard",
    "RestrictedProcessLauncher",
    "SandboxAttestation",
    "SandboxEvidenceSealer",
    "SandboxPolicyEngine",
    "SandboxPolicySpec",
    "SandboxQualificationEvaluator",
    "SandboxQualificationGate",
    "SandboxReferenceOracle",
    "SandboxSetupError",
    "SandboxTier",
    "SandboxValidationHarness",
    "SeverityLevel",
    "TokenDifferential",
    "TokenStateSnapshot",
    "VectorFamily",
    "Win32JobObjectEngine",
    "Win32TokenEngine",
    "WindowsJobObjectConfig",
    "WindowsTokenConfig",
    "WorkerLaunchContext",
]
