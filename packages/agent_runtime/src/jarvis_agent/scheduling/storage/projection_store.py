"""Materialized scheduler projection index backed by SQLite WAL.

HARD INVARIANT:
The projection tables are NOT the authoritative source of truth.
The projection can be completely dropped and reconstructed from the append-only
EventStore + deterministic reducer at any time.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.orchestration.state.reducer import reduce_events
from jarvis_agent.scheduling.models.node_state import (
    SchedulerNodeState,
    TaskAggregateState,
)
from jarvis_agent.scheduling.models.resource import (
    FencingToken,
    ResourceClaim,
    ResourceLease,
    ResourceMode,
)
from jarvis_agent.scheduling.storage.migrations import MigrationEngine


class ProjectionStore:
    """Materialized projection store for scheduler tasks, nodes, leases, and workers."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self._db_path = ":memory:"
        else:
            self._db_path = str(db_path)
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        cursor = self._conn.cursor()
        if self._db_path != ":memory:":
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        self._conn.commit()
        MigrationEngine.apply_migrations(self._conn)

    # --- Task Operations ---

    def upsert_task(
        self,
        task_id: str,
        conversation_id: str,
        plan_id: str | None,
        plan_revision: int,
        aggregate_state: TaskAggregateState,
        channel: str,
        created_at_utc: str,
        updated_at_utc: str,
        priority_ceiling: int = 3,
    ) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO scheduler_tasks_projection (
                task_id, conversation_id, plan_id, plan_revision,
                aggregate_state, channel, priority_ceiling,
                created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                plan_id=excluded.plan_id,
                plan_revision=excluded.plan_revision,
                aggregate_state=excluded.aggregate_state,
                updated_at_utc=excluded.updated_at_utc;
            """,
            (
                task_id,
                conversation_id,
                plan_id,
                plan_revision,
                aggregate_state.value,
                channel,
                priority_ceiling,
                created_at_utc,
                updated_at_utc,
            ),
        )
        self._conn.commit()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM scheduler_tasks_projection WHERE task_id = ?;", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    # --- Node Operations ---

    def upsert_node(
        self,
        node_id: str,
        task_id: str,
        plan_id: str,
        plan_revision: int,
        goal: str,
        capability_target: str,
        arguments: dict[str, Any],
        state: SchedulerNodeState,
        current_attempt: int,
        max_attempts: int,
        created_at_utc: str,
        updated_at_utc: str,
        effective_deadline_utc: str | None = None,
        priority_level: int = 2,
        worker_id: str | None = None,
        lease_generation: int = 0,
    ) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO scheduler_nodes_projection (
                node_id, task_id, plan_id, plan_revision, goal,
                capability_target, arguments_json, state, current_attempt,
                max_attempts, effective_deadline_utc, priority_level,
                worker_id, lease_generation, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                state=excluded.state,
                current_attempt=excluded.current_attempt,
                effective_deadline_utc=excluded.effective_deadline_utc,
                worker_id=excluded.worker_id,
                lease_generation=excluded.lease_generation,
                updated_at_utc=excluded.updated_at_utc;
            """,
            (
                node_id,
                task_id,
                plan_id,
                plan_revision,
                goal,
                capability_target,
                json.dumps(arguments, sort_keys=True, separators=(",", ":")),
                state.value,
                current_attempt,
                max_attempts,
                effective_deadline_utc,
                priority_level,
                worker_id,
                lease_generation,
                created_at_utc,
                updated_at_utc,
            ),
        )
        self._conn.commit()

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM scheduler_nodes_projection WHERE node_id = ?;", (node_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["arguments"] = json.loads(d.pop("arguments_json"))
        return d

    def get_nodes_for_task(self, task_id: str) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM scheduler_nodes_projection WHERE task_id = ? ORDER BY priority_level DESC, created_at_utc ASC;",
            (task_id,),
        )
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d["arguments"] = json.loads(d.pop("arguments_json"))
            results.append(d)
        return results

    def get_nodes_by_state(self, state: SchedulerNodeState) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM scheduler_nodes_projection WHERE state = ?;",
            (state.value,),
        )
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d["arguments"] = json.loads(d.pop("arguments_json"))
            results.append(d)
        return results

    # --- Resource Lease Operations with Fencing Generation ---

    def acquire_lease(
        self,
        claim: ResourceClaim,
        lease_id: str,
        worker_id: str,
        acquired_at_utc: str,
        expires_at_utc: str,
    ) -> ResourceLease | None:
        """Atomically acquire a lease, incrementing monotonic generation."""
        cursor = self._conn.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        try:
            # Query highest generation ever recorded for this resource key
            cursor.execute(
                "SELECT MAX(generation) FROM resource_leases WHERE resource_key = ?;",
                (claim.composite_key,),
            )
            max_gen_row = cursor.fetchone()
            current_max_gen = (
                int(max_gen_row[0]) if max_gen_row and max_gen_row[0] is not None else 0
            )
            next_gen = current_max_gen + 1

            # Check active leases for conflict
            cursor.execute(
                """
                SELECT worker_id, mode, expires_at_utc 
                FROM resource_leases 
                WHERE resource_key = ? AND is_active = 1;
                """,
                (claim.composite_key,),
            )
            active_rows = cursor.fetchall()
            for cur_worker, cur_mode, exp_str in active_rows:
                if exp_str > acquired_at_utc:
                    # Active lease exists
                    if (
                        claim.mode == ResourceMode.EXCLUSIVE
                        or cur_mode == ResourceMode.EXCLUSIVE.value
                    ):
                        if cur_worker != worker_id:
                            self._conn.rollback()
                            return None

            cursor.execute(
                """
                INSERT INTO resource_leases (
                    resource_key, worker_id, lease_id, task_id, node_id,
                    generation, mode, is_active, acquired_at_utc, expires_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(resource_key, worker_id) DO UPDATE SET
                    lease_id=excluded.lease_id,
                    task_id=excluded.task_id,
                    node_id=excluded.node_id,
                    generation=excluded.generation,
                    mode=excluded.mode,
                    is_active=1,
                    acquired_at_utc=excluded.acquired_at_utc,
                    expires_at_utc=excluded.expires_at_utc;
                """,
                (
                    claim.composite_key,
                    worker_id,
                    lease_id,
                    claim.task_id,
                    claim.node_id,
                    next_gen,
                    claim.mode.value,
                    acquired_at_utc,
                    expires_at_utc,
                ),
            )
            self._conn.commit()

            token = FencingToken(
                resource_key=claim.composite_key,
                owner_id=worker_id,
                generation=next_gen,
                acquired_at_utc=acquired_at_utc,
                expires_at_utc=expires_at_utc,
            )
            return ResourceLease(
                lease_id=lease_id,
                claim=claim,
                worker_id=worker_id,
                fencing_token=token,
            )
        except Exception:
            self._conn.rollback()
            raise

    def release_lease(self, resource_key: str, worker_id: str, generation: int) -> bool:
        """Release lease, marking is_active = 0 while preserving max generation history."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE resource_leases 
            SET is_active = 0
            WHERE resource_key = ? AND worker_id = ? AND generation = ?;
            """,
            (resource_key, worker_id, generation),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def get_lease(self, resource_key: str) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM resource_leases 
            WHERE resource_key = ? AND is_active = 1
            ORDER BY generation DESC LIMIT 1;
            """,
            (resource_key,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    # --- Reconstruction from Authoritative EventStore ---

    def rebuild_from_events(self, event_store: EventStore, task_id: str) -> None:
        """Drop and rebuild projection for a task deterministically from events."""
        events = event_store.get_events_for_task(task_id)
        if not events:
            return

        reduced_state = reduce_events(None, events)
        if not reduced_state.task:
            return

        cursor = self._conn.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        try:
            cursor.execute("DELETE FROM scheduler_nodes_projection WHERE task_id = ?;", (task_id,))
            cursor.execute("DELETE FROM scheduler_tasks_projection WHERE task_id = ?;", (task_id,))

            task = reduced_state.task
            cursor.execute(
                """
                INSERT INTO scheduler_tasks_projection (
                    task_id, conversation_id, plan_id, plan_revision,
                    aggregate_state, channel, priority_ceiling,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    task.task_id,
                    task.identity.conversation_id,
                    task.current_plan_id,
                    task.current_plan_revision,
                    TaskAggregateState.RUNNING.value,
                    task.response_route.channel,
                    3,
                    task.created_at_utc,
                    reduced_state.last_event_timestamp_utc or task.created_at_utc,
                ),
            )

            if reduced_state.plan:
                for _, node in reduced_state.plan.nodes.items():
                    sched_state = SchedulerNodeState.PENDING
                    if node.status.value == "COMPLETED":
                        sched_state = SchedulerNodeState.VERIFIED
                    elif node.status.value == "FAILED":
                        sched_state = SchedulerNodeState.FAILED
                    elif node.status.value == "READY":
                        sched_state = SchedulerNodeState.ELIGIBLE
                    elif node.status.value == "RUNNING":
                        sched_state = SchedulerNodeState.RUNNING
                    elif node.status.value == "CANCELLED":
                        sched_state = SchedulerNodeState.CANCELLED

                    cursor.execute(
                        """
                        INSERT INTO scheduler_nodes_projection (
                            node_id, task_id, plan_id, plan_revision, goal,
                            capability_target, arguments_json, state, current_attempt,
                            max_attempts, effective_deadline_utc, priority_level,
                            worker_id, lease_generation, created_at_utc, updated_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            node.node_id,
                            task.task_id,
                            reduced_state.plan.plan_id,
                            reduced_state.plan.revision,
                            node.goal,
                            node.capability,
                            json.dumps(node.arguments, sort_keys=True, separators=(",", ":")),
                            sched_state.value,
                            node.current_attempt,
                            node.max_attempts,
                            None,
                            2,
                            None,
                            0,
                            node.created_at_utc,
                            reduced_state.last_event_timestamp_utc or node.created_at_utc,
                        ),
                    )

            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self) -> None:
        self._conn.close()


__all__ = ["ProjectionStore"]
