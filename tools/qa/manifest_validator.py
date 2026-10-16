"""Track 3.5 Evidence Manifest Validation Engine.

Enforces schema validation, RFC-aligned deterministic hashing (DETERMINISTIC_SORTED_JSON_V1),
scenario uniqueness, qualification level consistency, and secret leakage prevention.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import jsonschema


class ManifestValidationError(Exception):
    """Raised when the qualification manifest violates schema or invariant rules."""


CANONICAL_ALGORITHM = "DETERMINISTIC_SORTED_JSON_V1"


def compute_manifest_hash(manifest_data: dict[str, Any]) -> str:
    """Compute deterministic canonical SHA-256 hash excluding manifestIntegrityHash."""
    data_copy = {k: v for k, v in manifest_data.items() if k != "manifestIntegrityHash"}
    canonical_json = json.dumps(
        data_copy,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return f"sha256:{hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()}"


def validate_manifest(
    manifest_path: Path,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate manifest schema, cryptographic integrity, uniqueness, consistency, and redaction."""
    if not manifest_path.exists():
        raise ManifestValidationError(f"Manifest file not found: {manifest_path}")

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ManifestValidationError(f"Malformed JSON in manifest: {exc}") from exc

    # 1. JSON Schema Validation
    if schema_path is None:
        schema_path = manifest_path.parent / "track35_evidence_manifest.schema.json"

    if schema_path.exists():
        with open(schema_path, "r", encoding="utf-8") as sf:
            schema_data = json.load(sf)
        try:
            jsonschema.validate(instance=data, schema=schema_data)
        except jsonschema.ValidationError as exc:
            raise ManifestValidationError(f"Schema validation error: {exc.message}") from exc

    # 2. Canonical Algorithm Verification
    alg = data.get("canonicalizationAlgorithm")
    if alg != CANONICAL_ALGORITHM:
        raise ManifestValidationError(
            f"Unsupported canonicalization algorithm: '{alg}'. Expected '{CANONICAL_ALGORITHM}'."
        )

    # 3. Cryptographic Integrity Hash
    recorded_hash = data.get("manifestIntegrityHash")
    computed_hash = compute_manifest_hash(data)
    if recorded_hash != computed_hash:
        raise ManifestValidationError(
            f"Manifest integrity verification failed!\nRecorded: {recorded_hash}\nComputed: {computed_hash}"
        )

    # 4. Duplicate Scenario ID Rejection & State Consistency
    seen_ids: set[str] = set()
    scenarios = data.get("scenarios", [])

    passed_count = 0
    failed_count = 0
    blocked_count = 0
    not_run_count = 0

    for idx, sc in enumerate(scenarios):
        sc_id = sc.get("scenarioId")
        if not sc_id:
            raise ManifestValidationError(f"Scenario at index {idx} is missing scenarioId")

        if sc_id in seen_ids:
            raise ManifestValidationError(f"Duplicate scenarioId detected: '{sc_id}'")
        seen_ids.add(sc_id)

        result = sc.get("result")
        level = sc.get("qualificationLevel")

        if result == "PASS":
            passed_count += 1
            assertions = sc.get("assertionsExecuted", [])
            if not assertions or len(assertions) == 0:
                raise ManifestValidationError(
                    f"Scenario '{sc_id}' has result 'PASS' but empty assertionsExecuted."
                )
            if level == "LIVE_PROVIDER":
                # Must not claim live provider PASS unless external provider is verified
                raise ManifestValidationError(
                    f"Scenario '{sc_id}' claims PASS at LIVE_PROVIDER level without live provider evidence."
                )
        elif result == "BLOCKED":
            blocked_count += 1
            blockers = sc.get("blockers", [])
            if not blockers or len(blockers) == 0:
                raise ManifestValidationError(
                    f"Scenario '{sc_id}' has result 'BLOCKED' but no blockers listed."
                )
            if sc.get("evidenceArtifacts"):
                raise ManifestValidationError(
                    f"Scenario '{sc_id}' has result 'BLOCKED' but contains fabricated evidenceArtifacts."
                )
        elif result == "NOT_RUN":
            not_run_count += 1
            if sc.get("evidenceArtifacts"):
                raise ManifestValidationError(
                    f"Scenario '{sc_id}' has result 'NOT_RUN' but contains fabricated evidenceArtifacts."
                )
        elif result == "FAIL":
            failed_count += 1
        else:
            raise ManifestValidationError(f"Scenario '{sc_id}' has unknown result: '{result}'")

        # 5. Secret Redaction Inspection
        for check_key in ["requirement", "limitations"]:
            val = str(sc.get(check_key, ""))
            for secret_pattern in ["sk-", "xoxb-", "ghp_", "Bearer "]:
                if secret_pattern in val:
                    raise ManifestValidationError(
                        f"Potential secret leakage detected in scenario '{sc_id}' field '{check_key}'!"
                    )

    # 6. Summary Count Parity
    summary = data.get("summary", {})
    if summary.get("totalScenarios") != len(scenarios):
        raise ManifestValidationError(
            f"Summary totalScenarios ({summary.get('totalScenarios')}) does not match scenarios list length ({len(scenarios)})"
        )
    if summary.get("passed") != passed_count:
        raise ManifestValidationError(
            f"Summary passed count ({summary.get('passed')}) does not match actual count ({passed_count})"
        )
    if summary.get("failed") != failed_count:
        raise ManifestValidationError(
            f"Summary failed count ({summary.get('failed')}) does not match actual count ({failed_count})"
        )
    if summary.get("blocked") != blocked_count:
        raise ManifestValidationError(
            f"Summary blocked count ({summary.get('blocked')}) does not match actual count ({blocked_count})"
        )
    if summary.get("notRun") != not_run_count:
        raise ManifestValidationError(
            f"Summary notRun count ({summary.get('notRun')}) does not match actual count ({not_run_count})"
        )

    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Track 3.5 Qualification Manifest")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("qa/manifests/track35_evidence_manifest.json"),
        help="Path to manifest JSON file",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Optional path to manifest schema JSON",
    )
    args = parser.parse_args()

    try:
        res = validate_manifest(args.manifest, args.schema)
        print(f"OK: Manifest validated successfully ({len(res.get('scenarios', []))} scenarios).")
        print(f"Integrity Hash: {res.get('manifestIntegrityHash')}")
        return 0
    except ManifestValidationError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
