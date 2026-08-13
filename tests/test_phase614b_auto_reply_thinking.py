"""Phase 6.14b — ``src/auto-reply/thinking.test.ts`` → Python.

OpenClaw parity: ports the ``it`` blocks from
``openclaw-main/src/auto-reply/thinking.test.ts`` (905 lines: describe
groups normalizeThinkLevel, listThinkingLevels, listThinkingLevelLabels,
resolveThinkingDefaultForModel, normalizeReasoningLevel,
resolveEffectiveResponseUsage).

Python adaptations, marked at their sites:

- ``vi.hoisted`` + ``vi.mock("../plugins/provider-thinking.js")``
  becomes attribute patching of the four provider hook names that
  ``src.auto_reply.thinking`` binds at import
  (``resolve_provider_binary_thinking``,
  ``resolve_provider_default_thinking_level``,
  ``resolve_provider_thinking_profile``,
  ``resolve_provider_xhigh_thinking``) via the ``provider_mocks``
  generator fixture (patch → yield → restore).
- ``mockReturnValue(undefined)`` becomes a default ``None`` return.
- ``toHaveBeenLastCalledWith(objectContaining(...))`` becomes explicit
  recorded-call assertions on the mock's ``calls`` list.
- The Claude resolver (``provider-claude-thinking``) stays REAL, same
  as the TS test (only provider-thinking is mocked).
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

import src.auto_reply.thinking as thinking_mod
from src.auto_reply.thinking import (
    format_thinking_levels,
    is_thinking_level_supported,
    list_thinking_level_labels,
    list_thinking_level_options,
    list_thinking_levels,
    normalize_reasoning_level,
    normalize_think_level,
    resolve_effective_response_usage,
    resolve_supported_thinking_level,
    resolve_thinking_default_for_model,
)


class _Mock:
    """Minimal vi.fn() stand-in: records calls, settable impl."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []
        self.impl: Any = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.impl is not None:
            return self.impl(*args, **kwargs)
        return None

    @property
    def last_call(self) -> tuple[tuple, dict]:
        return self.calls[-1]


class _ProviderMocks:
    def __init__(self) -> None:
        self.binary = _Mock()
        self.default_level = _Mock()
        self.profile = _Mock()
        self.xhigh = _Mock()


@pytest.fixture
def provider_mocks():
    """Fixture: patch the four provider hooks bound in thinking.py."""
    mocks = _ProviderMocks()
    saved = (
        thinking_mod.resolve_provider_binary_thinking,
        thinking_mod.resolve_provider_default_thinking_level,
        thinking_mod.resolve_provider_thinking_profile,
        thinking_mod.resolve_provider_xhigh_thinking,
    )
    thinking_mod.resolve_provider_binary_thinking = mocks.binary
    thinking_mod.resolve_provider_default_thinking_level = (
        mocks.default_level
    )
    thinking_mod.resolve_provider_thinking_profile = mocks.profile
    thinking_mod.resolve_provider_xhigh_thinking = mocks.xhigh
    yield mocks
    (
        thinking_mod.resolve_provider_binary_thinking,
        thinking_mod.resolve_provider_default_thinking_level,
        thinking_mod.resolve_provider_thinking_profile,
        thinking_mod.resolve_provider_xhigh_thinking,
    ) = saved


# ============================================================================
# normalizeThinkLevel
# ============================================================================


