"""jarvis.gateway.server_lanes — gateway command-lane concurrency applier.

OpenClaw parity: mirrors ``src/gateway/server-lanes.ts``.

Resolves per-lane concurrency limits from config and applies them to the
process command queue. Called at gateway startup and on config live-reload.

Key design contract (from OpenClaw source):
  - Main lane:     ``agents.defaults.maxConcurrent`` (default 4)
  - Subagent lane: ``agents.defaults.subagents.maxConcurrent`` (default 8)
  - Cron lane:     ``cron.maxConcurrentRuns`` (default 8)
  - Cron-nested:   same limit as cron (inner LLM work from cron jobs)
  - Nested lane:   always 1 (serialized sessions.send work)

Public surface
--------------
``GatewayLaneConcurrency``
``resolve_gateway_lane_concurrency``
``apply_gateway_lane_concurrency``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.agents.embedded_agent_runner.lanes import CommandLane
from src.config.agent_limits import (
    resolve_agent_max_concurrent,
    resolve_subagent_max_concurrent,
)
from src.config.cron_limits import resolve_cron_max_concurrent_runs


# ---------------------------------------------------------------------------
# Data shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GatewayLaneConcurrency:
    """Resolved concurrency limits for the three gateway-managed lanes.

    Mirrors ``GatewayLaneConcurrency`` (``gateway/server-lanes.ts``).
    """

    cron: int
    main: int
    subagent: int


# ---------------------------------------------------------------------------
# Process-level lane concurrency registry (in-process singleton)
# ---------------------------------------------------------------------------
# Stores the live concurrency setting per lane id.  The gateway applier
# writes here; the command queue reads it on each scheduling decision.
# Mirrors ``setCommandLaneConcurrency`` / the command-queue lane table.

_lane_concurrency: dict[str, int] = {}


def set_command_lane_concurrency(lane_id: str, limit: int) -> None:
    """Set the concurrency limit for *lane_id* in the process lane table.

    Mirrors ``setCommandLaneConcurrency`` (``process/command-queue.ts``).
    """
    _lane_concurrency[lane_id] = max(1, int(limit))


def get_command_lane_concurrency(lane_id: str) -> int | None:
    """Return the live concurrency limit for *lane_id*, or None if unset."""
    return _lane_concurrency.get(lane_id)


def get_all_lane_concurrency() -> dict[str, int]:
    """Return a snapshot of all live lane concurrency settings."""
    return dict(_lane_concurrency)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_gateway_lane_concurrency(cfg: dict[str, Any] | None = None) -> GatewayLaneConcurrency:
    """Derive lane concurrency limits from *cfg*.

    Mirrors ``resolveGatewayLaneConcurrency``.
    """
    cron_cfg = (cfg or {}).get("cron") if isinstance(cfg, dict) else None
    return GatewayLaneConcurrency(
        cron=resolve_cron_max_concurrent_runs(cron_cfg),
        main=resolve_agent_max_concurrent(cfg),
        subagent=resolve_subagent_max_concurrent(cfg),
    )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


def apply_gateway_lane_concurrency(
    concurrency: GatewayLaneConcurrency,
    *,
    gateway_start: bool = False,
) -> None:
    """Push *concurrency* limits into the process lane table.

    Mirrors ``applyGatewayLaneConcurrency``.

    Parameters
    ----------
    concurrency:
        Resolved concurrency values from :func:`resolve_gateway_lane_concurrency`.
    gateway_start:
        When True, also sets the ``Nested`` lane to concurrency=1.
        This is deferred on live-reload to avoid resuming a suspended
        nested lane before its TTL.

    Lane assignments
    ----------------
    Cron       → concurrency.cron
    CronNested → concurrency.cron  (inner LLM work from cron)
    Main       → concurrency.main
    Nested     → 1  (only on gateway_start; serializes sessions.send)
    Subagent   → concurrency.subagent
    """
    set_command_lane_concurrency(CommandLane.Cron, concurrency.cron)
    # Cron isolated-agent turns remap inner LLM work to CronNested.
    set_command_lane_concurrency(CommandLane.CronNested, concurrency.cron)
    set_command_lane_concurrency(CommandLane.Main, concurrency.main)
    if gateway_start:
        # sessions.send work uses a shared nested lane with no config knob;
        # live reload must not resume a currently suspended nested lane before
        # its TTL.
        set_command_lane_concurrency(CommandLane.Nested, 1)
    set_command_lane_concurrency(CommandLane.Subagent, concurrency.subagent)


__all__ = [
    "GatewayLaneConcurrency",
    "apply_gateway_lane_concurrency",
    "get_all_lane_concurrency",
    "get_command_lane_concurrency",
    "resolve_gateway_lane_concurrency",
    "set_command_lane_concurrency",
]
