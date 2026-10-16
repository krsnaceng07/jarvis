"""Parity tests for model-id normalization policies and built-ins.

Mirrors ``provider-model-id-normalize.ts``,
``provider-model-id-normalization.ts`` and their test vectors.
"""

from __future__ import annotations

from jarvis_model_catalog import (
    ManifestModelIdNormalizationProvider,
    ManifestModelIdNormalizationRecord,
    collect_manifest_model_id_normalization_policies,
    normalize_builtin_provider_model_id,
    normalize_configured_provider_catalog_model_id,
    normalize_configured_provider_catalog_model_ref,
    normalize_google_preview_model_id,
    normalize_provider_model_id_with_policies,
    normalize_static_provider_model_id_with_policies,
    normalize_together_model_id,
    set_current_manifest_model_id_normalization_policies,
    strip_self_provider_model_prefix,
)


def test_google_preview_normalization() -> None:
    assert normalize_google_preview_model_id("gemini-3-pro") == "gemini-3.1-pro-preview"
    assert normalize_google_preview_model_id("gemini-3-flash") == "gemini-3-flash-preview"
    assert (
        normalize_google_preview_model_id("gemini-3.1-flash-lite-preview")
        == "gemini-3.1-flash-lite"
    )
    assert normalize_google_preview_model_id("gemma-4-26b") == "gemma-4-26b-a4b-it"
    # google/ prefix recurses into the bare id.
    assert (
        normalize_google_preview_model_id("google/gemini-3-flash")
        == "google/gemini-3-flash-preview"
    )
    assert normalize_google_preview_model_id("gemini-2.0-flash") == "gemini-2.0-flash"


def test_together_normalization() -> None:
    assert normalize_together_model_id("moonshotai/Kimi-K2.5") == "moonshotai/Kimi-K2.6"
    assert normalize_together_model_id("other/model") == "other/model"


def test_builtin_dispatch() -> None:
    assert normalize_builtin_provider_model_id("google", "gemini-3-flash") == (
        "gemini-3-flash-preview"
    )
    assert normalize_builtin_provider_model_id("openrouter", "gpt-5") == "openrouter/gpt-5"
    assert normalize_builtin_provider_model_id("openrouter", "a/b") == "a/b"
    assert normalize_builtin_provider_model_id("anthropic", "sonnet") == "claude-sonnet-5"
    assert normalize_builtin_provider_model_id("anthropic", "anthropic/opus") == ("claude-opus-5")
    assert normalize_builtin_provider_model_id("nvidia", "llama") == "nvidia/llama"
    assert normalize_builtin_provider_model_id("xai", "grok-build-latest") == "grok-4.5"
    assert normalize_builtin_provider_model_id("openai", "gpt-5") == "gpt-5"
    assert normalize_builtin_provider_model_id("unknown", "m") == "m"


def test_manifest_policies_alias_strip_prefix() -> None:
    policies = collect_manifest_model_id_normalization_policies(
        [
            {
                "modelIdNormalization": {
                    "providers": {
                        "acme": {
                            "aliases": {"old": "new"},
                            "stripPrefixes": ["acme/"],
                            "prefixWhenBare": "acme",
                        }
                    }
                }
            }
        ]
    )
    # Alias applies first, then the aliased bare id gets the bare prefix.
    assert normalize_provider_model_id_with_policies("ACME", "acme/old", policies) == "acme/new"
    assert (
        normalize_provider_model_id_with_policies("acme", "bare-model", policies)
        == "acme/bare-model"
    )
    assert normalize_provider_model_id_with_policies("other", "x", policies) is None


def test_prefix_when_bare_after_alias_rule() -> None:
    policies = collect_manifest_model_id_normalization_policies(
        [
            {
                "modelIdNormalization": {
                    "providers": {
                        "acme": {
                            "prefixWhenBareAfterAliasStartsWith": [
                                {"modelPrefix": "special", "prefix": "acme/special"}
                            ],
                            "prefixWhenBare": "acme/general",
                        }
                    }
                }
            }
        ]
    )
    assert (
        normalize_provider_model_id_with_policies("acme", "special-x", policies)
        == "acme/special/special-x"
    )
    assert (
        normalize_provider_model_id_with_policies("acme", "plain", policies) == "acme/general/plain"
    )


def test_manifest_record_shape_accepted() -> None:

    policies = collect_manifest_model_id_normalization_policies(
        [
            ManifestModelIdNormalizationRecord(
                providers={"acme": ManifestModelIdNormalizationProvider(prefix_when_bare="acme")}
            )
        ]
    )
    assert normalize_provider_model_id_with_policies("acme", "m", policies) == "acme/m"


def test_static_applies_manifest_then_builtin() -> None:
    assert (
        normalize_static_provider_model_id_with_policies("openrouter", "gpt-5", None)
        == "openrouter/gpt-5"
    )


def test_strip_self_provider_prefix() -> None:
    assert strip_self_provider_model_prefix("openai", "openai/gpt-5") == "gpt-5"
    assert strip_self_provider_model_prefix("openai", "gpt-5") == "gpt-5"


def test_configured_ref_google_alias() -> None:
    assert (
        normalize_configured_provider_catalog_model_ref("google/gemini-3-flash")
        == "google/gemini-3-flash-preview"
    )
    assert (
        normalize_configured_provider_catalog_model_ref("openai/google/gemini-3-flash")
        == "openai/google/gemini-3-flash-preview"
    )
    assert normalize_configured_provider_catalog_model_ref("openai/gpt-5") == "openai/gpt-5"


def test_configured_model_id_uses_snapshot() -> None:
    try:
        set_current_manifest_model_id_normalization_policies(None)
        assert (
            normalize_configured_provider_catalog_model_id("openrouter", "gpt-5")
            == "openrouter/gpt-5"
        )
    finally:
        set_current_manifest_model_id_normalization_policies(None)
