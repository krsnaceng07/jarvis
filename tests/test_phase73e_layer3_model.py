"""Phase 7.3e tests — model (main entry)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.model import (
    create_empty_agent_discovery_stores,
    resolve_model,
    resolve_model_async,
    resolve_model_with_registry,
    set_build_unknown_model_error_hook,
    set_create_empty_discovery_stores_hook,
    set_discover_auth_storage_hook,
    set_discover_cached_agent_stores_hook,
    set_discover_models_hook,
    set_normalize_provider_model_ref_hook,
    set_resolve_default_agent_dir_hook,
    set_resolve_model_workspace_dir_hook,
    set_resolve_model_with_prepared_registry_hook,
    set_resolve_runtime_hooks_hook,
)


def _install_default_hooks() -> None:
    set_create_empty_discovery_stores_hook(
        lambda: {"authStorage": None, "modelRegistry": None}
    )
    set_normalize_provider_model_ref_hook(
        lambda **kwargs: {
            "provider": kwargs.get("provider", ""),
            "model": kwargs.get("modelId", ""),
        }
    )
    set_resolve_model_with_prepared_registry_hook(lambda **_: None)
    set_build_unknown_model_error_hook(
        lambda **kwargs: f"unknown model: {kwargs.get('provider', '')}/{kwargs.get('modelId', '')}"
    )
    set_discover_cached_agent_stores_hook(
        lambda **_: {"authStorage": None, "modelRegistry": None}
    )
    set_discover_auth_storage_hook(lambda **_: None)
    set_discover_models_hook(lambda **_: None)
    set_resolve_default_agent_dir_hook(lambda _cfg: "")
    set_resolve_model_workspace_dir_hook(lambda cfg, fallback: fallback)
    set_resolve_runtime_hooks_hook(lambda **_: None)


# ============================================================================
# create_empty_agent_discovery_stores
# ============================================================================


class TestCreateEmptyAgentDiscoveryStores:
    def setup_method(self) -> None:
        _install_default_hooks()

    def test_default_returns_none_pair(self) -> None:
        result = create_empty_agent_discovery_stores()
        assert "authStorage" in result
        assert "modelRegistry" in result

    def test_custom_hook(self) -> None:
        def custom() -> Dict[str, Any]:
            return {
                "authStorage": {"id": "auth"},
                "modelRegistry": {"models": []},
            }

        set_create_empty_discovery_stores_hook(custom)
        try:
            result = create_empty_agent_discovery_stores()
            assert result["authStorage"] == {"id": "auth"}
            assert result["modelRegistry"] == {"models": []}
        finally:
            set_create_empty_discovery_stores_hook(
                lambda: {"authStorage": None, "modelRegistry": None}
            )


# ============================================================================
# resolve_model_with_registry
# ============================================================================


class TestResolveModelWithRegistry:
    def setup_method(self) -> None:
        _install_default_hooks()

    def test_returns_none_when_no_match(self) -> None:
        result = resolve_model_with_registry(
            {
                "provider": "openai",
                "modelId": "gpt-5.4",
                "agentDir": "/tmp/agent",
                "cfg": {},
            }
        )
        assert result is None

    def test_returns_resolved_model(self) -> None:
        def resolve(**kwargs: Any) -> Dict[str, Any]:
            return {"id": kwargs.get("modelId"), "provider": kwargs.get("provider")}

        set_resolve_model_with_prepared_registry_hook(resolve)
        try:
            result = resolve_model_with_registry(
                {
                    "provider": "openai",
                    "modelId": "gpt-5.4",
                    "agentDir": "/tmp/agent",
                }
            )
            assert result == {"id": "gpt-5.4", "provider": "openai"}
        finally:
            set_resolve_model_with_prepared_registry_hook(lambda **_: None)

    def test_normalizes_provider_model_ref(self) -> None:
        def normalize(**kwargs: Any) -> Dict[str, str]:
            return {
                "provider": "normalized-provider",
                "model": "normalized-model",
            }

        captured: List[Dict[str, Any]] = []

        def resolve(**kwargs: Any) -> Dict[str, Any]:
            captured.append(kwargs)
            return {"id": kwargs.get("modelId")}

        set_normalize_provider_model_ref_hook(normalize)
        set_resolve_model_with_prepared_registry_hook(resolve)
        try:
            resolve_model_with_registry(
                {
                    "provider": "openai",
                    "modelId": "gpt-5.4",
                }
            )
            assert captured[0]["provider"] == "normalized-provider"
            assert captured[0]["modelId"] == "normalized-model"
        finally:
            set_normalize_provider_model_ref_hook(
                lambda **kwargs: {
                    "provider": kwargs.get("provider", ""),
                    "model": kwargs.get("modelId", ""),
                }
            )
            set_resolve_model_with_prepared_registry_hook(lambda **_: None)

    def test_workspace_dir_fallback(self) -> None:
        captured: List[Dict[str, Any]] = []

        def resolve(**kwargs: Any) -> Dict[str, Any]:
            captured.append(kwargs)
            return None

        set_resolve_model_with_prepared_registry_hook(resolve)
        try:
            resolve_model_with_registry(
                {
                    "provider": "openai",
                    "modelId": "gpt-5.4",
                    "cfg": {
                        "agents": {"defaults": {"workspace": "/tmp/ws"}},
                    },
                }
            )
            assert captured[0]["workspaceDir"] == "/tmp/ws"
        finally:
            set_resolve_model_with_prepared_registry_hook(lambda **_: None)


# ============================================================================
# resolve_model
# ============================================================================


class TestResolveModel:
    def setup_method(self) -> None:
        _install_default_hooks()

    def test_no_match_returns_error(self) -> None:
        result = resolve_model("openai", "gpt-5.4")
        assert "error" in result
        assert "model" not in result
        assert "openai" in result["error"]

    def test_match_returns_model(self) -> None:
        def resolve(**kwargs: Any) -> Dict[str, Any]:
            return {"id": kwargs.get("modelId"), "provider": kwargs.get("provider")}

        set_resolve_model_with_prepared_registry_hook(resolve)
        try:
            result = resolve_model("openai", "gpt-5.4")
            assert "model" in result
            assert result["model"] == {"id": "gpt-5.4", "provider": "openai"}
        finally:
            set_resolve_model_with_prepared_registry_hook(lambda **_: None)

    def test_uses_caller_supplied_auth_storage(self) -> None:
        called: List[bool] = []

        def cached(**kwargs: Any) -> Dict[str, Any]:
            called.append(True)
            return {"authStorage": None, "modelRegistry": None}

        set_discover_cached_agent_stores_hook(cached)
        try:
            result = resolve_model(
                "openai", "gpt-5.4", options={"authStorage": {"id": "auth"}}
            )
            assert "model" not in result
            # Cache not consulted when authStorage is supplied.
            assert called == []
        finally:
            set_discover_cached_agent_stores_hook(
                lambda **_: {"authStorage": None, "modelRegistry": None}
            )

    def test_uses_caller_supplied_model_registry(self) -> None:
        called: List[bool] = []

        def cached(**kwargs: Any) -> Dict[str, Any]:
            called.append(True)
            return {"authStorage": None, "modelRegistry": None}

        set_discover_cached_agent_stores_hook(cached)
        try:
            result = resolve_model(
                "openai",
                "gpt-5.4",
                options={"modelRegistry": {"id": "registry"}},
            )
            assert "model" not in result
            assert called == []
        finally:
            set_discover_cached_agent_stores_hook(
                lambda **_: {"authStorage": None, "modelRegistry": None}
            )

    def test_cached_discovery_used_when_no_overrides(self) -> None:
        captured: List[Dict[str, Any]] = []

        def cached(**kwargs: Any) -> Dict[str, Any]:
            captured.append(kwargs)
            return {
                "authStorage": {"id": "cached-auth"},
                "modelRegistry": {"id": "cached-registry"},
            }

        set_discover_cached_agent_stores_hook(cached)
        try:
            result = resolve_model(
                "openai",
                "gpt-5.4",
                agent_dir="/tmp/agent",
                cfg={"x": 1},
            )
            # Cached stores should have been consulted.
            assert len(captured) == 1
            assert captured[0]["agentDir"] == "/tmp/agent"
            # The auth storage from cache should appear in the result.
            assert result["authStorage"] == {"id": "cached-auth"}
            assert result["modelRegistry"] == {"id": "cached-registry"}
        finally:
            set_discover_cached_agent_stores_hook(
                lambda **_: {"authStorage": None, "modelRegistry": None}
            )

    def test_default_agent_dir_when_omitted(self) -> None:
        captured: List[Dict[str, Any]] = []

        def cached(**kwargs: Any) -> Dict[str, Any]:
            captured.append(kwargs)
            return {"authStorage": None, "modelRegistry": None}

        set_discover_cached_agent_stores_hook(cached)
        set_resolve_default_agent_dir_hook(lambda _cfg: "/tmp/default-agent")
        try:
            resolve_model("openai", "gpt-5.4")
            assert captured[0]["agentDir"] == "/tmp/default-agent"
        finally:
            set_discover_cached_agent_stores_hook(
                lambda **_: {"authStorage": None, "modelRegistry": None}
            )
            set_resolve_default_agent_dir_hook(lambda _cfg: "")

    def test_custom_unknown_model_error(self) -> None:
        def custom_error(**kwargs: Any) -> str:
            return f"no model named {kwargs.get('modelId', '')}"

        set_build_unknown_model_error_hook(custom_error)
        try:
            result = resolve_model("openai", "gpt-5.4")
            assert result["error"] == "no model named gpt-5.4"
        finally:
            set_build_unknown_model_error_hook(
                lambda **kwargs: f"unknown model: {kwargs.get('provider', '')}/{kwargs.get('modelId', '')}"
            )


# ============================================================================
# resolve_model_async
# ============================================================================


class TestResolveModelAsync:
    def setup_method(self) -> None:
        _install_default_hooks()

    @pytest.mark.asyncio
    async def test_no_match(self) -> None:
        result = await resolve_model_async("openai", "gpt-5.4")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_match(self) -> None:
        def resolve(**kwargs: Any) -> Dict[str, Any]:
            return {"id": kwargs.get("modelId")}

        set_resolve_model_with_prepared_registry_hook(resolve)
        try:
            result = await resolve_model_async("openai", "gpt-5.4")
            assert "model" in result
            assert result["model"] == {"id": "gpt-5.4"}
        finally:
            set_resolve_model_with_prepared_registry_hook(lambda **_: None)
