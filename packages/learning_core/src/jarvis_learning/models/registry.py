"""jarvis_learning.models.registry — model registry and lifecycle tracking.

Persists model metadata, verification checksums, evaluation scores,
and status in SQLite table `learning_models`.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from ..experience import now_ms
from .lifecycle import ModelLifecycle, ModelStatus, StatusTransition

logger = logging.getLogger(__name__)

_REGISTRY_DDL = """
CREATE TABLE IF NOT EXISTS learning_models (
    model_id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    version TEXT NOT NULL,
    architecture TEXT NOT NULL,
    compute_tier TEXT NOT NULL,
    weights_path TEXT NOT NULL,
    weights_sha256 TEXT NOT NULL,
    artifact_size INTEGER NOT NULL,
    dataset_manifest_hash TEXT NOT NULL,
    parameters_count INTEGER NOT NULL,
    baseline_beaten TEXT NOT NULL,
    val_loss REAL NOT NULL,
    val_metrics TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at INTEGER NOT NULL,
    promoted_at INTEGER DEFAULT 0,
    rolled_back_at INTEGER DEFAULT 0,
    approved_by TEXT DEFAULT '',
    transition_history TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_learning_models_target ON learning_models(target);
CREATE INDEX IF NOT EXISTS idx_learning_models_status ON learning_models(status);
"""


@dataclass_entry := __import__("dataclasses").dataclass(frozen=True, slots=True)
class ModelRecord:
    """Registry record for a trained model."""

    model_id: str
    target: str
    version: str
    architecture: str
    compute_tier: str
    weights_path: str
    weights_sha256: str
    artifact_size: int
    dataset_manifest_hash: str
    parameters_count: int
    baseline_beaten: str
    val_loss: float
    val_metrics: dict[str, float]
    status: ModelStatus
    created_at: int
    promoted_at: int = 0
    rolled_back_at: int = 0
    approved_by: str = ""
    transition_history: tuple[StatusTransition, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "target": self.target,
            "version": self.version,
            "architecture": self.architecture,
            "compute_tier": self.compute_tier,
            "weights_path": self.weights_path,
            "weights_sha256": self.weights_sha256,
            "artifact_size": self.artifact_size,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "parameters_count": self.parameters_count,
            "baseline_beaten": self.baseline_beaten,
            "val_loss": self.val_loss,
            "val_metrics": json.dumps(self.val_metrics),
            "status": self.status.value,
            "created_at": self.created_at,
            "promoted_at": self.promoted_at,
            "rolled_back_at": self.rolled_back_at,
            "approved_by": self.approved_by,
            "transition_history": json.dumps([t.to_dict() for t in self.transition_history]),
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ModelRecord:
        d = dict(row)
        history_raw = json.loads(d.get("transition_history", "[]"))
        history = tuple(StatusTransition.from_dict(t) for t in history_raw)
        return cls(
            model_id=d["model_id"],
            target=d["target"],
            version=d["version"],
            architecture=d["architecture"],
            compute_tier=d.get("compute_tier", "fallback"),
            weights_path=d.get("weights_path", ""),
            weights_sha256=d.get("weights_sha256", ""),
            artifact_size=int(d.get("artifact_size", 0)),
            dataset_manifest_hash=d.get("dataset_manifest_hash", ""),
            parameters_count=int(d.get("parameters_count", 0)),
            baseline_beaten=d.get("baseline_beaten", ""),
            val_loss=float(d.get("val_loss", 0.0)),
            val_metrics=json.loads(d.get("val_metrics", "{}")),
            status=ModelStatus(d.get("status", "candidate")),
            created_at=int(d["created_at"]),
            promoted_at=int(d.get("promoted_at", 0)),
            rolled_back_at=int(d.get("rolled_back_at", 0)),
            approved_by=d.get("approved_by", ""),
            transition_history=history,
        )


class ModelRegistry:
    """Thread-safe SQLite model registry managing model lifecycles."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".jarvis" / "learning" / "learning.sqlite"
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(_REGISTRY_DDL)
                conn.commit()
            finally:
                conn.close()

    def register_model(
        self,
        *,
        model_id: str,
        target: str,
        version: str,
        architecture: str,
        compute_tier: str,
        weights_path: str,
        weights_sha256: str,
        artifact_size: int,
        dataset_manifest_hash: str,
        parameters_count: int,
        baseline_beaten: str,
        val_loss: float,
        val_metrics: dict[str, float],
        initial_status: ModelStatus = ModelStatus.CANDIDATE,
    ) -> ModelRecord:
        """Register a newly trained model candidate."""
        record = ModelRecord(
            model_id=model_id,
            target=target,
            version=version,
            architecture=architecture,
            compute_tier=compute_tier,
            weights_path=weights_path,
            weights_sha256=weights_sha256,
            artifact_size=artifact_size,
            dataset_manifest_hash=dataset_manifest_hash,
            parameters_count=parameters_count,
            baseline_beaten=baseline_beaten,
            val_loss=val_loss,
            val_metrics=val_metrics,
            status=initial_status,
            created_at=now_ms(),
        )

        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO learning_models
                    (model_id, target, version, architecture, compute_tier, weights_path,
                     weights_sha256, artifact_size, dataset_manifest_hash, parameters_count,
                     baseline_beaten, val_loss, val_metrics, status, created_at,
                     promoted_at, rolled_back_at, approved_by, transition_history)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.model_id,
                        record.target,
                        record.version,
                        record.architecture,
                        record.compute_tier,
                        record.weights_path,
                        record.weights_sha256,
                        record.artifact_size,
                        record.dataset_manifest_hash,
                        record.parameters_count,
                        record.baseline_beaten,
                        record.val_loss,
                        json.dumps(record.val_metrics),
                        record.status.value,
                        record.created_at,
                        record.promoted_at,
                        record.rolled_back_at,
                        record.approved_by,
                        json.dumps([]),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        logger.info(
            "Registered model %s (target=%s, status=%s)", model_id, target, initial_status.value
        )
        return record

    def register(self, record: ModelRecord) -> ModelRecord:
        """Register a model record directly."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO learning_models
                    (model_id, target, version, architecture, compute_tier, weights_path,
                     weights_sha256, artifact_size, dataset_manifest_hash, parameters_count,
                     baseline_beaten, val_loss, val_metrics, status, created_at,
                     promoted_at, rolled_back_at, approved_by, transition_history)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.model_id,
                        record.target,
                        record.version,
                        record.architecture,
                        record.compute_tier,
                        record.weights_path,
                        record.weights_sha256,
                        record.artifact_size,
                        record.dataset_manifest_hash,
                        record.parameters_count,
                        record.baseline_beaten,
                        record.val_loss,
                        json.dumps(record.val_metrics),
                        record.status.value,
                        record.created_at,
                        record.promoted_at,
                        record.rolled_back_at,
                        record.approved_by,
                        json.dumps([t.to_dict() for t in record.transition_history]),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return record

    def get(self, model_id: str) -> ModelRecord | None:
        """Alias for get_model."""
        return self.get_model(model_id)

    def get_model(self, model_id: str) -> ModelRecord | None:
        """Fetch model by unique identifier."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM learning_models WHERE model_id = ?", (model_id,)
            ).fetchone()
            return ModelRecord.from_row(row) if row else None
        finally:
            conn.close()

    def get_active(self, target: str) -> ModelRecord | None:
        """Alias for get_active_model."""
        return self.get_active_model(target)

    def get_active_model(self, target: str) -> ModelRecord | None:
        """Fetch the currently promoted model for a target."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM learning_models WHERE target = ? AND status = 'promoted' ORDER BY promoted_at DESC LIMIT 1",
                (target,),
            ).fetchone()
            return ModelRecord.from_row(row) if row else None
        finally:
            conn.close()

    def list_models(
        self, target: str | None = None, status: ModelStatus | None = None
    ) -> list[ModelRecord]:
        """List models filtered by target and/or status."""
        clauses = []
        params = []
        if target:
            clauses.append("target = ?")
            params.append(target)
        if status:
            clauses.append("status = ?")
            params.append(status.value)

        sql = "SELECT * FROM learning_models"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [ModelRecord.from_row(r) for r in rows]
        finally:
            conn.close()

    def transition_status(
        self,
        model_id: str,
        target_status: ModelStatus,
        *,
        actor: str,
        reason: str,
    ) -> ModelRecord:
        """Execute and persist an atomic lifecycle transition."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM learning_models WHERE model_id = ?", (model_id,)
                ).fetchone()
                if not row:
                    raise KeyError(f"Model {model_id} not found in registry")
                record = ModelRecord.from_row(row)

                # Validate transition through state machine
                transition = ModelLifecycle.transition(
                    record.status,
                    target_status,
                    actor=actor,
                    reason=reason,
                )

                new_history = list(record.transition_history) + [transition]
                promoted_at = (
                    now_ms() if target_status == ModelStatus.PROMOTED else record.promoted_at
                )
                rolled_back_at = (
                    now_ms() if target_status == ModelStatus.ROLLED_BACK else record.rolled_back_at
                )
                approved_by = actor if target_status == ModelStatus.PROMOTED else record.approved_by

                conn.execute(
                    """
                    UPDATE learning_models
                    SET status = ?, promoted_at = ?, rolled_back_at = ?, approved_by = ?, transition_history = ?
                    WHERE model_id = ?
                    """,
                    (
                        target_status.value,
                        promoted_at,
                        rolled_back_at,
                        approved_by,
                        json.dumps([t.to_dict() for t in new_history]),
                        model_id,
                    ),
                )
                conn.commit()

                # Fetch updated record
                row_upd = conn.execute(
                    "SELECT * FROM learning_models WHERE model_id = ?", (model_id,)
                ).fetchone()
                return ModelRecord.from_row(row_upd)
            finally:
                conn.close()

    def update_status(
        self,
        model_id: str,
        target_status: ModelStatus,
        *,
        actor: str = "operator",
        reason: str = "",
    ) -> ModelRecord:
        """Convenience alias for transition_status."""
        return self.transition_status(model_id, target_status, actor=actor, reason=reason)
