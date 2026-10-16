"""Job definitions for jarvis_cron_core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


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
        Async or sync function invoked when the job fires.
    timezone : str
        IANA timezone (e.g. ``"America/New_York"``). Defaults to host's
        local timezone when empty.
    enabled : bool
        Whether the job is active. ``False`` pauses the job without
        removing it.
    description : str
        Human-readable description (shown in ``jarvis cron list``).
    automation_payload : dict[str, Any] | None
        Optional payload passed to automated runners.
    """

    id: str
    schedule: str
    handler: Callable[..., Any]
    timezone: str = ""
    enabled: bool = True
    description: str = ""
    automation_payload: dict[str, Any] | None = None


__all__ = ["CronDecl"]
