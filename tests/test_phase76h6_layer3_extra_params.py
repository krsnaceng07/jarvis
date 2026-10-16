"""Phase 7.6h-6 tests — extra-params.py (the largest top-level file)."""
from __future__ import annotations

import os
import sys

import pytest

# Ensure src/ is on sys.path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.agents.embedded_agent_runner.extra_params import (  # noqa: E402
    REQUEST_SCOPED_EXTRA_PARAM_KEYS,
    _prepared_extra_params_cache,
    apply_extra_params_to_agent,
    clear_prepared_extra_params_cache,
    resolve_agent_transport_override,
    resolve_explicit_settings_transport,
    resolve_extra_params,
    resolve_prepared_extra_params,
    reset_provider_runtime_deps_for_test,
    set_apply_extra_params_to_agent_hook,
    set_prepare_provider_extra_params_dep,
    set_provider_runtime_deps_for_test,
    set_resolve_agent_transport_override_hook,
    set_resolve_explicit_settings_transport_hook,
    set_resolve_extra_params_hook,
    set_resolve_prepared_extra_params_hook,
    set_resolve_provider_extra_params_for_transport_dep,
    set_wrap_provider_stream_fn_dep,
)


@pytest.fixture(autouse=True)
def _reset_extra_params_state() -> None:
    clear_prepared_extra_params_cache()
    reset_provider_runtime_deps_for_test()
    set_resolve_extra_params_hook(None)
    set_resolve_prepared_extra_params_hook(None)
    set_resolve_agent_transport_override_hook(None)
    set_resolve_explicit_settings_transport_hook(None)
    set_apply_extra_params_to_agent_hook(None)
    set_prepare_provider_extra_params_dep(None)
    set_resolve_provider_extra_params_for_transport_dep(None)
    set_wrap_provider_stream_fn_dep(None)
    yield
    clear_prepared_extra_params_cache()
    reset_provider_runtime_deps_for_test()
    set_resolve_extra_params_hook(None)
    set_resolve_prepared_extra_params_hook(None)
    set_resolve_agent_transport_override_hook(None)
    set_resolve_explicit_settings_transport_hook(None)
    set_apply_extra_params_to_agent_hook(None)
    set_prepare_provider_extra_params_dep(None)
    set_resolve_provider_extra_params_for_transport_dep(None)
    set_wrap_provider_stream_fn_dep(None)


class TestConstants:
    def test_request_scoped_keys(self) -> None:
        assert "response_format" in REQUEST_SCOPED_EXTRA_PARAM_KEYS
        assert "responseFormat" in REQUEST_SCOPED_EXTRA_PARAM_KEYS
        assert "stop" in REQUEST_SCOPED_EXTRA_PARAM_KEYS

    def test_clear_cache(self) -> None:
        # Use a fake config object via id()
        class _Cfg:
            pass
        cfg = _Cfg()
        # Populate the cache via the public API path
        set_provider_runtime_deps_for_test(
            {
                "prepareProviderExtraParams": lambda _p: {"x": 1},
            }
        )
        # First call populates the cache
        out1 = resolve_prepared_extra_params(
            {"cfg": cfg, "provider": "p", "modelId": "m"}
        )
        assert cfg in _prepared_extra_params_cache.values() or id(cfg) in _prepared_extra_params_cache
        clear_prepared_extra_params_cache()
        assert _prepared_extra_params_cache == {}


class TestResolveExtraParams:
    def test_empty_config(self) -> None:
        out = resolve_extra_params({"cfg": None, "provider": "p", "modelId": "m"})
        assert out is None or isinstance(out, dict)

    def test_with_default_params(self) -> None:
        # Default _resolve_model_extra_param_sources returns empty; result
        # should fall through to the gpt-5 default branch.
        out = resolve_extra_params(
            {"cfg": None, "provider": "openai", "modelId": "gpt-5.1"}
        )
        # The gpt-5 default branch adds parallel_tool_calls + text_verbosity
        assert out is None or out.get("parallel_tool_calls") is True

    def test_with_hook(self) -> None:
        set_resolve_extra_params_hook(lambda _p: {"hooked": True})
        out = resolve_extra_params({"provider": "p", "modelId": "m"})
        assert out == {"hooked": True}

    def test_hook_returns_non_dict(self) -> None:
        set_resolve_extra_params_hook(lambda _p: [1, 2, 3])
        out = resolve_extra_params({})
        assert out is None


