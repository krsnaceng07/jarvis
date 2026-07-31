"""Phase 6.7a — Layer 2 model registry (minimal).

Tests for
:class:`jarvis.agents.sessions.model_registry.ModelRegistry`
+ the per-instance runtime +
``model_registry_loader``.

- ``ModelRegistry.create(cwd, agent_dir?, auth_storage?)``
  builds a fresh registry.
- The per-instance runtime is initialised on
  construction.
- ``get_runtime()`` returns the runtime facts.
- ``get_models()`` / ``get_configured_models()``
  return the (initially empty) lists.
- ``resolve_api_key(provider)`` delegates to
  ``AuthStorage.get_api_key``.
- ``drain_errors()`` returns + clears the
  error list.
- ``get_model_registry_runtime(owner)`` returns
  the per-instance runtime; re-calls return
  the same instance.
- ``reset_model_registry_runtime(owner)``
  resets the api-registry.
- ``load_agent_model_registry(config, options?)``
  returns ``{"agentDir", "registry"}``.
"""
from __future__ import annotations

import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agents.sessions import (  # noqa: E402
    ApiRegistry,
    AuthStorage,
    LlmRuntime,
    ModelRegistry,
    ModelRegistryRuntime,
    get_model_registry_runtime,
    initialize_model_registry_runtime,
    load_agent_model_registry,
    reset_model_registry_runtime,
)


# ── ModelRegistry.create / constructor ──────────────────────


class TestModelRegistry:
    def test_create_fresh(self, tmp_path) -> None:
        """``ModelRegistry.create`` builds a
        fresh registry."""
        agent_dir = str(tmp_path / "agent")
        registry = ModelRegistry.create(
            cwd="/some/cwd",
            agent_dir=agent_dir,
        )
        assert registry.get_cwd() == "/some/cwd"
        assert registry.get_agent_dir() == agent_dir
        # The runtime is initialised.
        runtime = registry.get_runtime()
        assert "apiRegistry" in runtime
        assert "llmRuntime" in runtime

    def test_default_agent_dir(self) -> None:
        """``agent_dir=None`` uses the JARVIS
        default."""
        registry = ModelRegistry.create(cwd="/x")
        assert "jarvis" in registry.get_agent_dir()
        assert "agents" in registry.get_agent_dir()

    def test_get_models_initially_empty(self, tmp_path) -> None:
        """``get_models`` returns an empty list
        in Phase 6.7a (the discovery lands in
        6.7b)."""
        registry = ModelRegistry.create(
            cwd="/x",
            agent_dir=str(tmp_path / "agent"),
        )
        assert registry.get_models() == []
        assert registry.get_configured_models() == []

    def test_drain_errors(self, tmp_path) -> None:
        """``drain_errors`` returns + clears the
        error list."""
        registry = ModelRegistry.create(
            cwd="/x",
            agent_dir=str(tmp_path / "agent"),
        )
        # Initially empty.
        assert registry.drain_errors() == []
        # Manually record an error.
        registry.errors.append(RuntimeError("test"))
        errors = registry.drain_errors()
        assert len(errors) == 1
        # The error list is cleared.
        assert registry.errors == []

    def test_resolve_api_key_no_auth_storage(self, tmp_path) -> None:
        """``resolve_api_key`` returns None when
        no auth storage is set."""
        registry = ModelRegistry.create(
            cwd="/x",
            agent_dir=str(tmp_path / "agent"),
        )
        assert registry.resolve_api_key("anthropic") is None

    def test_resolve_api_key_with_auth_storage(self, tmp_path) -> None:
        """``resolve_api_key`` delegates to
        ``AuthStorage.get_api_key``."""
        auth_storage = AuthStorage.in_memory()
        auth_storage.set("anthropic", {"type": "api_key", "key": "sk-test"})
        registry = ModelRegistry.create(
            cwd="/x",
            agent_dir=str(tmp_path / "agent"),
            auth_storage=auth_storage,
        )
        assert registry.resolve_api_key("anthropic") == "sk-test"


# ── Per-instance runtime ────────────────────────────────────


class _RuntimeOwner:
    """Test helper: a class instance that
    supports weak references (a bare
    ``object()`` does not)."""

    pass


class TestPerInstanceRuntime:
    def test_get_runtime_after_init(self) -> None:
        """``get_model_registry_runtime`` returns
        the runtime after
        ``initialize_model_registry_runtime``."""
        owner = _RuntimeOwner()
        initialize_model_registry_runtime(owner)
        runtime = get_model_registry_runtime(owner)
        assert "apiRegistry" in runtime
        assert "llmRuntime" in runtime

    def test_get_runtime_raises_when_not_init(self) -> None:
        """``get_model_registry_runtime`` raises
        when the owner is uninitialised."""
        owner = _RuntimeOwner()
        with pytest.raises(RuntimeError, match="not initialized"):
            get_model_registry_runtime(owner)

    def test_re_init_resets_runtime(self) -> None:
        """A second ``initialize`` call on the
        same owner resets the runtime."""
        owner = _RuntimeOwner()
        initialize_model_registry_runtime(owner)
        runtime_1 = get_model_registry_runtime(owner)
        # Re-initialise (the ``ModelRegistry``
        # constructor does this on a re-init).
        initialize_model_registry_runtime(owner)
        runtime_2 = get_model_registry_runtime(owner)
        # The runtime is a fresh instance.
        # (The same dict is replaced.)
        assert runtime_1 is not runtime_2

    def test_reset_runtime(self) -> None:
        """``reset_model_registry_runtime`` clears
        the api-registry's providers."""
        owner = _RuntimeOwner()
        initialize_model_registry_runtime(owner)
        runtime = get_model_registry_runtime(owner)
        api_registry: ApiRegistry = runtime["apiRegistry"]
        # Register a provider.
        api_registry.register_api_provider({"id": "anthropic"})
        assert len(api_registry.get_all()) == 1
        # Reset.
        reset_model_registry_runtime(owner)
        # The provider is gone (the reset
        # clears the api-registry).
        assert len(api_registry.get_all()) == 0


# ── load_agent_model_registry ──────────────────────────────


class TestLoadAgentModelRegistry:
    def test_load_returns_agent_dir_and_registry(self, tmp_path) -> None:
        """``load_agent_model_registry`` returns
        ``{"agentDir", "registry"}``."""
        result = load_agent_model_registry(config={})
        # The agent dir is the JARVIS default.
        assert "agentDir" in result
        assert "jarvis" in result["agentDir"]
        # The registry is a ``ModelRegistry``.
        assert isinstance(result["registry"], ModelRegistry)

    def test_load_with_options(self) -> None:
        """``load_agent_model_registry`` accepts
        options (provider filter, normalize,
        read-only, skip credentials,
        workspace dir)."""
        result = load_agent_model_registry(
            config={},
            options={
                "readOnly": True,
                "normalizeModels": True,
            },
        )
        assert "registry" in result
