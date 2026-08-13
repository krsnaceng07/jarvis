"""Tests for Wave 17 — Exec Approval Gate."""

from __future__ import annotations

import asyncio
import pytest

from src.agents.sessions.exec_approval_request import GLOBAL_EXEC_APPROVAL_STORE
from src.agents.sessions.exec_approval_followup import poll_and_wait_approval


@pytest.mark.asyncio
async def test_exec_approval_approved():
    rec = GLOBAL_EXEC_APPROVAL_STORE.create_request("rm -rf /", "/tmp", "session-123")
    assert rec.status == "pending"

    # Simulate async approval response in background
    async def _approve():
        await asyncio.sleep(0.1)
        GLOBAL_EXEC_APPROVAL_STORE.respond(rec.approval_id, approved=True)

    asyncio.create_task(_approve())

    status = await poll_and_wait_approval(rec.approval_id, timeout_s=2.0, poll_interval_s=0.05)
    assert status == "approved"


@pytest.mark.asyncio
async def test_exec_approval_denied():
    rec = GLOBAL_EXEC_APPROVAL_STORE.create_request("shutdown", "/tmp", "session-123")

    async def _deny():
        await asyncio.sleep(0.1)
        GLOBAL_EXEC_APPROVAL_STORE.respond(rec.approval_id, approved=False)

    asyncio.create_task(_deny())

    status = await poll_and_wait_approval(rec.approval_id, timeout_s=2.0, poll_interval_s=0.05)
    assert status == "denied"