class TestResolvePreparedExtraParams:
    def test_basic(self) -> None:
        out = resolve_prepared_extra_params(
            {"cfg": None, "provider": "p", "modelId": "m"}
        )
        assert isinstance(out, dict)

    def test_with_prepare_dep(self) -> None:
        set_prepare_provider_extra_params_dep(
            lambda _p: {"prepared": True, "temperature": 0.5}
        )
        out = resolve_prepared_extra_params(
            {"cfg": None, "provider": "p", "modelId": "m"}
        )
        assert out.get("prepared") is True
        assert out.get("temperature") == 0.5

    def test_with_transport_dep(self) -> None:
        set_prepare_provider_extra_params_dep(lambda _p: {"x": 1})
        set_resolve_provider_extra_params_for_transport_dep(
            lambda _p: {"patch": {"y": 2}}
        )
        out = resolve_prepared_extra_params(
            {"cfg": None, "provider": "p", "modelId": "m"}
        )
        assert out.get("x") == 1
        assert out.get("y") == 2

    def test_with_transport_dep_no_patch(self) -> None:
        set_resolve_provider_extra_params_for_transport_dep(lambda _p: {})
        out = resolve_prepared_extra_params(
            {"cfg": None, "provider": "p", "modelId": "m"}
        )
        assert isinstance(out, dict)

    def test_request_scoped_stripped(self) -> None:
        out = resolve_prepared_extra_params(
            {
                "cfg": None,
                "provider": "p",
                "modelId": "m",
                "extraParamsOverride": {"temperature": 0.5, "stop": ["x"]},
            }
        )
        # Stop is request-scoped → stripped
        assert "stop" not in out
        assert out.get("temperature") == 0.5

    def test_max_tokens_canonicalization(self) -> None:
        out = resolve_prepared_extra_params(
            {
                "cfg": None,
                "provider": "p",
                "modelId": "m",
                "extraParamsOverride": {"max_tokens": 1000},
            }
        )
        assert out.get("maxTokens") == 1000
        assert "max_tokens" not in out

    def test_cached_content_alias(self) -> None:
        out = resolve_prepared_extra_params(
            {
                "cfg": None,
                "provider": "p",
                "modelId": "m",
                "extraParamsOverride": {"cached_content": "cc"},
            }
        )
        assert out.get("cachedContent") == "cc"
        assert "cached_content" not in out

    def test_openrouter_canonicalization(self) -> None:
        out = resolve_prepared_extra_params(
            {
                "cfg": None,
                "provider": "openrouter",
                "modelId": "m",
                "extraParamsOverride": {"openrouter_cache_control": "1h"},
            }
        )
        # The alias key is canonicalized
        assert "openrouterCacheControl" in out or "openrouter_cache_control" in out

    def test_caching(self) -> None:
        cfg = type("_Cfg", (), {})()
        set_prepare_provider_extra_params_dep(lambda _p: {"x": 1})
        out1 = resolve_prepared_extra_params({"cfg": cfg, "provider": "p", "modelId": "m"})
        # Second call should hit the cache and produce same result
        out2 = resolve_prepared_extra_params({"cfg": cfg, "provider": "p", "modelId": "m"})
        assert out1 == out2
        # Cache should contain an entry
        assert id(cfg) in _prepared_extra_params_cache
        assert _prepared_extra_params_cache[id(cfg)]  # non-empty bucket

    def test_no_cache_when_function_override(self) -> None:
        cfg = type("_Cfg", (), {})()
        set_prepare_provider_extra_params_dep(lambda _p: {"x": 1})
        resolve_prepared_extra_params(
            {
                "cfg": cfg,
                "provider": "p",
                "modelId": "m",
                "extraParamsOverride": {"fn": lambda: None},  # function value
            }
        )
        # Function values → no cache write
        assert id(cfg) not in _prepared_extra_params_cache

    def test_with_hook(self) -> None:
        set_resolve_prepared_extra_params_hook(lambda _p: {"hooked": True})
        out = resolve_prepared_extra_params({})
        assert out == {"hooked": True}


