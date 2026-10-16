"""Tests for the llm-task tool port.

Covers the helper functions + the dependency-injected
``create_llm_task_tool`` flow.

Mirrors a subset of OpenClaw's
``extensions/llm-task/src/llm-task-tool.test.ts``.

The extension directory uses a hyphen (``llm-task``)
which is not a valid Python identifier; the test loads
the module via ``importlib.util`` to avoid the namespace
collision and the ``sys.path.insert`` race that pytest
triggers in full-suite collection.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EXT_ROOT = os.path.dirname(_THIS_DIR)
if _EXT_ROOT not in sys.path:
    sys.path.insert(0, _EXT_ROOT)


def _load_module(name: str, file_path: str):
    spec = importlib.util.spec_from_file_location(name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module {name!r} from {file_path!r}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_LIB_PATH = os.path.join(_EXT_ROOT, "lib", "llm_task_tool.py")
_llm_task = _load_module("llm_task_tool", _LIB_PATH)

# Re-export the public surface for the test body.
LlmTaskDeps = _llm_task.LlmTaskDeps
LlmTaskToolDefinition = _llm_task.LlmTaskToolDefinition
LlmTaskToolName = _llm_task.LlmTaskToolName
LlmTaskToolLabel = _llm_task.LlmTaskToolLabel
LlmTaskToolDescription = _llm_task.LlmTaskToolDescription
create_llm_task_tool = _llm_task.create_llm_task_tool
collect_text = _llm_task.collect_text
format_thinking_policy = _llm_task.format_thinking_policy
llm_task_tool_definition = _llm_task.llm_task_tool_definition
resolve_llm_task_model_ref = _llm_task.resolve_llm_task_model_ref
strip_code_fences = _llm_task.strip_code_fences
strip_duplicate_provider_prefix = _llm_task.strip_duplicate_provider_prefix
supports_thinking_policy_level = _llm_task.supports_thinking_policy_level
to_model_key = _llm_task.to_model_key

from jarvis_sdk.api import (  # noqa: E402
    PluginApi,
)
from jarvis_sdk.context import (  # noqa: E402
    PluginContext,
)


# ── Helpers ──────────────────────────────────────────────


class TestStripCodeFences:
    def test_strips_json_fence(self) -> None:
        assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_plain_fence(self) -> None:
        assert strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_passes_through_unfenced(self) -> None:
        assert strip_code_fences('{"a": 1}') == '{"a": 1}'

    def test_handles_whitespace(self) -> None:
        assert strip_code_fences("  \n```\nhi\n```\n  ") == "hi"

    def test_handles_empty(self) -> None:
        assert strip_code_fences("") == ""


class TestCollectText:
    def test_concatenates_non_error_payloads(self) -> None:
        payloads = [
            {"text": "hello", "isError": False},
            {"text": "world", "isError": False},
        ]
        assert collect_text(payloads) == "hello\nworld"

    def test_skips_error_payloads(self) -> None:
        payloads = [
            {"text": "hello", "isError": False},
            {"text": "boom", "isError": True},
            {"text": "world", "isError": False},
        ]
        assert collect_text(payloads) == "hello\nworld"

    def test_handles_none(self) -> None:
        assert collect_text(None) == ""

    def test_skips_non_string_text(self) -> None:
        assert collect_text([{"text": 42, "isError": False}]) == ""


class TestToModelKey:
    def test_builds_provider_slash_model(self) -> None:
        assert to_model_key("openai", "gpt-5.4") == "openai/gpt-5.4"

    def test_returns_none_for_missing_provider(self) -> None:
        assert to_model_key(None, "gpt-5.4") is None
        assert to_model_key("", "gpt-5.4") is None

    def test_returns_none_for_missing_model(self) -> None:
        assert to_model_key("openai", None) is None
        assert to_model_key("openai", "") is None

    def test_strips_whitespace(self) -> None:
        assert to_model_key("  openai  ", "  gpt-5.4  ") == "openai/gpt-5.4"


class TestStripDuplicateProviderPrefix:
    def test_strips_when_present(self) -> None:
        assert strip_duplicate_provider_prefix("openai", "openai/gpt-5.4") == "gpt-5.4"

    def test_leaves_alone_when_absent(self) -> None:
        assert strip_duplicate_provider_prefix("openai", "gpt-5.4") == "gpt-5.4"

    def test_does_not_strip_partial_match(self) -> None:
        # "openai" does not start with "open/", so we leave it.
        assert strip_duplicate_provider_prefix("open", "openai/gpt-5.4") == "openai/gpt-5.4"

    def test_returns_model_when_no_provider(self) -> None:
        assert strip_duplicate_provider_prefix(None, "gpt-5.4") == "gpt-5.4"
        assert strip_duplicate_provider_prefix("", "gpt-5.4") == "gpt-5.4"

    def test_returns_none_when_both_missing(self) -> None:
        assert strip_duplicate_provider_prefix(None, None) is None


class TestResolveLlmTaskModelRef:
    def test_returns_raw_provider_and_stripped_model_when_no_resolution(
        self,
    ) -> None:
        api = PluginApi(PluginContext(plugin_id="t", plugin_kind="tool"))
        result = resolve_llm_task_model_ref(api=api, provider="openai", raw_model="gpt-5.4")
        assert result == {"provider": "openai", "model": "gpt-5.4"}

    def test_returns_none_provider_when_missing(self) -> None:
        api = PluginApi(PluginContext(plugin_id="t", plugin_kind="tool"))
        result = resolve_llm_task_model_ref(api=api, provider=None, raw_model="gpt-5.4")
        assert result == {"provider": None, "model": "gpt-5.4"}

    def test_uses_resolved_ref_when_available(self) -> None:
        api = PluginApi(PluginContext(plugin_id="t", plugin_kind="tool"))
        # The default resolve_model_ref_from_string returns
        # None, so the fallback path is used.
        result = resolve_llm_task_model_ref(api=api, provider="openai", raw_model="openai/gpt-5.4")
        assert result == {"provider": "openai", "model": "gpt-5.4"}


class TestThinkingPolicy:
    def test_format_returns_joined_labels(self) -> None:
        policy = {
            "levels": [
                {"id": "low", "label": "Low"},
                {"id": "high", "label": "High"},
            ]
        }
        assert format_thinking_policy(policy) == "Low, High"

    def test_format_handles_empty_levels(self) -> None:
        assert format_thinking_policy({"levels": []}) == ""

    def test_format_handles_missing_levels(self) -> None:
        assert format_thinking_policy({}) == ""

    def test_supports_returns_true_for_matching_level(self) -> None:
        policy = {
            "levels": [
                {"id": "low", "label": "Low"},
                {"id": "high", "label": "High"},
            ]
        }
        assert supports_thinking_policy_level(policy, "low") is True
        assert supports_thinking_policy_level(policy, "high") is True

    def test_supports_returns_false_for_unknown_level(self) -> None:
        policy = {"levels": [{"id": "low", "label": "Low"}]}
        assert supports_thinking_policy_level(policy, "missing") is False

    def test_supports_returns_false_for_none(self) -> None:
        assert supports_thinking_policy_level({"levels": []}, None) is False


# ── create_llm_task_tool ─────────────────────────────────


class TestLlmTaskToolDefinition:
    def test_default_definition(self) -> None:
        assert llm_task_tool_definition.name == "llm-task"
        assert llm_task_tool_definition.label == "LLM Task"
        params = llm_task_tool_definition.parameters
        assert "prompt" in params["properties"]
        assert "input" in params["properties"]
        assert "schema" in params["properties"]
        assert "provider" in params["properties"]
        assert "model" in params["properties"]
        assert "thinking" in params["properties"]
        assert "authProfileId" in params["properties"]
        assert "temperature" in params["properties"]
        assert "maxTokens" in params["properties"]
        assert "timeoutMs" in params["properties"]
        assert params["required"] == ["prompt"]


def _make_api(
    *,
    plugin_config: dict | None = None,
    config: dict | None = None,
) -> PluginApi:
    ctx = PluginContext(plugin_id="llm-task", plugin_kind="tool", config=config)
    api = PluginApi(ctx)
    if config is not None:
        api.set_config(config)
    if plugin_config is not None:
        api.set_plugin_config(plugin_config)
    return api


def _fake_run_agent(
    result: dict | None = None,
    capture: dict | None = None,
):
    """Build a fake ``run_embedded_agent`` callable."""

    async def run(params: dict) -> dict:
        if capture is not None:
            capture.update(params)
        return result or {"payloads": [{"text": '{"answer": 42}', "isError": False}]}

    return run


class TestCreateLlmTaskTool:
    def test_returns_tool_with_name_label_description(self) -> None:
        api = _make_api()
        tool = create_llm_task_tool(api)
        assert tool["name"] == "llm-task"
        assert tool["label"] == "LLM Task"
        assert "JSON-only" in tool["description"]
        assert "parameters" in tool
        assert "execute" in tool

    def test_execute_raises_when_prompt_missing(self) -> None:
        api = _make_api()
        tool = create_llm_task_tool(api, deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent()))
        with pytest.raises(ValueError, match="prompt required"):
            asyncio.run(
                tool["execute"](
                    "id1",
                    {
                        "prompt": "",
                        "provider": "openai",
                        "model": "gpt-5.4",
                    },
                )
            )

    def test_execute_raises_when_run_embedded_agent_not_wired(self) -> None:
        api = _make_api()
        tool = create_llm_task_tool(api, deps=LlmTaskDeps())
        with pytest.raises(NotImplementedError, match="run_embedded_agent"):
            asyncio.run(
                tool["execute"](
                    "id1",
                    {
                        "prompt": "do it",
                        "provider": "openai",
                        "model": "gpt-5.4",
                    },
                )
            )

    def test_execute_returns_parsed_json(self) -> None:
        capture: dict = {}
        api = _make_api()
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent(capture=capture)),
        )
        result = asyncio.run(
            tool["execute"](
                "id1",
                {
                    "prompt": "compute it",
                    "provider": "openai",
                    "model": "gpt-5.4",
                },
            )
        )
        assert result["details"]["json"] == {"answer": 42}
        # The full_prompt was passed through to the
        # embedded agent.
        sent_prompt = capture["prompt"]
        assert "TASK:" in sent_prompt
        assert "compute it" in sent_prompt
        assert "INPUT_JSON:" in sent_prompt

    def test_execute_strips_code_fences(self) -> None:
        api = _make_api()
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(
                run_embedded_agent=_fake_run_agent(
                    result={
                        "payloads": [
                            {
                                "text": '```json\n{"answer": 42}\n```',
                                "isError": False,
                            }
                        ]
                    }
                )
            ),
        )
        result = asyncio.run(
            tool["execute"](
                "id1",
                {
                    "prompt": "do it",
                    "provider": "openai",
                    "model": "gpt-5.4",
                },
            )
        )
        assert result["details"]["json"] == {"answer": 42}

    def test_execute_raises_on_invalid_json(self) -> None:
        api = _make_api()
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(
                run_embedded_agent=_fake_run_agent(
                    result={"payloads": [{"text": "not valid json", "isError": False}]}
                )
            ),
        )
        with pytest.raises(RuntimeError, match="invalid JSON"):
            asyncio.run(
                tool["execute"](
                    "id1",
                    {
                        "prompt": "do it",
                        "provider": "openai",
                        "model": "gpt-5.4",
                    },
                )
            )

    def test_execute_raises_on_empty_output(self) -> None:
        api = _make_api()
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent(result={"payloads": []})),
        )
        with pytest.raises(RuntimeError, match="empty output"):
            asyncio.run(
                tool["execute"](
                    "id1",
                    {
                        "prompt": "do it",
                        "provider": "openai",
                        "model": "gpt-5.4",
                    },
                )
            )

    def test_execute_rejects_model_not_in_allowed_list(self) -> None:
        api = _make_api(plugin_config={"allowedModels": ["openai/gpt-5.4"]})
        tool = create_llm_task_tool(api, deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent()))
        with pytest.raises(RuntimeError, match="not allowed"):
            asyncio.run(
                tool["execute"](
                    "id1",
                    {
                        "prompt": "do it",
                        "provider": "openai",
                        "model": "gpt-3.5-turbo",
                    },
                )
            )

    def test_execute_accepts_model_in_allowed_list(self) -> None:
        api = _make_api(plugin_config={"allowedModels": ["openai/gpt-5.4"]})
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(
                run_embedded_agent=_fake_run_agent(
                    result={"payloads": [{"text": '{"ok": true}', "isError": False}]}
                )
            ),
        )
        result = asyncio.run(
            tool["execute"](
                "id1",
                {
                    "prompt": "do it",
                    "provider": "openai",
                    "model": "gpt-5.4",
                },
            )
        )
        assert result["details"]["json"] == {"ok": True}

    def test_execute_resolves_provider_model_from_plugin_config(self) -> None:
        capture: dict = {}
        api = _make_api(
            plugin_config={
                "defaultProvider": "openai",
                "defaultModel": "gpt-5.4",
            }
        )
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent(capture=capture)),
        )
        asyncio.run(
            tool["execute"](
                "id1",
                {"prompt": "do it"},
            )
        )
        assert capture["provider"] == "openai"
        assert capture["model"] == "gpt-5.4"

    def test_execute_resolves_model_from_primary_when_plugin_config_missing(
        self,
    ) -> None:
        capture: dict = {}
        api = _make_api(config={"agents": {"defaults": {"model": "anthropic/claude-sonnet-4-6"}}})
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent(capture=capture)),
        )
        asyncio.run(
            tool["execute"](
                "id1",
                {"prompt": "do it"},
            )
        )
        assert capture["provider"] == "anthropic"
        assert capture["model"] == "claude-sonnet-4-6"

    def test_execute_raises_when_provider_model_unresolved(self) -> None:
        api = _make_api()
        tool = create_llm_task_tool(api, deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent()))
        with pytest.raises(RuntimeError, match="could not be resolved"):
            asyncio.run(
                tool["execute"](
                    "id1",
                    {"prompt": "do it"},  # no provider, no model
                )
            )

    def test_execute_passes_timeout_from_params(self) -> None:
        capture: dict = {}
        api = _make_api()
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent(capture=capture)),
        )
        asyncio.run(
            tool["execute"](
                "id1",
                {
                    "prompt": "do it",
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "timeoutMs": 60_000,
                },
            )
        )
        assert capture["timeoutMs"] == 60_000

    def test_execute_falls_back_to_default_timeout(self) -> None:
        capture: dict = {}
        api = _make_api()
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent(capture=capture)),
        )
        asyncio.run(
            tool["execute"](
                "id1",
                {
                    "prompt": "do it",
                    "provider": "openai",
                    "model": "gpt-5.4",
                },
            )
        )
        assert capture["timeoutMs"] == 30_000

    def test_execute_passes_disable_tools_true(self) -> None:
        capture: dict = {}
        api = _make_api()
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent(capture=capture)),
        )
        asyncio.run(
            tool["execute"](
                "id1",
                {
                    "prompt": "do it",
                    "provider": "openai",
                    "model": "gpt-5.4",
                },
            )
        )
        assert capture["disableTools"] is True

    def test_execute_passes_stream_params(self) -> None:
        capture: dict = {}
        api = _make_api()
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent(capture=capture)),
        )
        asyncio.run(
            tool["execute"](
                "id1",
                {
                    "prompt": "do it",
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "temperature": 0.3,
                    "maxTokens": 1024,
                },
            )
        )
        assert capture["streamParams"]["temperature"] == 0.3
        assert capture["streamParams"]["maxTokens"] == 1024

    def test_execute_passes_input_as_serialized_json(self) -> None:
        capture: dict = {}
        api = _make_api()
        tool = create_llm_task_tool(
            api,
            deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent(capture=capture)),
        )
        asyncio.run(
            tool["execute"](
                "id1",
                {
                    "prompt": "do it",
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "input": {"a": 1, "b": [1, 2]},
                },
            )
        )
        sent_prompt = capture["prompt"]
        # The JSON-serialized input should appear in the
        # prompt.
        assert '"a": 1' in sent_prompt
        assert '"b"' in sent_prompt


class TestThinkingPolicyHostWiring:
    def test_thinking_low_rejected_without_host_policy(self) -> None:
        from jarvis_sdk.api import (  # noqa: E402
            set_host_thinking_policy_resolver,
        )

        set_host_thinking_policy_resolver(None)
        api = _make_api()
        tool = create_llm_task_tool(api, deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent()))
        with pytest.raises(RuntimeError, match="not supported"):
            asyncio.run(
                tool["execute"](
                    "id1",
                    {
                        "prompt": "do it",
                        "provider": "openai",
                        "model": "gpt-5.6-sol",
                        "thinking": "low",
                    },
                )
            )

    def test_thinking_low_accepted_with_host_policy(self) -> None:
        from jarvis_sdk.api import (  # noqa: E402
            set_host_thinking_policy_resolver,
        )
        from src.plugins.provider_thinking import (  # noqa: E402
            resolve_host_thinking_policy,
        )

        set_host_thinking_policy_resolver(resolve_host_thinking_policy)
        try:
            capture: dict = {}
            api = _make_api()
            tool = create_llm_task_tool(
                api,
                deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent(capture=capture)),
            )
            asyncio.run(
                tool["execute"](
                    "id1",
                    {
                        "prompt": "do it",
                        "provider": "openai",
                        "model": "gpt-5.6-sol",
                        "thinking": "low",
                    },
                )
            )
            assert capture["thinkLevel"] == "low"
        finally:
            set_host_thinking_policy_resolver(None)

    def test_fail_closed_runtime_override_reaches_runner(self) -> None:
        from jarvis_sdk.api import (  # noqa: E402
            set_host_effective_agent_runtime_resolver,
        )
        from src.agents.harness.selection import (  # noqa: E402
            resolve_host_effective_agent_runtime,
        )

        set_host_effective_agent_runtime_resolver(resolve_host_effective_agent_runtime)
        try:
            capture: dict = {}
            api = _make_api(
                config={
                    "models": {"providers": {"openai": {"agentRuntime": {"id": "codex"}}}},
                }
            )
            tool = create_llm_task_tool(
                api,
                deps=LlmTaskDeps(run_embedded_agent=_fake_run_agent(capture=capture)),
            )
            asyncio.run(
                tool["execute"](
                    "id1",
                    {"prompt": "do it", "provider": "openai", "model": "gpt-5.6-sol"},
                )
            )
            # Fail-closed requirement propagates instead of vanishing to None.
            assert capture["agentHarnessRuntimeOverride"] == "codex"
        finally:
            set_host_effective_agent_runtime_resolver(None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
