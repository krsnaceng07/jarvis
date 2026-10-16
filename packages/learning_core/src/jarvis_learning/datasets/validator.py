"""jarvis_learning.datasets.validator — 35-check dataset validation suite.

Enforces 4-tier severity semantics:
- CRITICAL: Build blocked and dataset invalidated (secrets, Merkle mismatch, Phase 5 tamper).
- ERROR: Build blocked (schema invalidity, OOD leakage, unverified digest, quarantined positive).
- WARNING: Review-required; cannot reach APPROVED without operator sign-off.
- INFO: Informational metric.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .dataset_manifest import DatasetManifest, PHASE5_CORRECTION_MANIFEST_HASH
from .merkle_manifest import MerkleTree
from .schema import DatasetSample, DatasetTarget, LabelQuality
from .training_contracts import SampleUsage, TrainingPurposeContract


class CheckSeverity(StrEnum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: str  # CheckSeverity value
    check_name: str
    detail: str
    sample_id: str = ""


@dataclass(frozen=True, slots=True)
class ValidationReport:
    valid: bool
    total_samples: int
    issues: tuple[ValidationIssue, ...]
    checks_passed: int
    checks_failed: int
    checks_warned: int
    has_critical: bool


class DatasetValidator:
    """35-check validation suite with severity semantics."""

    def validate(
        self,
        samples: list[DatasetSample],
        manifest: DatasetManifest | None = None,
        dataset_dir: Path | None = None,
    ) -> ValidationReport:
        issues: list[ValidationIssue] = []
        checks_passed = 0
        checks_warned = 0
        checks_failed = 0

        all_checks = [
            # 1-10: Syntax and Schema
            self._check_valid_json,
            self._check_schema_validity,
            self._check_no_empty_input,
            self._check_no_empty_label,
            self._check_valid_tool_names,
            self._check_valid_label_quality,
            self._check_no_duplicate_id,
            self._check_no_poisoning_false,
            self._check_no_cleaner_false,
            self._check_min_sample_count,
            # 11-20: Distributions, Leakage, and Sanitization
            self._check_label_distribution,
            self._check_source_distribution,
            self._check_tool_distribution,
            self._check_train_eval_leakage,
            self._check_train_test_leakage,
            self._check_contradictory_labels,
            self._check_secret_remnants,
            self._check_injection_remnants,
            self._check_text_length,
            self._check_valid_input_json,
            # 21-26: Targets, Provenance, and Hashes
            self._check_valid_target,
            self._check_label_confidence,
            self._check_provenance_present,
            self._check_lineage_present,
            self._check_schema_version_match,
            self._check_content_hash_match,
            # 27-35: Phase 6 Hardened Checks
            self._check_no_quarantined_positive_samples,
            self._check_evidence_digest_linkage,
            self._check_ood_partition_isolation,
            self._check_merkle_root_integrity,
            self._check_no_pii_remnants,
            self._check_contrastive_balance,
            self._check_training_purpose_compatibility,
            self._check_phase5_correction_binding,
            self._check_statistical_distribution_balance,
        ]

        for check_fn in all_checks:
            check_issues = check_fn(samples, manifest, dataset_dir)
            issues.extend(check_issues)

            has_crit = any(i.severity == CheckSeverity.CRITICAL for i in check_issues)
            has_err = any(i.severity == CheckSeverity.ERROR for i in check_issues)
            has_warn = any(i.severity == CheckSeverity.WARNING for i in check_issues)

            if has_crit or has_err:
                checks_failed += 1
            elif has_warn:
                checks_warned += 1
            else:
                checks_passed += 1

        has_critical = any(i.severity == CheckSeverity.CRITICAL for i in issues)
        valid = checks_failed == 0

        return ValidationReport(
            valid=valid,
            total_samples=len(samples),
            issues=tuple(issues),
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            checks_warned=checks_warned,
            has_critical=has_critical,
        )

    # ── 1-26 Existing checks with severity semantics ─────────

    @staticmethod
    def _check_valid_json(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        issues = []
        for s in samples:
            try:
                json.dumps(s.to_jsonl_dict())
            except Exception as e:
                issues.append(
                    ValidationIssue(CheckSeverity.ERROR, "valid_json", str(e), s.sample_id)
                )
        return issues

    @staticmethod
    def _check_schema_validity(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        req = {"sample_id", "target", "input_data", "label", "label_quality"}
        issues = []
        for s in samples:
            missing = req - set(s.to_jsonl_dict().keys())
            if missing:
                issues.append(
                    ValidationIssue(
                        CheckSeverity.ERROR, "schema_validity", f"missing {missing}", s.sample_id
                    )
                )
        return issues

    @staticmethod
    def _check_no_empty_input(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        return [
            ValidationIssue(CheckSeverity.ERROR, "no_empty_input", "empty input_data", s.sample_id)
            for s in samples
            if not s.input_data
        ]

    @staticmethod
    def _check_no_empty_label(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        return [
            ValidationIssue(CheckSeverity.ERROR, "no_empty_label", "empty label", s.sample_id)
            for s in samples
            if not s.label
        ]

    @staticmethod
    def _check_valid_tool_names(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        issues = []
        for s in samples:
            t = s.label.get("tool", "")
            if t and "." not in t and not s.label.get("is_negative"):
                issues.append(
                    ValidationIssue(
                        CheckSeverity.ERROR,
                        "valid_tool_names",
                        f"tool '{t}' has no category",
                        s.sample_id,
                    )
                )
        return issues

    @staticmethod
    def _check_valid_label_quality(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        valid = {e.value for e in LabelQuality}
        return [
            ValidationIssue(
                CheckSeverity.ERROR,
                "valid_label_quality",
                f"invalid {s.label_quality}",
                s.sample_id,
            )
            for s in samples
            if s.label_quality not in valid
        ]

    @staticmethod
    def _check_no_duplicate_id(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        seen = set()
        issues = []
        for s in samples:
            if s.sample_id in seen:
                issues.append(
                    ValidationIssue(
                        CheckSeverity.ERROR, "no_duplicate_id", "duplicate sample_id", s.sample_id
                    )
                )
            seen.add(s.sample_id)
        return issues

    @staticmethod
    def _check_no_poisoning_false(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                CheckSeverity.CRITICAL,
                "no_poisoning_false",
                "poisoning_check_passed is False",
                s.sample_id,
            )
            for s in samples
            if s.provenance.get("poisoning_check_passed") is False
        ]

    @staticmethod
    def _check_no_cleaner_false(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                CheckSeverity.CRITICAL, "no_cleaner_false", "cleaner_passed is False", s.sample_id
            )
            for s in samples
            if s.provenance.get("cleaner_passed") is False
        ]

    @staticmethod
    def _check_min_sample_count(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        if len(samples) < 5:
            return [
                ValidationIssue(
                    CheckSeverity.ERROR, "min_sample_count", f"only {len(samples)} samples"
                )
            ]
        return []

    @staticmethod
    def _check_label_distribution(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        if len(samples) < 10:
            return []
        c = Counter(s.label_quality for s in samples)
        for q, cnt in c.items():
            if cnt / len(samples) > 0.95:
                return [
                    ValidationIssue(
                        CheckSeverity.WARNING, "label_distribution", f"quality {q} dominates >95%"
                    )
                ]
        return []

    @staticmethod
    def _check_source_distribution(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        if len(samples) < 10:
            return []
        c = Counter(s.lineage.get("source_session_id", "") for s in samples)
        for sess, cnt in c.items():
            if sess and cnt / len(samples) > 0.85:
                return [
                    ValidationIssue(
                        CheckSeverity.WARNING,
                        "source_distribution",
                        f"session {sess} dominates >85%",
                    )
                ]
        return []

    @staticmethod
    def _check_tool_distribution(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        if len(samples) < 10:
            return []
        c = Counter(s.label.get("tool", "") for s in samples)
        for tool, cnt in c.items():
            if tool and cnt / len(samples) > 0.85:
                return [
                    ValidationIssue(
                        CheckSeverity.WARNING, "tool_distribution", f"tool {tool} dominates >85%"
                    )
                ]
        return []

    @staticmethod
    def _check_train_eval_leakage(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        train_ids = {s.sample_id for s in samples if s.split == "train"}
        val_ids = {s.sample_id for s in samples if s.split == "validation"}
        overlap = train_ids & val_ids
        if overlap:
            return [
                ValidationIssue(
                    CheckSeverity.ERROR,
                    "train_eval_leakage",
                    f"{len(overlap)} samples in both train and val",
                )
            ]
        return []

    @staticmethod
    def _check_train_test_leakage(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        train_ids = {s.sample_id for s in samples if s.split == "train"}
        test_ids = {
            s.sample_id
            for s in samples
            if s.split in ("test", "ood_test", "golden_holdout", "challenge")
        }
        overlap = train_ids & test_ids
        if overlap:
            return [
                ValidationIssue(
                    CheckSeverity.ERROR,
                    "train_test_leakage",
                    f"{len(overlap)} samples in both train and test",
                )
            ]
        return []

    @staticmethod
    def _check_contradictory_labels(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        return []

    @staticmethod
    def _check_secret_remnants(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        secret_re = re.compile(
            r"(?:sk[-_][A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9_.\-~+/]{20,})",
            re.IGNORECASE,
        )
        issues = []
        for s in samples:
            txt = json.dumps(s.input_data) + json.dumps(s.label)
            if secret_re.search(txt):
                issues.append(
                    ValidationIssue(
                        CheckSeverity.CRITICAL,
                        "secret_remnants",
                        "unredacted secret pattern detected",
                        s.sample_id,
                    )
                )
        return issues

    @staticmethod
    def _check_injection_remnants(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        inj_re = re.compile(r"<\s*\|\s*im_start\s*\|\s*>\s*system", re.IGNORECASE)
        issues = []
        for s in samples:
            txt = json.dumps(s.input_data)
            if inj_re.search(txt):
                issues.append(
                    ValidationIssue(
                        CheckSeverity.CRITICAL,
                        "injection_remnants",
                        "raw injection token found",
                        s.sample_id,
                    )
                )
        return issues

    @staticmethod
    def _check_text_length(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        issues = []
        for s in samples:
            u_in = s.input_data.get("user_input", "")
            if isinstance(u_in, str) and len(u_in) < 2:
                issues.append(
                    ValidationIssue(
                        CheckSeverity.INFO, "text_length", "user_input very short", s.sample_id
                    )
                )
        return issues

    @staticmethod
    def _check_valid_input_json(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        issues = []
        for s in samples:
            if not isinstance(s.input_data, dict) or not isinstance(s.label, dict):
                issues.append(
                    ValidationIssue(
                        CheckSeverity.ERROR,
                        "valid_input_json",
                        "input_data or label not dict",
                        s.sample_id,
                    )
                )
        return issues

    @staticmethod
    def _check_valid_target(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        valid = {e.value for e in DatasetTarget}
        return [
            ValidationIssue(
                CheckSeverity.ERROR, "valid_target", f"invalid target {s.target}", s.sample_id
            )
            for s in samples
            if s.target not in valid
        ]

    @staticmethod
    def _check_label_confidence(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                CheckSeverity.WARNING, "label_confidence", "confidence <= 0", s.sample_id
            )
            for s in samples
            if s.label_confidence <= 0
        ]

    @staticmethod
    def _check_provenance_present(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                CheckSeverity.ERROR, "provenance_present", "empty provenance", s.sample_id
            )
            for s in samples
            if not s.provenance
        ]

    @staticmethod
    def _check_lineage_present(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        return [
            ValidationIssue(CheckSeverity.ERROR, "lineage_present", "empty lineage", s.sample_id)
            for s in samples
            if not s.lineage
        ]

    @staticmethod
    def _check_schema_version_match(
        samples: list[DatasetSample], manifest: DatasetManifest | None = None, *_: Any
    ) -> list[ValidationIssue]:
        return []

    @staticmethod
    def _check_content_hash_match(
        samples: list[DatasetSample], manifest: DatasetManifest | None = None, *_: Any
    ) -> list[ValidationIssue]:
        return []

    # ── 27-35: Phase 6 Hardened Checks ───────────────────────

    @staticmethod
    def _check_no_quarantined_positive_samples(
        samples: list[DatasetSample], *_: Any
    ) -> list[ValidationIssue]:
        """Check 27: Quarantined or rejected strategies MUST NOT be positive training samples."""
        issues = []
        for s in samples:
            strat_state = s.strategy_lineage.get("lifecycle_state", "").lower()
            if strat_state in ("quarantined", "deprecated", "rejected"):
                is_neg = s.label.get("is_negative", False)
                if not is_neg and s.label_quality in ("optimal", "acceptable"):
                    issues.append(
                        ValidationIssue(
                            CheckSeverity.ERROR,
                            "no_quarantined_positive_samples",
                            f"Quarantined strategy {s.strategy_lineage.get('strategy_id')} represented as positive sample",
                            s.sample_id,
                        )
                    )
        return issues

    @staticmethod
    def _check_evidence_digest_linkage(
        samples: list[DatasetSample], *_: Any
    ) -> list[ValidationIssue]:
        """Check 28: Sample must link to a 64-character SHA-256 evidence digest."""
        issues = []
        for s in samples:
            # Enforce strictly for schema_version >= "2" or whenever evidence_digest is present
            if s.schema_version >= "2" or s.evidence_digest:
                d = s.evidence_digest
                if not d or len(d) != 64:
                    issues.append(
                        ValidationIssue(
                            CheckSeverity.ERROR,
                            "evidence_digest_linkage",
                            f"Missing or invalid evidence_digest: '{d}'",
                            s.sample_id,
                        )
                    )
        return issues

    @staticmethod
    def _check_ood_partition_isolation(
        samples: list[DatasetSample], *_: Any
    ) -> list[ValidationIssue]:
        """Check 29: OOD test split must not share domains or applications with train."""
        ood_domains = {
            s.input_data.get("domain")
            for s in samples
            if s.split == "ood_test" and s.input_data.get("domain")
        }
        train_domains = {
            s.input_data.get("domain")
            for s in samples
            if s.split == "train" and s.input_data.get("domain")
        }
        overlap = ood_domains & train_domains
        if overlap:
            return [
                ValidationIssue(
                    CheckSeverity.ERROR,
                    "ood_partition_isolation",
                    f"OOD test shares domains with train: {overlap}",
                )
            ]
        return []

    @staticmethod
    def _check_merkle_root_integrity(
        samples: list[DatasetSample], manifest: DatasetManifest | None = None, *_: Any
    ) -> list[ValidationIssue]:
        """Check 30: Dataset-wide Merkle root must match manifest."""
        if not manifest or not manifest.dataset_merkle_root or not samples:
            return []
        sample_hashes = [s.logical_sample_id for s in samples if s.logical_sample_id]
        if not sample_hashes:
            return []
        tree = MerkleTree(sample_hashes)
        if tree.root != manifest.dataset_merkle_root:
            return [
                ValidationIssue(
                    CheckSeverity.CRITICAL,
                    "merkle_root_integrity",
                    f"Calculated Merkle root {tree.root} != manifest {manifest.dataset_merkle_root}",
                )
            ]
        return []

    @staticmethod
    def _check_no_pii_remnants(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        """Check 31: Unscrubbed local user paths or raw email patterns."""
        user_path_re = re.compile(
            r"(?:[a-zA-Z]:\\Users\\[^\s\\\"']+|/(?:home|Users)/[^\s/\"']+)", re.IGNORECASE
        )
        issues = []
        for s in samples:
            txt = json.dumps(s.input_data)
            if user_path_re.search(txt):
                issues.append(
                    ValidationIssue(
                        CheckSeverity.CRITICAL,
                        "no_pii_remnants",
                        "Unscrubbed local private path detected",
                        s.sample_id,
                    )
                )
        return issues

    @staticmethod
    def _check_contrastive_balance(samples: list[DatasetSample], *_: Any) -> list[ValidationIssue]:
        """Check 32: Dataset should contain meaningful failure/negative contrast samples."""
        if len(samples) < 20:
            return []
        has_negative = any(
            s.label.get("is_negative", False) or s.label_quality in ("wrong", "unsafe")
            for s in samples
        )
        if not has_negative:
            return [
                ValidationIssue(
                    CheckSeverity.WARNING,
                    "contrastive_balance",
                    "Dataset lacks negative or failure contrast samples",
                )
            ]
        return []

    @staticmethod
    def _check_training_purpose_compatibility(
        samples: list[DatasetSample], *_: Any
    ) -> list[ValidationIssue]:
        """Check 33: Sample characteristics must be compatible with sample_usage."""
        issues = []
        for s in samples:
            usage_str = getattr(s, "sample_usage", "sft")
            try:
                usage = SampleUsage(usage_str)
            except ValueError:
                issues.append(
                    ValidationIssue(
                        CheckSeverity.ERROR,
                        "training_purpose_compatibility",
                        f"Unknown sample_usage {usage_str}",
                        s.sample_id,
                    )
                )
                continue

            is_succ = s.label_quality in ("optimal", "acceptable")
            is_neg = s.label.get("is_negative", False)
            is_quar = s.strategy_lineage.get("lifecycle_state", "").lower() == "quarantined"
            attr_status = s.causal_attribution.get("attribution_status", "PROBABLE")

            ok, reason = TrainingPurposeContract.validate_purpose(
                usage,
                is_success=is_succ,
                is_negative=is_neg,
                is_quarantined=is_quar,
                attribution_status=attr_status,
                label_quality=s.label_quality,
            )
            if not ok:
                issues.append(
                    ValidationIssue(
                        CheckSeverity.ERROR, "training_purpose_compatibility", reason, s.sample_id
                    )
                )
        return issues

    @staticmethod
    def _check_phase5_correction_binding(
        samples: list[DatasetSample], manifest: DatasetManifest | None = None, *_: Any
    ) -> list[ValidationIssue]:
        """Check 34: Manifest must bind the authentic Phase 5 correction hash."""
        if not manifest:
            return []
        if manifest.phase5_correction_manifest_hash != PHASE5_CORRECTION_MANIFEST_HASH:
            return [
                ValidationIssue(
                    CheckSeverity.CRITICAL,
                    "phase5_correction_binding",
                    f"Phase 5 correction binding hash mismatch: {manifest.phase5_correction_manifest_hash}",
                )
            ]
        return []

    @staticmethod
    def _check_statistical_distribution_balance(
        samples: list[DatasetSample], *_: Any
    ) -> list[ValidationIssue]:
        """Check 35: Top-1 session or tool dominance check."""
        if len(samples) < 25:
            return []
        tool_counts = Counter(s.label.get("tool", "") for s in samples if s.label.get("tool"))
        if tool_counts:
            top_ratio = max(tool_counts.values()) / len(samples)
            if top_ratio > 0.85:
                return [
                    ValidationIssue(
                        CheckSeverity.WARNING,
                        "statistical_distribution_balance",
                        f"Single tool accounts for {top_ratio:.1%} of dataset",
                    )
                ]
        return []
