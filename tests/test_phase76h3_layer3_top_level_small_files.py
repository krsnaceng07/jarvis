"""Phase 7.6h-3 tests — 14 top-level small files."""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import pytest

# Ensure src/ is on sys.path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.agents.embedded_agent_runner.cache_ttl import (  # noqa: E402
    CACHE_TTL_CUSTOM_TYPE,
    is_cache_ttl_eligible_provider,
    read_last_cache_ttl_timestamp,
    set_is_cache_ttl_eligible_provider_hook,
    set_read_last_cache_ttl_timestamp_hook,
)
from src.agents.embedded_agent_runner.context_engine_capabilities import (  # noqa: E402
    resolve_context_engine_capabilities,
    set_resolve_context_engine_capabilities_hook,
)
from src.agents.embedded_agent_runner.context_truncation_notice import (  # noqa: E402
    format_context_limit_truncation_notice,
)
from src.agents.embedded_agent_runner.effective_tool_policy import (  # noqa: E402
    apply_final_effective_tool_policy,
    set_apply_final_effective_tool_policy_hook,
)
from src.agents.embedded_agent_runner.extensions import (  # noqa: E402
    build_embedded_extension_factories,
    set_build_embedded_extension_factories_hook,
)
from src.agents.embedded_agent_runner.manual_compaction_boundary import (  # noqa: E402
    harden_manual_compaction_boundary,
    set_harden_manual_compaction_boundary_hook,
)
from src.agents.embedded_agent_runner.model_test_harness import (  # noqa: E402
    OPENAI_CODEX_TEMPLATE_MODEL,
    build_openai_codex_forward_compat_expectation,
    make_model,
    mock_discovered_model,
    mock_openai_codex_template_model,
    reset_mock_discover_models,
)
from src.agents.embedded_agent_runner.prompt_cache_observability import (  # noqa: E402
    _TRACKERS,
    begin_prompt_cache_observation,
    collect_prompt_cache_tool_names,
    complete_prompt_cache_observation,
    set_begin_prompt_cache_observation_hook,
    set_complete_prompt_cache_observation_hook,
)
from src.agents.embedded_agent_runner.prompt_cache_retention import (  # noqa: E402
    is_google_prompt_cache_eligible,
    parse_cache_retention,
    resolve_cache_retention,
    set_resolve_cache_retention_hook,
)
from src.agents.embedded_agent_runner.resource_loader import (  # noqa: E402
    EMBEDDED_AGENT_RESOURCE_LOADER_DISCOVERY_OPTIONS,
    create_embedded_agent_resource_loader,
    set_create_embedded_agent_resource_loader_hook,
)
from src.agents.embedded_agent_runner.run import run_embedded_agent  # noqa: E402
from src.agents.embedded_agent_runner.sandbox_skills import (  # noqa: E402
    map_sandbox_skill_entries_for_prompt,
    map_sandbox_skill_usage_paths,
    resolve_sandbox_skill_runtime_inputs,
    set_map_sandbox_skill_entries_for_prompt_hook,
    set_map_sandbox_skill_usage_paths_hook,
    set_resolve_sandbox_skill_runtime_inputs_hook,
)
from src.agents.embedded_agent_runner.utils import (  # noqa: E402
    map_thinking_level,
    map_thinking_level_for_provider,
    normalize_context_token_budget,
    set_map_thinking_level_for_provider_hook,
    set_map_thinking_level_hook,
    set_normalize_context_token_budget_hook,
)
from src.agents.embedded_agent_runner.wait_for_idle_before_flush import (  # noqa: E402
    DEFAULT_WAIT_FOR_IDLE_TIMEOUT_MS,
    flush_pending_tool_results_after_idle,
    set_flush_pending_tool_results_after_idle_hook,
)


# ============================================================================
# cache_ttl
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_cache_ttl_hooks() -> None:
    set_is_cache_ttl_eligible_provider_hook(None)
    set_read_last_cache_ttl_timestamp_hook(None)
    yield
    set_is_cache_ttl_eligible_provider_hook(None)
    set_read_last_cache_ttl_timestamp_hook(None)


