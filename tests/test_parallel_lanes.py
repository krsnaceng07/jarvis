"""Tests for the parallel-specialist-lanes system.

Covers:
  - CommandLane new constants (Nested, Subagent)
  - src/agents/lanes.py (resolve_cron_agent_lane, resolve_nested_agent_lane_for_session, is_nested_agent_lane)
  - src/config/queue_config.py (resolve_queue_mode/cap/drop/config)
  - src/gateway/server_lanes.py (resolve_gateway_lane_concurrency, apply_gateway_lane_concurrency)
  - src/agents/lane_contract.py (render, write, read, prompt block)
  - src/agents/delegation_capability.py (resolve, enforce)

OpenClaw parity: mirrors contracts from:
  agents/lanes.ts, gateway/server-lanes.ts, config/agent-limits.ts,
  config/cron-limits.ts, agents/delegation-capability.ts
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# CommandLane new constants
# ---------------------------------------------------------------------------

from src.agents.embedded_agent_runner.lanes import CommandLane


def test_command_lane_nested():
    assert CommandLane.Nested == "nested"


def test_command_lane_subagent():
    assert CommandLane.Subagent == "subagent"


def test_command_lane_main():
    assert CommandLane.Main == "main"


def test_command_lane_cron():
    assert CommandLane.Cron == "cron"


def test_command_lane_cron_nested():
    assert CommandLane.CronNested == "cron-nested"


# ---------------------------------------------------------------------------
# src/agents/lanes.py — cron lane resolution
# ---------------------------------------------------------------------------

from src.agents.lanes import (
    AGENT_LANE_SUBAGENT,
    is_nested_agent_lane,
    resolve_cron_agent_lane,
    resolve_nested_agent_lane_for_session,
)


def test_resolve_cron_agent_lane_cron_moves_to_cron_nested():
    # Mirrors: it("moves the cron lane to cron-nested for embedded runs")
    assert resolve_cron_agent_lane("cron") == "cron-nested"


def test_resolve_cron_agent_lane_none_defaults_to_cron_nested():
    # Mirrors: it("defaults missing lanes to cron-nested for embedded runs")
    assert resolve_cron_agent_lane() == "cron-nested"
    assert resolve_cron_agent_lane("") == "cron-nested"


def test_resolve_cron_agent_lane_preserves_non_cron():
    # Mirrors: it("preserves non-cron lanes for embedded runs")
    assert resolve_cron_agent_lane("subagent") == "subagent"
    assert resolve_cron_agent_lane("custom-lane") == "custom-lane"


def test_resolve_nested_agent_lane_for_session_with_key():
    lane = resolve_nested_agent_lane_for_session("sess-abc")
    assert lane == "nested:sess-abc"


def test_resolve_nested_agent_lane_for_session_empty_defaults_nested():
    assert resolve_nested_agent_lane_for_session(None) == "nested"
    assert resolve_nested_agent_lane_for_session("") == "nested"


def test_is_nested_agent_lane_true_for_nested():
    assert is_nested_agent_lane("nested") is True


def test_is_nested_agent_lane_true_for_prefixed():
    assert is_nested_agent_lane("nested:sess-abc") is True


def test_is_nested_agent_lane_false_for_main():
    assert is_nested_agent_lane("main") is False


def test_is_nested_agent_lane_false_for_none():
    assert is_nested_agent_lane(None) is False


def test_agent_lane_subagent_constant():
    assert AGENT_LANE_SUBAGENT == "subagent"


# ---------------------------------------------------------------------------
# src/config/queue_config.py
# ---------------------------------------------------------------------------

from src.config.queue_config import (
    DEFAULT_QUEUE_CAP,
    DEFAULT_QUEUE_DROP,
    DEFAULT_QUEUE_MODE,
    resolve_queue_cap,
    resolve_queue_config,
    resolve_queue_drop,
    resolve_queue_mode,
)


def _q(mode=None, cap=None, drop=None) -> dict:
    queue: dict = {}
    if mode is not None:
        queue["mode"] = mode
    if cap is not None:
        queue["cap"] = cap
    if drop is not None:
        queue["drop"] = drop
    return {"messages": {"queue": queue}}


def test_queue_mode_default_when_absent():
    assert resolve_queue_mode(None) == DEFAULT_QUEUE_MODE
    assert resolve_queue_mode({}) == DEFAULT_QUEUE_MODE


def test_queue_mode_collect():
    assert resolve_queue_mode(_q(mode="collect")) == "collect"


def test_queue_mode_invalid_falls_back():
    assert resolve_queue_mode(_q(mode="bogus")) == DEFAULT_QUEUE_MODE


def test_queue_cap_default():
    assert resolve_queue_cap(None) == DEFAULT_QUEUE_CAP


def test_queue_cap_custom():
    assert resolve_queue_cap(_q(cap=5)) == 5


def test_queue_cap_clamps_to_one():
    assert resolve_queue_cap(_q(cap=0)) == 1
    assert resolve_queue_cap(_q(cap=-3)) == 1


def test_queue_drop_default():
    assert resolve_queue_drop(None) == DEFAULT_QUEUE_DROP


def test_queue_drop_summarize():
    assert resolve_queue_drop(_q(drop="summarize")) == "summarize"


def test_queue_drop_invalid_falls_back():
    assert resolve_queue_drop(_q(drop="junk")) == DEFAULT_QUEUE_DROP


def test_resolve_queue_config_full():
    cfg = _q(mode="collect", cap=20, drop="summarize")
    result = resolve_queue_config(cfg)
    assert result == {"mode": "collect", "cap": 20, "drop": "summarize"}


def test_resolve_queue_config_defaults_on_empty():
    result = resolve_queue_config(None)
    assert result["mode"] == DEFAULT_QUEUE_MODE
    assert result["cap"] == DEFAULT_QUEUE_CAP
    assert result["drop"] == DEFAULT_QUEUE_DROP


# ---------------------------------------------------------------------------
# src/config/agent_limits.py — already exists, just verify complete surface
# ---------------------------------------------------------------------------

from src.config.agent_limits import (
    DEFAULT_AGENT_MAX_CONCURRENT,
    DEFAULT_SUBAGENT_MAX_CONCURRENT,
    resolve_agent_max_concurrent,
    resolve_subagent_max_concurrent,
)


def test_resolve_agent_max_concurrent_default():
    assert resolve_agent_max_concurrent(None) == DEFAULT_AGENT_MAX_CONCURRENT == 4


def test_resolve_agent_max_concurrent_custom():
    cfg = {"agents": {"defaults": {"maxConcurrent": 6}}}
    assert resolve_agent_max_concurrent(cfg) == 6


def test_resolve_agent_max_concurrent_clamps_to_one():
    cfg = {"agents": {"defaults": {"maxConcurrent": 0}}}
    assert resolve_agent_max_concurrent(cfg) == 1


def test_resolve_subagent_max_concurrent_default():
    assert resolve_subagent_max_concurrent(None) == DEFAULT_SUBAGENT_MAX_CONCURRENT == 8


def test_resolve_subagent_max_concurrent_custom():
    cfg = {"agents": {"defaults": {"subagents": {"maxConcurrent": 12}}}}
    assert resolve_subagent_max_concurrent(cfg) == 12


# ---------------------------------------------------------------------------
# src/gateway/server_lanes.py
# ---------------------------------------------------------------------------

from src.gateway.server_lanes import (
    GatewayLaneConcurrency,
    apply_gateway_lane_concurrency,
    get_command_lane_concurrency,
    resolve_gateway_lane_concurrency,
    set_command_lane_concurrency,
)


@pytest.fixture(autouse=True)
def _clear_lane_table():
    """Reset the in-process lane concurrency table between tests."""
    from src.gateway import server_lanes as sl
    sl._lane_concurrency.clear()
    yield
    sl._lane_concurrency.clear()


def test_resolve_gateway_lane_concurrency_defaults():
    result = resolve_gateway_lane_concurrency(None)
    assert isinstance(result, GatewayLaneConcurrency)
    assert result.main == 4
    assert result.subagent == 8
    assert result.cron == 8


def test_resolve_gateway_lane_concurrency_custom():
    cfg = {
        "agents": {"defaults": {"maxConcurrent": 6, "subagents": {"maxConcurrent": 10}}},
        "cron": {"maxConcurrentRuns": 3},
    }
    result = resolve_gateway_lane_concurrency(cfg)
    assert result.main == 6
    assert result.subagent == 10
    assert result.cron == 3


def test_apply_gateway_lane_concurrency_sets_all_lanes():
    concurrency = GatewayLaneConcurrency(cron=3, main=5, subagent=10)
    apply_gateway_lane_concurrency(concurrency, gateway_start=True)
    assert get_command_lane_concurrency("cron") == 3
    assert get_command_lane_concurrency("cron-nested") == 3
    assert get_command_lane_concurrency("main") == 5
    assert get_command_lane_concurrency("nested") == 1  # always 1
    assert get_command_lane_concurrency("subagent") == 10


def test_apply_gateway_lane_concurrency_no_nested_on_reload():
    """Live-reload (gateway_start=False) must NOT set Nested lane."""
    concurrency = GatewayLaneConcurrency(cron=3, main=5, subagent=10)
    apply_gateway_lane_concurrency(concurrency, gateway_start=False)
    assert get_command_lane_concurrency("nested") is None


def test_set_get_command_lane_concurrency():
    set_command_lane_concurrency("custom-lane", 7)
    assert get_command_lane_concurrency("custom-lane") == 7


def test_set_command_lane_concurrency_clamps_to_one():
    set_command_lane_concurrency("main", 0)
    assert get_command_lane_concurrency("main") == 1


# ---------------------------------------------------------------------------
# src/agents/lane_contract.py
# ---------------------------------------------------------------------------

from src.agents.lane_contract import (
    DEFAULT_LANE_CONTRACT,
    LaneContract,
    build_lane_contract_prompt_block,
    read_lane_contract,
    render_lane_contract,
    write_lane_contract,
)


def test_render_lane_contract_contains_sections():
    contract = LaneContract(
        owns=["coding tasks"],
        does_not_own=["research"],
    )
    md = render_lane_contract(contract)
    assert "# Lane contract" in md
    assert "## Owns" in md
    assert "- coding tasks" in md
    assert "## Does not own" in md
    assert "- research" in md
    assert "## Chat budget" in md
    assert "## Handoff" in md
    assert "## Tool posture" in md


def test_render_lane_contract_empty_lists():
    contract = LaneContract()
    md = render_lane_contract(contract)
    assert "(none)" in md


def test_write_and_read_lane_contract(tmp_path):
    contract = LaneContract(
        owns=["debugging", "code review"],
        does_not_own=["research tasks"],
        notes="Created for testing",
    )
    written = write_lane_contract(tmp_path, contract)
    assert written.exists()

    parsed = read_lane_contract(tmp_path)
    assert parsed is not None
    assert "debugging" in parsed.owns
    assert "code review" in parsed.owns
    assert "research tasks" in parsed.does_not_own
    assert "Created for testing" in parsed.notes


def test_read_lane_contract_missing_returns_none(tmp_path):
    assert read_lane_contract(tmp_path) is None


def test_build_lane_contract_prompt_block():
    contract = LaneContract(
        owns=["coding"],
        does_not_own=["research"],
    )
    block = build_lane_contract_prompt_block(contract)
    assert "## Lane contract" in block
    assert "coding" in block
    assert "research" in block
    assert "Chat budget" in block


def test_default_lane_contract_is_template():
    assert DEFAULT_LANE_CONTRACT.owns  # has placeholder text
    assert DEFAULT_LANE_CONTRACT.does_not_own  # has placeholder text


# ---------------------------------------------------------------------------
# src/agents/delegation_capability.py
# ---------------------------------------------------------------------------

from src.agents.delegation_capability import (
    DelegationCapabilityError,
    enforce_delegation_capability,
    resolve_delegation_capability,
)


def test_resolve_full_when_no_fallback():
    cap = resolve_delegation_capability(fallback_active=False)
    assert cap == "full"


def test_resolve_full_when_fallback_but_no_report_provenance():
    cap = resolve_delegation_capability(
        fallback_active=True,
        input_provenance={"kind": "user_message"},
    )
    assert cap == "full"


def test_resolve_report_only_on_fallback_completion_report():
    cap = resolve_delegation_capability(
        fallback_active=True,
        input_provenance={"kind": "completion_report"},
    )
    assert cap == "report_only"


def test_enforce_full_capability_allows_delegation_tools():
    # Should not raise
    enforce_delegation_capability("sessions_spawn", {}, "full")
    enforce_delegation_capability("sessions_send", {}, None)


def test_enforce_report_only_blocks_new_delegation():
    with pytest.raises(DelegationCapabilityError):
        enforce_delegation_capability("sessions_spawn", {}, "report_only")


def test_enforce_report_only_blocks_llm_task():
    with pytest.raises(DelegationCapabilityError):
        enforce_delegation_capability("llm-task", {}, "report_only")


def test_enforce_report_only_allows_cron_list():
    # read-only cron action should not raise
    enforce_delegation_capability("cron", {"action": "list"}, "report_only")


def test_enforce_report_only_blocks_cron_write():
    with pytest.raises(DelegationCapabilityError):
        enforce_delegation_capability("cron", {"action": "create"}, "report_only")


def test_enforce_report_only_allows_image_generate_status():
    enforce_delegation_capability("image_generate", {"action": "status"}, "report_only")


def test_enforce_report_only_blocks_image_generate_create():
    with pytest.raises(DelegationCapabilityError):
        enforce_delegation_capability("image_generate", {"action": "generate"}, "report_only")


def test_enforce_unknown_tool_not_blocked_in_report_only():
    # Tools not in either set are not restricted
    enforce_delegation_capability("custom_tool", {}, "report_only")
