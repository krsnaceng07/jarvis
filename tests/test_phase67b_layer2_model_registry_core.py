"""Phase 6.7b — Layer 2 model registry core (1:1 port).

Tests for
:class:`jarvis.agents.sessions.model_registry.ModelRegistry`.

- Constructors: ``create`` (file-backed) +
  ``in_memory`` (no file).
- ``refresh()`` re-reads + re-applies dynamic
  providers.
- ``getError()`` returns the latest load
  error.
- ``getAll()`` / ``getAvailable()`` /
  ``find(provider, modelId)``.
- ``hasConfiguredAuth(model)`` checks
  storage + AWS-SDK + ``apiKey`` in
  ``models.json``.
- ``getApiKeyAndHeaders(model)`` resolves
  the API key + headers chain.
- ``getProviderAuthStatus(provider)`` returns
  the right source per auth type.
- ``getProviderDisplayName(provider)`` falls
  back to ``BUILT_IN_PROVIDER_DISPLAY_NAMES``.
- ``getApiKeyForProvider(provider)`` is a
  thin wrapper around
  ``AuthStorage.getApiKey`` + the
  ``models.json`` API key.
- ``isUsingOAuth(model)``.
- ``registerProvider(name, config)`` +
  ``unregisterProvider(name)``.
- ``models.json` parsing — successful load +
  schema error + parse error + missing file.
- ``_strip_json_comments`` (the OpenClaw
  helper).
- ``_merge_compat`` (the OpenClaw helper).
- ``_validate_config`` (the OpenClaw
  validator).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agents.sessions import (  # noqa: E402
    AuthStorage,
    ModelRegistry,
    ProviderRequestConfig,
)


# ── Helpers ─────────────────────────────────────────────────────


def _v3_models_json(providers: dict) -> str:
    return json.dumps({"providers": providers})


def _write_models_json(
    file_path: str, providers: dict
) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(_v3_models_json(providers))


def _anthropic_provider() -> dict:
    return {
        "anthropic": {
            "baseUrl": "https://api.anthropic.com",
            "apiKey": "sk-test",
            "models": [
                {
                    "id": "claude-3-5-sonnet",
                    "name": "Claude 3.5 Sonnet",
                    "api": "anthropic-messages",
                    "contextWindow": 200000,
                    "maxTokens": 8192,
                }
            ],
        }
    }


# ── Constructors ──────────────────────────────────────────────


class TestConstructors:
    def test_create_with_models_json(self, tmp_path) -> None:
        """``ModelRegistry.create`` loads the
        ``models.json`` at the given path."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, _anthropic_provider())
        auth_storage = AuthStorage.in_memory()
        registry = ModelRegistry.create(
            auth_storage=auth_storage,
            models_json_path=models_path,
        )
        models = registry.get_all()
        assert len(models) == 1
        assert models[0]["id"] == "claude-3-5-sonnet"
        assert models[0]["provider"] == "anthropic"

    def test_create_with_missing_models_json(self, tmp_path) -> None:
        """A missing ``models.json`` is OK (no
        models, no error)."""
        auth_storage = AuthStorage.in_memory()
        registry = ModelRegistry.create(
            auth_storage=auth_storage,
            models_json_path=str(tmp_path / "missing.json"),
        )
        assert registry.get_all() == []
        assert registry.get_error() is None

    def test_in_memory(self) -> None:
        """``inMemory`` builds a registry with
        no file path."""
        registry = ModelRegistry.in_memory(
            auth_storage=AuthStorage.in_memory()
        )
        assert registry.get_all() == []


# ── refresh / getError ───────────────────────────────────────


