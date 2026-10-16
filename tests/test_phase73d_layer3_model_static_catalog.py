"""Phase 7.3d tests — model.static-catalog."""
from __future__ import annotations


import pytest

from src.agents.embedded_agent_runner.model_static_catalog import (
    DEFAULT_CONTEXT_TOKENS,
    bundled_static_catalog_provider_uses_runtime_augment,
    canonicalize_manifest_model_catalog_provider_alias,
    create_bundled_provider_static_catalog_context_resolver,
    create_bundled_provider_static_catalog_model_resolver,
    create_bundled_static_catalog_model_resolver,
    load_bundled_provider_static_catalog_context_models,
    resolve_bundled_provider_static_catalog_model,
    resolve_bundled_static_catalog_model,
    resolve_manifest_model_catalog_provider_alias_metadata,
    resolve_manifest_model_catalog_provider_transport,
    set_build_plugin_row_hook,
    set_list_bundled_static_catalog_plugins_hook,
    set_plan_manifest_model_catalog_rows_hook,
    set_provider_id_normalizer,
)


def _install_default_hooks() -> None:
    set_list_bundled_static_catalog_plugins_hook(lambda **_: [])
    set_plan_manifest_model_catalog_rows_hook(lambda **_: {"rows": []})
    set_build_plugin_row_hook(lambda row: row)
    set_provider_id_normalizer(lambda v: (v or "").strip().lower())


# ============================================================================
# bundled_static_catalog_provider_uses_runtime_augment
# ============================================================================


class TestBundledStaticCatalogProviderUsesRuntimeAugment:
    def setup_method(self) -> None:
        _install_default_hooks()

    def test_no_provider(self) -> None:
        assert bundled_static_catalog_provider_uses_runtime_augment(provider="") is False

    def test_no_plugins(self) -> None:
        assert (
            bundled_static_catalog_provider_uses_runtime_augment(provider="openai")
            is False
        )

    def test_runtime_augment_not_set(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {"openai": {}},
                    },
                },
            ]
        )
        assert (
            bundled_static_catalog_provider_uses_runtime_augment(provider="openai")
            is False
        )

    def test_runtime_augment_providers_match(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "runtimeAugment": True,
                        "providers": {"openai": {}},
                    },
                },
            ]
        )
        assert (
            bundled_static_catalog_provider_uses_runtime_augment(provider="openai")
            is True
        )

    def test_runtime_augment_aliases_match(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "runtimeAugment": True,
                        "aliases": {"openai": {}},
                    },
                },
            ]
        )
        assert (
            bundled_static_catalog_provider_uses_runtime_augment(provider="openai")
            is True
        )

    def test_no_match(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "runtimeAugment": True,
                        "providers": {"anthropic": {}},
                    },
                },
            ]
        )
        assert (
            bundled_static_catalog_provider_uses_runtime_augment(provider="openai")
            is False
        )


# ============================================================================
# create_bundled_static_catalog_model_resolver
# ============================================================================


class TestCreateBundledStaticCatalogModelResolver:
    def setup_method(self) -> None:
        _install_default_hooks()

    def test_no_plugins(self) -> None:
        resolver = create_bundled_static_catalog_model_resolver()
        assert resolver({"provider": "openai", "modelId": "gpt-5.4"}) is None

    def test_no_provider(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {"modelCatalog": {"providers": {"openai": {"models": []}}}},
            ]
        )
        resolver = create_bundled_static_catalog_model_resolver()
        assert resolver({"provider": "", "modelId": "gpt-5.4"}) is None

    def test_no_model_id(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {"modelCatalog": {"providers": {"openai": {"models": []}}}},
            ]
        )
        resolver = create_bundled_static_catalog_model_resolver()
        assert resolver({"provider": "openai", "modelId": ""}) is None

    def test_resolves_model(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {
                                "models": [
                                    {"id": "gpt-5.4", "contextWindow": 128_000},
                                ],
                            },
                        },
                    },
                },
            ]
        )
        set_plan_manifest_model_catalog_rows_hook(
            lambda **_: {
                "rows": [
                    {
                        "id": "gpt-5.4",
                        "provider": "openai",
                        "contextWindow": 128_000,
                        "api": "openai-responses",
                    },
                ],
            }
        )
        resolver = create_bundled_static_catalog_model_resolver()
        result = resolver({"provider": "openai", "modelId": "gpt-5.4"})
        assert result is not None
        assert result["id"] == "gpt-5.4"
        assert result["provider"] == "openai"

    def test_no_matching_model(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {
                                "models": [{"id": "gpt-3.5-turbo"}],
                            },
                        },
                    },
                },
            ]
        )
        set_plan_manifest_model_catalog_rows_hook(
            lambda **_: {
                "rows": [
                    {"id": "gpt-3.5-turbo", "provider": "openai"},
                ],
            }
        )
        resolver = create_bundled_static_catalog_model_resolver()
        result = resolver({"provider": "openai", "modelId": "gpt-5.4"})
        assert result is None