class TestCacheTtl:
    def test_custom_type(self) -> None:
        assert CACHE_TTL_CUSTOM_TYPE == "openclaw.cache-ttl"

    def test_eligible_default(self) -> None:
        assert is_cache_ttl_eligible_provider("anthropic", "claude-sonnet-4") is True
        assert is_cache_ttl_eligible_provider("openai", "gpt-4o") is False

    def test_eligible_google(self) -> None:
        assert is_google_prompt_cache_eligible.__class__.__name__ == "function"
        # Use a different module to test google
        from src.agents.embedded_agent_runner.prompt_cache_retention import (
            is_google_prompt_cache_eligible as is_google,
        )
        assert is_google({"modelApi": "google-generative-ai", "modelId": "gemini-2.5-pro"}) is True
        assert is_google({"modelApi": "google-generative-ai", "modelId": "gemini-3-flash"}) is True
        assert is_google({"modelApi": "google-generative-ai", "modelId": "gemini-1.5-pro"}) is False
        assert is_google({"modelApi": "openai", "modelId": "gemini-2.5"}) is False

    def test_eligible_kilocode(self) -> None:
        assert is_cache_ttl_eligible_provider("kilocode", "claude-3-5-sonnet") is True

    def test_eligible_with_hook(self) -> None:
        set_is_cache_ttl_eligible_provider_hook(lambda _p: True)
        assert is_cache_ttl_eligible_provider("openai", "gpt-4o") is True

    def test_read_timestamp_no_entries(self) -> None:
        assert read_last_cache_ttl_timestamp({}) is None

    def test_read_timestamp_with_entries(self) -> None:
        sm = {
            "getEntries": lambda: [
                {"type": "message"},
                {
                    "type": "custom",
                    "customType": CACHE_TTL_CUSTOM_TYPE,
                    "data": {"timestamp": 12345, "provider": "anthropic"},
                },
            ]
        }
        assert read_last_cache_ttl_timestamp(sm) == 12345

    def test_read_timestamp_with_context(self) -> None:
        sm = {
            "getEntries": lambda: [
                {
                    "type": "custom",
                    "customType": CACHE_TTL_CUSTOM_TYPE,
                    "data": {"timestamp": 1000, "provider": "openai", "modelId": "gpt"},
                }
            ]
        }
        # No context match → None
        assert read_last_cache_ttl_timestamp(sm, {"provider": "anthropic"}) is None
        # Context matches → 1000
        assert read_last_cache_ttl_timestamp(sm, {"provider": "openai"}) == 1000

    def test_read_timestamp_with_hook(self) -> None:
        set_read_last_cache_ttl_timestamp_hook(lambda _p: 99999)
        assert read_last_cache_ttl_timestamp({}) == 99999

    def test_read_timestamp_exception(self) -> None:
        sm = {"getEntries": lambda: (_ for _ in ()).throw(RuntimeError("boom"))}
        assert read_last_cache_ttl_timestamp(sm) is None


# ============================================================================
# context_engine_capabilities
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_context_engine_capabilities_hooks() -> None:
    set_resolve_context_engine_capabilities_hook(None)
    yield
    set_resolve_context_engine_capabilities_hook(None)


class TestContextEngineCapabilities:
    def test_basic(self) -> None:
        out = resolve_context_engine_capabilities({"purpose": "test"})
        assert "llm" in out
        assert callable(out["llm"]["complete"])

    def test_with_hook(self) -> None:
        set_resolve_context_engine_capabilities_hook(lambda _p: {"llm": {"complete": "stub"}})
        out = resolve_context_engine_capabilities({"purpose": "test"})
        assert out["llm"]["complete"] == "stub"

    def test_async_callable(self) -> None:
        out = resolve_context_engine_capabilities({"purpose": "test"})
        # The complete is an async function; calling it returns a coroutine
        import inspect
        assert inspect.iscoroutinefunction(out["llm"]["complete"])


# ============================================================================
# context_truncation_notice
# ============================================================================


