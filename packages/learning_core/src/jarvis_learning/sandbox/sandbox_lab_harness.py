"""Master laboratory validation harness for Track 2.3 Host OS Sandbox & Isolation."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import platform
import time
from typing import Any

from jarvis_learning.sandbox.evidence_sealer import EventHashChain, SandboxEvidenceSealer
from jarvis_learning.sandbox.hostile_matrix import HostileAttackMatrix
from jarvis_learning.sandbox.qualification import SandboxQualificationEvaluator
from jarvis_learning.sandbox.sandbox_oracle import SandboxReferenceOracle
from jarvis_learning.sandbox.win32_token import Win32TokenEngine

logger = logging.getLogger(__name__)


class SandboxValidationHarness:
    """Master orchestrator for Track 2.3 Sandbox & Execution Boundary laboratory validation."""

    def __init__(self, scratch_dir: Path | None = None) -> None:
        self.scratch_dir = (
            scratch_dir.resolve()
            if scratch_dir is not None
            else (Path.home() / ".jarvis" / "sandbox_scratch").resolve()
        )
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        self.hash_chain = EventHashChain()

    def run_validation(self) -> dict[str, Any]:
        """Execute complete Track 2.3 sandbox boundary validation suite."""
        start_time = time.time()
        start_mono = time.perf_counter()

        # 1. Capture baseline host snapshot
        token_baseline = Win32TokenEngine.snapshot_current_process()
        self.hash_chain.add_event(
            {
                "stage": "BASELINE_HOST_SNAPSHOT",
                "token": token_baseline.to_dict(),
                "timestamp": start_time,
            }
        )

        # 2. Execute hostile attack matrix across all 16 vector families
        matrix = HostileAttackMatrix(self.scratch_dir)
        probe_results, forensic_diffs = matrix.run_all_vectors()

        for probe in probe_results:
            self.hash_chain.add_event(
                {
                    "stage": "HOSTILE_PROBE",
                    "probe": probe.to_dict(),
                }
            )

        for diff in forensic_diffs:
            self.hash_chain.add_event(
                {
                    "stage": "FORENSIC_DIFF",
                    "diff": diff.to_dict(),
                }
            )

        # 3. Independent Governance Oracle evaluation
        oracle_eval = SandboxReferenceOracle.evaluate_all(probe_results)
        self.hash_chain.add_event(
            {
                "stage": "ORACLE_EVALUATION",
                "oracle": oracle_eval,
            }
        )

        # 4. 20-Dimension Qualification Gate evaluation
        all_diffs_clean = all(d.is_clean for d in forensic_diffs)
        gate = SandboxQualificationEvaluator.evaluate(
            probe_results,
            is_clean_room=all_diffs_clean,
        )
        is_win_native = platform.system() == "Windows" and os.name == "nt"
        effective_level = gate.determine_effective_level(is_win_native)

        self.hash_chain.add_event(
            {
                "stage": "QUALIFICATION_EVALUATION",
                "gate": gate.to_dict(),
                "effective_level": effective_level.value,
            }
        )

        duration_sec = time.perf_counter() - start_mono

        # 5. Build raw manifest dictionary
        manifest = {
            "track": "TRACK_2.3",
            "title": "Host OS Sandbox, Isolation & Execution Boundary Harness",
            "timestamp": start_time,
            "duration_seconds": round(duration_sec, 3),
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "node": platform.node(),
            },
            "token_baseline": token_baseline.to_dict(),
            "probes": [p.to_dict() for p in probe_results],
            "forensic_diffs": [d.to_dict() for d in forensic_diffs],
            "oracle_evaluation": oracle_eval,
            "qualification_gate": gate.to_dict(),
            "effective_evidence_level": effective_level.value,
            "event_hash_chain_final": self.hash_chain.current_hash,
            "total_events_chained": self.hash_chain.event_count,
            "governance_status": {
                "live_training_enabled": False,
                "auto_promotion_enabled": False,
                "auto_deployment_enabled": False,
                "auto_strategy_promotion_enabled": False,
                "production_activation_enabled": False,
                "operator_approval_required": True,
                "production_readiness_approved": False,
                "production_active": False,
            },
            "scope_limitation": (
                "This validation certifies containment against the tested 16-family attack matrix "
                "under the observed host configuration. It does not claim absence of unmodeled "
                "or theoretical kernel vulnerabilities."
            ),
        }

        # 6. Seal manifest with SHA-256 and HMAC-SHA256
        digest = SandboxEvidenceSealer.compute_sha256_digest(manifest)
        attestation = SandboxEvidenceSealer.sign_attestation(digest)
        manifest["attestation"] = attestation

        # 7. Self-verify seal integrity
        seal_valid = SandboxEvidenceSealer.verify_seal(manifest)
        manifest["seal_verified"] = seal_valid

        return manifest


__all__ = ["SandboxValidationHarness"]
