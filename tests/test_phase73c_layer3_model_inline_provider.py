"""Phase 7.3c tests — model.inline-provider."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.model_inline_provider import (
    SUPPORTED_TRANSPORT_APIS,
    build_inline_provider_models,
    normalize_resolved_transport_api,
    resolve_provider_model_input,
    sanitize_model_headers,
    set_attach_model_provider_local_service_hook,
    set_attach_model_provider_request_transport_hook,
    set_is_secret_ref_header_value_marker_hook,
    set_normalize_google_api_base_url_hook,
    set_resolve_provider_request_config_hook,
    set_sanitize_configured_model_provider_request_hook,
)


# ============================================================================
# normalize_resolved_transport_api
# ============================================================================


class TestNormalizeResolvedTransportApi:
    def test_supported_api(self) -> None:
        assert normalize_resolved_transport_api("openai-responses") == "openai-responses"
        assert (
            normalize_resolved_transport_api("google-generative-ai")
            == "google-generative-ai"
        )

    def test_unsupported_api(self) -> None:
        assert normalize_resolved_transport_api("unknown-api") is None

    def test_non_string(self) -> None:
        assert normalize_resolved_transport_api(None) is None
        assert normalize_resolved_transport_api(42) is None
        assert normalize_resolved_transport_api(["openai-responses"]) is None

    def test_all_supported_apis(self) -> None:
        for api in SUPPORTED_TRANSPORT_APIS:
            assert normalize_resolved_transport_api(api) == api


# ============================================================================
# sanitize_model_headers
# ============================================================================


class TestSanitizeModelHeaders:
    def test_basic(self) -> None:
        result = sanitize_model_headers(
            {"Authorization": "Bearer xyz", "X-Custom": "v"}
        )
        assert result == {"Authorization": "Bearer xyz", "X-Custom": "v"}

    def test_non_string_value_skipped(self) -> None:
        result = sanitize_model_headers({"X-Numeric": 42, "X-Valid": "v"})
        assert result == {"X-Valid": "v"}

    def test_empty_when_all_filtered(self) -> None:
        result = sanitize_model_headers({"X-Numeric": 42})
        assert result is None

    def test_non_dict(self) -> None:
        assert sanitize_model_headers(None) is None
        assert sanitize_model_headers([]) is None
        assert sanitize_model_headers("string") is None

    def test_strip_secret_ref_markers(self) -> None:
        set_is_secret_ref_header_value_marker_hook(lambda v: v == "secret://key")
        try:
            result = sanitize_model_headers(
                {"X-Secret": "secret://key", "X-Valid": "v"},
                strip_secret_ref_markers=True,
            )
            assert result == {"X-Valid": "v"}
        finally:
            set_is_secret_ref_header_value_marker_hook(lambda _v: False)


# ============================================================================
# resolve_provider_model_input
# ============================================================================


class TestResolveProviderModelInput:
    def test_basic_input(self) -> None:
        result = resolve_provider_model_input(
            input=["text", "image"],
        )
        assert result == ["text", "image"]

    def test_filters_unknown(self) -> None:
        result = resolve_provider_model_input(
            input=["text", "audio", "image"],
        )
        assert result == ["text", "image"]

    def test_default_to_text(self) -> None:
        result = resolve_provider_model_input(input=[])
        assert result == ["text"]

    def test_none_input_uses_fallback(self) -> None:
        result = resolve_provider_model_input(
            input=None, fallback_input=["text"]
        )
        assert result == ["text"]

    def test_foundry_legacy_vision(self) -> None:
        result = resolve_provider_model_input(
            provider="microsoft-foundry",
            model_id="gpt-5.4",
            input=["text"],
        )
        assert result == ["text", "image"]

    def test_non_foundry_no_auto_image(self) -> None:
        result = resolve_provider_model_input(
            provider="openai",
            model_id="gpt-5.4",
            input=["text"],
        )
        assert result == ["text"]

    def test_o1_prefix(self) -> None:
        result = resolve_provider_model_input(
            provider="microsoft-foundry",
            model_id="o1-preview",
            input=["text"],
        )
        assert result == ["text", "image"]

    def test_computer_use_preview(self) -> None:
        result = resolve_provider_model_input(
            provider="microsoft-foundry",
            model_id="computer-use-preview",
            input=["text"],
        )
        assert result == ["text", "image"]

    def test_non_microsoft_foundry_model(self) -> None:
        result = resolve_provider_model_input(
            provider="microsoft-foundry",
            model_id="some-other-model",
            input=["text"],
        )
        assert result == ["text"]


# ============================================================================
# build_inline_provider_models
# ============================================================================


class TestBuildInlineProviderModels:
    def setup_method(self) -> None:
        # Reset to default hooks.
        set_is_secret_ref_header_value_marker_hook(lambda _v: False)
        set_normalize_google_api_base_url_hook(lambda v: v)
        set_resolve_provider_request_config_hook(
            lambda **kwargs: {
                "api": kwargs.get("api"),
                "baseUrl": kwargs.get("baseUrl"),
                "headers": kwargs.get("providerHeaders") or {},
            }
        )
        set_sanitize_configured_model_provider_request_hook(lambda v: v)
        set_attach_model_provider_request_transport_hook(
            lambda m, _r: m
        )
        set_attach_model_provider_local_service_hook(
            lambda m, _l: m
        )

    def test_basic(self) -> None:
        providers = {
            "openai": {
                "baseUrl": "https://api.openai.com/v1",
                "api": "openai-responses",
                "models": [{"id": "gpt-5.4"}],
            }
        }
        result = build_inline_provider_models(providers)
        assert len(result) == 1
        assert result[0]["provider"] == "openai"
        assert result[0]["id"] == "gpt-5.4"
        assert result[0]["baseUrl"] == "https://api.openai.com/v1"
        assert result[0]["api"] == "openai-responses"
        assert result[0]["input"] == ["text"]

    def test_model_api_overrides_provider_api(self) -> None:
        providers = {
            "custom": {
                "api": "openai-responses",
                "models": [
                    {"id": "m1", "api": "anthropic-messages"},
                ],
            }
        }
        result = build_inline_provider_models(providers)
        assert result[0]["api"] == "anthropic-messages"

    def test_context_window_fallback(self) -> None:
        providers = {
            "openai": {
                "contextWindow": 200_000,
                "models": [
                    {"id": "m1", "contextWindow": 100_000},
                    {"id": "m2"},
                ],
            }
        }
        result = build_inline_provider_models(providers)
        assert result[0]["contextWindow"] == 100_000
        assert result[1]["contextWindow"] == 200_000

    def test_blank_provider_id_skipped(self) -> None:
        providers = {
            "": {
                "models": [{"id": "m1"}],
            },
            "  ": {
                "models": [{"id": "m2"}],
            },
        }
        result = build_inline_provider_models(providers)
        assert result == []

    def test_provider_headers_applied(self) -> None:
        providers = {
            "openai": {
                "headers": {"X-Custom": "v"},
                "models": [{"id": "m1"}],
            }
        }
        result = build_inline_provider_models(providers)
        assert result[0]["headers"] == {"X-Custom": "v"}

    def test_secret_ref_markers_stripped(self) -> None:
        set_is_secret_ref_header_value_marker_hook(lambda v: v == "secret://key")
        providers = {
            "openai": {
                "headers": {"X-Secret": "secret://key", "X-OK": "v"},
                "models": [{"id": "m1"}],
            }
        }
        result = build_inline_provider_models(providers)
        assert "X-Secret" not in result[0]["headers"]
        assert result[0]["headers"]["X-OK"] == "v"

    def test_google_api_base_url_normalized(self) -> None:
        def normalize(url: Optional[str]) -> Optional[str]:
            if url is None:
                return None
            return url.rstrip("/") + "/"

        set_normalize_google_api_base_url_hook(normalize)
        providers = {
            "google": {
                "api": "google-generative-ai",
                "baseUrl": "https://generativelanguage.googleapis.com/v1beta",
                "models": [{"id": "gemini-1.5"}],
            }
        }
        result = build_inline_provider_models(providers)
        # The baseUrl is normalized via the hook.
        assert result[0]["baseUrl"] == "https://generativelanguage.googleapis.com/v1beta/"

    def test_attach_request_transport(self) -> None:
        called: List[Dict[str, Any]] = []

        def attach(model: Dict[str, Any], request: Any) -> Dict[str, Any]:
            called.append(model)
            return {**model, "transport": "attached"}

        set_attach_model_provider_request_transport_hook(attach)
        providers = {
            "openai": {
                "models": [{"id": "m1"}],
            }
        }
        result = build_inline_provider_models(providers)
        assert result[0]["transport"] == "attached"
        assert len(called) == 1

    def test_attach_local_service(self) -> None:
        called: List[Any] = []

        def attach(model: Dict[str, Any], local_service: Any) -> Dict[str, Any]:
            called.append(local_service)
            return {**model, "localService": local_service}

        set_attach_model_provider_local_service_hook(attach)
        providers = {
            "openai": {
                "localService": {"port": 8080},
                "models": [{"id": "m1"}],
            }
        }
        result = build_inline_provider_models(providers)
        assert result[0]["localService"] == {"port": 8080}
        assert called == [{"port": 8080}]

    def test_resolve_request_config_hook(self) -> None:
        def resolver(**kwargs: Any) -> Dict[str, Any]:
            return {
                "api": "openai-responses",
                "baseUrl": "https://custom.example.com/v1",
                "headers": {"X-Resolved": "yes"},
            }

        set_resolve_provider_request_config_hook(resolver)
        providers = {
            "openai": {
                "models": [{"id": "m1"}],
            }
        }
        result = build_inline_provider_models(providers)
        assert result[0]["baseUrl"] == "https://custom.example.com/v1"
        assert result[0]["api"] == "openai-responses"
        assert result[0]["headers"] == {"X-Resolved": "yes"}

    def test_multiple_providers(self) -> None:
        providers = {
            "openai": {
                "models": [{"id": "gpt-5.4"}],
            },
            "anthropic": {
                "models": [{"id": "claude-opus-4-6"}],
            },
        }
        result = build_inline_provider_models(providers)
        assert len(result) == 2
        assert result[0]["provider"] == "openai"
        assert result[1]["provider"] == "anthropic"

    def test_non_dict_provider_skipped(self) -> None:
        providers: Dict[str, Any] = {
            "openai": None,
        }
        result = build_inline_provider_models(providers)
        assert result == []

    def test_non_dict_model_skipped(self) -> None:
        providers = {
            "openai": {
                "models": [None, {"id": "m1"}],
            },
        }
        result = build_inline_provider_models(providers)
        assert len(result) == 1
        assert result[0]["id"] == "m1"
