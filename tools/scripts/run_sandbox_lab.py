#!/usr/bin/env python3
"""Standalone CLI runner for Track 2.3 Host OS Sandbox & Execution Boundary Validation Harness.

Usage:
    uv run python tools/scripts/run_sandbox_lab.py [--mode <mode>] [--output <path>] [options]

Modes:
    full-lab        - Run complete 16-family hostile attack matrix and generate sealed evidence
    token-audit     - Snapshot host and restricted tokens, compute differential
    quick-audit     - Fast non-destructive security boundary preflight audit
    verify-evidence - Cryptographically verify existing evidence file
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from jarvis_learning.sandbox.evidence_sealer import SandboxEvidenceSealer
from jarvis_learning.sandbox.handle_isolator import HandleIsolator
from jarvis_learning.sandbox.models import IntegrityLevel
from jarvis_learning.sandbox.sandbox_lab_harness import SandboxValidationHarness
from jarvis_learning.sandbox.win32_token import Win32TokenEngine


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def mode_token_audit() -> int:
    print("\n--- TOKEN AND INTEGRITY AUDIT ---")
    base = Win32TokenEngine.snapshot_current_process()
    print(f"Current Process Integrity: {base.integrity_level.value} (SID: {base.integrity_sid})")
    print(f"Is Elevated: {base.is_elevated} (Type: {base.elevation_type})")
    print(f"Privileges Count: {len(base.privileges)} (Enabled: {len(base.enabled_privileges)})")

    try:
        restr = Win32TokenEngine.create_restricted_token(target_integrity=IntegrityLevel.LOW)
        diff = Win32TokenEngine.compute_differential(base, restr)
        print("\nRestricted Token Differential:")
        print(
            f"  Integrity Lowered: {diff.integrity_lowered} ({diff.baseline_integrity.value} -> {diff.restricted_integrity.value})"
        )
        print(f"  Stripped Privileges: {len(diff.stripped_privileges)}")
        print(f"  Deny-Only Groups Added: {len(diff.deny_only_groups_added)}")
        print(f"  Is Strictly Confined: {diff.is_strictly_confined}")
    except Exception as exc:
        print(f"Restricted token creation error: {exc}")

    handle_audit = HandleIsolator.audit_handle_leakage()
    print(f"\nHandle Leak Audit: {'CLEAN' if handle_audit['is_clean'] else 'LEAK DETECTED'}")
    return 0


def mode_verify_evidence(evidence_path: Path) -> int:
    if not evidence_path.exists():
        print(f"ERROR: Evidence file not found: {evidence_path}")
        return 1

    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
        is_valid = SandboxEvidenceSealer.verify_seal(data)
        if is_valid:
            print(f"VALID: Evidence seal verified successfully: {evidence_path}")
            print(f"  Effective Evidence Level: {data.get('effective_evidence_level')}")
            print(f"  Event Hash Chain Final: {data.get('event_hash_chain_final')}")
            print(f"  Total Events Chained: {data.get('total_events_chained')}")
            return 0
        else:
            print(f"INVALID: Evidence seal verification failed for {evidence_path}")
            return 1
    except Exception as exc:
        print(f"ERROR: Failed parsing evidence file: {exc}")
        return 1


def mode_full_lab(output_path: Path | None, scratch_dir: Path | None) -> int:
    print("=" * 80)
    print("JARVIS TRACK 2.3 — HOST OS SANDBOX & EXECUTION BOUNDARY HARNESS")
    print("=" * 80)

    harness = SandboxValidationHarness(scratch_dir=scratch_dir)
    manifest = harness.run_validation()

    gate = manifest["qualification_gate"]
    oracle = manifest["oracle_evaluation"]
    level = manifest["effective_evidence_level"]
    seal_ok = manifest.get("seal_verified", False)

    print("\n[VALIDATION RESULTS]")
    print(f"  Overall Oracle Verdict:     {oracle['overall_verdict']}")
    print(f"  Total Hostile Probes:       {oracle['total_probes']}")
    print(f"  Passed Probes:              {oracle['passed']}")
    print(f"  Blocked Probes:             {oracle['blocked_count']}")
    print(f"  Degraded Probes:            {oracle['degraded']}")
    print(f"  Failed Probes:              {oracle['failed']}")
    print(f"  20-Dimension Gate Score:    {gate['passed_dimensions']} / 20")
    print(f"  Effective Evidence Level:   {level}")
    print(f"  Cryptographic Seal Valid:   {seal_ok}")
    print(f"  Event Hash Chain Final:     {manifest['event_hash_chain_final']}")
    print(f"  Total Chained Events:       {manifest['total_events_chained']}")

    print("\n[GOVERNANCE STATUS]")
    gov = manifest["governance_status"]
    print(
        f"  Live Training:              {'ENABLED' if gov['live_training_enabled'] else 'DISABLED'}"
    )
    print(
        f"  Auto Promotion:             {'ENABLED' if gov['auto_promotion_enabled'] else 'DISABLED'}"
    )
    print(f"  Operator Approval Required: {'YES' if gov['operator_approval_required'] else 'NO'}")
    print(f"  Production Active:          {'YES' if gov['production_active'] else 'NO'}")

    target_out = output_path or (Path.home() / ".jarvis" / "evidence" / "sandbox_lab.json")
    target_out.parent.mkdir(parents=True, exist_ok=True)
    target_out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n[EVIDENCE MANIFEST WRITTEN]: {target_out}")

    return 0 if oracle["overall_verdict"] == "PASS" and gate["is_qualified"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JARVIS Host OS Sandbox & Isolation Laboratory Validation Harness (Track 2.3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["full-lab", "token-audit", "verify-evidence"],
        default="full-lab",
        help="Execution mode (default: full-lab)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write evidence JSON manifest",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=None,
        help="Path to existing evidence manifest for verify-evidence mode",
    )
    parser.add_argument(
        "--scratch-dir",
        type=Path,
        default=None,
        help="Directory to use for transient probe files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging output",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.mode == "token-audit":
        return mode_token_audit()
    elif args.mode == "verify-evidence":
        path = args.evidence or (Path.home() / ".jarvis" / "evidence" / "sandbox_lab.json")
        return mode_verify_evidence(path)
    elif args.mode == "full-lab":
        return mode_full_lab(args.output, args.scratch_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
