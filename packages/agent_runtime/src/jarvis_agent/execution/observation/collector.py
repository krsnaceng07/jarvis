"""Observation Collector and Domain Collectors for Track 3.2.

Gathers empirical observations from external environment and adapter output,
producing machine-verifiable ObservationRecord instances with cryptographic
digests and timestamps.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
import uuid

from jarvis_agent.execution.adapters.base import AdapterExecutionOutput
from jarvis_agent.orchestration.models.command import ExecutionCommand
from jarvis_agent.orchestration.models.observation import (
    ObservationRecord,
    ObservationRequirement,
)

logger = logging.getLogger(__name__)


class ObservationCollector:
    """Collects empirical observations from command execution and environment."""

    def __init__(self) -> None:
        pass

    def collect(
        self,
        command: ExecutionCommand,
        adapter_output: AdapterExecutionOutput,
        requirements: list[ObservationRequirement] | None = None,
    ) -> list[ObservationRecord]:
        """Collect all required and domain observations for the command execution."""
        records: list[ObservationRecord] = []
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # If explicit requirements specified, evaluate each
        if requirements:
            for req in requirements:
                rec = self._evaluate_requirement(req, command, adapter_output, now_str)
                records.append(rec)
        else:
            # Generate default domain observation based on capability target
            rec = self._generate_default_observation(command, adapter_output, now_str)
            records.append(rec)

        return records

    def _evaluate_requirement(
        self,
        req: ObservationRequirement,
        command: ExecutionCommand,
        adapter_output: AdapterExecutionOutput,
        now_str: str,
    ) -> ObservationRecord:
        pred = req.predicate_type.upper()
        target = req.target

        success = False
        raw_data: Any = None
        err_msg: str | None = None

        if pred == "FILE_EXISTS":
            p = Path(target)
            exists = p.exists()
            success = exists
            if exists and p.is_file():
                try:
                    digest = hashlib.sha256(p.read_bytes()).hexdigest()
                    raw_data = {
                        "path": str(p),
                        "exists": True,
                        "sha256": digest,
                        "size_bytes": p.stat().st_size,
                    }
                except Exception as ex:
                    raw_data = {"path": str(p), "exists": True, "error": str(ex)}
            else:
                raw_data = {"path": str(p), "exists": exists}
                if not exists:
                    err_msg = f"File does not exist: {target}"

        elif pred == "EXIT_CODE_ZERO":
            ec = adapter_output.exit_code
            success = (ec == 0)
            raw_data = {"exit_code": ec}
            if not success:
                err_msg = f"Exit code is {ec}, expected 0"

        elif pred == "MEDIA_PAUSED":
            # Check media playback state in adapter evidence or output
            med_state = adapter_output.raw_evidence.get("media_state") or adapter_output.output_data or {}
            is_paused = bool(med_state.get("paused", False))
            success = is_paused
            raw_data = {"media_state": med_state, "paused": is_paused}
            if not success:
                err_msg = "Media playback is not paused"

        elif pred == "MEDIA_PLAYING":
            med_state = adapter_output.raw_evidence.get("media_state") or adapter_output.output_data or {}
            is_paused = bool(med_state.get("paused", True))
            success = not is_paused
            raw_data = {"media_state": med_state, "playing": not is_paused}
            if not success:
                err_msg = "Media is not playing"

        elif pred == "DOM_VISIBLE" or pred == "DOM_ELEMENT":
            evidence = adapter_output.raw_evidence
            success = adapter_output.success
            raw_data = {"target_selector": target, "evidence": evidence}

        elif pred == "JSON_MATCH" or pred == "EQUALS":
            out_val = adapter_output.output_data
            success = (out_val == req.expected_value)
            raw_data = {"observed": out_val, "expected": req.expected_value}
            if not success:
                err_msg = f"Observed value {out_val} does not equal expected {req.expected_value}"

        else:
            # Generic fallback
            success = adapter_output.success
            raw_data = adapter_output.output_data
            err_msg = adapter_output.error_message

        # Generate cryptographic digest of observation raw data
        raw_json = json.dumps(raw_data, sort_keys=True, default=str)
        data_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
        evidence_ref = f"obs:{req.requirement_id}:{data_hash[:16]}"

        return ObservationRecord(
            observation_id=f"obs_{uuid.uuid4().hex[:12]}",
            node_id=command.node_id,
            captured_at_utc=now_str,
            success=success,
            raw_data=raw_data,
            evidence_ref=evidence_ref,
            error_message=err_msg,
            metadata={
                "requirement_id": req.requirement_id,
                "predicate_type": req.predicate_type,
                "target": req.target,
            },
        )

    def _generate_default_observation(
        self,
        command: ExecutionCommand,
        adapter_output: AdapterExecutionOutput,
        now_str: str,
    ) -> ObservationRecord:
        raw_data = {
            "capability_target": command.capability_target,
            "success": adapter_output.success,
            "exit_code": adapter_output.exit_code,
            "output_data": adapter_output.output_data,
            "raw_evidence": adapter_output.raw_evidence,
        }
        raw_json = json.dumps(raw_data, sort_keys=True, default=str)
        data_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
        evidence_ref = f"ev:{command.node_id}:{data_hash[:16]}"

        return ObservationRecord(
            observation_id=f"obs_{uuid.uuid4().hex[:12]}",
            node_id=command.node_id,
            captured_at_utc=now_str,
            success=adapter_output.success,
            raw_data=raw_data,
            evidence_ref=evidence_ref,
            error_message=adapter_output.error_message,
            metadata={"capability_target": command.capability_target},
        )


__all__ = ["ObservationCollector"]
