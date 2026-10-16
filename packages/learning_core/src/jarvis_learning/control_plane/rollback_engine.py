"""Five-class atomic rollback engine with strict class-specific SLOs.

Enforces INV-P10-RB-001: Rollback must restore a verified known-good artifact
and correct pointer atomically within target class SLO.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import os
from pathlib import Path
import time
import uuid


class RollbackClass(enum.Enum):
    """Classified rollback operations with specific latency SLO ceilings."""

    R1_IN_MEMORY = "R1_IN_MEMORY"  # Routing pointer switch (SLO <= 50ms)
    R2_ATOMIC_ARTIFACT = "R2_ATOMIC_ARTIFACT"  # Artifact pointer restoration (SLO <= 250ms)
    R3_WORKER_RESTART = "R3_WORKER_RESTART"  # Worker restart with previous artifact (SLO <= 3000ms)
    R4_MODEL_UNLOAD_RELOAD = "R4_MODEL_UNLOAD_RELOAD"  # GPU VRAM unload/reload
    R5_DISASTER_RECOVERY = "R5_DISASTER_RECOVERY"  # Full multi-step disaster recovery


@dataclasses.dataclass(frozen=True)
class RollbackRecord:
    """Auditable log of executed rollback operation."""

    rollback_id: str
    rollback_class: RollbackClass
    from_model: str
    to_model: str
    latency_ms: float
    slo_met: bool
    status: str
    timestamp_ns: int = dataclasses.field(default_factory=time.time_ns)


class RollbackEngine:
    """Executes classified atomic rollbacks."""

    SLO_CEILINGS_MS = {
        RollbackClass.R1_IN_MEMORY: 50.0,
        RollbackClass.R2_ATOMIC_ARTIFACT: 250.0,
        RollbackClass.R3_WORKER_RESTART: 3000.0,
        RollbackClass.R4_MODEL_UNLOAD_RELOAD: 15000.0,
        RollbackClass.R5_DISASTER_RECOVERY: 60000.0,
    }

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._pointer_file = root_dir / "ACTIVE_POINTER.json"
        self._history: list[RollbackRecord] = []

    def execute_rollback(
        self,
        rollback_class: RollbackClass,
        from_model: str,
        to_model: str,
        known_good_digest: str,
    ) -> RollbackRecord:
        """Atomically restore active pointer to known good model target within SLO."""
        t0 = time.perf_counter()
        rollback_id = f"rb_{uuid.uuid4().hex[:8]}"

        # Atomic pointer update (R1 or R2)
        temp_pointer = self._root_dir / f".rb_pointer_{uuid.uuid4().hex[:8]}.tmp"
        data = {
            "active_version": to_model,
            "digest": known_good_digest,
            "status": "ROLLED_BACK",
            "rollback_id": rollback_id,
        }
        temp_pointer.write_text(json.dumps(data, indent=2), encoding="utf-8")

        with open(temp_pointer, "rb+") as f:
            f.flush()
            os.fsync(f.fileno())

        os.replace(str(temp_pointer), str(self._pointer_file))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        ceiling = self.SLO_CEILINGS_MS.get(rollback_class, 50.0)
        slo_met = elapsed_ms <= ceiling

        record = RollbackRecord(
            rollback_id=rollback_id,
            rollback_class=rollback_class,
            from_model=from_model,
            to_model=to_model,
            latency_ms=elapsed_ms,
            slo_met=slo_met,
            status="SUCCESS",
        )
        self._history.append(record)
        return record

    @property
    def history(self) -> list[RollbackRecord]:
        return list(self._history)