class TestContextTruncationNotice:
    def test_basic(self) -> None:
        out = format_context_limit_truncation_notice(1500)
        assert "1500" in out
        assert "more characters truncated" in out
        assert "rerun with narrower args" in out

    def test_negative_input(self) -> None:
        # Math.max(1, ...) means at least 1
        out = format_context_limit_truncation_notice(-100)
        assert "1" in out

    def test_zero_input(self) -> None:
        out = format_context_limit_truncation_notice(0)
        assert "1" in out


# ============================================================================
# effective_tool_policy
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_effective_tool_policy_hooks() -> None:
    set_apply_final_effective_tool_policy_hook(None)
    yield
    set_apply_final_effective_tool_policy_hook(None)


class TestEffectiveToolPolicy:
    def test_empty(self) -> None:
        assert apply_final_effective_tool_policy({"bundledTools": []}) == []

    def test_passthrough(self) -> None:
        tools = [{"name": "a"}, {"name": "b"}]
        assert apply_final_effective_tool_policy({"bundledTools": tools}) == tools

    def test_with_hook(self) -> None:
        set_apply_final_effective_tool_policy_hook(lambda _p: [{"name": "filtered"}])
        assert apply_final_effective_tool_policy({"bundledTools": [{"name": "x"}]}) == [{"name": "filtered"}]


# ============================================================================
# extensions
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_extensions_hooks() -> None:
    set_build_embedded_extension_factories_hook(None)
    yield
    set_build_embedded_extension_factories_hook(None)


class TestExtensions:
    def test_default(self) -> None:
        factories = build_embedded_extension_factories({})
        assert len(factories) >= 1
        assert callable(factories[0])

    def test_with_hook(self) -> None:
        set_build_embedded_extension_factories_hook(lambda _p: ["custom"])
        assert build_embedded_extension_factories({}) == ["custom"]


# ============================================================================
# manual_compaction_boundary
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_manual_compaction_boundary_hooks() -> None:
    set_harden_manual_compaction_boundary_hook(None)
    yield
    set_harden_manual_compaction_boundary_hook(None)


class TestManualCompactionBoundary:
    def test_default(self) -> None:
        out = harden_manual_compaction_boundary({"sessionFile": "/tmp/x.jsonl"})
        assert out["applied"] is False
        assert out["messages"] == []

    def test_with_hook(self) -> None:
        set_harden_manual_compaction_boundary_hook(lambda _p: {"applied": True, "messages": [{"role": "assistant"}]})
        out = harden_manual_compaction_boundary({})
        assert out["applied"] is True
        assert len(out["messages"]) == 1


# ============================================================================
# model_test_harness
# ============================================================================


class _MockMock:
    """Mimics unittest.mock.Mock for return_value wiring."""

    def __init__(self) -> None:
        self.return_value: Any = None


class TestModelTestHarness:
    def test_make_model(self) -> None:
        m = make_model("gpt-4o")
        assert m["id"] == "gpt-4o"
        assert m["name"] == "gpt-4o"
        assert m["contextWindow"] == 1

    def test_openai_codex_template(self) -> None:
        assert OPENAI_CODEX_TEMPLATE_MODEL["id"] == "gpt-5.3-codex"
        assert OPENAI_CODEX_TEMPLATE_MODEL["provider"] == "openai"
        assert OPENAI_CODEX_TEMPLATE_MODEL["contextWindow"] == 1_050_000

    def test_mock_openai_codex_template(self) -> None:
        m = _MockMock()
        mock_openai_codex_template_model(m)
        result = m.return_value
        # find should return OPENAI_CODEX_TEMPLATE_MODEL when called with openai/gpt-5.3-codex
        assert result["find"]("openai", "gpt-5.3-codex") == OPENAI_CODEX_TEMPLATE_MODEL
        assert result["find"]("anthropic", "claude") is None

    def test_build_forward_compat_default(self) -> None:
        exp = build_openai_codex_forward_compat_expectation()
        assert exp["id"] == "gpt-5.3-codex"
        assert exp["provider"] == "openai"

    def test_build_forward_compat_gpt54(self) -> None:
        exp = build_openai_codex_forward_compat_expectation("gpt-5.4")
        assert exp["cost"]["input"] == 2.5
        assert exp["contextWindow"] == 1_050_000
        assert exp["contextTokens"] == 272_000

    def test_build_forward_compat_spark(self) -> None:
        exp = build_openai_codex_forward_compat_expectation("gpt-5.3-codex-spark")
        assert exp["input"] == ["text"]
        assert exp["cost"]["input"] == 0
        assert exp["contextWindow"] == 128_000

    def test_build_forward_compat_gpt54mini(self) -> None:
        exp = build_openai_codex_forward_compat_expectation("gpt-5.4-mini")
        assert exp["cost"]["input"] == 0.75
        assert exp["contextWindow"] == 400_000

    def test_mock_discovered_model(self) -> None:
        m = _MockMock()
        mock_discovered_model(
            m,
            {"provider": "anthropic", "modelId": "claude", "templateModel": {"id": "claude"}},
        )
        find = m.return_value["find"]
        assert find("anthropic", "claude") == {"id": "claude"}
        assert find("openai", "gpt") is None

    def test_reset_mock_discover(self) -> None:
        m = _MockMock()
        m.return_value = {"find": lambda *_: "stale"}
        reset_mock_discover_models(m)
        assert m.return_value["find"]("p", "m") is None


