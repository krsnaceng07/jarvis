"""Phase 7.3a tests — small model helpers."""
from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from src.agents.embedded_agent_runner.model_compat import (
    merge_model_compat,
    merge_model_media_input,
    resolve_configured_fallback_reasoning,
    resolve_configured_model_reasoning,
    resolve_merged_configured_model_reasoning,
    set_provider_id_normalizer as set_compat_provider_normalizer,
)
from src.agents.embedded_agent_runner.model_context_tokens import (
    read_agent_model_context_tokens,
)
from src.agents.embedded_agent_runner.model_provider_normalization import (
    normalize_resolved_provider_model,
    set_model_compat_normalizer,
)
from src.agents.embedded_agent_runner.model_static_id import (
    set_provider_id_normalizer as set_static_provider_normalizer,
    set_static_provider_model_id_normalizer,
    static_model_id_matches,
)


# ============================================================================
# read_agent_model_context_tokens
# ============================================================================


class TestReadAgentModelContextTokens:
    def test_returns_value_when_present(self) -> None:
        assert read_agent_model_context_tokens({"contextTokens": 128_000}) == 128_000

    def test_returns_none_when_missing(self) -> None:
        assert read_agent_model_context_tokens({"id": "gpt-5.4"}) is None

    def test_returns_none_when_null_model(self) -> None:
        assert read_agent_model_context_tokens(None) is None

    def test_returns_none_for_non_finite(self) -> None:
        assert read_agent_model_context_tokens({"contextTokens": float("inf")}) is None
        assert read_agent_model_context_tokens({"contextTokens": float("nan")}) is None

    def test_returns_none_for_bool(self) -> None:
        assert read_agent_model_context_tokens({"contextTokens": True}) is None

    def test_returns_int_when_float(self) -> None:
        assert read_agent_model_context_tokens({"contextTokens": 128_000.0}) == 128_000

    def test_supports_object_with_attr(self) -> None:
        class _Model:
            contextTokens = 200_000

        assert read_agent_model_context_tokens(_Model()) == 200_000


# ============================================================================
# static_model_id_matches
# ============================================================================


class TestStaticModelIdMatches:
    def test_basic_match(self) -> None:
        assert (
            static_model_id_matches(
                candidate_id="gpt-5.4",
                provider="openai",
                model_id="gpt-5.4",
            )
            is True
        )

    def test_case_insensitive(self) -> None:
        assert (
            static_model_id_matches(
                candidate_id="GPT-5.4",
                provider="openai",
                model_id="gpt-5.4",
            )
            is True
        )

    def test_mismatch(self) -> None:
        assert (
            static_model_id_matches(
                candidate_id="gpt-5.4",
                provider="openai",
                model_id="gpt-3.5-turbo",
            )
            is False
        )

    def test_row_provider_mismatch(self) -> None:
        assert (
            static_model_id_matches(
                candidate_id="gpt-5.4",
                provider="openai",
                model_id="gpt-5.4",
                row_provider="anthropic",
            )
            is False
        )

    def test_row_provider_match(self) -> None:
        assert (
            static_model_id_matches(
                candidate_id="gpt-5.4",
                provider="openai",
                model_id="gpt-5.4",
                row_provider="openai",
            )
            is True
        )

    def test_custom_normalizers(self) -> None:
        set_static_provider_normalizer(lambda v: v.strip())
        set_static_provider_model_id_normalizer(
            lambda provider, model: f"{provider}:{model}".lower()
        )
        try:
            assert (
                static_model_id_matches(
                    candidate_id="gpt-5.4",
                    provider="openai",
                    model_id="gpt-5.4",
                )
                is True
            )
        finally:
            set_static_provider_normalizer(
                lambda v: (v or "").strip().lower()
            )
            set_static_provider_model_id_normalizer(
                lambda _p, v: (v or "").strip().lower()
            )


# ============================================================================
# merge_model_media_input
# ============================================================================


