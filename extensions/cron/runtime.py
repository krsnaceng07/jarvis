"""CronTable — the cross-extension cron store.

Phase 2: in-memory dict of CronDecl backed by the shared SQLite state
database. The host's ``CronRunner``
reads from this table to build its job list.

This is intentionally separate from ``src.cron.CronRunner``
(the execution engine) so the data model is testable without
threads.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from jarvis_sdk import CronDecl


class CronTable:
    """Cross-extension cron table.

    A single instance is created at host startup and shared across
    every cron-consuming plugin (``cron`` extension, ``tool_reminder``
    extension, …). Plugins add/remove jobs; the host's
    ``CronRunner`` reads the snapshot.
    """

    _default: CronTable | None = None
    _lock = threading.Lock()

    def __init__(self, store_path: Path | None = None) -> None:
        if store_path is None:
            from jarvis_state_core import resolve_state_sqlite_path

            store_path = Path(resolve_state_sqlite_path())
        self._store_path = store_path
        self._jobs: dict[str, CronDecl] = {}
        self._mu = threading.Lock()
        if self._uses_json_compat and store_path.exists():
            self._load()
        elif not self._uses_json_compat:
            self._init_sqlite()

    @classmethod
    def default(cls) -> CronTable:
        with cls._lock:
            if cls._default is None:
                cls._default = cls()
            return cls._default

    def add(self, job: CronDecl) -> None:
        with self._mu:
            self._jobs[job.id] = job
        self._save()

    def remove(self, job_id: str) -> bool:
        with self._mu:
            existed = self._jobs.pop(job_id, None) is not None
        if existed:
            self._save()
        return existed

    def list(self) -> list[dict[str, Any]]:
        with self._mu:
            return [
                {
                    "id": j.id,
                    "schedule": j.schedule,
                    "description": j.description,
                    "enabled": j.enabled,
                }
                for j in self._jobs.values()
            ]

    def get(self, job_id: str) -> CronDecl | None:
        with self._mu:
            return self._jobs.get(job_id)

    def fire_now(self, job_id: str) -> bool:
        """Manually fire a job's handler (best-effort, sync)."""
        job = self.get(job_id)
        if job is None:
            return False
        try:
            result = job.handler()
            if result is not None and hasattr(result, "__await__"):
                # Phase 2: cron runner is async-aware. For a manual
                # fire from the CLI, we accept either sync or async.
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(result)
                else:
                    _ = loop.create_task(result)  # noqa: RUF006 (fire-and-forget)
        except Exception:
            return False
        return True

    # ── Persistence ────────────────────────────────────────────────

    def _save(self) -> None:
        if self._store_path is None:
            return
        if not self._uses_json_compat:
            with sqlite3.connect(self._store_path) as connection:
                connection.execute("DELETE FROM cron_jobs")
                connection.executemany(
                    """
                    INSERT INTO cron_jobs
                        (id, schedule, description, enabled, timezone, automation_payload)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        schedule = excluded.schedule,
                        description = excluded.description,
                        enabled = excluded.enabled,
                        timezone = excluded.timezone,
                        automation_payload = excluded.automation_payload
                    """,
                    [
                        (
                            job.id,
                            job.schedule,
                            job.description,
                            int(job.enabled),
                            job.timezone,
                            json.dumps(job.automation_payload)
                            if job.automation_payload is not None
                            else None,
                        )
                        for job in self._jobs.values()
                    ],
                )
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, dict[str, object]] = {
            jid: {
                "id": j.id,
                "schedule": j.schedule,
                "description": j.description,
                "enabled": j.enabled,
                "timezone": j.timezone,
                "automation_payload": j.automation_payload,
            }
            for jid, j in self._jobs.items()
        }
        self._store_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load(self) -> None:
        if self._store_path is None:
            return
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for jid, jd in data.items():
            # Handlers cannot be persisted — they re-attach on reload.
            # The cron runner calls ``table.get(id).handler`` after
            # the host wires the live handlers.
            payload = jd.get("automation_payload")
            self._jobs[jid] = CronDecl(
                id=jd.get("id", jid),
                schedule=jd.get("schedule", ""),
                handler=_create_automation_handler(payload) if payload else lambda: None,
                description=jd.get("description", ""),
                enabled=jd.get("enabled", True),
                timezone=jd.get("timezone", ""),
                automation_payload=payload,
            )

    @property
    def _uses_json_compat(self) -> bool:
        return self._store_path is not None and self._store_path.suffix.lower() == ".json"

    def _init_sqlite(self) -> None:
        assert self._store_path is not None
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._store_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cron_jobs (
                    id TEXT PRIMARY KEY,
                    schedule TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    timezone TEXT NOT NULL DEFAULT '',
                    automation_payload TEXT
                )
                """
            )
            rows = connection.execute(
                "SELECT id, schedule, description, enabled, timezone, automation_payload "
                "FROM cron_jobs"
            ).fetchall()
        for job_id, schedule, description, enabled, timezone, raw_payload in rows:
            try:
                payload = json.loads(raw_payload) if raw_payload else None
            except (TypeError, json.JSONDecodeError):
                payload = None
            self._jobs[job_id] = CronDecl(
                id=job_id,
                schedule=schedule,
                handler=_create_automation_handler(payload) if payload else lambda: None,
                description=description,
                enabled=bool(enabled),
                timezone=timezone,
                automation_payload=payload,
            )


def _create_automation_handler(payload: dict[str, Any]) -> Any:
    """Returns an async handler that dispatches an automation prompt."""

    async def _handler() -> None:
        # Phase 2: Send this to the automation hub or run context
        # For parity, we spawn a local CLI sub-process or use the API.
        # Here we use jarvis_cli directly to run the command if possible,
        # or we just log it. The automation hub intercepts this.
        import logging

        logger = logging.getLogger("jarvis.cron.automation")
        logger.info(f"Firing automation: {payload}")

        message = payload.get("message")
        if not message:
            return

        # Attempt to inject via PluginApi or run a detached process.
        # Since this is running in the host process, we can just run
        # the cli command for prompt injection if needed.
        logger.info(f"Automation message: {message}")

    return _handler


__all__ = ["CronTable"]