class TestNormalizeThinkLevel:
    def test_accepts_mid_as_medium(self) -> None:
        assert normalize_think_level("mid") == "medium"

    def test_accepts_xhigh_aliases(self) -> None:
        assert normalize_think_level("xhigh") == "xhigh"
        assert normalize_think_level("x-high") == "xhigh"
        assert normalize_think_level("x_high") == "xhigh"
        assert normalize_think_level("x high") == "xhigh"

    def test_accepts_extra_high_aliases_as_xhigh(self) -> None:
        assert normalize_think_level("extra-high") == "xhigh"
        assert normalize_think_level("extra high") == "xhigh"
        assert normalize_think_level("extra_high") == "xhigh"
        assert normalize_think_level("  extra high  ") == "xhigh"

    def test_does_not_over_match_nearby_xhigh_words(self) -> None:
        assert normalize_think_level("extra-highest") is None
        assert normalize_think_level("xhigher") is None

    def test_accepts_on_as_low(self) -> None:
        assert normalize_think_level("on") == "low"

    def test_accepts_adaptive_and_auto_aliases(self) -> None:
        assert normalize_think_level("adaptive") == "adaptive"
        assert normalize_think_level("auto") == "adaptive"
        assert normalize_think_level("Adaptive") == "adaptive"

    def test_accepts_max_as_its_own_level(self) -> None:
        assert normalize_think_level("max") == "max"
        assert normalize_think_level("MAX") == "max"

    def test_keeps_explicit_ultra_distinct_from_ultrathink(self) -> None:
        assert normalize_think_level("ultra") == "ultra"
        assert normalize_think_level("ULTRA") == "ultra"
        assert normalize_think_level("ultrathink") == "high"


# ============================================================================
# listThinkingLevels
# ============================================================================


