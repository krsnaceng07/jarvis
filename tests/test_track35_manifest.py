"""Test suite for Track 3.5 Evidence Manifest and Validation Engine.

Tests:
1. Schema conformance of the canonical manifest against Draft-07.
2. Duplicate scenario ID rejection.
3. Consistency between result and qualificationLevel.
4. Required assertionsExecuted evidence for PASS results.
5. BLOCKED and NOT_RUN records forbid fabricated evidence artifacts.
6. Secret and credential leakage detection.
7. Deterministic canonical serialization and integrity hashing (DETERMINISTIC_SORTED_JSON_V1).
8. Manifest regeneration idempotency.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.qa.generate_manifest import build_manifest_data
from tools.qa.manifest_validator import (
    ManifestValidationError,
    compute_manifest_hash,
    validate_manifest,
)

MANIFEST_PATH = Path("qa/manifests/track35_evidence_manifest.json")
SCHEMA_PATH = Path("qa/manifests/track35_evidence_manifest.schema.json")


def test_01_canonical_manifest_validates_cleanly() -> None:
    """Canonical manifest passes full schema, integrity, and consistency validation."""
    data = validate_manifest(MANIFEST_PATH, SCHEMA_PATH)
    assert data["manifestVersion"] == "1.0.0"
    assert data["canonicalizationAlgorithm"] == "DETERMINISTIC_SORTED_JSON_V1"
    assert len(data["scenarios"]) == 47
    assert data["summary"]["totalScenarios"] == 47
    assert data["summary"]["passed"] == 43
    assert data["summary"]["blocked"] == 3
    assert data["summary"]["notRun"] == 1
    assert data["summary"]["failed"] == 0


def test_02_duplicate_scenario_id_rejected(tmp_path: Path) -> None:
    """Manifest containing duplicate scenario IDs is rejected."""
    data = build_manifest_data()
    # Duplicate first scenario
    dup_sc = copy.deepcopy(data["scenarios"][0])
    data["scenarios"].append(dup_sc)
    data["summary"]["totalScenarios"] += 1
    data["summary"]["passed"] += 1
    data["manifestIntegrityHash"] = compute_manifest_hash(data)

    bad_path = tmp_path / "dup_manifest.json"
    bad_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="Duplicate scenarioId detected"):
        validate_manifest(bad_path, SCHEMA_PATH)


def test_03_pass_requires_assertions_executed(tmp_path: Path) -> None:
    """PASS scenario without assertionsExecuted is rejected."""
    data = build_manifest_data()
    data["scenarios"][0]["assertionsExecuted"] = []
    data["manifestIntegrityHash"] = compute_manifest_hash(data)

    bad_path = tmp_path / "empty_asserts.json"
    bad_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="empty assertionsExecuted"):
        validate_manifest(bad_path, SCHEMA_PATH)


def test_04_live_provider_pass_forbidden_without_evidence(tmp_path: Path) -> None:
    """LIVE_PROVIDER qualification level cannot be marked PASS prematurely."""
    data = build_manifest_data()
    # Attempt to mark Telegram live provider as PASS
    for sc in data["scenarios"]:
        if sc["scenarioId"] == "CH-LIVE-TG":
            sc["result"] = "PASS"
            sc["assertionsExecuted"] = ["telegram.send_message() returned 200"]
            sc.pop("blockers", None)
            break
    data["summary"]["passed"] += 1
    data["summary"]["blocked"] -= 1
    data["manifestIntegrityHash"] = compute_manifest_hash(data)

    bad_path = tmp_path / "live_pass.json"
    bad_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="claims PASS at LIVE_PROVIDER level"):
        validate_manifest(bad_path, SCHEMA_PATH)


def test_05_blocked_forbids_fabricated_artifacts(tmp_path: Path) -> None:
    """BLOCKED scenario cannot attach fabricated evidence artifacts."""
    data = build_manifest_data()
    for sc in data["scenarios"]:
        if sc["scenarioId"] == "CH-LIVE-DC":
            sc["evidenceArtifacts"] = [{"relativePath": "fake_dc_proof.json", "sha256": "0" * 64}]
            break
    data["manifestIntegrityHash"] = compute_manifest_hash(data)

    bad_path = tmp_path / "blocked_with_artifacts.json"
    bad_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="fabricated evidenceArtifacts"):
        validate_manifest(bad_path, SCHEMA_PATH)


def test_06_not_run_forbids_fabricated_artifacts(tmp_path: Path) -> None:
    """NOT_RUN scenario cannot attach fabricated evidence artifacts."""
    data = build_manifest_data()
    for sc in data["scenarios"]:
        if sc["scenarioId"] == "RH-PWR":
            sc["evidenceArtifacts"] = [{"relativePath": "fake_power_loss.log", "sha256": "1" * 64}]
            break
    data["manifestIntegrityHash"] = compute_manifest_hash(data)

    bad_path = tmp_path / "not_run_with_artifacts.json"
    bad_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="fabricated evidenceArtifacts"):
        validate_manifest(bad_path, SCHEMA_PATH)


def test_07_secret_redaction_guard(tmp_path: Path) -> None:
    """Unredacted API keys or Bearer tokens in manifest strings are caught and rejected."""
    data = build_manifest_data()
    data["scenarios"][0]["limitations"] += " using Bearer sk-live-secret-unmasked-token"
    data["manifestIntegrityHash"] = compute_manifest_hash(data)

    bad_path = tmp_path / "leaked_secret.json"
    bad_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="Potential secret leakage detected"):
        validate_manifest(bad_path, SCHEMA_PATH)


def test_08_deterministic_integrity_hash_and_idempotency() -> None:
    """Regenerating manifest reproduces exact byte-stable data and cryptographic hash."""
    m1 = build_manifest_data()
    m2 = build_manifest_data()

    assert m1["manifestIntegrityHash"] == m2["manifestIntegrityHash"]
    assert compute_manifest_hash(m1) == m1["manifestIntegrityHash"]

    # Tampering with a single character in requirement invalidates the hash
    tampered = copy.deepcopy(m1)
    tampered["scenarios"][0]["requirement"] += " modified"
    assert compute_manifest_hash(tampered) != m1["manifestIntegrityHash"]
