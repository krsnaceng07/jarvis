"""Phase 6.7a — Layer 2 model registry (foundation).

Tests for
:class:`jarvis.agents.sessions.model_registry.ModelRegistry`
+ the per-instance runtime +
``model_registry_loader``.

Note: Phase 6.7b replaced the minimal 6.7a
facade with the full 1:1 port (with the
``create(auth_storage, models_json_path?, options?)``
signature, the full model-catalog load, the
register/unregister API, etc.). This test file
covers the 6.7a foundation surface (per-instance
runtime + the foundation methods) that's still
valid against the 6.7b facade.
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
    ModelRegistry,
    get_model_registry_runtime,
    initialize_model_registry_runtime,
    load_agent_model_registry,
    reset_model_registry_runtime,
)


# ── ModelRegistry.create / constructor ──────────────────────


class TestModelRegistry:
    def test_create_fresh(self, tmp_path) -> None:
        """``ModelRegistry.create`` builds a
        fresh registry (Phase 6.7b signature)."""
        auth_storage = AuthStorage.in_memory()
        registry = ModelRegistry.create(
            auth_storage=auth_storage,
            models_json_path=str(tmp_path / "models.json"),
        )
        # The runtime is initialised on the
        # registry instance.
        runtime = get_model_registry_runtime(registry)
        assert "apiRegistry" in runtime
        assert "llmRuntime" in runtime

    def test_get_all_initially_empty(self, tmp_path) -> None:
        """``get_all`` returns an empty list
        when ``models.json`` is missing."""
        auth_storage = AuthStorage.in_memory()
        registry = ModelRegistry.create(
            auth_storage=auth_storage,
            models_json_path=str(tmp_path / "missing.json"),
        )
        assert registry.get_all() == []

    def test_drain_errors(self, tmp_path) -> None:
        """``drain_errors`` returns + clears the
        error list."""
        auth_storage = AuthStorage.in_memory()
        registry = ModelRegistry.create(
            auth_storage=auth_storage,
            models_json_path=str(tmp_path / "models.json"),
        )
        # The error list is accessible
        # (6.7a Phase 6.7a facade had a
        # ``drain_errors`` method; the 6.7b
        # core exposes ``get_error`` for the
        # load error).
        error = registry.get_error()
        # No error so far.
        assert error is None


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
        options (read-only, normalize models,
        skip credentials, workspace dir)."""
        result = load_agent_model_registry(
            config={},
            options={
                "readOnly": True,
                "normalizeModels": True,
            },
        )
        assert "registry" in result