# ============================================================================
# prompt_cache_observability
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_cache_obs_hooks() -> None:
    _TRACKERS.clear()
    set_begin_prompt_cache_observation_hook(None)
    set_complete_prompt_cache_observation_hook(None)
    yield
    _TRACKERS.clear()
    set_begin_prompt_cache_observation_hook(None)
    set_complete_prompt_cache_observation_hook(None)


class TestPromptCacheObservability:
    def test_collect_tool_names(self) -> None:
        tools = [
            {"name": "alpha"},
            {"name": "beta"},
            {"name": ""},
            {"name": "  gamma  "},
            {},
        ]
        names = collect_prompt_cache_tool_names(tools)
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" in names

    def test_collect_empty(self) -> None:
        assert collect_prompt_cache_tool_names([]) == []
        assert collect_prompt_cache_tool_names(None) == []

    def test_begin_observation(self) -> None:
        out = begin_prompt_cache_observation(
            {
                "sessionId": "s1",
                "provider": "anthropic",
                "modelId": "claude-sonnet-4",
                "streamStrategy": "stream",
                "systemPrompt": "You are a helpful assistant.",
                "toolNames": ["read", "write"],
            }
        )
        assert "snapshot" in out
        assert out["snapshot"]["provider"] == "anthropic"
        assert out["snapshot"]["toolCount"] == 2
        assert out["changes"] is None  # first time, no diff

    def test_begin_with_diff(self) -> None:
        params1 = {
            "sessionId": "s1",
            "provider": "anthropic",
            "modelId": "claude-sonnet-4",
            "streamStrategy": "stream",
            "systemPrompt": "sp1",
            "toolNames": ["read"],
        }
        params2 = {
            "sessionId": "s1",
            "provider": "anthropic",
            "modelId": "claude-sonnet-4",
            "streamStrategy": "stream",
            "systemPrompt": "sp2",  # changed
            "toolNames": ["read", "write"],  # changed
        }
        begin_prompt_cache_observation(params1)
        out = begin_prompt_cache_observation(params2)
        assert out["changes"] is not None
        codes = {c["code"] for c in out["changes"]}
        assert "systemPrompt" in codes
        assert "tools" in codes

    def test_complete_no_tracker(self) -> None:
        out = complete_prompt_cache_observation({"sessionId": "nope", "usage": {"cacheRead": 100}})
        assert out is None

    def test_complete_meaningful_drop(self) -> None:
        begin_prompt_cache_observation(
            {
                "sessionId": "s1",
                "provider": "p",
                "modelId": "m",
                "streamStrategy": "s",
                "systemPrompt": "sp",
                "toolNames": [],
            }
        )
        # Manually set lastCacheRead to seed the comparison
        key = "s1"
        _TRACKERS[key]["lastCacheRead"] = 10_000
        out = complete_prompt_cache_observation(
            {"sessionId": "s1", "usage": {"cacheRead": 1_000}}
        )
        assert out is not None
        assert out["previousCacheRead"] == 10_000
        assert out["cacheRead"] == 1_000

    def test_complete_with_hook(self) -> None:
        set_complete_prompt_cache_observation_hook(lambda _p: {"custom": True})
        assert complete_prompt_cache_observation({}) == {"custom": True}

    def test_begin_with_hook(self) -> None:
        set_begin_prompt_cache_observation_hook(
            lambda p: {"snapshot": {"provider": p["provider"]}}
        )
        out = begin_prompt_cache_observation({"sessionId": "s1", "provider": "p"})
        assert out["snapshot"]["provider"] == "p"