# ============================================================================
# resolve_bundled_static_catalog_model
# ============================================================================


class TestResolveBundledStaticCatalogModel:
    def setup_method(self) -> None:
        _install_default_hooks()

    def test_resolves_model(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {
                                "models": [
                                    {"id": "gpt-5.4", "contextWindow": 128_000},
                                ],
                            },
                        },
                    },
                },
            ]
        )
        set_plan_manifest_model_catalog_rows_hook(
            lambda **_: {
                "rows": [
                    {
                        "id": "gpt-5.4",
                        "provider": "openai",
                        "contextWindow": 128_000,
                        "api": "openai-responses",
                    },
                ],
            }
        )
        result = resolve_bundled_static_catalog_model(
            provider="openai", model_id="gpt-5.4"
        )
        assert result is not None
        assert result["id"] == "gpt-5.4"


# ============================================================================
# load_bundled_provider_static_catalog_context_models
# ============================================================================


class TestLoadBundledProviderStaticCatalogContextModels:
    def setup_method(self) -> None:
        _install_default_hooks()

    @pytest.mark.asyncio
    async def test_no_provider(self) -> None:
        result = await load_bundled_provider_static_catalog_context_models(provider="")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_matching_provider(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "anthropic": {"models": [{"id": "claude"}]},
                        },
                    },
                },
            ]
        )
        result = await load_bundled_provider_static_catalog_context_models(
            provider="openai"
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_loads_models(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {
                                "models": [
                                    {"id": "gpt-5.4"},
                                    {"id": "gpt-3.5-turbo"},
                                ],
                            },
                        },
                    },
                },
            ]
        )
        result = await load_bundled_provider_static_catalog_context_models(
            provider="openai"
        )
        assert len(result) == 2
        assert result[0]["id"] == "gpt-5.4"

    @pytest.mark.asyncio
    async def test_skips_non_dict_models(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {
                                "models": [None, {"id": "gpt-5.4"}, "string"],
                            },
                        },
                    },
                },
            ]
        )
        result = await load_bundled_provider_static_catalog_context_models(
            provider="openai"
        )
        assert len(result) == 1
        assert result[0]["id"] == "gpt-5.4"


# ============================================================================
# create_bundled_provider_static_catalog_model_resolver
# ============================================================================


class TestCreateBundledProviderStaticCatalogModelResolver:
    def setup_method(self) -> None:
        _install_default_hooks()

    def test_no_provider(self) -> None:
        resolver = create_bundled_provider_static_catalog_model_resolver({})
        assert resolver({"provider": "openai", "modelId": "gpt-5.4"}) is None

    def test_no_matching_provider(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "anthropic": {"models": [{"id": "claude"}]},
                        },
                    },
                },
            ]
        )
        resolver = create_bundled_provider_static_catalog_model_resolver(
            {"provider": "openai"}
        )
        assert resolver({"provider": "openai", "modelId": "gpt-5.4"}) is None

    def test_provider_mismatch(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {"models": [{"id": "gpt-5.4"}]},
                        },
                    },
                },
            ]
        )
        resolver = create_bundled_provider_static_catalog_model_resolver(
            {"provider": "openai"}
        )
        assert resolver({"provider": "anthropic", "modelId": "gpt-5.4"}) is None

    def test_resolves_model(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {
                                "models": [
                                    {"id": "gpt-5.4", "contextWindow": 128_000},
                                ],
                            },
                        },
                    },
                },
            ]
        )
        resolver = create_bundled_provider_static_catalog_model_resolver(
            {"provider": "openai"}
        )
        result = resolver({"provider": "openai", "modelId": "gpt-5.4"})
        assert result is not None
        assert result["id"] == "gpt-5.4"

    def test_no_model_id(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {"models": [{"id": "gpt-5.4"}]},
                        },
                    },
                },
            ]
        )
        resolver = create_bundled_provider_static_catalog_model_resolver(
            {"provider": "openai"}
        )
        assert resolver({"provider": "openai", "modelId": ""}) is None

    @pytest.mark.asyncio
    async def test_resolve_bundled_provider_helper(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {
                                "models": [
                                    {"id": "gpt-5.4", "contextWindow": 128_000},
                                ],
                            },
                        },
                    },
                },
            ]
        )
        result = await resolve_bundled_provider_static_catalog_model(
            provider="openai", model_id="gpt-5.4"
        )
        assert result is not None
        assert result["id"] == "gpt-5.4"


