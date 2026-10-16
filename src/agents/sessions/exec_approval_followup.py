"""Exec approval followup poller — mirrors OpenClaw exec approval waiting loop."""

from __future__ import annotations

import asyncio
from .exec_approval_request import GLOBAL_EXEC_APPROVAL_STORE, ApprovalStatus


async def poll_and_wait_approval(
    approval_id: str,
    timeout_s: float = 30.0,
    poll_interval_s: float = 0.5,
) -> ApprovalStatus:
    """Poll the approval store asynchronously until approved, denied, or timed out."""
    start = asyncio.get_running_loop().time()
    while True:
        status = GLOBAL_EXEC_APPROVAL_STORE.poll_status(approval_id, timeout_s=timeout_s)
        if status != "pending":
            return status

        now = asyncio.get_running_loop().time()
        if now - start >= timeout_s:
            GLOBAL_EXEC_APPROVAL_STORE.respond(approval_id, approved=False)
            return "timeout"

        await asyncio.sleep(poll_interval_s)


__all__ = ["poll_and_wait_approval"]
