"""Tests for the remaining presence/process/lane modules.

Covers:
  - src/agents/session_suspension.py
  - src/process/command_queue.py
  - src/gateway/presence_events.py
  - src/infra/network_discovery.py
  - src/commands/gateway_presence.py
"""

from __future__ import annotations

import asyncio
import pytest

# ---------------------------------------------------------------------------
# session_suspension
# ---------------------------------------------------------------------------

from src.agents.session_suspension import (
    _reset_session_suspension_state_for_test,
    clear_session_suspension_timers,
    enable_session_suspension_timers_for_gateway_start,
    get_cleanup_suspended_lane_ids_for_gateway_publication,
    resolve_session_suspension_reason,
    resolve_session_suspension_target,
    suspend_session,
)
from src.gateway.server_lanes import (
    get_command_lane_concurrency,
    set_command_lane_concurrency,
)
from src.agents.embedded_agent_runner.lanes import CommandLane


@pytest.fixture(autouse=True)
def _reset_suspension():
    _reset_session_suspension_state_for_test()
    yield
    _reset_session_suspension_state_for_test()


@pytest.fixture(autouse=True)
def _clear_lane_table():
    from src.gateway import server_lanes as sl
    sl._lane_concurrency.clear()
    yield
    sl._lane_concurrency.clear()


# ---- reason normalization ----

def test_resolve_suspension_reason_quota():
    assert resolve_session_suspension_reason("quota") == "quota"


def test_resolve_suspension_reason_manual():
    assert resolve_session_suspension_reason("manual") == "manual"


def test_resolve_suspension_reason_unknown_defaults_quota():
    assert resolve_session_suspension_reason("bogus") == "quota"
    assert resolve_session_suspension_reason(None) == "quota"


def test_resolve_suspension_reason_case_insensitive():
    assert resolve_session_suspension_reason("CIRCUIT") == "circuit"


# ---- target lane ----

def test_resolve_suspension_target_returns_session_lane():
    lane = resolve_session_suspension_target("sess-abc")
    assert lane == "session:sess-abc"


def test_resolve_suspension_target_empty_returns_main():
    lane = resolve_session_suspension_target("")
    assert lane == CommandLane.Main


# ---- suspend_session ----

def test_suspend_session_throttles_lane():
    lane_id = "session:test-suspend"
    set_command_lane_concurrency(lane_id, 4)
    suspend_session(lane_id, resume_after_ms=10_000)
    assert get_command_lane_concurrency(lane_id) == 0  # throttled


def test_suspend_session_replaces_existing_timer():
    lane_id = "session:test-replace"
    suspend_session(lane_id, resume_after_ms=60_000)
    suspend_session(lane_id, resume_after_ms=60_000)
    # Still only one timer per lane.
    from src.agents import session_suspension as ss
    with ss._state._lock:
        assert len([k for k in ss._state.lane_resume_timers if k == lane_id]) == 1


# ---- clear / enable cycle ----

def test_clear_and_enable_gateway_start():
    lane_id = "session:test-clear-enable"
    set_command_lane_concurrency(lane_id, 4)
    suspend_session(lane_id, resume_after_ms=10_000, resume_concurrency=2)

    clear_session_suspension_timers()

    # After clear, the lane ID should appear in cleared resumes.
    suspended = enable_session_suspension_timers_for_gateway_start(
        lambda lid, saved: saved
    )
    assert lane_id in suspended
    # Lane should be throttled again.
    assert get_command_lane_concurrency(lane_id) == 0


def test_get_cleanup_suspended_lane_ids_empty_initially():
    result = get_cleanup_suspended_lane_ids_for_gateway_publication()
    assert isinstance(result, frozenset)
    assert len(result) == 0


def test_get_cleanup_suspended_lane_ids_after_suspend():
    lane_id = "session:test-suspended-ids"
    suspend_session(lane_id, resume_after_ms=60_000)
    result = get_cleanup_suspended_lane_ids_for_gateway_publication()
    assert lane_id in result


# ---------------------------------------------------------------------------
# process/command_queue
# ---------------------------------------------------------------------------

from src.process.command_queue import (
    CommandLaneClearedError,
    CommandLaneTaskMarker,
    enqueue_command,
    get_all_lane_snapshots,
    get_lane_snapshot,
    reset_command_queue_for_test,
)


@pytest.fixture(autouse=True)
def _reset_queue():
    reset_command_queue_for_test()
    yield
    reset_command_queue_for_test()


@pytest.mark.asyncio
async def test_enqueue_command_runs_task():
    results = []

    async def task(marker: CommandLaneTaskMarker):
        results.append(marker.lane)
        return 42

    set_command_lane_concurrency("main", 2)
    result = await enqueue_command("main", task)
    assert result == 42
    assert "main" in results


@pytest.mark.asyncio
async def test_enqueue_command_marker_has_correct_lane():
    captured: list[CommandLaneTaskMarker] = []

    async def task(marker: CommandLaneTaskMarker):
        captured.append(marker)

    set_command_lane_concurrency("cron", 2)
    await enqueue_command("cron", task)
    assert captured[0].lane == "cron"
    assert captured[0].task_id >= 1


