"""jarvis.desktop_automation.core.checkpoint_store — Task state persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..state.active_desktop_context import ActiveDesktopContext


@dataclass(slots=True)
class TaskCheckpoint:
    task_id: str
    application: str
    goal: str
    stage: str
    completed_stages: List[str] = field(default_factory=list)
    pending_stage: Optional[str] = None
    active_target: Dict[str, Any] = field(default_factory=dict)
    last_verified_state: Dict[str, Any] = field(default_factory=dict)
    can_resume: bool = True


class CheckpointStore:
    """In-memory and persistent SQLite store for desktop automation task checkpoints."""

    _instance: Optional[CheckpointStore] = None

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._checkpoints: Dict[str, Any] = {}
        self._active_task_id: Optional[str] = None

        if self.db_path:
            p = Path(self.db_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS desktop_checkpoints "
                    "(task_id TEXT PRIMARY KEY, payload TEXT)"
                )
                conn.commit()

    @classmethod
    def get_instance(cls) -> CheckpointStore:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def save_checkpoint(
        self,
        task_id_or_cp: Union[str, TaskCheckpoint],
        context: Optional[ActiveDesktopContext] = None,
    ) -> None:
        if isinstance(task_id_or_cp, TaskCheckpoint):
            task_id = task_id_or_cp.task_id
            payload = asdict(task_id_or_cp)
            self._checkpoints[task_id] = task_id_or_cp
        else:
            task_id = str(task_id_or_cp)
            payload = context.to_dict() if context else {}
            self._checkpoints[task_id] = context or payload

        self._active_task_id = task_id

        if self.db_path:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO desktop_checkpoints (task_id, payload) VALUES (?, ?)",
                    (task_id, json.dumps(payload)),
                )
                conn.commit()

    def restore_checkpoint(self, task_id: str) -> Optional[ActiveDesktopContext]:
        # Check in-memory
        in_mem = self._checkpoints.get(task_id)
        if isinstance(in_mem, ActiveDesktopContext):
            return in_mem

        if self.db_path:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT payload FROM desktop_checkpoints WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                if row:
                    data = json.loads(row[0])
                    ctx = ActiveDesktopContext(
                        active_application=data.get("active_application"),
                        active_window_title=data.get("active_window_title"),
                        active_hwnd=data.get("active_hwnd"),
                        active_pid=data.get("active_pid"),
                        focused_control=data.get("focused_control"),
                        current_task=data.get("current_task"),
                        workflow_stage=data.get("workflow_stage"),
                        active_recipient=data.get("active_recipient"),
                        active_document=data.get("active_document"),
                        pending_message=data.get("pending_message"),
                        last_verified_action=data.get("last_verified_action"),
                        next_expected_action=data.get("next_expected_action"),
                        can_continue=data.get("can_continue", True),
                        task_parameters=data.get("task_parameters", {}),
                    )
                    self._checkpoints[task_id] = ctx
                    return ctx
        return None

    def get_checkpoint(self, task_id: str) -> Optional[Any]:
        return self._checkpoints.get(task_id)

    def get_active_checkpoint(self) -> Optional[Any]:
        if self._active_task_id:
            return self._checkpoints.get(self._active_task_id)
        return None

    def clear_active(self) -> None:
        self._active_task_id = None

