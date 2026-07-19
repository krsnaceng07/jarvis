"""Cron types — scheduled jobs.

Mirrors OpenClaw's ``src/cron/`` system. A plugin registers a cron
job via ``api.register_cron(decl)``; the host's cron runner wakes
the job on its schedule and invokes the handler.

A cron job has:

  - ``id`` — stable id (used for cancel + list).
  - ``schedule`` — either a cron expression (``"*/5 * * * *"``) or a
    one-shot ISO timestamp (``"2026-07-20T09:00:00"``).
  - ``handler`` — async function called when the job fires.
  - ``timezone`` — optional IANA tz (default: host's local tz).
  - ``enabled`` — start/stop toggle.

The OpenClaw cron model is a single cross-platform runner; JARVIS
follows the same shape (one runner, one job table, OS-agnostic).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class CronDecl:
    """A plugin-registered scheduled job.

    Attributes
    ----------
    id : str
        Stable id (e.g. ``"jarvis_reminder_<timestamp>"``).
    schedule : str
        Cron expression (``"*/5 * * * *"``) or ISO timestamp.
    handler : Callable
        Async function invoked when the job fires. No required args;
        any payload comes from the schedule's last run metadata.
    timezone : str
        IANA timezone (e.g. ``"America/New_York"``). Defaults to host's
        local timezone when empty.
    enabled : bool
        Whether the job is active. ``False`` pauses the job without
        removing it.
    description : str
        Human-readable description (shown in ``jarvis cron list``).
    """

    id: str
    schedule: str
    handler: Callable[..., Any]
    timezone: str = ""
    enabled: bool = True
    description: str = ""


__all__ = ["CronDecl"]