class TestRefreshAndError:
    def test_refresh_re_reads(self, tmp_path) -> None:
        """``refresh()`` re-reads the file."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, _anthropic_provider())
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        assert len(registry.get_all()) == 1
        # Update the file + refresh.
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-test",
                    "models": [
                        {
                            "id": "claude-3-5-sonnet",
                            "api": "anthropic-messages",
                        },
                        {
                            "id": "claude-3-opus",
                            "api": "anthropic-messages",
                        },
                    ],
                }
            },
        )
        registry.refresh()
        assert len(registry.get_all()) == 2

    def test_schema_error_captured(self, tmp_path) -> None:
        """A ``models.json`` with a schema error
        is captured in ``getError()``."""
        models_path = str(tmp_path / "models.json")
        # ``providers`` is not a dict.
        with open(models_path, "w", encoding="utf-8") as f:
            f.write('{"providers": "not-a-dict"}')
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        assert registry.get_error() is not None
        assert "schema" in registry.get_error().lower()

    def test_parse_error_captured(self, tmp_path) -> None:
        """A ``models.json`` with a parse error
        is captured in ``getError()``."""
        models_path = str(tmp_path / "models.json")
        with open(models_path, "w", encoding="utf-8") as f:
            f.write("not valid json")
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        assert registry.get_error() is not None


# ── getAll / getAvailable / find ─────────────────────────────


class TestGetters:
    def test_get_available_filters_unauthed(self, tmp_path) -> None:
        """``getAvailable`` filters out models
        without auth."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-test",
                    "models": [
                        {
                            "id": "claude-3-5-sonnet",
                            "api": "anthropic-messages",
                        }
                    ],
                },
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "models": [
                        {
                            "id": "gpt-4",
                            "api": "openai-completions",
                        }
                    ],
                },
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        all_models = registry.get_all()
        assert len(all_models) == 2
        available = registry.get_available()
        # Only anthropic is configured (has
        # apiKey).
        assert len(available) == 1
        assert available[0]["provider"] == "anthropic"

    def test_find(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, _anthropic_provider())
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        m = registry.find("anthropic", "claude-3-5-sonnet")
        assert m is not None
        assert m["id"] == "claude-3-5-sonnet"
        assert registry.find("unknown", "x") is None


# ── hasConfiguredAuth ──────────────────────────────────────