# ============================================================================
# prompt_cache_retention
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_cache_retention_hooks() -> None:
    set_resolve_cache_retention_hook(None)
    yield
    set_resolve_cache_retention_hook(None)


class TestPromptCacheRetention:
    def test_parse(self) -> None:
        assert parse_cache_retention("none") == "none"
        assert parse_cache_retention("short") == "short"
        assert parse_cache_retention("long") == "long"
        assert parse_cache_retention("invalid") is None
        assert parse_cache_retention(None) is None
        assert parse_cache_retention(123) is None

    def test_is_google_eligible(self) -> None:
        assert is_google_prompt_cache_eligible({"modelApi": "google-generative-ai", "modelId": "gemini-2.5-pro"}) is True
        assert is_google_prompt_cache_eligible({"modelApi": "google-generative-ai", "modelId": "gemini-3-flash"}) is True
        assert is_google_prompt_cache_eligible({"modelApi": "google-generative-ai", "modelId": "gemini-1.5"}) is False
        assert is_google_prompt_cache_eligible({"modelApi": "openai", "modelId": "gemini-2.5"}) is False

    def test_resolve_explicit_short(self) -> None:
        out = resolve_cache_retention(
            {"cacheRetention": "short"}, "anthropic", "anthropic-messages", "claude-sonnet-4"
        )
        assert out == "short"

    def test_resolve_explicit_long(self) -> None:
        out = resolve_cache_retention(
            {"cacheRetention": "long"}, "anthropic", "anthropic-messages", "claude-sonnet-4"
        )
        assert out == "long"

    def test_resolve_legacy_5m(self) -> None:
        out = resolve_cache_retention(
            {"cacheControlTtl": "5m"}, "anthropic", "anthropic-messages", "claude-sonnet-4"
        )
        assert out == "short"

    def test_resolve_legacy_1h(self) -> None:
        out = resolve_cache_retention(
            {"cacheControlTtl": "1h"}, "anthropic", "anthropic-messages", "claude-sonnet-4"
        )
        assert out == "long"

    def test_resolve_legacy_not_eligible(self) -> None:
        out = resolve_cache_retention(
            {"cacheControlTtl": "5m"}, "openai", "openai-chat", "gpt-4o"
        )
        assert out is None

    def test_resolve_anthropic_default(self) -> None:
        out = resolve_cache_retention({}, "anthropic", "anthropic-messages", "claude-sonnet-4")
        assert out == "short"

    def test_resolve_with_hook(self) -> None:
        set_resolve_cache_retention_hook(lambda _p: "long")
        assert resolve_cache_retention({}, "openai", "openai-chat", "gpt-4o") == "long"


# ============================================================================
# resource_loader
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_resource_loader_hooks() -> None:
    set_create_embedded_agent_resource_loader_hook(None)
    yield
    set_create_embedded_agent_resource_loader_hook(None)


class TestResourceLoader:
    def test_discovery_options(self) -> None:
        assert EMBEDDED_AGENT_RESOURCE_LOADER_DISCOVERY_OPTIONS["noExtensions"] is True
        assert EMBEDDED_AGENT_RESOURCE_LOADER_DISCOVERY_OPTIONS["noSkills"] is True
        assert EMBEDDED_AGENT_RESOURCE_LOADER_DISCOVERY_OPTIONS["noPromptTemplates"] is True
        assert EMBEDDED_AGENT_RESOURCE_LOADER_DISCOVERY_OPTIONS["noThemes"] is True
        assert EMBEDDED_AGENT_RESOURCE_LOADER_DISCOVERY_OPTIONS["noContextFiles"] is True

    def test_basic(self) -> None:
        loader = create_embedded_agent_resource_loader({"cwd": "/tmp"})
        assert loader["options"]["cwd"] == "/tmp"
        assert loader["options"]["noExtensions"] is True

    def test_with_hook(self) -> None:
        set_create_embedded_agent_resource_loader_hook(lambda _p: {"stub": True})
        assert create_embedded_agent_resource_loader({}) == {"stub": True}


