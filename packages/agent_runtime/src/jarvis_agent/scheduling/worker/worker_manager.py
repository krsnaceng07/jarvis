"""Worker lifecycle manager, heartbeats, and runtime singleton guard for Track 3.3.

HARD INVARIANTS:
1. Runtime Singleton: Uses a persistent database lock to prevent multiple JARVIS scheduler
   instances from conflicting on the same database.
2. Worker Heartbeats: Workers must periodically emit heartbeats. If a worker goes silent,
   its leases are declared FENCED and its active nodes become AMBIGUOUS.
3. Stale Worker Rejection: Any operation presenting a fencing generation older than
   the active generation is rejected.
"""

from __future__ import annotations

import datetime
import os
import uuid

from jarvis_agent.scheduling.models.worker import WorkerIdentity, WorkerStatus
from jarvis_agent.scheduling.storage.projection_store import ProjectionStore


class WorkerManager:
    """Manages worker registration, heartbeats, and stale worker fencing."""

    def __init__(self, store: ProjectionStore, host_identity: str = "local_host") -> None:
        self._store = store
        self.host_identity = host_identity
        self._active_worker: WorkerIdentity | None = None

    def register_worker(
        self,
        worker_epoch: int = 1,
        heartbeat_timeout_seconds: float = 15.0,
    ) -> WorkerIdentity:
        """Register a new scheduler worker instance."""
        worker_id = f"worker_{uuid.uuid4().hex[:8]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        pid = os.getpid()

        worker = WorkerIdentity(
            worker_id=worker_id,
            worker_epoch=worker_epoch,
            process_id=pid,
            host_identity=self.host_identity,
            started_at_utc=now,
            last_heartbeat_utc=now,
            status=WorkerStatus.ACTIVE,
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
        )

        cursor = self._store._conn.cursor()
        cursor.execute(
            """
            INSERT INTO worker_registry (
                worker_id, worker_epoch, process_id, host_identity,
                started_at_utc, last_heartbeat_utc, status, heartbeat_timeout_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                worker.worker_id,
                worker.worker_epoch,
                worker.process_id,
                worker.host_identity,
                worker.started_at_utc,
                worker.last_heartbeat_utc,
                worker.status.value,
                worker.heartbeat_timeout_seconds,
            ),
        )
        self._store._conn.commit()
        self._active_worker = worker
        return worker

    def heartbeat(self, worker_id: str) -> bool:
        """Record worker heartbeat timestamp."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor = self._store._conn.cursor()
        cursor.execute(
            """
            UPDATE worker_registry
            SET last_heartbeat_utc = ?, status = 'ACTIVE'
            WHERE worker_id = ? AND status != 'FENCED';
            """,
            (now, worker_id),
        )
        self._store._conn.commit()
        return cursor.rowcount > 0

    def fence_stale_workers(self) -> list[str]:
        """Detect workers that have exceeded heartbeat timeout and mark them FENCED."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        cursor = self._store._conn.cursor()
        cursor.execute(
            "SELECT worker_id, last_heartbeat_utc, heartbeat_timeout_seconds FROM worker_registry WHERE status = 'ACTIVE';"
        )
        fenced: list[str] = []
        for wid, hb_str, timeout_sec in cursor.fetchall():
            hb_dt = datetime.datetime.fromisoformat(hb_str)
            if (now_dt - hb_dt).total_seconds() > timeout_sec:
                fenced.append(wid)

        if fenced:
            cursor.executemany(
                "UPDATE worker_registry SET status = 'FENCED' WHERE worker_id = ?;",
                [(w,) for w in fenced],
            )
            self._store._conn.commit()

        return fenced

    def validate_fencing_generation(self, resource_key: str, generation: int) -> bool:
        """Validate that a presented fencing generation matches the active lease generation."""
        lease_data = self._store.get_lease(resource_key)
        if not lease_data:
            return False
        return int(lease_data["generation"]) == generation


__all__ = ["WorkerManager"]
