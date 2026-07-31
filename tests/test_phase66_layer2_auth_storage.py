"""Phase 6.6 — Layer 2 auth storage.

Tests for
:class:`jarvis.agents.sessions.auth_storage.AuthStorage` +
the file / in-memory backends + the
per-instance OAuth provider registry.

- ``AuthStorage.create(path)`` — file backend.
- ``AuthStorage.in_memory(data?)`` — in-memory
  backend.
- ``AuthStorage.from_storage(backend)`` —
  custom backend.
- ``set_runtime_api_key`` /
  ``remove_runtime_api_key`` — runtime
  overrides (not persisted).
- ``set_fallback_resolver`` — fallback chain.
- ``reload()`` — re-read from the backend.
- ``get`` / ``set`` / ``remove`` / ``list`` /
  ``has`` — CRUD.
- ``has_auth(provider)`` — checks runtime +
  stored + env + fallback.
- ``get_auth_status(provider)`` — returns
  ``{configured, source, label}``.
- ``get_all()`` — returns every credential.
- ``drain_errors()`` — returns + clears the
  error list.
- ``login`` (Phase 6.6 stub) raises.
- ``logout(provider)`` — calls
  ``remove(provider)``.
- ``get_api_key(provider)`` — runtime →
  auth.json → env → fallback chain.
- ``find_env_keys(provider)`` /
  ``get_env_api_key(provider)`` — env-var
  helpers.
- ``FileAuthStorageBackend`` — file IO +
  cross-process lock + 0o600 permissions.
- ``InMemoryAuthStorageBackend`` — in-memory
  thread-safe backend.
- ``get_auth_storage_oauth_provider_registry`` —
  weak-keyed per-instance registry.
"""
from __future__ import annotations

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
    AuthStoragePersistenceError,
    FileAuthStorageBackend,
    InMemoryAuthStorageBackend,
    OAuthProviderRegistry,
    find_env_keys,
    get_auth_storage_oauth_provider_registry,
    get_env_api_key,
)


# ── AuthStorage.create / in_memory / from_storage ────────────


class TestAuthStorageFactories:
    def test_create_file_backend(self, tmp_path) -> None:
        """``AuthStorage.create`` returns a
        file-backed auth storage."""
        auth_path = str(tmp_path / "auth.json")
        storage = AuthStorage.create(auth_path=auth_path)
        # The auth file is created.
        assert os.path.exists(auth_path)
        # The data is empty.
        assert storage.list() == []

    def test_in_memory(self) -> None:
        """``AuthStorage.in_memory`` returns an
        in-memory auth storage."""
        storage = AuthStorage.in_memory()
        assert storage.list() == []
        # Set + get round-trips.
        storage.set("anthropic", {"type": "api_key", "key": "sk-test"})
        assert storage.get("anthropic") == {
            "type": "api_key",
            "key": "sk-test",
        }

    def test_in_memory_with_initial_data(self) -> None:
        """``AuthStorage.in_memory`` accepts
        initial data."""
        storage = AuthStorage.in_memory(
            data={"anthropic": {"type": "api_key", "key": "sk-initial"}}
        )
        assert storage.get("anthropic") == {
            "type": "api_key",
            "key": "sk-initial",
        }

    def test_from_storage(self) -> None:
        """``AuthStorage.from_storage`` wraps a
        custom backend."""
        backend = InMemoryAuthStorageBackend()
        storage = AuthStorage.from_storage(backend)
        assert storage.list() == []


# ── Runtime overrides ────────────────────────────────────────


