"""Windows Scheduled Task (schtasks) manager for one-shot post-reboot verification.

Automates one-shot execution after a physical reboot:
- Registers a task named `JARVIS_Track22_<tx_id>` triggered ONLOGON or ONSTART.
- Directs execution to the verification CLI (`tools/scripts/run_reboot_lab.py --mode verify`).
- Handles task querying and post-verification self-removal via `schtasks /delete /f`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys

logger = logging.getLogger(__name__)


class PostBootTriggerManager:
    """Manages creation, query, and removal of one-shot Windows scheduled tasks."""

    TASK_PREFIX = "JARVIS_Track22_"

    @classmethod
    def get_task_name(cls, transaction_id: str) -> str:
        """Return standardized task name for the given transaction."""
        clean_id = transaction_id.replace("-", "_")
        return f"{cls.TASK_PREFIX}{clean_id}"

    @classmethod
    def build_create_command(
        cls,
        task_name: str,
        python_exe: str,
        script_path: Path,
        lab_dir: Path,
        transaction_id: str,
        trigger_type: str = "ONLOGON",
    ) -> list[str]:
        """Construct the schtasks /create command line arguments."""
        # Command line that will run on logon
        action_cmd = (
            f'"{python_exe}" "{script_path}" --mode verify '
            f'--tx "{transaction_id}" --lab-dir "{lab_dir}"'
        )
        return [
            "schtasks",
            "/create",
            "/tn",
            task_name,
            "/tr",
            action_cmd,
            "/sc",
            trigger_type,
            "/rl",
            "HIGHEST",
            "/f",
        ]

    @classmethod
    def build_delete_command(cls, task_name: str) -> list[str]:
        """Construct the schtasks /delete command line arguments."""
        return ["schtasks", "/delete", "/tn", task_name, "/f"]

    @classmethod
    def build_query_command(cls, task_name: str) -> list[str]:
        """Construct the schtasks /query command line arguments."""
        return ["schtasks", "/query", "/tn", task_name, "/fo", "LIST"]

    @classmethod
    def register_one_shot_task(
        cls,
        transaction_id: str,
        lab_dir: Path,
        script_path: Path | None = None,
        python_exe: str | None = None,
    ) -> tuple[bool, str]:
        """Register the one-shot scheduled task on Windows."""
        if os.name != "nt":
            return False, "Scheduled tasks only supported on Windows (os.name == 'nt')"

        task_name = cls.get_task_name(transaction_id)
        py = python_exe or sys.executable
        scr = script_path or (Path(__file__).parents[5] / "tools" / "scripts" / "run_reboot_lab.py")

        cmd = cls.build_create_command(
            task_name=task_name,
            python_exe=py,
            script_path=scr,
            lab_dir=lab_dir,
            transaction_id=transaction_id,
        )

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if res.returncode == 0:
                logger.info("Successfully registered scheduled task %s", task_name)
                return True, f"Task {task_name} registered successfully"
            logger.warning("Failed to register scheduled task: %s", res.stderr)
            return False, f"schtasks failed (code {res.returncode}): {res.stderr.strip()}"
        except Exception as exc:
            logger.error("Exception registering scheduled task: %s", exc)
            return False, f"Exception registering task: {exc}"

    @classmethod
    def remove_task(cls, transaction_id: str) -> tuple[bool, str]:
        """Remove scheduled task once post-reboot verification has concluded."""
        if os.name != "nt":
            return True, "Non-Windows OS: no task to remove"

        task_name = cls.get_task_name(transaction_id)
        cmd = cls.build_delete_command(task_name)

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if res.returncode == 0:
                logger.info("Successfully removed scheduled task %s", task_name)
                return True, f"Task {task_name} removed successfully"
            return False, f"schtasks delete failed (code {res.returncode}): {res.stderr.strip()}"
        except Exception as exc:
            return False, f"Exception deleting task: {exc}"

    @classmethod
    def is_task_registered(cls, transaction_id: str) -> bool:
        """Check if the scheduled task is currently registered."""
        if os.name != "nt":
            return False

        task_name = cls.get_task_name(transaction_id)
        cmd = cls.build_query_command(task_name)

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            return res.returncode == 0
        except Exception:
            return False


__all__ = ["PostBootTriggerManager"]
