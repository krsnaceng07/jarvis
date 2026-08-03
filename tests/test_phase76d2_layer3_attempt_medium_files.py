"""Phase 7.6d-2 tests — 7 medium attempt.* files (tool-catalog, bundle-tools, prompt-observability, tool-construction-plan, abort, context-guards, client-tools)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.run.attempt_tool_catalog import (
    prepare_embedded_attempt_tool_catalog,
    set_effective_tool_policy_hook,
    set_tool_search_hook,
)
from src.agents.embedded_agent_runner.run.attempt_bundle_tools import (
    prepare_embedded_attempt_bundle_tools,
    set_create_bundle_lsp_runtime_hook,
    set_create_bundle_mcp_runtime_hook,
    set_should_create_bundle_lsp_runtime_hook,
    set_should_create_bundle_mcp_runtime_hook,
)
from src.agents.embedded_agent_runner.run.attempt_prompt_observability import (
    observe_embedded_attempt_prompt,
    set_record_stage_attempt_prompt_hook,
    set_resolve_prompt_cache_changes_hook,
)
from src.agents.embedded_agent_runner.run.attempt_tool_construction_plan import (
    apply_embedded_attempt_tools_allow,
    merge_forced_embedded_attempt_tools_allow,
    resolve_embedded_attempt_tool_construction_plan,
    set_should_create_bundle_lsp_runtime_construction_hook,
    set_should_create_bundle_mcp_runtime_construction_hook,
    should_create_bundle_lsp_runtime_for_attempt,
    should_create_bundle_mcp_runtime_for_attempt,
)
from src.agents.embedded_agent_runner.run.attempt_abort import (
    create_embedded_attempt_external_abort_controller,
    create_embedded_attempt_run_abort,
    set_create_external_abort_controller_hook,
    set_create_run_abort_controller_hook,
)
from src.agents.embedded_agent_runner.run.attempt_context_guards import (
    install_embedded_attempt_context_guards,
    set_install_context_guards_hook,
)
from src.agents.embedded_agent_runner.run.attempt_client_tools import (
    prepare_embedded_attempt_client_tools,
    set_create_client_tool_slots_hook,
    set_resolve_client_tool_policy_hook,
)


# ============================================================================
# attempt-tool-catalog
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_tool_catalog_hooks() -> None:
    set_effective_tool_policy_hook(lambda _p: None)
    set_tool_search_hook(lambda _p: {})
    yield
    set_effective_tool_policy_hook(lambda _p: None)
    set_tool_search_hook(lambda _p: {})


class TestPrepareEmbeddedAttemptToolCatalog:
    def test_basic(self) -> None:
        result = prepare_embedded_attempt_tool_catalog(
            {"effectiveTools": [{"name": "read"}]}
        )
        assert result["effectiveTools"] == [{"name": "read"}]
        assert result["uncompactedEffectiveTools"] == []
        assert result["emptyExplicitToolAllowlistError"] is None
        assert result["toolSearch"] == {}
        assert result["policy"] is None

    def test_with_tool_search(self) -> None:
        set_tool_search_hook(lambda _p: {"compacted": True})
        result = prepare_embedded_attempt_tool_catalog({})
        assert result["toolSearch"] == {"compacted": True}


# ============================================================================
# attempt-bundle-tools
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_bundle_tools_hooks() -> None:
    set_create_bundle_lsp_runtime_hook(lambda _p: asyncio.sleep(0))
    set_create_bundle_mcp_runtime_hook(lambda _p: asyncio.sleep(0))
    set_should_create_bundle_lsp_runtime_hook(lambda _p: False)
    set_should_create_bundle_mcp_runtime_hook(lambda _p: False)
    yield
    set_should_create_bundle_lsp_runtime_hook(lambda _p: False)
    set_should_create_bundle_mcp_runtime_hook(lambda _p: False)


class TestPrepareEmbeddedAttemptBundleTools:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_bundle_tools(
            {
                "tools": [{"name": "read"}],
                "uncompactedEffectiveTools": [{"name": "read"}],
            }
        )
        )
        assert result["tools"] == [{"name": "read"}]
        assert result["uncompactedEffectiveTools"] == [{"name": "read"}]
        assert result["toolSearch"] is None


# ============================================================================
# attempt-prompt-observability
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_observability_hooks() -> None:
    set_record_stage_attempt_prompt_hook(lambda _p: None)
    set_resolve_prompt_cache_changes_hook(lambda _p: None)
    yield
    set_record_stage_attempt_prompt_hook(lambda _p: None)
    set_resolve_prompt_cache_changes_hook(lambda _p: None)


class TestObserveEmbeddedAttemptPrompt:
    def test_no_changes(self) -> None:
        result = observe_embedded_attempt_prompt({})
        assert result["changes"] == []
        assert result["break"] is None

    def test_with_changes(self) -> None:
        set_resolve_prompt_cache_changes_hook(
            lambda _p: [{"code": "x", "detail": "y"}]
        )
        result = observe_embedded_attempt_prompt({})
        assert len(result["changes"]) == 1

    def test_with_trace_and_changes(self) -> None:
        captured: List[Dict[str, Any]] = []

        def _record(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_record_stage_attempt_prompt_hook(_record)
        set_resolve_prompt_cache_changes_hook(
            lambda _p: [{"code": "x"}]
        )
        result = observe_embedded_attempt_prompt(
            {"cacheTrace": {"recordStage": lambda *_: None}}
        )
        assert len(result["changes"]) == 1
        assert len(captured) == 1


# ============================================================================
# attempt-tool-construction-plan
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_construction_plan_hooks() -> None:
    set_should_create_bundle_lsp_runtime_construction_hook(lambda _p: False)
    set_should_create_bundle_mcp_runtime_construction_hook(lambda _p: False)
    yield
    set_should_create_bundle_lsp_runtime_construction_hook(lambda _p: False)
    set_should_create_bundle_mcp_runtime_construction_hook(lambda _p: False)


class TestApplyEmbeddedAttemptToolsAllow:
    def test_no_allow(self) -> None:
        tools = [{"name": "read"}, {"name": "write"}]
        result = apply_embedded_attempt_tools_allow(tools, None)
        assert result == tools

    def test_with_allow(self) -> None:
        tools = [{"name": "read"}, {"name": "write"}, {"name": "bash"}]
        result = apply_embedded_attempt_tools_allow(tools, ["read", "bash"])
        names = [t["name"] for t in result]
        assert "read" in names
        assert "bash" in names
        assert "write" not in names

    def test_empty_allow(self) -> None:
        tools = [{"name": "read"}]
        result = apply_embedded_attempt_tools_allow(tools, [])
        assert result == tools

    def test_empty_allow_explicit(self) -> None:
        # `[]` is falsy in Python, so the function returns all tools.
        # OpenClaw treats `[]` as "no allow-list" too.
        tools = [{"name": "read"}]
        result = apply_embedded_attempt_tools_allow(tools, [])
        assert result == tools

    def test_non_list(self) -> None:
        result = apply_embedded_attempt_tools_allow("not a list", None)  # type: ignore[arg-type]
        assert result == []

    def test_tool_with_no_name_filtered_out(self) -> None:
        tools = [{"name": "read"}, {}]
        result = apply_embedded_attempt_tools_allow(tools, ["read"])
        # Tool without a name is filtered out
        assert len(result) == 1


class TestMergeForcedEmbeddedAttemptToolsAllow:
    def test_basic(self) -> None:
        result = merge_forced_embedded_attempt_tools_allow(
            [["read", "write"], ["write", "bash"]]
        )
        assert set(result) == {"read", "write", "bash"}

    def test_with_none(self) -> None:
        result = merge_forced_embedded_attempt_tools_allow(
            [None, ["read"], None]
        )
        assert result == ["read"]

    def test_with_non_list(self) -> None:
        result = merge_forced_embedded_attempt_tools_allow(
            ["not-a-list", ["read"]]
        )
        assert result == ["read"]

    def test_empty(self) -> None:
        assert merge_forced_embedded_attempt_tools_allow([]) == []


class TestResolveEmbeddedAttemptToolConstructionPlan:
    def test_basic(self) -> None:
        result = resolve_embedded_attempt_tool_construction_plan(
            {
                "allowLists": [["read"]],
                "runtimeAllow": ["bash"],
            }
        )
        assert set(result["toolsAllow"]) == {"read", "bash"}
        assert result["shouldCreateBundleMcpRuntime"] is False
        assert result["shouldCreateBundleLspRuntime"] is False

    def test_with_hooks(self) -> None:
        set_should_create_bundle_mcp_runtime_construction_hook(
            lambda _p: True
        )
        result = resolve_embedded_attempt_tool_construction_plan({})
        assert result["shouldCreateBundleMcpRuntime"] is True


class TestShouldCreateBundleRuntimeHelpers:
    def test_mcp(self) -> None:
        assert should_create_bundle_mcp_runtime_for_attempt({}) is False
        set_should_create_bundle_mcp_runtime_construction_hook(
            lambda _p: True
        )
        assert should_create_bundle_mcp_runtime_for_attempt({}) is True

    def test_lsp(self) -> None:
        assert should_create_bundle_lsp_runtime_for_attempt({}) is False
        set_should_create_bundle_lsp_runtime_construction_hook(
            lambda _p: True
        )
        assert should_create_bundle_lsp_runtime_for_attempt({}) is True


# ============================================================================
# attempt-abort
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_abort_hooks() -> None:
    set_create_external_abort_controller_hook(lambda _p: None)
    set_create_run_abort_controller_hook(lambda _p: None)
    yield
    set_create_external_abort_controller_hook(lambda _p: None)
    set_create_run_abort_controller_hook(lambda _p: None)


class TestCreateEmbeddedAttemptExternalAbortController:
    def test_basic(self) -> None:
        result = create_embedded_attempt_external_abort_controller(
            {"externalAbort": True, "signal": "sig"}
        )
        assert result["externalAbort"] is True
        assert result["signal"] == "sig"
        assert result["controller"] is None

    def test_hook_override(self) -> None:
        set_create_external_abort_controller_hook(
            lambda _p: "ctrl-1"
        )
        result = create_embedded_attempt_external_abort_controller({})
        assert result["controller"] == "ctrl-1"


class TestCreateEmbeddedAttemptRunAbort:
    def test_basic(self) -> None:
        result = create_embedded_attempt_run_abort(
            {"aborted": True, "externalAbort": False}
        )
        assert result["aborted"] is True
        assert result["externalAbort"] is False

    def test_hook_override(self) -> None:
        set_create_run_abort_controller_hook(lambda _p: "run-ctrl")
        result = create_embedded_attempt_run_abort({})
        assert result["controller"] == "run-ctrl"


# ============================================================================
# attempt-context-guards
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_context_guards_hooks() -> None:
    set_install_context_guards_hook(lambda _p: {})
    yield
    set_install_context_guards_hook(lambda _p: {})


class TestInstallEmbeddedAttemptContextGuards:
    def test_basic(self) -> None:
        result = install_embedded_attempt_context_guards({})
        assert result["guards"] == {}
        assert result["takePendingMidTurnPrecheckRequest"] is None
        assert result["getAfterTurnCheckpoint"] is None

    def test_with_guards(self) -> None:
        def _take_pending() -> Any:
            return "pending"

        def _get_checkpoint() -> Any:
            return "checkpoint"

        set_install_context_guards_hook(
            lambda _p: {
                "takePendingMidTurnPrecheckRequest": _take_pending,
                "getAfterTurnCheckpoint": _get_checkpoint,
            }
        )
        result = install_embedded_attempt_context_guards({})
        assert result["takePendingMidTurnPrecheckRequest"]() == "pending"
        assert result["getAfterTurnCheckpoint"]() == "checkpoint"


# ============================================================================
# attempt-client-tools
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_client_tools_hooks() -> None:
    set_create_client_tool_slots_hook(lambda _p: [])
    set_resolve_client_tool_policy_hook(lambda _p: None)
    yield
    set_create_client_tool_slots_hook(lambda _p: [])
    set_resolve_client_tool_policy_hook(lambda _p: None)


class TestPrepareEmbeddedAttemptClientTools:
    def test_basic(self) -> None:
        result = prepare_embedded_attempt_client_tools({})
        assert result["clientToolCallSlots"] == []
        assert result["clientToolPolicy"] is None
        assert result["hasDeliveredSourceReply"] is False

    def test_with_slots(self) -> None:
        set_create_client_tool_slots_hook(
            lambda _p: [{"toolCallId": "t1", "name": "n1"}]
        )
        result = prepare_embedded_attempt_client_tools(
            {"hasDeliveredSourceReply": True}
        )
        assert len(result["clientToolCallSlots"]) == 1
        assert result["hasDeliveredSourceReply"] is True