# ============================================================================
# create_bundled_provider_static_catalog_context_resolver
# ============================================================================


class TestCreateBundledProviderStaticCatalogContextResolver:
    def setup_method(self) -> None:
        _install_default_hooks()

    def test_no_provider(self) -> None:
        resolver = create_bundled_provider_static_catalog_context_resolver({})
        assert resolver({"provider": "openai", "modelId": "gpt-5.4"}) is None

    def test_no_matching_provider(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "anthropic": {"models": [{"id": "claude"}]},
                        },
                    },
                },
            ]
        )
        resolver = create_bundled_provider_static_catalog_context_resolver(
            {"provider": "openai"}
        )
        assert resolver({"provider": "openai", "modelId": "gpt-5.4"}) is None

    def test_provider_mismatch(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {"models": [{"id": "gpt-5.4"}]},
                        },
                    },
                },
            ]
        )
        resolver = create_bundled_provider_static_catalog_context_resolver(
            {"provider": "openai"}
        )
        assert resolver({"provider": "anthropic", "modelId": "gpt-5.4"}) is None

    def test_resolves_context(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {
                                "models": [
                                    {
                                        "id": "gpt-5.4",
                                        "contextWindow": 128_000,
                                        "contextTokens": 120_000,
                                    },
                                ],
                            },
                        },
                    },
                },
            ]
        )
        resolver = create_bundled_provider_static_catalog_context_resolver(
            {"provider": "openai"}
        )
        result = resolver({"provider": "openai", "modelId": "gpt-5.4"})
        assert result == {
            "contextWindow": 128_000,
            "contextTokens": 120_000,
        }

    def test_no_matching_model_id(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {"models": [{"id": "gpt-3.5-turbo"}]},
                        },
                    },
                },
            ]
        )
        resolver = create_bundled_provider_static_catalog_context_resolver(
            {"provider": "openai"}
        )
        assert resolver({"provider": "openai", "modelId": "gpt-5.4"}) is None

    def test_default_context_window(self) -> None:
        set_list_bundled_static_catalog_plugins_hook(
            lambda **_: [
                {
                    "modelCatalog": {
                        "providers": {
                            "openai": {"models": [{"id": "gpt-5.4"}]},
                        },
                    },
                },
            ]
        )
        resolver = create_bundled_provider_static_catalog_context_resolver(
            {"provider": "openai"}
        )
        result = resolver({"provider": "openai", "modelId": "gpt-5.4"})
        assert result["contextWindow"] == DEFAULT_CONTEXT_TOKENS
        assert result["contextTokens"] is None


# ============================================================================
# Re-exports
# ============================================================================


class TestReExports:
    def test_canonicalize_alias_re_export(self) -> None:
        # Just verify the re-export works (the heavy logic lives in
        # model_manifest_alias which is independently tested).
        assert canonicalize_manifest_model_catalog_provider_alias(provider="openai") == "openai"

    def test_resolve_metadata_re_export(self) -> None:
        result = resolve_manifest_model_catalog_provider_alias_metadata(provider="openai")
        assert "provider" in result

    def test_resolve_transport_re_export(self) -> None:
        result = resolve_manifest_model_catalog_provider_transport(provider="openai")
        # Empty default: no plugins installed -> None.
        assert result is None