class TestMergeModelMediaInput:
    def test_no_base(self) -> None:
        override = {"image": {"a": 1}}
        assert merge_model_media_input(None, override) is override

    def test_no_override(self) -> None:
        base = {"image": {"a": 1}}
        assert merge_model_media_input(base, None) is base

    def test_shallow_merge(self) -> None:
        merged = merge_model_media_input(
            {"audio": True},
            {"video": True},
        )
        assert merged == {"audio": True, "video": True}

    def test_image_deep_merged(self) -> None:
        merged = merge_model_media_input(
            {"image": {"a": 1, "b": 2}},
            {"image": {"b": 3, "c": 4}},
        )
        assert merged["image"] == {"a": 1, "b": 3, "c": 4}

    def test_image_omitted_when_neither(self) -> None:
        merged = merge_model_media_input(
            {"audio": True},
            {"video": True},
        )
        assert "image" not in merged


# ============================================================================
# merge_model_compat
# ============================================================================


class TestMergeModelCompat:
    def test_no_base(self) -> None:
        override = {"a": 1}
        assert merge_model_compat(None, override) is override

    def test_no_override(self) -> None:
        base = {"a": 1}
        assert merge_model_compat(base, None) is base

    def test_shallow_merge(self) -> None:
        merged = merge_model_compat(
            {"a": 1, "b": 2},
            {"b": 3, "c": 4},
        )
        assert merged == {"a": 1, "b": 3, "c": 4}


# ============================================================================
# resolve_configured_model_reasoning
# ============================================================================


class TestResolveConfiguredModelReasoning:
    def test_explicit_reasoning(self) -> None:
        assert (
            resolve_configured_model_reasoning(provider="openai", reasoning=True)
            is True
        )
        assert (
            resolve_configured_model_reasoning(provider="openai", reasoning=False)
            is False
        )

    def test_vllm_qwen_thinking_compat(self) -> None:
        assert (
            resolve_configured_model_reasoning(
                provider="vllm", compat={"thinkingFormat": "qwen"}
            )
            is True
        )

    def test_vllm_qwen_chat_template(self) -> None:
        assert (
            resolve_configured_model_reasoning(
                provider="vllm", compat={"thinkingFormat": "qwen-chat-template"}
            )
            is True
        )

    def test_vllm_other_thinking_format(self) -> None:
        assert (
            resolve_configured_model_reasoning(
                provider="vllm", compat={"thinkingFormat": "openai"}
            )
            is None
        )

    def test_non_vllm_provider(self) -> None:
        assert (
            resolve_configured_model_reasoning(
                provider="openai", compat={"thinkingFormat": "qwen"}
            )
            is None
        )

    def test_fallback_returns_bool(self) -> None:
        assert (
            resolve_configured_fallback_reasoning(provider="openai") is False
        )
        assert (
            resolve_configured_fallback_reasoning(
                provider="vllm", compat={"thinkingFormat": "qwen"}
            )
            is True
        )


class TestResolveMergedConfiguredModelReasoning:
    def test_configured_reasoning_takes_precedence(self) -> None:
        assert (
            resolve_merged_configured_model_reasoning(
                provider="vllm",
                configured_compat={"thinkingFormat": "qwen"},
                configured_reasoning=False,
            )
            is False
        )

    def test_vllm_qwen_from_configured(self) -> None:
        assert (
            resolve_merged_configured_model_reasoning(
                provider="vllm",
                configured_compat={"thinkingFormat": "qwen"},
            )
            is True
        )

    def test_falls_back_to_resolved(self) -> None:
        assert (
            resolve_merged_configured_model_reasoning(
                provider="openai",
                resolved_compat={"thinkingFormat": "openai"},
                discovered_reasoning=True,
            )
            is True
        )

    def test_defaults_to_false(self) -> None:
        assert (
            resolve_merged_configured_model_reasoning(provider="openai") is False
        )


# ============================================================================
# normalize_resolved_provider_model
# ============================================================================


class TestNormalizeResolvedProviderModel:
    def test_default_no_op(self) -> None:
        model = {"id": "gpt-5.4"}
        assert normalize_resolved_provider_model(provider="openai", model=model) is model

    def test_custom_normalizer(self) -> None:
        called: list[Any] = []

        def normalizer(model: Any) -> Dict[str, Any]:
            called.append(model)
            return {**model, "normalized": True}

        set_model_compat_normalizer(normalizer)
        try:
            result = normalize_resolved_provider_model(
                provider="openai", model={"id": "gpt-5.4"}
            )
            assert result == {"id": "gpt-5.4", "normalized": True}
            assert len(called) == 1
        finally:
            set_model_compat_normalizer(lambda m: m)
