"""CronTable — the cross-extension cron store.

Phase 2: in-memory dict of CronDecl + a JSON file for persistence
(``$JARVIS_DATA_DIR/core/cron.json``). The host's ``CronRunner``
reads from this table to build its job list.

This is intentionally separate from ``src.cron.CronRunner``
(the execution engine) so the data model is testable without
threads.
"""

from __future__ import annotations

import json
import os
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
        self._store_path = store_path
        self._jobs: dict[str, CronDecl] = {}
        self._mu = threading.Lock()
        if store_path and store_path.exists():
            self._load()

    @classmethod
    def default(cls) -> CronTable:
        with cls._lock:
            if cls._default is None:
                data_dir = Path(os.environ.get("JARVIS_DATA_DIR") or (Path.home() / ".jarvis"))
                cls._default = cls(data_dir / "core" / "cron.json")
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
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, dict[str, object]] = {
            jid: {
                "id": j.id,
                "schedule": j.schedule,
                "description": j.description,
                "enabled": j.enabled,
                "timezone": j.timezone,
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
            self._jobs[jid] = CronDecl(
                id=jd.get("id", jid),
                schedule=jd.get("schedule", ""),
                handler=lambda: None,
                description=jd.get("description", ""),
                enabled=jd.get("enabled", True),
                timezone=jd.get("timezone", ""),
            )


__all__ = ["CronTable"]