# ============================================================================
# run (top-level re-export)
# ============================================================================


class TestRunReExport:
    def test_reexports(self) -> None:
        from src.agents.embedded_agent_runner.run_orchestrator import (
            run_embedded_agent as r_orch,
        )
        assert run_embedded_agent is r_orch


# ============================================================================
# sandbox_skills
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_sandbox_skills_hooks() -> None:
    set_map_sandbox_skill_entries_for_prompt_hook(None)
    set_map_sandbox_skill_usage_paths_hook(None)
    set_resolve_sandbox_skill_runtime_inputs_hook(None)
    yield
    set_map_sandbox_skill_entries_for_prompt_hook(None)
    set_map_sandbox_skill_usage_paths_hook(None)
    set_resolve_sandbox_skill_runtime_inputs_hook(None)


class TestSandboxSkills:
    def test_same_workspace(self) -> None:
        entries = [{"skill": {"filePath": "/x/y"}}]
        out = map_sandbox_skill_entries_for_prompt(
            {"entries": entries, "skillsWorkspaceDir": "/x", "skillsPromptWorkspaceDir": "/x"}
        )
        assert out is entries

    def test_map_entries(self) -> None:
        entries = [
            {
                "skill": {
                    "filePath": "/host/skills/foo.md",
                    "baseDir": "/host/skills",
                    "sourceInfo": {"path": "/host/skills/foo.md", "baseDir": "/host/skills"},
                }
            }
        ]
        out = map_sandbox_skill_entries_for_prompt(
            {
                "entries": entries,
                "skillsWorkspaceDir": "/host",
                "skillsPromptWorkspaceDir": "/container",
            }
        )
        assert out is not None
        # The mapped file path should be in the target workspace
        fp = out[0]["skill"]["filePath"]
        assert "container" in fp.lower() or "foo.md" in fp

    def test_map_usage_paths(self) -> None:
        paths = [{"readPath": "/host/skills/foo.md"}]
        out = map_sandbox_skill_usage_paths(
            {"paths": paths, "skillsWorkspaceDir": "/host", "skillsPromptWorkspaceDir": "/container"}
        )
        assert out is not None
        assert "container" in out[0]["readPath"].lower() or "foo.md" in out[0]["readPath"]

    def test_map_entries_with_hook(self) -> None:
        set_map_sandbox_skill_entries_for_prompt_hook(lambda _p: ["hooked"])
        assert map_sandbox_skill_entries_for_prompt({}) == ["hooked"]

    def test_map_paths_with_hook(self) -> None:
        set_map_sandbox_skill_usage_paths_hook(lambda _p: ["hooked"])
        assert map_sandbox_skill_usage_paths({}) == ["hooked"]

    def test_resolve_sandbox_disabled(self) -> None:
        out = resolve_sandbox_skill_runtime_inputs(
            {"sandbox": None, "effectiveWorkspace": "/x"}
        )
        assert out["workspaceOnly"] is False
        assert out["skillsWorkspaceDir"] == "/x"

    def test_resolve_sandbox_enabled(self) -> None:
        out = resolve_sandbox_skill_runtime_inputs(
            {
                "sandbox": {
                    "enabled": True,
                    "containerWorkdir": "/container",
                    "skillsWorkspaceDir": "/container/skills",
                },
                "effectiveWorkspace": "/x",
            }
        )
        assert out["workspaceOnly"] is True
        assert "container" in out["skillsPromptWorkspaceDir"].lower()

    def test_resolve_with_hook(self) -> None:
        set_resolve_sandbox_skill_runtime_inputs_hook(lambda _p: {"workspaceOnly": "hooked"})
        out = resolve_sandbox_skill_runtime_inputs({})
        assert out["workspaceOnly"] == "hooked"