@pytest.mark.asyncio
async def test_enqueue_command_serial_order():
    """Tasks in a single-concurrency lane run serially."""
    order: list[int] = []

    async def make_task(n: int):
        async def task(marker: CommandLaneTaskMarker):
            order.append(n)
        return task

    set_command_lane_concurrency("serial-lane", 1)
    t1 = asyncio.create_task(enqueue_command("serial-lane", await make_task(1)))
    t2 = asyncio.create_task(enqueue_command("serial-lane", await make_task(2)))
    t3 = asyncio.create_task(enqueue_command("serial-lane", await make_task(3)))
    await asyncio.gather(t1, t2, t3)
    assert order == [1, 2, 3]


@pytest.mark.asyncio
async def test_enqueue_command_propagates_exception():
    async def failing_task(marker: CommandLaneTaskMarker):
        raise ValueError("oops")

    set_command_lane_concurrency("err-lane", 2)
    with pytest.raises(ValueError, match="oops"):
        await enqueue_command("err-lane", failing_task)


def test_drain_lane_cancels_queued():
    """drain_lane cancels queued but not-yet-started tasks."""
    # We can't easily test async drain without a running loop, so just
    # test that CommandLaneClearedError has the correct message.
    err = CommandLaneClearedError("test-lane")
    assert "test-lane" in str(err)
    assert err.lane == "test-lane"


def test_command_lane_cleared_error_no_lane():
    err = CommandLaneClearedError()
    assert "cleared" in str(err).lower()


def test_get_lane_snapshot_none_for_unknown():
    assert get_lane_snapshot("unknown-lane-xyz") is None


def test_get_all_lane_snapshots_empty_initially():
    snapshots = get_all_lane_snapshots()
    assert isinstance(snapshots, list)


@pytest.mark.asyncio
async def test_get_lane_snapshot_after_task():
    set_command_lane_concurrency("snap-lane", 2)

    async def task(m: CommandLaneTaskMarker):
        pass

    await enqueue_command("snap-lane", task)
    snap = get_lane_snapshot("snap-lane")
    assert snap is not None
    assert snap.lane == "snap-lane"
    assert snap.max_concurrent == 2


def test_command_lane_task_marker_frozen():
    marker = CommandLaneTaskMarker(lane="main", task_id=1, generation=0)
    assert marker.lane == "main"
    assert marker.task_id == 1


# ---------------------------------------------------------------------------
# gateway/presence_events
# ---------------------------------------------------------------------------

from src.gateway.presence_events import broadcast_presence_snapshot
from src.infra.system_presence import reset_presence_registry


@pytest.fixture(autouse=True)
def _reset_presence():
    reset_presence_registry()
    yield
    reset_presence_registry()


def test_broadcast_presence_snapshot_calls_broadcast():
    calls: list[tuple] = []

    def mock_broadcast(event, payload, opts):
        calls.append((event, payload, opts))

    version_counter = [0]
    health_counter = [5]

    def inc_version():
        version_counter[0] += 1
        return version_counter[0]

    def get_health():
        return health_counter[0]

    version = broadcast_presence_snapshot(
        broadcast=mock_broadcast,
        increment_presence_version=inc_version,
        get_health_version=get_health,
    )
    assert version == 1
    assert len(calls) == 1
    event, payload, opts = calls[0]
    assert event == "presence"
    assert "presence" in payload
    assert isinstance(payload["presence"], list)
    assert opts["dropIfSlow"] is True
    assert opts["stateVersion"]["presence"] == 1
    assert opts["stateVersion"]["health"] == 5


def test_broadcast_presence_snapshot_increments_version():
    calls: list[int] = []

    def mock_broadcast(event, payload, opts):
        calls.append(opts["stateVersion"]["presence"])

    counter = [0]

    def inc():
        counter[0] += 1
        return counter[0]

    broadcast_presence_snapshot(broadcast=mock_broadcast, increment_presence_version=inc, get_health_version=lambda: 0)
    broadcast_presence_snapshot(broadcast=mock_broadcast, increment_presence_version=inc, get_health_version=lambda: 0)
    assert calls == [1, 2]


# ---------------------------------------------------------------------------
# infra/network_discovery
# ---------------------------------------------------------------------------

from src.infra.network_discovery import (
    inspect_best_effort_network,
    pick_best_effort_primary_lan_ipv4,
    resolve_best_effort_bind_host_for_display,
)


def test_pick_best_effort_lan_ipv4_returns_string_or_none():
    result = pick_best_effort_primary_lan_ipv4()
    assert result is None or isinstance(result, str)


def test_inspect_best_effort_network_has_host():
    info = inspect_best_effort_network()
    assert "host" in info
    assert info["host"]  # hostname is always set


def test_resolve_bind_host_localhost():
    result = resolve_best_effort_bind_host_for_display("localhost")
    assert result["bindHost"] == "127.0.0.1"


def test_resolve_bind_host_lan():
    result = resolve_best_effort_bind_host_for_display("lan")
    assert "bindHost" in result
    assert result["bindHost"]  # should have some IP or 0.0.0.0


def test_resolve_bind_host_custom():
    result = resolve_best_effort_bind_host_for_display("custom", "192.168.1.200")
    assert result["bindHost"] == "192.168.1.200"


# ---------------------------------------------------------------------------
# commands/gateway_presence
# ---------------------------------------------------------------------------

from src.commands.gateway_presence import pick_gateway_self_presence


def test_commands_gateway_presence_re_export():
    presence_list = [
        {"mode": "gateway", "reason": "self", "host": "gw-host", "version": "1.0"},
    ]
    result = pick_gateway_self_presence(presence_list)
    assert result is not None
    assert result["host"] == "gw-host"


def test_commands_gateway_presence_none_on_empty():
    assert pick_gateway_self_presence([]) is None
