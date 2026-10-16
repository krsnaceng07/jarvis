"""jarvis_learning.datasets — training dataset generation pipeline."""

from .builder import DatasetBuildResult, DatasetBuilder, DatasetConfig
from .canonicalization import canonical_hash, canonical_json_bytes
from .dataset_lifecycle import DatasetLifecycleManager, DatasetLifecycleState, OperatorApproval
from .dataset_manifest import DatasetManifest, PHASE5_CORRECTION_MANIFEST_HASH, compute_file_sha256
from .dataset_revocation import DatasetRevocationManager, DatasetRevocationRecord
from .deduplicator import DatasetDeduplicator, DeduplicationResult
from .evidence_registry import EvidenceRegistryResolver, EvidenceResolutionResult
from .injection_filter import ContentOrigin, InjectionFilter, InjectionScanResult
from .leakage_groups import DisjointSet, LeakageGroupBuilder, LeakageGroupingResult, LeakageIdentity
from .merkle_manifest import MerkleTree
from .ood_policy import (
    HistoricalOODRegistry,
    HistoricalOODScope,
    OODHoldoutConfig,
    OODMode,
    OODPolicySelector,
    OODSelectionResult,
)
from .privacy_filter import PrivacyFilter
from .provenance_ledger import LedgerCheckpoint, ProvenanceEntry, ProvenanceLedger
from .redaction import RedactionAuditRecord, SecretScanner
from .resource_limits import ResourceLimits, validate_resource_bounds
from .sample_identity import compute_logical_sample_id, compute_materialized_sample_id
from .schema import DEFAULT_SAMPLE_WEIGHTS, DatasetSample, DatasetTarget, FailureType, LabelQuality
from .snapshot import ExperienceSourceSnapshot, compute_snapshot
from .split import GroupedSplitter, SplitResult, StratifiedGroupedSplitter
from .statistical_audit import DistributionAuditReport, StatisticalAuditor
from .training_contracts import SampleUsage, TrainingPurposeContract
from .validator import CheckSeverity, DatasetValidator, ValidationIssue, ValidationReport

__all__ = [
    "CheckSeverity",
    "ContentOrigin",
    "DEFAULT_SAMPLE_WEIGHTS",
    "DatasetBuildResult",
    "DatasetBuilder",
    "DatasetConfig",
    "DatasetDeduplicator",
    "DatasetLifecycleManager",
    "DatasetLifecycleState",
    "DatasetManifest",
    "DatasetRevocationManager",
    "DatasetRevocationRecord",
    "DatasetSample",
    "DatasetTarget",
    "DatasetValidator",
    "DeduplicationResult",
    "DisjointSet",
    "DistributionAuditReport",
    "EvidenceRegistryResolver",
    "EvidenceResolutionResult",
    "ExperienceSourceSnapshot",
    "FailureType",
    "GroupedSplitter",
    "HistoricalOODRegistry",
    "HistoricalOODScope",
    "InjectionFilter",
    "InjectionScanResult",
    "LabelQuality",
    "LedgerCheckpoint",
    "LeakageGroupBuilder",
    "LeakageGroupingResult",
    "LeakageIdentity",
    "MerkleTree",
    "OODHoldoutConfig",
    "OODMode",
    "OODPolicySelector",
    "OODSelectionResult",
    "OperatorApproval",
    "PHASE5_CORRECTION_MANIFEST_HASH",
    "PrivacyFilter",
    "ProvenanceEntry",
    "ProvenanceLedger",
    "RedactionAuditRecord",
    "ResourceLimits",
    "SampleUsage",
    "SecretScanner",
    "SplitResult",
    "StatisticalAuditor",
    "StratifiedGroupedSplitter",
    "TrainingPurposeContract",
    "ValidationIssue",
    "ValidationReport",
    "canonical_hash",
    "canonical_json_bytes",
    "compute_file_sha256",
    "compute_logical_sample_id",
    "compute_materialized_sample_id",
    "compute_snapshot",
    "validate_resource_bounds",
]
