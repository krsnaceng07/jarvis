"""jarvis_learning.datasets.sample_identity — deterministic dual sample identity.

Enforces:
- logical_sample_id: deterministic hash of canonical evidence + transformation semantics.
  Stable across dataset rebuilds with the same inputs and transformation.
- materialized_sample_id: hash of logical_sample_id + dataset_build_id.
  Uniquely identifies a sample instance within a specific materialized build.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .canonicalization import canonical_json_bytes


def compute_logical_sample_id(
    evidence_digest: str,
    target: str,
    sample_usage: str,
    transformation_version: str = "v1",
    semantic_payload: dict[str, Any] | None = None,
) -> str:
    """Compute stable logical sample ID across builds."""
    record = {
        "evidence_digest": evidence_digest,
        "target": target,
        "sample_usage": sample_usage,
        "transformation_version": transformation_version,
        "semantic_payload": semantic_payload or {},
    }
    raw_hash = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    return f"lsmp_{raw_hash[:24]}"


def compute_materialized_sample_id(
    logical_sample_id: str,
    dataset_build_id: str,
    split: str = "",
) -> str:
    """Compute unique sample ID for a specific dataset build and split."""
    record = {
        "logical_sample_id": logical_sample_id,
        "dataset_build_id": dataset_build_id,
        "split": split,
    }
    raw_hash = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    return f"msmp_{raw_hash[:24]}"
