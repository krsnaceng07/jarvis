"""Runtime helpers for tool_reminder.

Phase 1C: exposes the public API used by the slash-command handler
(``/reminders list`` / ``cancel-all``) and the future CLI subcommand.
The actual ``schtasks`` invocation lives in ``plugin.py``; this module
is the read-side (list + cancel) so the command handler doesn't need
to know Windows Task Scheduler details.
"""
from __future__ import annotations

import re
import subprocess
from typing import Any


_REMINDER_PREFIX = "JARVISReminder_"
_REMINDER_NAME_RE = re.compile(r"^" + _REMINDER_PREFIX + r"(\d{8})_(\d{4})$")


def _run_schtasks_query() -> tuple[int, str, str]:
    """Run ``schtasks /Query /FO LIST /V`` and return (rc, stdout, stderr).

    Returns a tuple; never raises. The caller decides how to handle a
    non-zero return code.
    """
    result = subprocess.run(
        ["schtasks", "/Query", "/FO", "LIST", "/V"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    return result.returncode, result.stdout, result.stderr


def list_scheduled_reminders() -> list[str]:
    """Return a list of human-readable reminder rows.

    Each row is a string like ``"2026-07-20 09:00 — JARVISReminder_..."``.
    Empty list if no reminders or ``schtasks`` is unavailable.
    """
    rc, stdout, _stderr = _run_schtasks_query()
    if rc != 0:
        return []

    rows: list[str] = []
    current: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line.strip():
            if current.get("TaskName", "").startswith(_REMINDER_PREFIX):
                rows.append(_format_row(current))
            current = {}
            continue
        # Lines look like "TaskName:  \\JARVISReminder_20260720_0900"
        if ":" in line:
            key, _, value = line.partition(":")
            current[key.strip()] = value.strip()
    # Tail block (no trailing blank line)
    if current.get("TaskName", "").startswith(_REMINDER_PREFIX):
        rows.append(_format_row(current))
    return rows


def cancel_all_reminders() -> int:
    """Delete every ``JARVISReminder_*`` task. Returns the count deleted."""
    rc, stdout, _stderr = _run_schtasks_query()
    if rc != 0:
        return 0

    names: list[str] = []
    for line in stdout.splitlines():
        if line.startswith("TaskName:"):
            _, _, value = line.partition(":")
            name = value.strip()
            # schtasks may prefix with "\\"; strip it
            if name.startswith("\\"):
                name = name[1:]
            if name.startswith(_REMINDER_PREFIX):
                names.append(name)

    deleted = 0
    for name in names:
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", name, "/F"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        if result.returncode == 0:
            deleted += 1
    return deleted


def _format_row(task: dict[str, str]) -> str:
    """Render one parsed task as a single human-readable row."""
    name = task.get("TaskName", "").lstrip("\\")
    schedule = task.get("Scheduled Task Time", "") or task.get("Schedule", "")
    status = task.get("Status", "")
    m = _REMINDER_NAME_RE.match(name)
    if m:
        ymd, hm = m.group(1), m.group(2)
        when = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]} {hm[:2]}:{hm[2:4]}"
    else:
        when = schedule or "?"
    return f"{when}  {status:<10}  {name}"


__all__ = ["cancel_all_reminders", "list_scheduled_reminders"]


# Sentinel to keep type checkers happy about the `Any` import in stubs.
_ = Any
