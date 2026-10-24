"""Autonomous Claw Abstract Base Class and Execution Context — JARVIS Autonomous Architecture.

Every autonomous background worker agent (Claw) subclasses Claw and implements run().
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .types import ClawPriority, ClawResult

logger = logging.getLogger("jarvis.claws.base")


@dataclass(slots=True)
class ClawExecutionContext:
    """Execution context injected into each Claw run."""

    job_id: str
    claw_id: str
    workspace_root: Path
    state_dir: Path
    payload: dict[str, Any] = field(default_factory=dict)
    _checkpoint_fn: Callable[[str, dict[str, Any]], None] | None = None
    _notify_fn: Callable[[str, str, str], None] | None = None
    _outbound_fn: Callable[[str, str, str | None], None] | None = None

    async def checkpoint(self, data: dict[str, Any]) -> None:
        """Persist a progress checkpoint to SQLite for this Claw."""
        if self._checkpoint_fn:
            self._checkpoint_fn(self.claw_id, data)
        logger.debug("Claw %s recorded checkpoint: %s", self.claw_id, data)

    async def notify(self, title: str, message: str, level: str = "info") -> None:
        """Emit a user-facing notification or HUD event."""
        if self._notify_fn:
            self._notify_fn(title, message, level)
        logger.info("Claw %s [%s] %s: %s", self.claw_id, level.upper(), title, message)

    async def deliver_outbound(
        self,
        message: str,
        channel: str = "telegram",
        recipient: str | None = None,
        webhook_url: str | None = None,
    ) -> dict[str, Any]:
        """Deliver summary or status report to an outbound channel (e.g. Telegram or Webhook)."""
        logger.info(
            "Claw %s delivering outbound message to %s (recipient=%s, webhook=%s)",
            self.claw_id,
            channel,
            recipient,
            bool(webhook_url),
        )
        if self._outbound_fn:
            try:
                self._outbound_fn(channel, message, recipient)
            except Exception as e:
                logger.warning("Claw %s custom outbound handler failed: %s", self.claw_id, e)

        # Webhook delivery if URL is specified
        if webhook_url:
            try:
                req_data = json.dumps(
                    {
                        "source": "jarvis.claws",
                        "claw_id": self.claw_id,
                        "job_id": self.job_id,
                        "channel": channel,
                        "recipient": recipient,
                        "message": message,
                    }
                ).encode("utf-8")
                req = urllib.request.Request(
                    webhook_url,
                    data=req_data,
                    headers={"Content-Type": "application/json", "User-Agent": "JARVIS-Claw/1.0"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    status_code = resp.status
                    return {"delivered": True, "channel": channel, "status_code": status_code}
            except Exception as e:
                logger.warning("Claw %s webhook delivery failed: %s", self.claw_id, e)
                return {"delivered": False, "channel": channel, "error": str(e)}

        return {"delivered": True, "channel": channel, "recipient": recipient}

    async def log(self, message: str) -> None:
        """Write an operational log entry."""
        logger.info("[Claw:%s:%s] %s", self.claw_id, self.job_id, message)

    async def run_agent(self, prompt: str, session_key: str | None = None) -> dict[str, Any]:
        """Execute an embedded agent turn autonomously on behalf of this Claw."""
        try:
            from src.agents.embedded_agent_runner.run import run_embedded_agent

            key = session_key or f"claw:{self.claw_id}:{self.job_id}"
            params = {
                "prompt": prompt,
                "session_key": key,
                "sessionKey": key,
                "agent_id": "default",
                "agentId": "default",
            }
            res = await run_embedded_agent(params)
            return {"success": True, "result": res}
        except Exception as e:
            logger.warning("Claw %s agent execution failed: %s", self.claw_id, e)
            return {"success": False, "error": str(e)}


class Claw(ABC):
    """Abstract Base Class for an Autonomous Background Worker Agent (Claw).

    Claws run periodically (or on demand) without interactive user conversation.
    They execute autonomous tasks such as database vacuuming, repository health
    audits, RSS/email digests, web monitoring, and self-healing checkpoints.
    """

    claw_id: str
    name: str
    description: str
    schedule: str  # Cron expression (e.g. '*/30 * * * *') or interval (e.g. 'every 1h')
    priority: ClawPriority = ClawPriority.NORMAL
    timeout_seconds: float = 300.0
    max_attempts: int = 3
    enabled: bool = True

    def __init__(
        self,
        claw_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        schedule: str | None = None,
        priority: ClawPriority | None = None,
        timeout_seconds: float | None = None,
        max_attempts: int | None = None,
        enabled: bool = True,
    ) -> None:
        if claw_id is not None:
            self.claw_id = claw_id
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if schedule is not None:
            self.schedule = schedule
        if priority is not None:
            self.priority = priority
        if timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        if max_attempts is not None:
            self.max_attempts = max_attempts
        self.enabled = enabled

    @abstractmethod
    async def run(self, ctx: ClawExecutionContext) -> ClawResult:
        """Execute the Claw's autonomous job logic.

        Must return a ClawResult indicating success, output, and optional metrics.
        Must not raise uncaught exceptions; errors should be caught and returned
        in ClawResult(success=False, error=str(e)).
        """


__all__ = [
    "Claw",
    "ClawExecutionContext",
]
