"""Tests for src/process/gateway_work_admission.py.

Mirrors tests and semantics of OpenClaw's gateway-work-admission.ts.
"""

from __future__ import annotations

import pytest

from src.process.gateway_work_admission import (
    GatewayDrainingError,
    begin_gateway_restart_signal_admission,
    begin_gateway_root_work_admission_when_open,
    get_active_gateway_root_work_count,
    get_gateway_suspend_admission_phase,
    is_gateway_restart_draining,
    is_gateway_subordinate_work_admission_closed,
    is_gateway_work_admission_closed,
    mark_gateway_restart_draining,
    reset_gateway_work_admission,
    try_begin_gateway_root_work_admission,
    try_begin_gateway_suspend_admission,
    wait_for_active_gateway_root_work,
)


@pytest.fixture(autouse=True)
def _reset_admission():
    reset_gateway_work_admission()
    yield
    reset_gateway_work_admission()


def test_initial_state_accepting():
    assert not is_gateway_work_admission_closed()
    assert not is_gateway_subordinate_work_admission_closed()
    assert not is_gateway_restart_draining()
    assert get_gateway_suspend_admission_phase() == "accepting"
    assert get_active_gateway_root_work_count() == 0


def test_try_begin_gateway_root_work_admission():
    lease = try_begin_gateway_root_work_admission()
    assert lease is not None
    assert lease.owns_root is True
    assert get_active_gateway_root_work_count() == 1

    lease.release()
    assert get_active_gateway_root_work_count() == 0


@pytest.mark.asyncio
async def test_run_lease():
    lease = try_begin_gateway_root_work_admission()
    assert lease is not None

    async def fn():
        assert get_active_gateway_root_work_count() == 1
        return "ok"

    res = await lease.run(fn)
    assert res == "ok"
    lease.release()


def test_restart_draining_blocks_new_admission():
    mark_gateway_restart_draining()
    assert is_gateway_restart_draining() is True
    assert is_gateway_work_admission_closed() is True
    assert try_begin_gateway_root_work_admission() is None


def test_restart_signal_fence():
    fence = begin_gateway_restart_signal_admission()
    assert fence is not None
    assert is_gateway_work_admission_closed() is True
    assert try_begin_gateway_root_work_admission() is None

    # Duplicate fence fails
    assert begin_gateway_restart_signal_admission() is None

    # Rollback fence reopens
    assert fence.rollback() is True
    assert is_gateway_work_admission_closed() is False


def test_suspend_admission_lifecycle():
    invalidated = False

    def on_inv():
        nonlocal invalidated
        invalidated = True

    suspend_lease = try_begin_gateway_suspend_admission(on_inv)
    assert suspend_lease is not None
    assert get_gateway_suspend_admission_phase() == "preparing"
    assert is_gateway_work_admission_closed() is True

    # Commit phase
    assert suspend_lease.commit() is True
    assert get_gateway_suspend_admission_phase() == "prepared"

    # Release phase
    assert suspend_lease.release() is True
    assert get_gateway_suspend_admission_phase() == "accepting"
    assert is_gateway_work_admission_closed() is False


@pytest.mark.asyncio
async def test_wait_for_active_gateway_root_work():
    res = await wait_for_active_gateway_root_work(timeout_ms=10)
    assert res["drained"] is True
    assert res["active"] == 0

    lease = try_begin_gateway_root_work_admission()
    assert lease is not None

    res2 = await wait_for_active_gateway_root_work(timeout_ms=10)
    assert res2["drained"] is False
    assert res2["active"] == 1

    lease.release()
    res3 = await wait_for_active_gateway_root_work(timeout_ms=10)
    assert res3["drained"] is True
    assert res3["active"] == 0


@pytest.mark.asyncio
async def test_begin_when_open_raises_when_draining():
    mark_gateway_restart_draining()
    with pytest.raises(GatewayDrainingError):
        await begin_gateway_root_work_admission_when_open()
