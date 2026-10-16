"""Discord doctor contract.

OpenClaw parity: mirrors ``doctor-contract-api.ts`` (the
TS module exports a single ``discordDoctorContract`` the
host calls to verify the channel is wired). The Python
port ships the equivalent as a function returning a dict
the host's ``doctor`` tool can render.
"""

from __future__ import annotations

from .runtime import get_discord_runtime


def discord_doctor_contract() -> dict:
    """Return a snapshot of the Discord channel's wiring state.

    Mirrors the OpenClaw ``discordDoctorContract`` shape:
    ``{status, channel, runtimePresent, lastTick}``. The
    host's doctor surface calls this on demand; the
    operator sees whether the channel is wired and how
    recently the poll loop ticked.
    """
    runtime = get_discord_runtime()
    if runtime is None:
        return {
            "status": "unwired",
            "channel": "discord",
            "runtimePresent": False,
            "lastTick": 0,
        }
    return {
        "status": "ready" if not runtime.is_stopped() else "stopped",
        "channel": "discord",
        "runtimePresent": True,
        "lastTick": runtime._poll_count,
    }
