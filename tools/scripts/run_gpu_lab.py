#!/usr/bin/env python3
"""Standalone CLI runner for Track 2.1 GPU Hardware Laboratory Validation Harness.

Usage:
    uv run python tools/scripts/run_gpu_lab.py [--mode <mode>] [--output <path>] [options]

Modes:
    observe          - Non-invasive hardware discovery & live sensor observation
    capability       - Deep backend execution and workload probing (CUDA, DirectML, CPU)
    safe-stress      - Safety-capped physical compute stress (max 80C, max 70% VRAM)
    replay           - Deterministic thermal hysteresis & emergency stop replay (L2)
    fault-injection  - Simulated GPU fault matrix (OOM, telemetry loss, contention)
    full-lab         - Complete laboratory run producing a signed evidence manifest
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys

from jarvis_learning.hardware.gpu_lab_harness import GPULabConfig, GPULabHarness
from jarvis_learning.hardware.models import TestVerdict


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JARVIS GPU Hardware Laboratory Validation Harness (Track 2.1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["observe", "capability", "safe-stress", "replay", "fault-injection", "full-lab"],
        default="full-lab",
        help="Execution mode (default: full-lab)",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=0,
        help="Device index to target for backend tests (default: 0)",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "cuda", "directml", "cpu"],
        default="auto",
        help="Compute backend to use (default: auto)",
    )
    parser.add_argument(
        "--max-vram-percent",
        type=float,
        default=70.0,
        help="Maximum VRAM utilization ratio percentage allowed during stress (default: 70.0)",
    )
    parser.add_argument(
        "--max-temperature-c",
        type=float,
        default=80.0,
        help="Maximum safe operating temperature in Celsius (default: 80.0)",
    )
    parser.add_argument(
        "--hard-abort-temperature-c",
        type=float,
        default=85.0,
        help="Hard emergency abort temperature in Celsius (default: 85.0)",
    )
    parser.add_argument(
        "--duration-sec",
        type=float,
        default=5.0,
        help="Observation or stress duration in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=None,
        help="Path to save evidence JSON report artifact",
    )
    parser.add_argument(
        "--operator",
        type=str,
        default="JARVIS_OPERATOR",
        help="Operator ID for cryptographic attestation (default: JARVIS_OPERATOR)",
    )
    parser.add_argument(
        "--allow-real-stress",
        action="store_true",
        help="Authorize bounded physical stress within safety limits",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON manifest to stdout",
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

    config = GPULabConfig(
        mode=args.mode,
        device_index=args.device,
        backend=args.backend,
        max_vram_ratio=args.max_vram_percent / 100.0,
        max_temperature_c=args.max_temperature_c,
        hard_abort_temperature_c=args.hard_abort_temperature_c,
        duration_seconds=args.duration_sec,
        output_path=args.output,
        operator_id=args.operator,
        allow_real_stress=args.allow_real_stress,
    )

    if not args.json:
        print("=" * 76)
        print("  JARVIS GPU Hardware Laboratory Validation Harness (Track 2.1)")
        print(
            f"  Mode: {config.mode.upper()} | Backend: {config.backend.upper()} | Device: {config.device_index}"
        )
        print("=" * 76)

    harness = GPULabHarness(config)
    report = harness.run()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    # Human-readable formatted console output
    print(f"\n[RUN COMPLETE] Run ID: {report.run_id} | Elapsed: {report.duration_ms:.1f}ms")
    print("-" * 76)
    print("DISCOVERED DEVICES:")
    for dev in report.devices:
        idx = dev["device_index"]
        name = dev["name"]["value"]
        vendor = dev["vendor"]["value"]
        dtype = dev["device_type"]["value"]
        vram_mb = dev["dedicated_vram_bytes"]["value"] // (1024 * 1024)
        shared_mb = dev["shared_memory_bytes"]["value"] // (1024 * 1024)
        driver = dev["driver_version"]["value"]
        backends = ", ".join(dev["backend_support"])
        print(f"  [{idx}] {name} ({vendor} {dtype})")
        print(f"      Dedicated VRAM: {vram_mb} MB | Shared Memory: {shared_mb} MB")
        print(f"      Driver: {driver} | Backends: [{backends}]")

    print("\nTEST EXECUTION MATRIX:")
    for t in report.test_records:
        badge = "[PASS]" if t.verdict == TestVerdict.PASS else f"[{t.verdict.value}]"
        print(
            f"  {badge:8s} {t.test_id:10s} {t.title[:42]:42s} | {t.evidence_level.value:18s} ({t.duration_ms:.1f}ms)"
        )

    print("\nL5 QUALIFICATION CHECKLIST:")
    checklist = report.l5_checklist.to_dict()
    for item, status in checklist.items():
        mark = "[x]" if status else "[ ]"
        print(f"  {mark} {item.replace('_', ' ').capitalize()}")

    print("-" * 76)
    print(f"EFFECTIVE EVIDENCE LEVEL: {report.effective_evidence_level.value}")
    print(f"RECOVERY STATUS:         {report.recovery_report['recovery_status']}")
    if report.attestation:
        print(f"SHA-256 DIGEST:          {report.attestation.get('integrity_digest', '')[:32]}...")
        print(f"OPERATOR ATTESTATION:    {report.attestation.get('operator_id')} (HMAC-SHA256)")

    if config.output_path:
        print(f"EVIDENCE SAVED TO:       {config.output_path.resolve()}")
    print("=" * 76)

    # Return exit code: fail if any test failed
    has_failure = any(t.verdict == TestVerdict.FAIL for t in report.test_records)
    return 1 if has_failure else 0


if __name__ == "__main__":
    sys.exit(main())
