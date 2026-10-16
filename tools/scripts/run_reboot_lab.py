#!/usr/bin/env python3
"""Standalone CLI runner for Track 2.2 Bare-Metal Reboot Persistence & Journal Harness.

Usage:
    uv run python tools/scripts/run_reboot_lab.py [--mode <mode>] [options]

Modes:
    arm       - Prepare durability workload, seal pre-reboot manifest, and arm transaction
    verify    - Verify persistence post-reboot, reconcile artifacts, audit PRAGMAs, seal evidence
    in-suite  - Complete self-contained durability audit (arm + crash matrix + same-session verify)
    status    - Display current lab state, active transaction, and boot session identity
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from jarvis_learning.persistence.boot_session import WindowsBootDetector
from jarvis_learning.persistence.models import RebootVerdict
from jarvis_learning.persistence.reboot_harness import RebootPersistenceHarness
from jarvis_learning.persistence.transaction import RebootTransactionManager


def default_lab_dir() -> Path:
    return Path.home() / ".jarvis" / "evidence" / "reboot_lab"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JARVIS Bare-Metal Reboot Persistence & Journal Harness (Track 2.2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["arm", "verify", "in-suite", "status"],
        default="in-suite",
        help="Harness execution mode (default: in-suite)",
    )
    parser.add_argument(
        "--lab-dir",
        type=Path,
        default=default_lab_dir(),
        help=f"Directory for persistence state, artifacts, and journals (default: {default_lab_dir()})",
    )
    parser.add_argument(
        "--tx",
        type=str,
        default=None,
        help="Expected transaction ID for verify mode",
    )
    parser.add_argument(
        "--trigger-task",
        action="store_true",
        help="Register one-shot Windows Scheduled Task on arming",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path to save final evidence JSON artifact",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON to stdout",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    lab_dir: Path = args.lab_dir.resolve()

    if not args.json:
        print("=" * 76)
        print("  JARVIS Bare-Metal Reboot Persistence & Journal Harness (Track 2.2)")
        print(f"  Mode: {args.mode.upper()} | Lab Directory: {lab_dir}")
        print("=" * 76)

    # 1. STATUS MODE
    if args.mode == "status":
        current_boot = WindowsBootDetector.capture_identity()
        active_tx = RebootTransactionManager.load_transaction(lab_dir)

        status_info = {
            "current_boot_session": current_boot.to_dict(),
            "active_transaction": active_tx.to_dict() if active_tx else None,
            "manifest_exists": (lab_dir / "pre_reboot_manifest.json").exists(),
            "evidence_exists": (lab_dir / RebootPersistenceHarness.EVIDENCE_FILE).exists(),
        }

        if args.json:
            print(json.dumps(status_info, indent=2))
            return 0

        print("\nCURRENT BOOT SESSION:")
        print(f"  Session ID:      {current_boot.boot_session_id}")
        print(f"  Boot Time UTC:   {current_boot.last_boot_up_time_utc}")
        print(f"  TickCount64:     {current_boot.tick_count_ms:,} ms")
        print(f"  Machine GUID:    {current_boot.machine_guid}")
        print(f"  OS Version:      {current_boot.os_version}")

        print("\nACTIVE TRANSACTION:")
        if active_tx:
            print(f"  Transaction ID:  {active_tx.transaction_id}")
            print(f"  State:           {active_tx.state.value}")
            print(f"  Armed At:        {active_tx.arm_timestamp_utc}")
            print(f"  Pre-Boot ID:     {active_tx.pre_boot_session_id}")
            print(f"  Expired:         {active_tx.is_expired()}")
        else:
            print("  No active transaction found in lab directory.")

        print("=" * 76)
        return 0

    # 2. ARM MODE
    if args.mode == "arm":
        success, msg, details = RebootPersistenceHarness.arm_pre_reboot(
            lab_dir,
            trigger_task=args.trigger_task,
        )

        if args.json:
            print(json.dumps({"success": success, "message": msg, "details": details}, indent=2))
            return 0 if success else 1

        print(f"\n[ARM RESULT] {'SUCCESS' if success else 'FAILED'}: {msg}")
        if success:
            tx_data = details["transaction"]
            print(f"  Transaction ID:  {tx_data['transaction_id']}")
            print(f"  Pre-Boot ID:     {tx_data['pre_boot_session_id']}")
            print(f"  Manifest Files:  {details['manifest_files']}")
            print(f"  Scheduled Task:  {details['task_details']}")
            print("\nREADY FOR REBOOT:")
            print("  To validate physical reboot, restart the machine now.")
            print(
                "  Upon reboot, log in and run: uv run python tools/scripts/run_reboot_lab.py --mode verify"
            )
        print("=" * 76)
        return 0 if success else 1

    # 3. VERIFY MODE
    if args.mode == "verify":
        success, msg, evidence = RebootPersistenceHarness.verify_post_reboot(
            lab_dir,
            expected_tx_id=args.tx,
            is_subprocess=True,
        )

        if args.output and evidence:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

        if args.json:
            print(json.dumps({"success": success, "message": msg, "evidence": evidence}, indent=2))
            return 0 if success else 1

        print(f"\n[VERIFY RESULT] {'SUCCESS' if success else 'FAILED'}: {msg}")
        if evidence:
            qual = evidence.get("qualification", {})
            print(f"  Transaction ID:  {evidence.get('transaction_id')}")
            print(f"  Verdict:         {evidence.get('verdict')}")
            print(f"  Reality:         {evidence.get('reboot_reality')}")
            print(f"  Evidence Level:  {evidence.get('evidence_level')}")
            print("\nQUALIFICATION DIMENSIONS:")
            for dim_name, dim_info in qual.get("dimensions", {}).items():
                mark = "[x]" if dim_info.get("qualified") else "[ ]"
                status = dim_info.get("status_label", "")
                print(f"  {mark} {dim_name:24s} [{status:12s}] {dim_info.get('details')}")

        if args.output:
            print(f"\nEVIDENCE SAVED TO: {args.output.resolve()}")
        print("=" * 76)
        return 0 if success else 1

    # 4. IN-SUITE MODE
    if args.mode == "in-suite":
        harness_result = RebootPersistenceHarness.run_in_suite_audit(
            lab_dir,
            is_subprocess=True,
        )

        evidence_dict = harness_result.to_dict()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(evidence_dict, indent=2), encoding="utf-8")

        if args.json:
            print(json.dumps(evidence_dict, indent=2))
            return 0 if harness_result.success else 1

        print(f"\n[IN-SUITE AUDIT RESULT] Verdict: {harness_result.verdict.value}")
        print(f"  Transaction ID:  {harness_result.transaction_id}")
        print(f"  Reboot Reality:  {harness_result.reboot_reality.value}")
        print(f"  Evidence Level:  {harness_result.evidence_level.value}")
        print(f"  Crashes Tested:  {harness_result.details['crash_points_tested']}/10 passed")

        print("\nCRASH POINT MATRIX (CP-01 to CP-10):")
        for cp in harness_result.details["crash_matrix"]:
            badge = "[PASS]" if cp["recovery_passed"] else "[FAIL]"
            print(
                f"  {badge:8s} {cp['crash_point_id']:6s} {cp['name']:26s} | Gen: {cp['recovered_generation']} | {cp['notes']}"
            )

        print("\nQUALIFICATION DIMENSIONS:")
        for dim_name, dim_info in harness_result.qualification.to_dict()["dimensions"].items():
            mark = "[x]" if dim_info["qualified"] else "[ ]"
            print(f"  {mark} {dim_name:24s} [{dim_info['status_label']:12s}] {dim_info['details']}")

        if args.output:
            print(f"\nEVIDENCE SAVED TO: {args.output.resolve()}")
        print("=" * 76)
        return 0 if (harness_result.verdict == RebootVerdict.PASS) else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