class TestRuntimeOverrides:
    def test_set_and_remove(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set_runtime_api_key("anthropic", "sk-runtime")
        assert "anthropic" in storage.runtime_overrides
        # The runtime override is NOT in
        # ``data`` (it isn't persisted).
        assert "anthropic" not in storage.data
        storage.remove_runtime_api_key("anthropic")
        assert "anthropic" not in storage.runtime_overrides

    def test_runtime_override_used_by_get_api_key(self) -> None:
        """``get_api_key`` returns the runtime
        override (highest priority)."""
        storage = AuthStorage.in_memory()
        storage.set("anthropic", {"type": "api_key", "key": "sk-stored"})
        storage.set_runtime_api_key("anthropic", "sk-runtime")
        # Async helper — the runtime key wins.
        import asyncio
        result = asyncio.run(storage.get_api_key("anthropic"))
        assert result == "sk-runtime"


# ── Fallback resolver ─────────────────────────────────────────


class TestFallbackResolver:
    def test_set_fallback_resolver(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set_fallback_resolver(
            lambda provider: f"sk-{provider}-fallback"
        )
        # The resolver is stored.
        assert storage.fallback_resolver is not None
        # ``has_auth`` returns True via the
        # fallback.
        assert storage.has_auth("custom") is True

    def test_get_api_key_uses_fallback(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set_fallback_resolver(
            lambda provider: f"sk-{provider}-fallback"
        )
        import asyncio
        result = asyncio.run(storage.get_api_key("custom"))
        assert result == "sk-custom-fallback"

    def test_get_api_key_skips_fallback_when_disabled(self) -> None:
        """``includeFallback=False`` skips the
        fallback resolver."""
        storage = AuthStorage.in_memory()
        storage.set_fallback_resolver(
            lambda provider: f"sk-{provider}-fallback"
        )
        import asyncio
        result = asyncio.run(
            storage.get_api_key("custom", options={"includeFallback": False})
        )
        assert result is None


# ── Reload + CRUD ────────────────────────────────────────────


class TestReloadAndCRUD:
    def test_reload_re_reads_data(self, tmp_path) -> None:
        """``reload`` re-reads the file content."""
        auth_path = str(tmp_path / "auth.json")
        with open(auth_path, "w", encoding="utf-8") as f:
            json.dump(
                {"anthropic": {"type": "api_key", "key": "sk-test"}},
                f,
            )
        storage = AuthStorage.create(auth_path=auth_path)
        assert storage.get("anthropic") == {
            "type": "api_key",
            "key": "sk-test",
        }
        # Mutate the file directly.
        with open(auth_path, "w", encoding="utf-8") as f:
            json.dump(
                {"openai": {"type": "api_key", "key": "sk-openai"}},
                f,
            )
        # Reload.
        storage.reload()
        assert storage.get("openai") == {
            "type": "api_key",
            "key": "sk-openai",
        }
        # The old entry is gone.
        assert storage.get("anthropic") is None

    def test_crud_round_trip(self) -> None:
        storage = AuthStorage.in_memory()
        # Set + get.
        storage.set("anthropic", {"type": "api_key", "key": "sk-test"})
        assert storage.get("anthropic") == {
            "type": "api_key",
            "key": "sk-test",
        }
        # List.
        assert storage.list() == ["anthropic"]
        # Has.
        assert storage.has("anthropic") is True
        assert storage.has("openai") is False
        # Remove.
        storage.remove("anthropic")
        assert storage.get("anthropic") is None
        assert storage.has("anthropic") is False

    def test_get_all(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set("anthropic", {"type": "api_key", "key": "sk-1"})
        storage.set("openai", {"type": "api_key", "key": "sk-2"})
        all_creds = storage.get_all()
        assert all_creds == {
            "anthropic": {"type": "api_key", "key": "sk-1"},
            "openai": {"type": "api_key", "key": "sk-2"},
        }


# ── hasAuth + getAuthStatus ──────────────────────────────────


class TestHasAuthAndStatus:
    def test_has_auth_stored(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set("anthropic", {"type": "api_key", "key": "sk"})
        assert storage.has_auth("anthropic") is True

    def test_has_auth_runtime(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set_runtime_api_key("anthropic", "sk-runtime")
        assert storage.has_auth("anthropic") is True

    def test_has_auth_env(self, monkeypatch) -> None:
        storage = AuthStorage.in_memory()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
        assert storage.has_auth("anthropic") is True

    def test_has_auth_fallback(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set_fallback_resolver(lambda _: "sk-fallback")
        assert storage.has_auth("anything") is True

    def test_has_auth_unknown(self) -> None:
        storage = AuthStorage.in_memory()
        assert storage.has_auth("unknown") is False

    def test_get_auth_status_stored(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set("anthropic", {"type": "api_key", "key": "sk"})
        status = storage.get_auth_status("anthropic")
        assert status["configured"] is True
        assert status["source"] == "stored"

    def test_get_auth_status_runtime(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set_runtime_api_key("anthropic", "sk-runtime")
        status = storage.get_auth_status("anthropic")
        assert status["configured"] is False
        assert status["source"] == "runtime"
        assert status["label"] == "--api-key"

    def test_get_auth_status_env(self, monkeypatch) -> None:
        storage = AuthStorage.in_memory()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
        status = storage.get_auth_status("anthropic")
        assert status["configured"] is False
        assert status["source"] == "environment"
        assert status["label"] == "ANTHROPIC_API_KEY"

    def test_get_auth_status_fallback(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set_fallback_resolver(lambda _: "sk-fallback")
        status = storage.get_auth_status("custom")
        assert status["configured"] is False
        assert status["source"] == "fallback"

    def test_get_auth_status_unknown(self) -> None:
        storage = AuthStorage.in_memory()
        status = storage.get_auth_status("unknown")
        assert status["configured"] is False
        assert status.get("source") is None


# ── Error handling ────────────────────────────────────────────


class TestErrorHandling:
    def test_drain_errors(self) -> None:
        storage = AuthStorage.in_memory()
        # No errors initially.
        assert storage.drain_errors() == []
        # Trigger a load error by setting an
        # invalid file.
        storage = AuthStorage.in_memory()
        # Manually record an error.
        storage._record_error(RuntimeError("test"))
        errors = storage.drain_errors()
        assert len(errors) == 1
        # The error list is cleared.
        assert storage.errors == []


# ── OAuth (Phase 6.6 stubs) ───────────────────────────────────


class TestOAuthStubs:
    def test_login_raises(self) -> None:
        """``login`` is a Phase 6.6 stub."""
        storage = AuthStorage.in_memory()
        import asyncio
        with pytest.raises(RuntimeError, match="Phase 6.6"):
            asyncio.run(storage.login("chutes", {}))

    def test_logout_removes(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set("anthropic", {"type": "api_key", "key": "sk"})
        storage.logout("anthropic")
        assert storage.get("anthropic") is None

    def test_get_oauth_providers_empty(self) -> None:
        """``get_oauth_providers`` returns an
        empty dict in Phase 6.6."""
        storage = AuthStorage.in_memory()
        assert storage.get_oauth_providers() == {}


# ── getApiKey chain ──────────────────────────────────────────


class TestGetApiKeyChain:
    def test_runtime_over_stored(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set("anthropic", {"type": "api_key", "key": "sk-stored"})
        storage.set_runtime_api_key("anthropic", "sk-runtime")
        import asyncio
        assert asyncio.run(storage.get_api_key("anthropic")) == "sk-runtime"

    def test_stored_over_env(self, monkeypatch) -> None:
        storage = AuthStorage.in_memory()
        storage.set("anthropic", {"type": "api_key", "key": "sk-stored"})
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
        import asyncio
        assert asyncio.run(storage.get_api_key("anthropic")) == "sk-stored"

    def test_env_over_fallback(self, monkeypatch) -> None:
        storage = AuthStorage.in_memory()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
        storage.set_fallback_resolver(lambda _: "sk-fallback")
        import asyncio
        assert asyncio.run(storage.get_api_key("anthropic")) == "sk-env"

    def test_fallback_when_nothing_else(self) -> None:
        storage = AuthStorage.in_memory()
        storage.set_fallback_resolver(lambda _: "sk-fallback")
        import asyncio
        assert asyncio.run(storage.get_api_key("custom")) == "sk-fallback"

    def test_none_when_nothing_configured(self) -> None:
        storage = AuthStorage.in_memory()
        import asyncio
        assert asyncio.run(storage.get_api_key("unknown")) is None


# ── Env-var helpers ──────────────────────────────────────────


class TestEnvVarHelpers:
    def test_get_env_api_key(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
        assert get_env_api_key("anthropic") == "sk-env"
        # A provider with no env var.
        assert get_env_api_key("unknown") is None

    def test_get_env_api_key_auth_token(self, monkeypatch) -> None:
        # Clear any pre-existing ``ANTHROPIC_API_KEY``
        # so the test is hermetic (the dev
        # env may have it set to "ollama" or
        # similar).
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-auth")
        assert get_env_api_key("anthropic") == "sk-auth"

    def test_find_env_keys(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-1")
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-2")
        keys = find_env_keys("anthropic")
        assert "ANTHROPIC_API_KEY" in keys
        assert "ANTHROPIC_AUTH_TOKEN" in keys


# ── File backend ─────────────────────────────────────────────


class TestFileAuthStorageBackend:
    def test_creates_parent_dir(self, tmp_path) -> None:
        """The file backend creates the parent
        directory if missing."""
        auth_path = str(tmp_path / "nested" / "auth.json")
        backend = FileAuthStorageBackend(auth_path=auth_path)
        backend.with_lock(lambda _: {"result": None})
        # The parent dir + file are created.
        assert os.path.isdir(os.path.dirname(auth_path))
        assert os.path.exists(auth_path)

    def test_creates_empty_file(self, tmp_path) -> None:
        """The file backend creates an empty
        ``{}`` file if missing."""
        auth_path = str(tmp_path / "auth.json")
        FileAuthStorageBackend(auth_path=auth_path).with_lock(
            lambda _: {"result": None}
        )
        with open(auth_path, "r", encoding="utf-8") as f:
            assert f.read() == "{}"

    def test_persists_next_content(self, tmp_path) -> None:
        """The file backend writes the
        ``next`` content."""
        auth_path = str(tmp_path / "auth.json")
        backend = FileAuthStorageBackend(auth_path=auth_path)
        backend.with_lock(
            lambda _: {
                "result": None,
                "next": json.dumps(
                    {"anthropic": {"type": "api_key", "key": "sk"}}
                ),
            }
        )
        with open(auth_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        assert data == {"anthropic": {"type": "api_key", "key": "sk"}}

    def test_returns_result(self, tmp_path) -> None:
        """The file backend returns the
        function's ``result``."""
        auth_path = str(tmp_path / "auth.json")
        backend = FileAuthStorageBackend(auth_path=auth_path)
        result = backend.with_lock(lambda _: {"result": "hello"})
        assert result == "hello"


# ── In-memory backend ────────────────────────────────────────


class TestInMemoryAuthStorageBackend:
    def test_persists_next_content(self) -> None:
        backend = InMemoryAuthStorageBackend()
        backend.with_lock(
            lambda _: {"result": None, "next": '{"a": 1}'}
        )
        assert backend._value == '{"a": 1}'

    def test_returns_result(self) -> None:
        backend = InMemoryAuthStorageBackend()
        result = backend.with_lock(lambda _: {"result": 42})
        assert result == 42


# ── OAuth-provider registry ──────────────────────────────────


class TestOAuthProviderRegistry:
    def test_per_instance(self) -> None:
        """``get_auth_storage_oauth_provider_registry``
        returns a fresh per-instance registry."""
        storage_a = AuthStorage.in_memory()
        storage_b = AuthStorage.in_memory()
        registry_a = get_auth_storage_oauth_provider_registry(storage_a)
        registry_b = get_auth_storage_oauth_provider_registry(storage_b)
        # Different instances get different
        # registries.
        assert registry_a is not registry_b

    def test_returns_same_registry_on_repeat_call(self) -> None:
        """Repeated calls return the same
        registry (per-instance cache)."""
        storage = AuthStorage.in_memory()
        registry_1 = get_auth_storage_oauth_provider_registry(storage)
        registry_2 = get_auth_storage_oauth_provider_registry(storage)
        assert registry_1 is registry_2

    def test_register_and_get(self) -> None:
        """``OAuthProviderRegistry.register`` +
        ``get`` works."""
        registry = OAuthProviderRegistry()
        sentinel = object()
        registry.register("chutes", sentinel)
        assert registry.get("chutes") is sentinel
        assert registry.get("unknown") is None
        # get_all returns a copy.
        all_providers = registry.get_all()
        assert "chutes" in all_providers
        assert all_providers["chutes"] is sentinel


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