class TestListThinkingLevels:
    def test_uses_provider_runtime_hooks_for_xhigh_support(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.xhigh.impl = lambda params: True
        assert "xhigh" in list_thinking_levels("demo", "demo-model")

    def test_uses_provider_runtime_hooks_for_xhigh_labels(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.xhigh.impl = lambda params: True
        assert "xhigh" in list_thinking_level_labels("demo", "demo-model")

    def test_includes_xhigh_for_provider_advertised_models(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        def impl(params: dict) -> Optional[bool]:
            provider = params["provider"]
            model_id = params["context"]["modelId"]
            if provider == "openai" and model_id in (
                "gpt-5.4",
                "gpt-5.4-pro",
                "gpt-5.3-codex-spark",
            ):
                return True
            if provider == "github-copilot" and model_id == "gpt-5.4":
                return True
            return None

        provider_mocks.xhigh.impl = impl
        for provider, model in [
            ("openai", "gpt-5.4"),
            ("openai", "gpt-5.4-pro"),
            ("openai", "gpt-5.3-codex-spark"),
            ("github-copilot", "gpt-5.4"),
        ]:
            assert "xhigh" in list_thinking_levels(provider, model)

    def test_excludes_xhigh_for_non_codex_models(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        assert "xhigh" not in list_thinking_levels(None, "gpt-4.1-mini")

    def test_does_not_include_max_without_provider_support(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        assert "max" not in list_thinking_levels("openai", "gpt-5.4")

    def test_passes_effective_agent_runtime_into_profiles(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        def impl(params: dict, options: Optional[dict] = None) -> dict:
            runtime = params["context"].get("agentRuntime")
            levels = [{"id": "off"}, {"id": "max"}]
            if runtime == "openclaw":
                levels.append({"id": "ultra"})
            return {"levels": levels}

        provider_mocks.profile.impl = impl
        assert "ultra" in list_thinking_levels(
            "openai", "gpt-5.6-luna", None, "openclaw"
        )
        assert "ultra" not in list_thinking_levels(
            "openai", "gpt-5.6-luna", None, "codex"
        )
        args, _ = provider_mocks.profile.last_call
        assert args[0]["provider"] == "openai"
        assert args[0]["context"]["agentRuntime"] == "codex"

    def test_clamps_from_active_provider_facts_without_fallback(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        assert (
            resolve_supported_thinking_level(
                {
                    "provider": "deepseek",
                    "model": "deepseek-v4-pro",
                    "level": "medium",
                    "providerPolicySource": "active",
                }
            )
            == "medium"
        )
        matched = [
            (args, kwargs)
            for args, kwargs in provider_mocks.profile.calls
            if args[0].get("provider") == "deepseek"
            and len(args) > 1
            and args[1] == {"allowPublicArtifactFallback": False}
        ]
        assert matched

    def test_does_not_include_adaptive_without_provider_support(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        assert "adaptive" not in list_thinking_levels(None, "gpt-4.1-mini")
        assert "adaptive" not in list_thinking_levels("openai", "gpt-5.4")

    def test_uses_provider_profiles_for_adaptive_and_max(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        def impl(params: dict, options: Optional[dict] = None):
            if params["provider"] == "anthropic":
                return {
                    "levels": [
                        {"id": "off"},
                        {"id": "adaptive"},
                        {"id": "max"},
                    ]
                }
            return None

        provider_mocks.profile.impl = impl
        assert "adaptive" in list_thinking_levels(
            "anthropic", "claude-opus-4-6"
        )
        assert "max" in list_thinking_levels("anthropic", "claude-opus-4-7")

    def test_preserves_provider_profile_ids_and_labels(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": [
                {"id": "off"},
                {"id": "adaptive", "label": "auto"},
                {"id": "max", "label": "maximum"},
            ],
            "defaultLevel": "adaptive",
        }
        assert list_thinking_level_options("demo", "demo-model") == [
            {"id": "off", "label": "off"},
            {"id": "adaptive", "label": "auto"},
            {"id": "max", "label": "maximum"},
        ]

    def test_uses_provider_profiles_ahead_of_legacy_hooks(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": [{"id": "off"}, {"id": "low", "label": "on"}],
            "defaultLevel": "off",
        }
        provider_mocks.xhigh.impl = lambda params: True
        assert list_thinking_levels("demo", "demo-model") == ["off", "low"]
        assert list_thinking_level_labels("demo", "demo-model") == [
            "off",
            "on",
        ]

    def test_treats_catalog_reasoning_false_as_explicit_opt_out(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": [
                {"id": "off"},
                {"id": "low"},
                {"id": "medium"},
                {"id": "high"},
            ],
            "defaultLevel": "medium",
        }
        catalog = [
            {
                "provider": "google",
                "id": "gemma-4-26b-a4b-it",
                "name": "Gemma 4 26B",
                "reasoning": False,
            }
        ]
        assert list_thinking_levels(
            "google", "gemma-4-26b-a4b-it", catalog
        ) == ["off"]
        assert (
            is_thinking_level_supported(
                {
                    "provider": "google",
                    "model": "gemma-4-26b-a4b-it",
                    "level": "medium",
                    "catalog": catalog,
                }
            )
            is False
        )
        assert (
            resolve_thinking_default_for_model(
                {
                    "provider": "google",
                    "model": "gemma-4-26b-a4b-it",
                    "catalog": catalog,
                }
            )
            == "off"
        )

    def test_preserves_authoritative_profiles_over_stale_reasoning(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": [
                {"id": "off"},
                {"id": "minimal"},
                {"id": "low"},
                {"id": "medium"},
            ],
            "preserveWhenCatalogReasoningFalse": True,
        }
        catalog = [
            {
                "provider": "google",
                "id": "gemini-3-flash-preview",
                "name": "Gemini 3 Flash Preview",
                "reasoning": False,
            }
        ]
        assert (
            is_thinking_level_supported(
                {
                    "provider": "google",
                    "model": "gemini-3-flash-preview",
                    "level": "low",
                    "catalog": catalog,
                }
            )
            is True
        )
        assert (
            resolve_supported_thinking_level(
                {
                    "provider": "google",
                    "model": "gemini-3-flash-preview",
                    "level": "low",
                    "catalog": catalog,
                }
            )
            == "low"
        )

    def test_passes_catalog_reasoning_into_profiles(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": (
                [
                    {"id": "off"},
                    {"id": "low"},
                    {"id": "medium"},
                    {"id": "high"},
                    {"id": "max"},
                ]
                if params["context"].get("reasoning") is True
                else [{"id": "off"}]
            ),
            "defaultLevel": "off",
        }
        catalog = [
            {
                "provider": "ollama",
                "id": "gpt-oss:20b",
                "name": "gpt-oss",
                "reasoning": True,
            }
        ]
        assert (
            is_thinking_level_supported(
                {
                    "provider": "ollama",
                    "model": "gpt-oss:20b",
                    "level": "max",
                    "catalog": catalog,
                }
            )
            is True
        )
        assert (
            format_thinking_levels("ollama", "gpt-oss:20b", ", ", catalog)
            == "off, low, medium, high, max"
        )
        assert (
            resolve_supported_thinking_level(
                {
                    "provider": "ollama",
                    "model": "gpt-oss:20b",
                    "level": "max",
                    "catalog": catalog,
                }
            )
            == "max"
        )

    def test_passes_catalog_compat_into_profiles(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        def impl(params: dict, options: Optional[dict] = None):
            ctx = params["context"]
            compat = ctx.get("compat") or {}
            if (
                ctx.get("reasoning") is True
                and compat.get("thinkingFormat") == "qwen-chat-template"
            ):
                return {
                    "levels": [{"id": "off"}, {"id": "low", "label": "on"}],
                    "defaultLevel": "off",
                }
            return None

        provider_mocks.profile.impl = impl
        catalog = [
            {
                "provider": "vllm",
                "id": "Qwen/Qwen3-8B",
                "reasoning": True,
                "compat": {"thinkingFormat": "qwen-chat-template"},
            }
        ]
        assert list_thinking_level_labels(
            "vllm", "Qwen/Qwen3-8B", catalog
        ) == ["off", "on"]
        assert (
            resolve_supported_thinking_level(
                {
                    "provider": "vllm",
                    "model": "Qwen/Qwen3-8B",
                    "level": "high",
                    "catalog": catalog,
                }
            )
            == "low"
        )

    def test_uses_canonical_fable_params_without_provider_profile(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        catalog = [
            {
                "provider": "microsoft-foundry",
                "id": "company-fable",
                "api": "anthropic-messages",
                "reasoning": False,
                "params": {"canonicalModelId": "claude-fable-5"},
            }
        ]
        assert list_thinking_levels(
            "microsoft-foundry", "company-fable", catalog
        ) == [
            "off",
            "minimal",
            "low",
            "medium",
            "adaptive",
            "high",
            "xhigh",
            "max",
        ]
        assert (
            resolve_thinking_default_for_model(
                {
                    "provider": "microsoft-foundry",
                    "model": "company-fable",
                    "catalog": catalog,
                }
            )
            == "high"
        )

    def test_exposes_claude_opus_xhigh_on_custom_anthropic_providers(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        # Regression for openclaw#91975.
        catalog = [
            {
                "provider": "jdcloud-anthropic",
                "id": "claude-opus-4.7-hq",
                "api": "anthropic-messages",
                "reasoning": True,
            }
        ]
        assert list_thinking_levels(
            "jdcloud-anthropic", "claude-opus-4.7-hq", catalog
        ) == [
            "off",
            "minimal",
            "low",
            "medium",
            "adaptive",
            "high",
            "xhigh",
            "max",
        ]
        assert (
            is_thinking_level_supported(
                {
                    "provider": "jdcloud-anthropic",
                    "model": "claude-opus-4.7-hq",
                    "level": "xhigh",
                    "catalog": catalog,
                }
            )
            is True
        )
        assert (
            resolve_supported_thinking_level(
                {
                    "provider": "jdcloud-anthropic",
                    "model": "claude-opus-4.7-hq",
                    "level": "xhigh",
                    "catalog": catalog,
                }
            )
            == "xhigh"
        )

    def test_no_invented_xhigh_for_non_claude_anthropic_routes(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        catalog = [
            {
                "provider": "jdcloud-anthropic",
                "id": "some-non-claude-model",
                "api": "anthropic-messages",
                "reasoning": True,
            }
        ]
        assert list_thinking_levels(
            "jdcloud-anthropic", "some-non-claude-model", catalog
        ) == ["off", "minimal", "low", "medium", "high"]

    def test_suppresses_compat_xhigh_for_non_claude_anthropic_rows(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        catalog = [
            {
                "provider": "jdcloud-anthropic",
                "id": "some-non-claude-model",
                "api": "anthropic-messages",
                "reasoning": True,
                "compat": {"supportedReasoningEfforts": ["xhigh"]},
            }
        ]
        assert "xhigh" not in list_thinking_levels(
            "jdcloud-anthropic", "some-non-claude-model", catalog
        )

    def test_no_claude_profile_without_anthropic_messages_row(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        catalog = [
            {
                "provider": "jdcloud-anthropic",
                "id": "claude-opus-4.7-hq",
                "api": "openai-completions",
                "reasoning": True,
            }
        ]
        assert list_thinking_levels(
            "jdcloud-anthropic", "claude-opus-4.7-hq", catalog
        ) == ["off", "minimal", "low", "medium", "high"]

    def test_native_anthropic_max_parity_for_adaptive_claude(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        catalog = [
            {
                "provider": "jdcloud-anthropic",
                "id": "claude-sonnet-4-6",
                "api": "anthropic-messages",
                "reasoning": True,
            }
        ]
        assert "max" in list_thinking_levels(
            "jdcloud-anthropic", "claude-sonnet-4-6", catalog
        )
        assert (
            is_thinking_level_supported(
                {
                    "provider": "jdcloud-anthropic",
                    "model": "claude-sonnet-4-6",
                    "level": "max",
                    "catalog": catalog,
                }
            )
            is True
        )

    def test_preserves_provider_profiles_for_fable_messages_routes(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": [{"id": "off"}, {"id": "low"}],
            "defaultLevel": "off",
        }
        assert list_thinking_levels(
            "proxy",
            "company-fable",
            [
                {
                    "provider": "proxy",
                    "id": "company-fable",
                    "api": "anthropic-messages",
                    "reasoning": True,
                    "params": {"canonicalModelId": "claude-fable-5"},
                }
            ],
        ) == ["off", "low"]

    def test_no_fable_contract_without_anthropic_messages_row(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": [{"id": "off"}, {"id": "low"}],
            "defaultLevel": "off",
        }
        assert list_thinking_levels(
            "openrouter", "anthropic/claude-fable-5"
        ) == ["off", "low"]

    def test_no_fable_profile_for_openai_compatible_rows(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": [{"id": "off"}, {"id": "low"}, {"id": "high"}],
            "defaultLevel": "off",
        }
        assert list_thinking_levels(
            "openrouter",
            "anthropic/claude-fable-5",
            [
                {
                    "provider": "openrouter",
                    "id": "anthropic/claude-fable-5",
                    "api": "openai-completions",
                    "reasoning": True,
                }
            ],
        ) == ["off", "low", "high"]

    def test_preserves_provider_opt_outs_for_canonical_fable_aliases(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": [{"id": "off"}],
            "defaultLevel": "off",
        }
        catalog = [
            {
                "provider": "claude-cli",
                "id": "company-fable",
                "api": "anthropic-messages",
                "reasoning": True,
                "params": {"canonicalModelId": "claude-fable-5"},
            }
        ]
        assert list_thinking_levels(
            "claude-cli", "company-fable", catalog
        ) == ["off"]

    def test_generic_levels_when_provider_has_no_custom_profile(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: None
        assert list_thinking_levels(
            "vllm",
            "reasoning-model",
            [
                {
                    "provider": "vllm",
                    "id": "reasoning-model",
                    "reasoning": True,
                }
            ],
        ) == ["off", "minimal", "low", "medium", "high"]

    def test_matches_provider_qualified_catalog_ids(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        def impl(params: dict, options: Optional[dict] = None):
            ctx = params["context"]
            compat = ctx.get("compat") or {}
            if (
                ctx.get("reasoning") is True
                and compat.get("thinkingFormat") == "qwen-chat-template"
            ):
                return {
                    "levels": [{"id": "off"}, {"id": "low", "label": "on"}],
                    "defaultLevel": "off",
                }
            return None

        provider_mocks.profile.impl = impl
        catalog = [
            {
                "provider": "vllm",
                "id": "vllm/Qwen/Qwen3-8B",
                "reasoning": True,
                "compat": {"thinkingFormat": "qwen-chat-template"},
            }
        ]
        assert list_thinking_level_labels(
            "vllm", "Qwen/Qwen3-8B", catalog
        ) == ["off", "on"]
        assert (
            resolve_supported_thinking_level(
                {
                    "provider": "vllm",
                    "model": "Qwen/Qwen3-8B",
                    "level": "high",
                    "catalog": catalog,
                }
            )
            == "low"
        )

    def test_catalog_compat_efforts_expose_xhigh(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        catalog = [
            {
                "provider": "gmn",
                "id": "gpt-5.4",
                "name": "GPT 5.4 via GMN",
                "reasoning": True,
                "compat": {
                    "supportedReasoningEfforts": [
                        "low",
                        "medium",
                        "high",
                        "xhigh",
                    ]
                },
            }
        ]
        assert "xhigh" in list_thinking_levels("gmn", "gpt-5.4", catalog)
        assert (
            format_thinking_levels("gmn", "gpt-5.4", ", ", catalog)
            == "off, minimal, low, medium, high, xhigh"
        )
        assert (
            is_thinking_level_supported(
                {
                    "provider": "gmn",
                    "model": "gpt-5.4",
                    "level": "xhigh",
                    "catalog": catalog,
                }
            )
            is True
        )

    def test_catalog_xhigh_compat_does_not_override_binary(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.binary.impl = lambda params: True
        catalog = [
            {
                "provider": "zai",
                "id": "glm-4.7",
                "name": "GLM 4.7",
                "compat": {"supportedReasoningEfforts": ["xhigh"]},
            }
        ]
        assert list_thinking_levels("zai", "glm-4.7", catalog) == [
            "off",
            "low",
        ]
        assert list_thinking_level_labels("zai", "glm-4.7", catalog) == [
            "off",
            "on",
        ]

    def test_maps_stale_unsupported_levels_to_largest_profile_level(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": [{"id": "off"}, {"id": "high"}]
        }
        assert (
            resolve_supported_thinking_level(
                {
                    "provider": "demo",
                    "model": "demo-model",
                    "level": "max",
                }
            )
            == "high"
        )

    def test_maps_xhigh_to_high_for_profiles_with_max_but_no_xhigh(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        def impl(params: dict, options: Optional[dict] = None):
            if params["provider"] == "anthropic":
                return {
                    "levels": [
                        {"id": "off"},
                        {"id": "minimal"},
                        {"id": "low"},
                        {"id": "medium"},
                        {"id": "high"},
                        {"id": "adaptive"},
                        {"id": "max"},
                    ]
                }
            return None

        provider_mocks.profile.impl = impl
        assert (
            resolve_supported_thinking_level(
                {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-6",
                    "level": "xhigh",
                }
            )
            == "high"
        )

    def test_maps_unsupported_adaptive_to_medium_and_xhigh_to_high(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": [
                {"id": "off"},
                {"id": "minimal"},
                {"id": "low"},
                {"id": "medium"},
                {"id": "high"},
            ]
        }
        assert (
            resolve_supported_thinking_level(
                {
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "level": "adaptive",
                }
            )
            == "medium"
        )
        assert (
            resolve_supported_thinking_level(
                {
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "level": "xhigh",
                }
            )
            == "high"
        )

    def test_clamps_below_range_to_cheapest_on_no_off_profile(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.profile.impl = lambda params, options=None: {
            "levels": [{"id": "low"}, {"id": "medium"}, {"id": "high"}]
        }
        assert (
            resolve_supported_thinking_level(
                {
                    "provider": "demo-noff",
                    "model": "demo-model",
                    "level": "off",
                }
            )
            == "low"
        )


# ============================================================================
# listThinkingLevelLabels
# ============================================================================


class TestListThinkingLevelLabels:
    def test_uses_provider_runtime_hooks_for_binary_providers(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.binary.impl = lambda params: True
        assert list_thinking_level_labels("demo", "demo-model") == [
            "off",
            "on",
        ]

    def test_returns_on_off_for_provider_advertised_binary(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.binary.impl = lambda params: (
            True if params["provider"] == "zai" else None
        )
        assert list_thinking_level_labels("zai", "glm-4.7") == ["off", "on"]

    def test_does_not_assume_binary_without_provider_runtime(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        labels = list_thinking_level_labels("zai", "glm-4.7")
        assert "low" in labels
        assert "on" not in labels

    def test_returns_full_levels_for_non_zai(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        labels = list_thinking_level_labels("openai", "gpt-4.1-mini")
        assert "low" in labels
        assert "on" not in labels


# ============================================================================
# resolveThinkingDefaultForModel
# ============================================================================


class TestResolveThinkingDefaultForModel:
    def test_uses_provider_runtime_hooks_for_defaults(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.default_level.impl = lambda params: "adaptive"
        assert (
            resolve_thinking_default_for_model(
                {"provider": "demo", "model": "demo-model"}
            )
            == "adaptive"
        )

    def test_uses_provider_advertised_adaptive_defaults(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.default_level.impl = lambda params: (
            "adaptive"
            if params["provider"] == "anthropic"
            and params["context"]["modelId"] == "claude-opus-4-6"
            else None
        )
        assert (
            resolve_thinking_default_for_model(
                {"provider": "anthropic", "model": "claude-opus-4-6"}
            )
            == "adaptive"
        )

    def test_no_adaptive_defaults_across_bedrock_id_variants(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.default_level.impl = lambda params: (
            "adaptive"
            if params["provider"] == "amazon-bedrock"
            and params["context"]["modelId"] == "claude-sonnet-4-6"
            else None
        )
        assert (
            resolve_thinking_default_for_model(
                {"provider": "aws-bedrock", "model": "claude-sonnet-4-6"}
            )
            == "off"
        )

    def test_no_adaptive_defaults_without_provider_runtime(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        assert (
            resolve_thinking_default_for_model(
                {"provider": "anthropic", "model": "claude-opus-4-6"}
            )
            == "off"
        )
        assert (
            resolve_thinking_default_for_model(
                {"provider": "aws-bedrock", "model": "claude-sonnet-4-6"}
            )
            == "off"
        )

    def test_defaults_reasoning_capable_catalog_models_to_medium(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        assert (
            resolve_thinking_default_for_model(
                {
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "catalog": [
                        {
                            "provider": "openai",
                            "id": "gpt-5.4",
                            "reasoning": True,
                        }
                    ],
                }
            )
            == "medium"
        )

    def test_remaps_implicit_reasoning_defaults_binary(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        provider_mocks.binary.impl = lambda params: (
            params["provider"] == "demo-binary"
        )
        assert (
            resolve_thinking_default_for_model(
                {
                    "provider": "demo-binary",
                    "model": "demo-model",
                    "catalog": [
                        {
                            "provider": "demo-binary",
                            "id": "demo-model",
                            "reasoning": True,
                        }
                    ],
                }
            )
            == "low"
        )

    def test_keeps_catalog_reasoning_context_when_remapping(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        def impl(params: dict, options: Optional[dict] = None):
            if params["provider"] == "demo-contextual":
                if params["context"].get("reasoning"):
                    return {
                        "levels": [
                            {"id": "off"},
                            {"id": "low"},
                            {"id": "medium"},
                        ]
                    }
                return {"levels": [{"id": "off"}]}
            return None

        provider_mocks.profile.impl = impl
        assert (
            resolve_thinking_default_for_model(
                {
                    "provider": "demo-contextual",
                    "model": "demo-model",
                    "catalog": [
                        {
                            "provider": "demo-contextual",
                            "id": "demo-model",
                            "reasoning": True,
                        }
                    ],
                }
            )
            == "medium"
        )

    def test_defaults_to_off_without_adaptive_or_reasoning_hint(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        assert (
            resolve_thinking_default_for_model(
                {
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "catalog": [
                        {
                            "provider": "openai",
                            "id": "gpt-4.1-mini",
                            "reasoning": False,
                        }
                    ],
                }
            )
            == "off"
        )

    def test_respects_provider_declared_off_default(
        self, provider_mocks: _ProviderMocks
    ) -> None:
        def impl(params: dict, options: Optional[dict] = None):
            if params["provider"] == "ollama":
                return {
                    "levels": [
                        {"id": "off"},
                        {"id": "low"},
                        {"id": "medium"},
                        {"id": "high"},
                        {"id": "max"},
                    ],
                    "defaultLevel": "off",
                }
            return None

        provider_mocks.profile.impl = impl
        assert (
            resolve_thinking_default_for_model(
                {
                    "provider": "ollama",
                    "model": "gemma4",
                    "catalog": [
                        {
                            "provider": "ollama",
                            "id": "gemma4",
                            "reasoning": True,
                        }
                    ],
                }
            )
            == "off"
        )


# ============================================================================
# normalizeReasoningLevel
# ============================================================================


class TestNormalizeReasoningLevel:
    def test_accepts_on_off(self) -> None:
        assert normalize_reasoning_level("on") == "on"
        assert normalize_reasoning_level("off") == "off"

    def test_accepts_show_hide(self) -> None:
        assert normalize_reasoning_level("show") == "on"
        assert normalize_reasoning_level("hide") == "off"

    def test_accepts_stream(self) -> None:
        assert normalize_reasoning_level("stream") == "stream"
        assert normalize_reasoning_level("streaming") == "stream"


# ============================================================================
# resolveEffectiveResponseUsage
# ============================================================================


class TestResolveEffectiveResponseUsage:
    def test_off_when_session_unset_and_no_config(self) -> None:
        assert resolve_effective_response_usage(None, None) == "off"

    def test_applies_config_default_when_session_unset(self) -> None:
        assert resolve_effective_response_usage(None, "tokens") == "tokens"
        assert resolve_effective_response_usage(None, "full") == "full"

    def test_applies_per_channel_config_when_session_unset(self) -> None:
        cfg = {"default": "off", "discord": "full", "telegram": "tokens"}
        assert (
            resolve_effective_response_usage(None, cfg, "discord") == "full"
        )
        assert (
            resolve_effective_response_usage(None, cfg, "telegram")
            == "tokens"
        )
        # Unknown channel falls back to config default
        assert (
            resolve_effective_response_usage(None, cfg, "whatsapp") == "off"
        )

    def test_session_explicit_off_overrides_config(self) -> None:
        assert resolve_effective_response_usage("off", "tokens") == "off"
        assert resolve_effective_response_usage("off", "full") == "off"
        assert (
            resolve_effective_response_usage(
                "off", {"default": "full", "discord": "full"}, "discord"
            )
            == "off"
        )

    def test_session_explicit_on_value_overrides_config(self) -> None:
        assert resolve_effective_response_usage("tokens", "full") == "tokens"
        assert resolve_effective_response_usage("full", "off") == "full"

    def test_unset_falls_through_explicit_off_does_not(self) -> None:
        assert resolve_effective_response_usage(None, "tokens") == "tokens"
        assert resolve_effective_response_usage("off", "tokens") == "off"
