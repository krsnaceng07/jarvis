"""jarvis_learning.datasets.dataset_manifest — reproducible dataset manifest contract.

Binds:
- Dataset ID and Builder Version
- Source Snapshot ID and Hash (frozen high-water mark)
- Random seeds (split_seed, ood_seed)
- Cryptographic Merkle Root over all sample digests
- Phase 5 Correction Manifest Hash (phase5_correction_manifest_hash)
- Logical build timestamp derived from source snapshot for byte-identical reproducibility.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .canonicalization import canonical_hash


# Canonical Phase 5 27-correction manifest hash
PHASE5_CORRECTION_MANIFEST_HASH = (
    "p5_corr_e9f18a24c58203b9b47e812d1c6809ef817a52cd719b33a02796e95c43d839bb"
)


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_id: str
    target: str
    dataset_version: str = "1.0.0"
    schema_version: str = "2"
    builder_version: str = "2.0.0"
    logical_build_timestamp: float = 0.0
    source_snapshot_id: str = ""
    source_snapshot_hash: str = ""
    phase5_correction_manifest_hash: str = PHASE5_CORRECTION_MANIFEST_HASH
    dataset_merkle_root: str = ""
    merkle_root: str = ""
    lifecycle_state: str = ""
    operator_approval: dict[str, Any] = field(default_factory=dict)
    total_samples: int = 0
    sample_counts: dict[str, int] = field(default_factory=dict)
    split_seed: int = 42
    ood_seed: int = 42
    split_counts: dict[str, int] = field(default_factory=dict)
    filter_config: dict[str, Any] = field(default_factory=dict)
    label_distribution: dict[str, int] = field(default_factory=dict)
    split_content_hashes: dict[str, str] = field(default_factory=dict)
    runtime_created_at: float = 0.0
    created_at: int = 0
    source_experience_count: int = 0
    approved_count: int = 0
    provenance_rejected: int = 0
    cleaning_rejected: int = 0
    label_rejected: int = 0
    dedup_removed: int = 0
    final_train_count: int = 0
    final_validation_count: int = 0
    final_test_count: int = 0
    final_challenge_count: int = 0
    train_content_hash: str = ""
    validation_content_hash: str = ""
    test_content_hash: str = ""
    challenge_content_hash: str = ""
    provenance_summary: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.dataset_merkle_root and self.merkle_root:
            object.__setattr__(self, "dataset_merkle_root", self.merkle_root)
        elif not self.merkle_root and self.dataset_merkle_root:
            object.__setattr__(self, "merkle_root", self.dataset_merkle_root)
        if not self.split_counts and (
            self.final_train_count
            or self.final_validation_count
            or self.final_test_count
            or self.final_challenge_count
        ):
            counts = {
                "train": self.final_train_count,
                "validation": self.final_validation_count,
                "test": self.final_test_count,
                "challenge": self.final_challenge_count,
            }
            object.__setattr__(self, "split_counts", counts)
        elif self.split_counts:
            if not self.final_train_count:
                object.__setattr__(self, "final_train_count", self.split_counts.get("train", 0))
            if not self.final_validation_count:
                object.__setattr__(
                    self, "final_validation_count", self.split_counts.get("validation", 0)
                )
            if not self.final_test_count:
                object.__setattr__(self, "final_test_count", self.split_counts.get("test", 0))
            if not self.final_challenge_count:
                object.__setattr__(
                    self, "final_challenge_count", self.split_counts.get("challenge", 0)
                )

    def compute_reproducibility_hash(self) -> str:
        """Compute deterministic hash of the dataset's logical inputs and resulting Merkle root."""
        core_record = {
            "target": self.target,
            "builder_version": self.builder_version,
            "logical_build_timestamp": self.logical_build_timestamp,
            "source_snapshot_hash": self.source_snapshot_hash,
            "phase5_correction_manifest_hash": self.phase5_correction_manifest_hash,
            "dataset_merkle_root": self.dataset_merkle_root,
            "split_seed": self.split_seed,
            "ood_seed": self.ood_seed,
            "split_counts": self.split_counts,
            "filter_config": self.filter_config,
            "label_distribution": self.label_distribution,
        }
        return canonical_hash(core_record)

    def to_json(self) -> str:
        d = {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "target": self.target,
            "schema_version": self.schema_version,
            "builder_version": self.builder_version,
            "logical_build_timestamp": self.logical_build_timestamp,
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "phase5_correction_manifest_hash": self.phase5_correction_manifest_hash,
            "dataset_merkle_root": self.dataset_merkle_root,
            "reproducibility_hash": self.compute_reproducibility_hash(),
            "split_seed": self.split_seed,
            "ood_seed": self.ood_seed,
            "split_counts": self.split_counts,
            "filter_config": self.filter_config,
            "label_distribution": self.label_distribution,
            "split_content_hashes": self.split_content_hashes,
            "runtime_created_at": self.runtime_created_at,
            "source_experience_count": self.source_experience_count,
            "approved_count": self.approved_count,
            "provenance_rejected": self.provenance_rejected,
            "cleaning_rejected": self.cleaning_rejected,
            "label_rejected": self.label_rejected,
            "dedup_removed": self.dedup_removed,
            "final_train_count": self.final_train_count,
            "final_validation_count": self.final_validation_count,
            "final_test_count": self.final_test_count,
            "final_challenge_count": self.final_challenge_count,
            "train_content_hash": self.train_content_hash,
            "validation_content_hash": self.validation_content_hash,
            "test_content_hash": self.test_content_hash,
            "challenge_content_hash": self.challenge_content_hash,
        }
        return json.dumps(d, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> DatasetManifest:
        data = json.loads(text)
        split_counts = data.get("split_counts", {})
        if not split_counts and "final_train_count" in data:
            split_counts = {
                "train": data.get("final_train_count", 0),
                "validation": data.get("final_validation_count", 0),
                "test": data.get("final_test_count", 0),
                "challenge": data.get("final_challenge_count", 0),
            }
        merkle = data.get("dataset_merkle_root", data.get("merkle_root", ""))
        return cls(
            dataset_id=data["dataset_id"],
            target=data["target"],
            dataset_version=data.get("dataset_version", "1.0.0"),
            schema_version=data.get("schema_version", "2"),
            builder_version=data.get("builder_version", "2.0.0"),
            logical_build_timestamp=data.get(
                "logical_build_timestamp", float(data.get("created_at", 0.0))
            ),
            source_snapshot_id=data.get("source_snapshot_id", ""),
            source_snapshot_hash=data.get("source_snapshot_hash", ""),
            phase5_correction_manifest_hash=data.get(
                "phase5_correction_manifest_hash", PHASE5_CORRECTION_MANIFEST_HASH
            ),
            dataset_merkle_root=merkle,
            merkle_root=merkle,
            lifecycle_state=data.get("lifecycle_state", ""),
            operator_approval=data.get("operator_approval", {}),
            total_samples=data.get("total_samples", 0),
            split_seed=int(data.get("split_seed", 42)),
            ood_seed=int(data.get("ood_seed", 42)),
            split_counts=split_counts,
            filter_config=data.get("filter_config", {}),
            label_distribution=data.get("label_distribution", {}),
            split_content_hashes=data.get("split_content_hashes", {}),
            runtime_created_at=data.get("runtime_created_at", 0.0),
            source_experience_count=data.get("source_experience_count", 0),
            approved_count=data.get("approved_count", 0),
            provenance_rejected=data.get("provenance_rejected", 0),
            cleaning_rejected=data.get("cleaning_rejected", 0),
            label_rejected=data.get("label_rejected", 0),
            dedup_removed=data.get("dedup_removed", 0),
            train_content_hash=data.get("train_content_hash", ""),
            validation_content_hash=data.get("validation_content_hash", ""),
            test_content_hash=data.get("test_content_hash", ""),
            challenge_content_hash=data.get("challenge_content_hash", ""),
        )

    def verify_hashes(self, dataset_dir: Path) -> dict[str, bool]:
        """Verify content hashes match actual files."""
        results: dict[str, bool] = {}
        for split_name in ("train", "validation", "test", "challenge"):
            expected = self.split_content_hashes.get(
                split_name, getattr(self, f"{split_name}_content_hash", "")
            )
            path = dataset_dir / f"{split_name}.jsonl"
            if not path.exists():
                results[split_name] = expected == ""
            elif expected:
                actual = compute_file_sha256(path)
                results[split_name] = actual == expected
            else:
                results[split_name] = True
        return results


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file's contents."""
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


compute_file_hash = compute_file_sha256
