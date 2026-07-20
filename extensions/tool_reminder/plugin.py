"""ReminderPlugin — the actual reminder tool.

Migrated from ``actions/reminder.py``. Behavior preserved exactly:
sets a one-shot Windows Task Scheduler entry that runs a small Python
script (beep + toast notification) at the requested time.

Phase 1B: Windows-only. Phase 9 (cron extension) will provide a
cross-platform fallback path.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis_sdk import (
    Err,
    Ok,
    Result,
    ToolDecl,
    ToolParam,
    ToolPlugin,
)

# ── Tool declaration (mirrors the manifest's tools[] entry) ──────────
REMINDER_TOOL = ToolDecl(
    name="reminder",
    description=(
        "Sets a timed reminder using Windows Task Scheduler. "
        "Returns a human-readable result string. Date is YYYY-MM-DD, "
        "time is HH:MM (24h). Message is the reminder text."
    ),
    parameters=[
        ToolParam(
            name="date",
            type="string",
            description="Date in YYYY-MM-DD format",
            required=True,
        ),
        ToolParam(
            name="time",
            type="string",
            description="Time in HH:MM format (24h)",
            required=True,
        ),
        ToolParam(
            name="message",
            type="string",
            description="Reminder text",
            required=False,
        ),
    ],
    returns="string",
    category="productivity",
)


class ReminderPlugin(ToolPlugin):
    """Sets timed reminders via Windows Task Scheduler.

    Plugin contract (PR 1B, formalized in Phase 1C):
    - ``id``/``kind``/``version``/``description``: identity (mirrors manifest).
    - ``tools`` property: list of ``ToolDecl`` for the LLM (mirrors manifest).
    - ``call(name, args) -> Result``: dispatch + run + return ``Ok/Err``.

    Plugin lifecycle (``init``/``shutdown``) is inherited from
    ``ToolPlugin`` (which extends ``Plugin``); this plugin has no
    persistent state so they're no-ops here.
    """

    # ── Identity (mirrors `openclaw.plugin.json`) ──────────────────────
    id = "tool_reminder"
    kind = "tool"
    version = "0.1.0"
    description = "Set timed reminders via Windows Task Scheduler."

    def init(self, ctx: Any) -> None:
        # No persistent state. Could cache the temp dir in Phase 1C.
        return

    async def shutdown(self) -> None:
        # No background tasks. No-op.
        return

    # ── Tool surface ─────────────────────────────────────────────────
    @property
    def tools(self) -> list[ToolDecl]:
        return [REMINDER_TOOL]

    async def call(self, name: str, args: dict[str, Any]) -> Result[str]:
        if name != "reminder":
            return Err(f"Unknown tool: {name}", code="UNKNOWN_TOOL")
        return self._set_reminder(args)

    # ── Tool implementations ────────────────────────────────────────
    def _set_reminder(self, args: dict[str, Any]) -> Result[str]:
        """Schedule a Windows Task Scheduler one-shot task."""
        date_str = args.get("date")
        time_str = args.get("time")
        message = (args.get("message") or "Reminder").strip() or "Reminder"

        if not date_str or not time_str:
            return Err("I need both a date and a time to set a reminder.", code="MISSING_ARG")

        try:
            target_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            return Err("I couldn't understand that date or time format.", code="BAD_FORMAT")

        if target_dt <= datetime.now():
            return Err("That time is already in the past.", code="TIME_IN_PAST")

        # Build a one-shot pythonw script that beeps + toasts + self-deletes.
        task_name = f"JARVISReminder_{target_dt.strftime('%Y%m%d_%H%M')}"
        safe_message = message.replace('"', "").replace("'", "").strip()[:200]
        python_exe = self._resolve_pythonw()
        temp_dir = os.environ.get("TEMP", "C:\\Temp")
        notify_script = os.path.join(temp_dir, f"{task_name}.pyw")
        project_root = str(Path(__file__).resolve().parents[3])  # jarvis workspace root

        script_code = self._render_notify_script(project_root, safe_message)
        xml_content = self._render_task_xml(target_dt, safe_message, python_exe, notify_script)

        try:
            with open(notify_script, "w", encoding="utf-8") as f:
                f.write(script_code)
            xml_path = os.path.join(temp_dir, f"{task_name}.xml")
            with open(xml_path, "w", encoding="utf-16") as f:
                f.write(xml_content)
        except OSError as e:
            return Err(f"Couldn't write temp scripts: {e}", code="FS_ERROR")

        # schtasks /Create /TN ... /XML ... /F
        #
        # We pass a static command template with a derived task_name and
        # xml_path (no user input). `shell=True` is required for
        # `schtasks` (a built-in Windows command, not an .exe), and the
        # inputs are pre-sanitized. Tracked by AGENTS.md §"Security
        # Invariants". S602 disabled: this is the documented exception.
        result = subprocess.run(  # noqa: S602
            f'schtasks /Create /TN "{task_name}" /XML "{xml_path}" /F',
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )

        # Clean up the XML (the script stays; the scheduled task runs it)
        with contextlib.suppress(OSError):
            os.remove(xml_path)

        if result.returncode != 0:
            err = (result.stderr or result.stdout).strip()
            with contextlib.suppress(OSError):
                os.remove(notify_script)
            return Err(f"schtasks failed: {err[:200]}", code="SCHTASKS_FAILED")

        return Ok(f"Reminder set for {target_dt.strftime('%B %d at %I:%M %p')}.")

    # ── Helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _resolve_pythonw() -> str:
        """Prefer ``pythonw.exe`` (no console window) over ``python.exe``."""
        python_exe = sys.executable
        if python_exe.lower().endswith("python.exe"):
            pythonw = python_exe.replace("python.exe", "pythonw.exe")
            if os.path.exists(pythonw):
                return pythonw
        return python_exe

    @staticmethod
    def _render_notify_script(project_root: str, safe_message: str) -> str:
        """Render the small .pyw script that runs at the scheduled time."""
        return f"""import sys, os, time
sys.path.insert(0, r"{project_root}")

try:
    import winsound
    for freq in [800, 1000, 1200]:
        winsound.Beep(freq, 200)
        time.sleep(0.1)
except Exception:
    pass

try:
    from win10toast import ToastNotifier
    ToastNotifier().show_toast(
        "JARVIS Reminder",
        "{safe_message}",
        duration=15,
        threaded=False
    )
except Exception:
    try:
        import subprocess
        subprocess.run(["msg", "*", "/TIME:30", "{safe_message}"], shell=True)
    except Exception:
        pass

time.sleep(3)
try:
    os.remove(__file__)
except Exception:
    pass
"""

    @staticmethod
    def _render_task_xml(
        target_dt: datetime, safe_message: str, python_exe: str, notify_script: str
    ) -> str:
        """Render the Windows Task Scheduler XML for a one-shot TimeTrigger task."""
        return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>JARVIS Reminder: {safe_message}</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>{target_dt.strftime("%Y-%m-%dT%H:%M:%S")}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Actions>
    <Exec>
      <Command>{python_exe}</Command>
      <Arguments>"{notify_script}"</Arguments>
    </Exec>
  </Actions>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Principals>
    <Principal>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
</Task>"""