class TestHasConfiguredAuth:
    def test_has_configured_auth_via_models_json(self, tmp_path) -> None:
        """A model is configured if its provider
        has ``apiKey`` in ``models.json``."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, _anthropic_provider())
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        m = registry.get_all()[0]
        # ``auth_storage`` has nothing, but
        # ``models.json`` has the apiKey.
        assert registry.has_configured_auth(m) is True

    def test_has_configured_auth_via_storage(self, tmp_path) -> None:
        """A model is configured if its provider
        has auth in the auth-storage."""
        models_path = str(tmp_path / "models.json")
        # A model with no ``apiKey`` in
        # ``models.json`` (so the models.json
        # doesn't have auth), but the
        # auth-storage has the key.
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        auth_storage = AuthStorage.in_memory()
        auth_storage.set("openai", {"type": "api_key", "key": "sk-x"})
        registry = ModelRegistry.create(
            auth_storage=auth_storage,
            models_json_path=models_path,
        )
        m = registry.get_all()[0]
        assert registry.has_configured_auth(m) is True

    def test_has_configured_auth_false(self, tmp_path) -> None:
        """A model without auth anywhere is not
        configured."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        m = registry.get_all()[0]
        assert registry.has_configured_auth(m) is False

    def test_has_configured_auth_aws_sdk(self, tmp_path) -> None:
        """A model with ``auth: "aws-sdk"`` is
        configured (no actual key needed)."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "bedrock": {
                    "baseUrl": "https://bedrock.us-east-1.amazonaws.com",
                    "auth": "aws-sdk",
                    "models": [
                        {"id": "claude", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        m = registry.get_all()[0]
        assert registry.has_configured_auth(m) is True


# ── getApiKeyAndHeaders ─────────────────────────────────────


class TestGetApiKeyAndHeaders:
    def test_resolves_via_auth_storage(self, tmp_path) -> None:
        """The API key comes from auth-storage
        (highest priority)."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        auth_storage = AuthStorage.in_memory()
        auth_storage.set("openai", {"type": "api_key", "key": "sk-storage"})
        registry = ModelRegistry.create(
            auth_storage=auth_storage,
            models_json_path=models_path,
        )
        m = registry.get_all()[0]
        result = asyncio.run(registry.get_api_key_and_headers(m))
        assert result["ok"] is True
        assert result["apiKey"] == "sk-storage"

    def test_resolves_via_models_json(self, tmp_path) -> None:
        """The API key falls back to the
        ``models.json`` ``apiKey``."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "apiKey": "sk-models-json",
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        m = registry.get_all()[0]
        result = asyncio.run(registry.get_api_key_and_headers(m))
        assert result["ok"] is True
        assert result["apiKey"] == "sk-models-json"

    def test_auth_header(self, tmp_path) -> None:
        """``authHeader: true`` injects a
        ``Bearer`` header."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "apiKey": "sk-models",
                    "authHeader": True,
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        m = registry.get_all()[0]
        result = asyncio.run(registry.get_api_key_and_headers(m))
        assert result["ok"] is True
        assert result["headers"]["Authorization"] == "Bearer sk-models"

    def test_auth_header_no_key(self, tmp_path) -> None:
        """``authHeader: true`` without an API
        key returns an error."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "authHeader": True,
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        m = registry.get_all()[0]
        result = asyncio.run(registry.get_api_key_and_headers(m))
        assert result["ok"] is False
        assert "API key" in result["error"]


# ── getProviderAuthStatus ───────────────────────────────────


class TestGetProviderAuthStatus:
    def test_aws_sdk(self, tmp_path) -> None:
        """``auth: "aws-sdk"`` returns
        ``models_json_key``."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "bedrock": {
                    "baseUrl": "https://bedrock.us-east-1.amazonaws.com",
                    "auth": "aws-sdk",
                    "models": [
                        {"id": "claude", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        status = registry.get_provider_auth_status("bedrock")
        assert status["configured"] is True
        assert status["source"] == "models_json_key"

    def test_storage_source(self, tmp_path) -> None:
        """The auth-storage source takes
        priority over ``models.json``."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "apiKey": "sk-models",
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        auth_storage = AuthStorage.in_memory()
        auth_storage.set("openai", {"type": "api_key", "key": "sk-x"})
        registry = ModelRegistry.create(
            auth_storage=auth_storage,
            models_json_path=models_path,
        )
        status = registry.get_provider_auth_status("openai")
        assert status["source"] == "stored"

    def test_command_source(self, tmp_path) -> None:
        """A ``models.json`` ``apiKey`` starting
        with ``!`` is a command source."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "apiKey": "!my-command",
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        status = registry.get_provider_auth_status("openai")
        assert status["source"] == "models_json_command"

    def test_env_var_source(self, tmp_path, monkeypatch) -> None:
        """A ``models.json`` ``apiKey`` matching
        an env-var name is an environment
        source."""
        monkeypatch.setenv("MY_OPENAI_KEY", "sk-env")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "apiKey": "MY_OPENAI_KEY",
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        status = registry.get_provider_auth_status("openai")
        assert status["source"] == "environment"
        assert status["label"] == "MY_OPENAI_KEY"


# ── getProviderDisplayName ──────────────────────────────────


class TestGetProviderDisplayName:
    def test_builtin_provider(self, tmp_path) -> None:
        """A built-in provider has a known
        display name."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-test",
                    "models": [
                        {"id": "claude", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        name = registry.get_provider_display_name("anthropic")
        assert name != "anthropic"  # has a real display name

    def test_unknown_provider_returns_id(self, tmp_path) -> None:
        """An unknown provider returns its id
        as the display name."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, _anthropic_provider())
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        assert registry.get_provider_display_name("unknown") == "unknown"


# ── getApiKeyForProvider ────────────────────────────────────


class TestGetApiKeyForProvider:
    def test_storage_first(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "apiKey": "sk-models",
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        auth_storage = AuthStorage.in_memory()
        auth_storage.set("openai", {"type": "api_key", "key": "sk-storage"})
        registry = ModelRegistry.create(
            auth_storage=auth_storage,
            models_json_path=models_path,
        )
        key = asyncio.run(registry.get_api_key_for_provider("openai"))
        assert key == "sk-storage"

    def test_fallback_to_models_json(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "apiKey": "sk-models",
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        key = asyncio.run(registry.get_api_key_for_provider("openai"))
        assert key == "sk-models"

    def test_no_key_returns_none(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "openai": {
                    "baseUrl": "https://api.openai.com",
                    "models": [
                        {"id": "gpt-4", "api": "openai-completions"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        key = asyncio.run(registry.get_api_key_for_provider("openai"))
        assert key is None


# ── isUsingOAuth ────────────────────────────────────────────


class TestIsUsingOAuth:
    def test_oauth_model(self, tmp_path) -> None:
        auth_storage = AuthStorage.in_memory()
        auth_storage.set(
            "chutes", {"type": "oauth", "accessToken": "x", "expires": 0}
        )
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "chutes": {
                    "baseUrl": "https://chutes.ai",
                    "models": [
                        {"id": "x", "api": "openai-completions"}
                    ],
                }
            },
        )
        registry = ModelRegistry.create(
            auth_storage=auth_storage,
            models_json_path=models_path,
        )
        m = registry.find("chutes", "x")
        assert m is not None
        assert registry.is_using_oauth(m) is True

    def test_non_oauth_model(self, tmp_path) -> None:
        auth_storage = AuthStorage.in_memory()
        auth_storage.set("anthropic", {"type": "api_key", "key": "sk-x"})
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, _anthropic_provider())
        registry = ModelRegistry.create(
            auth_storage=auth_storage,
            models_json_path=models_path,
        )
        m = registry.find("anthropic", "claude-3-5-sonnet")
        assert m is not None
        assert registry.is_using_oauth(m) is False


# ── registerProvider / unregisterProvider ──────────────────


class TestRegisterUnregisterProvider:
    def test_register_replaces_models(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, _anthropic_provider())
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        assert len(registry.get_all()) == 1
        # Register a new provider.
        registry.register_provider(
            "custom",
            {
                "name": "Custom Provider",
                "baseUrl": "https://custom.example.com",
                "api": "openai-completions",
                "apiKey": "sk-custom",
                "models": [
                    {
                        "id": "custom-1",
                        "name": "Custom 1",
                        "api": "openai-completions",
                        "baseUrl": "https://custom.example.com",
                        "reasoning": False,
                        "input": ["text"],
                        "cost": {
                            "input": 0,
                            "output": 0,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                        },
                        "contextWindow": 8000,
                        "maxTokens": 4000,
                    }
                ],
            },
        )
        # The custom provider's models are
        # added.
        assert len(registry.get_all()) == 2
        assert registry.find("custom", "custom-1") is not None

    def test_register_requires_baseurl_for_models(self, tmp_path) -> None:
        """``register_provider`` with models but
        no ``baseUrl`` raises."""
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, _anthropic_provider())
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        with pytest.raises(RuntimeError, match="baseUrl"):
            registry.register_provider(
                "custom",
                {
                    "api": "openai-completions",
                    "models": [
                        {
                            "id": "x",
                            "api": "openai-completions",
                            "baseUrl": "https://x.com",
                            "reasoning": False,
                            "input": ["text"],
                            "cost": {
                                "input": 0,
                                "output": 0,
                                "cacheRead": 0,
                                "cacheWrite": 0,
                            },
                            "contextWindow": 8000,
                            "maxTokens": 4000,
                        }
                    ],
                },
            )

    def test_unregister_removes(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, _anthropic_provider())
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        registry.register_provider(
            "custom",
            {
                "name": "Custom Provider",
                "baseUrl": "https://custom.example.com",
                "api": "openai-completions",
                "apiKey": "sk-custom",
                "models": [
                    {
                        "id": "custom-1",
                        "name": "Custom 1",
                        "api": "openai-completions",
                        "baseUrl": "https://custom.example.com",
                        "reasoning": False,
                        "input": ["text"],
                        "cost": {
                            "input": 0,
                            "output": 0,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                        },
                        "contextWindow": 8000,
                        "maxTokens": 4000,
                    }
                ],
            },
        )
        assert registry.find("custom", "custom-1") is not None
        # Unregister.
        registry.unregister_provider("custom")
        # The custom models are gone (the
        # ``refresh()`` re-reads from
        # ``models.json`` + re-applies dynamic
        # providers; since the custom provider
        # was unregistered, only the
        # ``models.json`` providers remain).
        assert registry.find("custom", "custom-1") is None

    def test_unregister_unknown_is_noop(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, _anthropic_provider())
        registry = ModelRegistry.create(
            auth_storage=AuthStorage.in_memory(),
            models_json_path=models_path,
        )
        # Unregistering an unknown provider is
        # a no-op.
        registry.unregister_provider("unknown")


# ── strip_json_comments ────────────────────────────────────


class TestStripJsonComments:
    def test_strips_line_comments(self) -> None:
        from src.agents.sessions.model_registry import (
            _strip_json_comments,
        )
        result = _strip_json_comments(
            '{\n  "a": 1 // line comment\n}'
        )
        assert "line comment" not in result
        assert '"a"' in result

    def test_preserves_string_with_url(self) -> None:
        from src.agents.sessions.model_registry import (
            _strip_json_comments,
        )
        # A string with ``//`` is preserved
        # (URL, etc.).
        result = _strip_json_comments(
            '{"url": "https://example.com"}'
        )
        assert "https://example.com" in result

    def test_strips_trailing_comma(self) -> None:
        from src.agents.sessions.model_registry import (
            _strip_json_comments,
        )
        result = _strip_json_comments('{"a": 1, "b": 2,}')
        # The trailing comma before ``}`` is
        # removed (so the JSON parses).
        assert "2,}" not in result
        assert "2}" in result


# ── merge_compat ────────────────────────────────────────────


class TestMergeCompat:
    def test_no_override(self) -> None:
        from src.agents.sessions.model_registry import _merge_compat
        base = {"supportsStore": True}
        assert _merge_compat(base, None) == base

    def test_merges_routing(self) -> None:
        from src.agents.sessions.model_registry import _merge_compat
        base = {"openRouterRouting": {"order": ["a"]}}
        override = {"openRouterRouting": {"only": ["b"]}}
        merged = _merge_compat(base, override)
        assert merged["openRouterRouting"] == {
            "order": ["a"],
            "only": ["b"],
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