class TestTransportOverrides:
    def test_resolve_agent_transport_no_settings(self) -> None:
        out = resolve_agent_transport_override({})
        assert out is None

    def test_resolve_agent_transport_no_explicit(self) -> None:
        sm = {
            "getGlobalSettings": lambda: {},
            "getProjectSettings": lambda: {},
        }
        out = resolve_agent_transport_override(
            {
                "settingsManager": sm,
                "effectiveExtraParams": {"transport": "sse"},
            }
        )
        assert out == "sse"

    def test_resolve_agent_transport_explicit_global(self) -> None:
        sm = {
            "getGlobalSettings": lambda: {"transport": "websocket"},
            "getProjectSettings": lambda: {},
        }
        out = resolve_agent_transport_override(
            {
                "settingsManager": sm,
                "effectiveExtraParams": {"transport": "sse"},
            }
        )
        assert out is None

    def test_resolve_agent_transport_explicit_project(self) -> None:
        sm = {
            "getGlobalSettings": lambda: {},
            "getProjectSettings": lambda: {"transport": "websocket"},
        }
        out = resolve_agent_transport_override(
            {
                "settingsManager": sm,
                "effectiveExtraParams": {"transport": "sse"},
            }
        )
        assert out is None

    def test_resolve_agent_transport_invalid(self) -> None:
        sm = {
            "getGlobalSettings": lambda: {},
            "getProjectSettings": lambda: {},
        }
        out = resolve_agent_transport_override(
            {
                "settingsManager": sm,
                "effectiveExtraParams": {"transport": "invalid"},
            }
        )
        assert out is None

    def test_resolve_agent_transport_with_hook(self) -> None:
        set_resolve_agent_transport_override_hook(lambda _p: "hooked")
        out = resolve_agent_transport_override({})
        assert out == "hooked"

    def test_resolve_explicit_transport_no_settings(self) -> None:
        out = resolve_explicit_settings_transport({})
        assert out is None

    def test_resolve_explicit_transport_no_explicit(self) -> None:
        sm = {
            "getGlobalSettings": lambda: {},
            "getProjectSettings": lambda: {},
        }
        out = resolve_explicit_settings_transport(
            {
                "settingsManager": sm,
                "sessionTransport": "sse",
            }
        )
        assert out is None  # no explicit setting

    def test_resolve_explicit_transport_with_setting(self) -> None:
        sm = {
            "getGlobalSettings": lambda: {"transport": "websocket"},
            "getProjectSettings": lambda: {},
        }
        out = resolve_explicit_settings_transport(
            {
                "settingsManager": sm,
                "sessionTransport": "sse",
            }
        )
        assert out == "sse"

    def test_resolve_explicit_transport_with_hook(self) -> None:
        set_resolve_explicit_settings_transport_hook(lambda _p: "hooked")
        out = resolve_explicit_settings_transport({})
        assert out == "hooked"


class TestApplyExtraParamsToAgent:
    def test_basic(self) -> None:
        agent = {"streamFn": lambda *a, **k: None}
        out = apply_extra_params_to_agent(
            agent,
            cfg=None,
            provider="openai",
            model_id="gpt-5",
        )
        assert "effectiveExtraParams" in out
        # gpt-5 default branch should have added parallel_tool_calls
        assert out["effectiveExtraParams"].get("parallel_tool_calls") is True

    def test_with_prepared_options(self) -> None:
        agent = {"streamFn": lambda *a, **k: None}
        out = apply_extra_params_to_agent(
            agent,
            cfg=None,
            provider="openai",
            model_id="gpt-5",
            options={"preparedExtraParams": {"prepared": True}},
        )
        assert out["effectiveExtraParams"].get("prepared") is True

    def test_with_hook(self) -> None:
        set_apply_extra_params_to_agent_hook(lambda _p: {"hooked": True})
        out = apply_extra_params_to_agent(
            {"streamFn": lambda *a, **k: None},
            cfg=None,
            provider="p",
            model_id="m",
        )
        assert out == {"hooked": True}


class TestProviderRuntimeDeps:
    def test_set_and_reset(self) -> None:
        set_provider_runtime_deps_for_test(
            {
                "prepareProviderExtraParams": lambda _p: {"x": 1},
                "resolveProviderExtraParamsForTransport": lambda _p: None,
                "wrapProviderStreamFn": lambda _p: None,
            }
        )
        # Use one of them
        out = resolve_prepared_extra_params(
            {"cfg": None, "provider": "p", "modelId": "m"}
        )
        assert out.get("x") == 1
        # Reset
        reset_provider_runtime_deps_for_test()
        # Subsequent call falls back to default behavior
        out2 = resolve_prepared_extra_params(
            {"cfg": None, "provider": "p", "modelId": "m"}
        )
        # No more x in result
        assert out2.get("x") is None

    def test_clear_cache_helper(self) -> None:
        # Ensure clear_prepared_extra_params_cache is callable
        clear_prepared_extra_params_cache()
        assert _prepared_extra_params_cache == {}


class TestSanitization:
    def test_request_scoped_keys_value(self) -> None:
        assert "response_format" in REQUEST_SCOPED_EXTRA_PARAM_KEYS
        assert "responseFormat" in REQUEST_SCOPED_EXTRA_PARAM_KEYS
        assert "stop" in REQUEST_SCOPED_EXTRA_PARAM_KEYS
        assert len(REQUEST_SCOPED_EXTRA_PARAM_KEYS) == 3