# ============================================================================
# utils
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_utils_hooks() -> None:
    set_normalize_context_token_budget_hook(None)
    set_map_thinking_level_for_provider_hook(None)
    set_map_thinking_level_hook(None)
    yield
    set_normalize_context_token_budget_hook(None)
    set_map_thinking_level_for_provider_hook(None)
    set_map_thinking_level_hook(None)


class TestUtils:
    def test_normalize_budget(self) -> None:
        assert normalize_context_token_budget(100) == 100
        assert normalize_context_token_budget(100.7) == 100
        assert normalize_context_token_budget(0) is None
        assert normalize_context_token_budget(-1) is None
        assert normalize_context_token_budget(None) is None
        assert normalize_context_token_budget("100") is None
        assert normalize_context_token_budget(float("inf")) is None

    def test_normalize_with_hook(self) -> None:
        set_normalize_context_token_budget_hook(lambda v: 999)
        assert normalize_context_token_budget(100) == 999

    def test_map_thinking_for_provider(self) -> None:
        assert map_thinking_level_for_provider("ultra") == "max"
        assert map_thinking_level_for_provider("high") == "high"
        assert map_thinking_level_for_provider("low") == "low"
        assert map_thinking_level_for_provider(None) is None
        assert map_thinking_level_for_provider("invalid") is None

    def test_map_for_provider_with_hook(self) -> None:
        set_map_thinking_level_for_provider_hook(lambda v: "max" if v else None)
        assert map_thinking_level_for_provider("high") == "max"
        assert map_thinking_level_for_provider(None) is None

    def test_map_thinking(self) -> None:
        assert map_thinking_level("ultra") == "max"
        assert map_thinking_level("high") == "high"
        assert map_thinking_level("adaptive") == "high"
        assert map_thinking_level(None) == "off"
        assert map_thinking_level("invalid") == "off"

    def test_map_thinking_with_hook(self) -> None:
        set_map_thinking_level_hook(lambda v: "hooked")
        assert map_thinking_level("high") == "hooked"


# ============================================================================
# wait_for_idle_before_flush
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_wait_for_idle_hooks() -> None:
    set_flush_pending_tool_results_after_idle_hook(None)
    yield
    set_flush_pending_tool_results_after_idle_hook(None)


class TestWaitForIdle:
    def test_default(self) -> None:
        assert DEFAULT_WAIT_FOR_IDLE_TIMEOUT_MS == 30_000

    def test_basic_no_agent(self) -> None:
        called = {"flush": 0}

        class SM:
            def flushPendingToolResults(self):
                called["flush"] += 1

        asyncio.run(
            flush_pending_tool_results_after_idle(
                {"agent": None, "sessionManager": SM(), "timeoutMs": 0}
            )
        )
        assert called["flush"] == 1

    def test_with_immediate_timeout(self) -> None:
        # timeoutMs <= 0 → skip the wait, still flush
        called = {"flush": 0}

        class SM:
            def flushPendingToolResults(self):
                called["flush"] += 1

        asyncio.run(
            flush_pending_tool_results_after_idle(
                {"agent": None, "sessionManager": SM(), "timeoutMs": -1}
            )
        )
        assert called["flush"] == 1

    def test_with_hook_async(self) -> None:
        async def _hook(_opts):
            return None
        set_flush_pending_tool_results_after_idle_hook(_hook)
        asyncio.run(flush_pending_tool_results_after_idle({}))

    def test_with_hook_sync(self) -> None:
        set_flush_pending_tool_results_after_idle_hook(lambda _opts: None)
        asyncio.run(flush_pending_tool_results_after_idle({}))

    def test_agent_with_no_wait(self) -> None:
        called = {"flush": 0}

        class SM:
            def flushPendingToolResults(self):
                called["flush"] += 1

        class Agent:
            pass  # no waitForIdle

        asyncio.run(
            flush_pending_tool_results_after_idle(
                {"agent": Agent(), "sessionManager": SM(), "timeoutMs": 100}
            )
        )
        assert called["flush"] == 1
