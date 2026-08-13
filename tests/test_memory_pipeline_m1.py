"""M1 memory-pipeline foundation test vectors.

Ports of the OpenClaw vitest suites covering the M1 modules:

- ``src/plugins/memory-embedding-providers.test.ts`` (registry)
- ``src/plugins/memory-embedding-provider-runtime.test.ts`` (runtime lookup)
- ``src/plugins/slots.test.ts`` (exclusive slot selection)
- ``src/plugins/memory-runtime.test.ts`` (runtime bridge; loader-seam subset)
- ``src/plugins/registry-registrars-memory.ts`` behavior (registrar gating)
- ``src/memory/root-memory-files.ts`` behavior (path resolution)

Source-of-truth citations are on each test. Vitest mock-based cases that
exercise the unported ``capability-provider-runtime.ts`` /
``active-runtime-registry.ts`` loaders are adapted to the ImportError
seams (module injection replaces ``vi.mock``).
"""
from __future__ import annotations

import asyncio
import sys
import types

from src.plugins.memory_embedding_providers import (
    clear_memory_embedding_providers,
    get_memory_embedding_provider as get_registered_adapter_only,
    get_registered_memory_embedding_provider,
    list_memory_embedding_providers as list_registered_adapters_only,
    list_registered_memory_embedding_providers,
    register_memory_embedding_provider,
    restore_registered_memory_embedding_providers,
)
from src.plugins import memory_embedding_provider_runtime as runtime_module
from src.plugins.memory_state import clear_memory_plugin_state
from src.plugins.slots import (
    apply_exclusive_slot_selection,
    has_kind,
    kinds_equal,
    reset_plugin_slots_to_defaults,
)
from src.plugins.memory_runtime import (
    _resolve_memory_runtime_plugin_ids,
    close_active_memory_search_manager,
    close_active_memory_search_managers,
    get_active_memory_search_manager,
    resolve_active_memory_backend_config,
)
from src.memory.root_memory_files import (
    CANONICAL_ROOT_MEMORY_FILENAME,
    LEGACY_ROOT_MEMORY_FILENAME,
    normalize_workspace_relative_path,
    resolve_canonical_root_memory_file,
    should_skip_root_memory_auxiliary_path,
)


def _adapter(id_: str) -> dict:
    """Mirrors ``createAdapter`` (memory-embedding-providers.test.ts:17-22)."""

    async def create(_options=None):
        return {"provider": None}

    return {"id": id_, "create": create}


def _reset():
    clear_memory_embedding_providers()
    clear_memory_plugin_state()


# ── memory-embedding-providers.test.ts ──────────────────────────────


def test_registers_and_lists_adapters_in_insertion_order():
    """memory-embedding-providers.test.ts:105-115."""
    _reset()
    alpha = _adapter("alpha")
    beta = _adapter("beta")
    register_memory_embedding_provider(alpha)
    register_memory_embedding_provider(beta)
    assert [a["id"] for a in list_registered_adapters_only()] == ["alpha", "beta"]
    assert get_registered_adapter_only("alpha") is alpha


def test_tracks_owner_plugin_ids_in_registered_snapshots():
    """memory-embedding-providers.test.ts:117-138 (case 1)."""
    _reset()
    alpha = _adapter("alpha")
    register_memory_embedding_provider(alpha, {"ownerPluginId": "memory-core"})
    entry = get_registered_memory_embedding_provider("alpha")
    assert entry == {"adapter": alpha, "ownerPluginId": "memory-core"}
    assert list_registered_memory_embedding_providers() == [entry]


def test_restores_registered_snapshots_with_owner_metadata():
    """memory-embedding-providers.test.ts:117-138 (case 2)."""
    _reset()
    beta = _adapter("beta")
    restore_registered_memory_embedding_providers(
        [{"adapter": beta, "ownerPluginId": "memory-core"}]
    )
    assert get_registered_memory_embedding_provider("beta") == {
        "adapter": beta,
        "ownerPluginId": "memory-core",
    }


def test_clears_the_registry():
    """memory-embedding-providers.test.ts:140-146."""
    _reset()
    register_memory_embedding_provider(_adapter("alpha"))
    clear_memory_embedding_providers()
    assert list_registered_adapters_only() == []


def test_stores_adapters_in_process_global_singleton_map():
    """memory-embedding-providers.test.ts:148-160. The TS source reads
    ``globalThis[Symbol.for("openclaw.memoryEmbeddingProviders")]``; the
    port keys the module-level ``_GLOBAL_STORE`` by the same string."""
    _reset()
    from src.plugins.memory_embedding_providers import (
        MEMORY_EMBEDDING_PROVIDERS_KEY,
        _GLOBAL_STORE,
    )

    alpha = _adapter("alpha")
    register_memory_embedding_provider(alpha, {"ownerPluginId": "memory-core"})
    assert MEMORY_EMBEDDING_PROVIDERS_KEY == "openclaw.memoryEmbeddingProviders"
    assert _GLOBAL_STORE[MEMORY_EMBEDDING_PROVIDERS_KEY]["alpha"] == {
        "adapter": alpha,
        "ownerPluginId": "memory-core",
    }


# ── memory-embedding-provider-runtime.test.ts ───────────────────────
# ``vi.mock("./capability-provider-runtime.js")`` is adapted to the
# ImportError seam: inject a stub module for the seam's relative import.

_SHARED_PKG = "src.plugins"
_CAP_MODULE = f"{_SHARED_PKG}.capability_provider_runtime"


class _CapabilityMock:
    """Adapts the vitest capability-runtime mocks to the Python seam."""

    def __init__(self, providers=None, provider_fn=None):
        self.providers = providers or []
        self.provider_fn = provider_fn or (lambda params: None)
        self.providers_calls = []
        self.provider_calls = []

    def __enter__(self):
        mod = types.ModuleType(_CAP_MODULE)

        def resolve_plugin_capability_providers(params):
            self.providers_calls.append(params)
            return self.providers

        def resolve_plugin_capability_provider(params):
            self.provider_calls.append(params)
            return self.provider_fn(params)

        mod.resolve_plugin_capability_providers = (
            resolve_plugin_capability_providers
        )
        mod.resolve_plugin_capability_provider = (
            resolve_plugin_capability_provider
        )
        self._prior = sys.modules.get(_CAP_MODULE)
        sys.modules[_CAP_MODULE] = mod
        return self

    def __exit__(self, *exc):
        if self._prior is None:
            sys.modules.pop(_CAP_MODULE, None)
        else:
            sys.modules[_CAP_MODULE] = self._prior
        return False


def test_merges_registered_and_capability_fallback_adapters():
    """memory-embedding-provider-runtime.test.ts:46-59."""
    _reset()
    register_memory_embedding_provider(_adapter("registered"))
    with _CapabilityMock(providers=[_adapter("capability")]) as cap:
        ids = [
            a["id"] for a in runtime_module.list_memory_embedding_providers()
        ]
        assert ids == ["registered", "capability"]
        got = runtime_module.get_memory_embedding_provider("registered")
        assert got is not None and got["id"] == "registered"
        assert len(cap.providers_calls) == 1


def test_falls_back_to_capability_adapters_when_registry_cold():
    """memory-embedding-provider-runtime.test.ts:61-75."""
    _reset()
    ollama = _adapter("ollama")
    with _CapabilityMock(
        providers=[ollama], provider_fn=lambda p: ollama
    ) as cap:
        ids = [
            a["id"] for a in runtime_module.list_memory_embedding_providers()
        ]
        assert ids == ["ollama"]
        got = runtime_module.get_memory_embedding_provider("ollama")
        assert got is not None and got["id"] == "ollama"
        assert len(cap.providers_calls) == 1
        assert cap.provider_calls[0] == {
            "key": "memoryEmbeddingProviders",
            "providerId": "ollama",
            "cfg": None,
        }


def test_uses_configured_provider_api_as_memory_adapter_owner():
    """memory-embedding-provider-runtime.test.ts:77-107."""
    _reset()
    ollama = _adapter("ollama")
    config = {
        "models": {
            "providers": {
                "ollama-5080": {
                    "api": "ollama",
                    "baseUrl": "http://10.0.0.8:11435",
                    "models": [],
                }
            }
        }
    }

    def provider_fn(params):
        return ollama if params.get("providerId") == "ollama" else None

    with _CapabilityMock(provider_fn=provider_fn) as cap:
        assert (
            runtime_module.get_memory_embedding_provider("ollama-5080", config)
            is ollama
        )
        assert {
            "key": "memoryEmbeddingProviders",
            "providerId": "ollama-5080",
            "cfg": config,
        } in cap.provider_calls
        assert {
            "key": "memoryEmbeddingProviders",
            "providerId": "ollama",
            "cfg": config,
        } in cap.provider_calls


def test_uses_registered_adapters_through_configured_provider_api():
    """memory-embedding-provider-runtime.test.ts:109-127."""
    _reset()
    ollama = _adapter("ollama")
    register_memory_embedding_provider(ollama)
    with _CapabilityMock() as cap:
        assert (
            runtime_module.get_memory_embedding_provider(
                "ollama-gpu1",
                {
                    "models": {
                        "providers": {
                            "ollama-gpu1": {
                                "api": "ollama",
                                "baseUrl": "http://ollama-host:11435",
                                "models": [],
                            }
                        }
                    }
                },
            )
            is ollama
        )
        assert cap.provider_calls == []


def test_prefers_registered_over_capability_adapters_same_id():
    """memory-embedding-provider-runtime.test.ts:129-144."""
    _reset()
    registered = _adapter("openai")
    register_memory_embedding_provider(registered)
    with _CapabilityMock(providers=[_adapter("openai")]) as cap:
        assert (
            runtime_module.get_memory_embedding_provider("openai")
            is registered
        )
        ids = [
            a["id"] for a in runtime_module.list_memory_embedding_providers()
        ]
        assert ids == ["openai"]
        assert len(cap.providers_calls) == 1


# ── slots.test.ts ───────────────────────────────────────────────────


def test_resets_every_slot_owned_by_the_plugin():
    """slots.test.ts:13-20."""
    assert reset_plugin_slots_to_defaults(
        {"memory": "dual-plugin", "contextEngine": "dual-plugin"},
        "dual-plugin",
    ) == {"memory": "memory-core", "contextEngine": "legacy"}


def test_preserves_slot_state_when_plugin_owns_no_slot():
    """slots.test.ts:22-27."""
    slots = {"memory": "memory-core", "contextEngine": "legacy"}
    assert reset_plugin_slots_to_defaults(slots, "other-plugin") is slots
    assert reset_plugin_slots_to_defaults(None, "other-plugin") is None


def _memory_selection(config, selected_id="memory"):
    """Mirrors ``runMemorySelection`` (slots.test.ts:44-55)."""
    return apply_exclusive_slot_selection(
        {
            "config": config,
            "selectedId": selected_id,
            "selectedKind": "memory",
            "registry": {
                "plugins": [
                    {"id": "memory-core", "kind": "memory"},
                    {"id": "memory", "kind": "memory"},
                ]
            },
        }
    )


def _memory_config(plugins=None):
    """Mirrors ``createMemoryConfig`` (slots.test.ts:31-42)."""
    plugins = plugins or {}
    return {
        "plugins": {
            **plugins,
            "entries": {
                **(plugins.get("entries") or {}),
                "memory": {
                    "enabled": True,
                    **((plugins.get("entries") or {}).get("memory") or {}),
                },
            },
        }
    }


def test_selects_slot_and_disables_other_entries_for_same_kind():
    """slots.test.ts:139-182 (case 1)."""
    result = _memory_selection(
        _memory_config(
            {
                "slots": {"memory": "memory-core"},
                "entries": {"memory-core": {"enabled": True}},
            }
        )
    )
    assert result["changed"] is True
    assert result["config"]["plugins"]["slots"]["memory"] == "memory"
    assert (
        result["config"]["plugins"]["entries"]["memory-core"]["enabled"]
        is False
    )
    assert result["warnings"] == [
        'Exclusive slot "memory" switched from "memory-core" to "memory".',
        'Disabled other "memory" slot plugins: memory-core.',
    ]


def test_warns_when_slot_falls_back_to_default():
    """slots.test.ts:139-182 (case 2)."""
    result = _memory_selection(_memory_config())
    assert result["changed"] is True
    assert result["warnings"] == [
        'Exclusive slot "memory" switched from "memory-core" to "memory".',
        'Disabled other "memory" slot plugins: memory-core.',
    ]


def test_keeps_disabled_competing_plugins_without_disable_warnings():
    """slots.test.ts:139-182 (case 3)."""
    result = _memory_selection(
        _memory_config({"entries": {"memory-core": {"enabled": False}}})
    )
    assert result["changed"] is True
    assert (
        result["config"]["plugins"]["entries"]["memory-core"]["enabled"]
        is False
    )
    assert result["warnings"] == [
        'Exclusive slot "memory" switched from "memory-core" to "memory".',
    ]


def test_does_nothing_when_slot_already_matches():
    """slots.test.ts:184-206 (case 1)."""
    config = _memory_config({"slots": {"memory": "memory"}})
    result = apply_exclusive_slot_selection(
        {
            "config": config,
            "selectedId": "memory",
            "selectedKind": "memory",
            "registry": {"plugins": [{"id": "memory", "kind": "memory"}]},
        }
    )
    assert result["changed"] is False
    assert result["warnings"] == []
    assert result["config"] is config


def test_skips_changes_when_no_exclusive_slot_applies():
    """slots.test.ts:184-206 (case 2)."""
    config: dict = {}
    result = apply_exclusive_slot_selection(
        {"config": config, "selectedId": "custom"}
    )
    assert result["changed"] is False
    assert result["config"] is config


def test_applies_slot_selection_for_each_kind_in_multi_kind_array():
    """slots.test.ts:208-233."""
    config = {
        "plugins": {
            "slots": {"memory": "memory-core", "contextEngine": "legacy"},
            "entries": {
                "memory-core": {"enabled": True},
                "legacy": {"enabled": True},
            },
        }
    }
    result = apply_exclusive_slot_selection(
        {
            "config": config,
            "selectedId": "dual-plugin",
            "selectedKind": ["memory", "context-engine"],
            "registry": {
                "plugins": [
                    {"id": "memory-core", "kind": "memory"},
                    {"id": "legacy", "kind": "context-engine"},
                    {"id": "dual-plugin", "kind": ["memory", "context-engine"]},
                ]
            },
        }
    )
    assert result["changed"] is True
    assert result["config"]["plugins"]["slots"]["memory"] == "dual-plugin"
    assert (
        result["config"]["plugins"]["slots"]["contextEngine"] == "dual-plugin"
    )
    assert (
        result["config"]["plugins"]["entries"]["memory-core"]["enabled"]
        is False
    )
    assert result["config"]["plugins"]["entries"]["legacy"]["enabled"] is False


def test_does_not_disable_dual_kind_plugin_owning_another_slot():
    """slots.test.ts:235-257."""
    config = {
        "plugins": {
            "slots": {"memory": "dual-plugin", "contextEngine": "dual-plugin"},
            "entries": {"dual-plugin": {"enabled": True}},
        }
    }
    result = apply_exclusive_slot_selection(
        {
            "config": config,
            "selectedId": "new-memory",
            "selectedKind": "memory",
            "registry": {
                "plugins": [
                    {"id": "dual-plugin", "kind": ["memory", "context-engine"]},
                    {"id": "new-memory", "kind": "memory"},
                ]
            },
        }
    )
    assert result["changed"] is True
    assert result["config"]["plugins"]["slots"]["memory"] == "new-memory"
    assert (
        result["config"]["plugins"]["entries"]["dual-plugin"].get("enabled")
        is not False
    )


def test_does_not_disable_dual_kind_plugin_owning_slot_via_default():
    """slots.test.ts:259-282."""
    config = {
        "plugins": {
            "slots": {"memory": "legacy"},
            "entries": {"legacy": {"enabled": True}},
        }
    }
    result = apply_exclusive_slot_selection(
        {
            "config": config,
            "selectedId": "new-memory",
            "selectedKind": "memory",
            "registry": {
                "plugins": [
                    {"id": "legacy", "kind": ["memory", "context-engine"]},
                    {"id": "new-memory", "kind": "memory"},
                ]
            },
        }
    )
    assert result["changed"] is True
    assert result["config"]["plugins"]["slots"]["memory"] == "new-memory"
    assert (
        result["config"]["plugins"]["entries"]["legacy"].get("enabled")
        is not False
    )


def test_has_kind_vectors():
    """slots.test.ts:285-299."""
    assert has_kind(None, "memory") is False
    assert has_kind("memory", "memory") is True
    assert has_kind("memory", "context-engine") is False
    assert has_kind(["memory", "context-engine"], "memory") is True
    assert has_kind(["memory", "context-engine"], "context-engine") is True


def test_kinds_equal_vectors():
    """slots.test.ts:301-325."""
    assert kinds_equal(None, None) is True
    assert kinds_equal("memory", "memory") is True
    assert kinds_equal("memory", "context-engine") is False
    assert (
        kinds_equal(
            ["memory", "context-engine"], ["context-engine", "memory"]
        )
        is True
    )
    assert kinds_equal("memory", ["memory"]) is True
    assert kinds_equal("memory", ["memory", "context-engine"]) is False


# ── memory-runtime.ts (loader-seam subset of memory-runtime.test.ts) ─


def test_memory_slot_plugin_id_resolution_vectors():
    """resolveMemoryRuntimePluginIds semantics (memory-runtime.ts:11-22 +
    config-normalization-shared.ts:232-241 slot defaulting)."""
    # Unset slot defaults to the implicit slot owner "memory-core".
    assert _resolve_memory_runtime_plugin_ids({}) == ["memory-core"]
    assert _resolve_memory_runtime_plugin_ids({"plugins": {}}) == [
        "memory-core"
    ]
    # Explicit slot.
    assert _resolve_memory_runtime_plugin_ids(
        {"plugins": {"slots": {"memory": "memory-lancedb"}}}
    ) == ["memory-lancedb"]
    # "none" disables (memory-runtime.test.ts:221-247).
    assert (
        _resolve_memory_runtime_plugin_ids(
            {"plugins": {"slots": {"memory": "none"}}}
        )
        == []
    )
    # Globally disabled plugins (memory-runtime.test.ts:249-265).
    assert (
        _resolve_memory_runtime_plugin_ids({"plugins": {"enabled": False}})
        == []
    )
    # Denied slot plugin (memory-runtime.test.ts:267-299 case 1).
    assert (
        _resolve_memory_runtime_plugin_ids(
            {
                "plugins": {
                    "deny": ["memory-core"],
                    "slots": {"memory": "memory-core"},
                }
            }
        )
        == []
    )
    # Entry-disabled slot plugin (memory-runtime.test.ts:267-299 case 2).
    assert (
        _resolve_memory_runtime_plugin_ids(
            {
                "plugins": {
                    "entries": {"memory-core": {"enabled": False}},
                    "slots": {"memory": "memory-core"},
                }
            }
        )
        == []
    )


def test_unavailable_memory_runtime_returns_error_result():
    """memory-runtime.test.ts:221-247 result shape (loaders unported →
    runtime stays unset → "memory plugin unavailable")."""
    _reset()
    result = asyncio.run(
        get_active_memory_search_manager(
            {"cfg": {"plugins": {"slots": {"memory": "none"}}}, "agentId": "main"}
        )
    )
    assert result == {"manager": None, "error": "memory plugin unavailable"}
    assert (
        resolve_active_memory_backend_config({"cfg": {}, "agentId": "main"})
        is None
    )


class _FakeRuntime:
    """Mirrors ``createMemoryRuntimeFixture`` (memory-runtime.test.ts:68-74)."""

    def __init__(self):
        self.search_calls = []
        self.backend_calls = []
        self.close_all_calls = 0
        self.close_one_calls = []

    async def get_memory_search_manager(self, params):
        self.search_calls.append(params)
        return {"manager": None, "error": "no index"}

    def resolve_memory_backend_config(self, params):
        self.backend_calls.append(params)
        return {"backend": "builtin"}

    async def close_all_memory_search_managers(self):
        self.close_all_calls += 1

    async def close_memory_search_manager(self, params):
        self.close_one_calls.append(params)


def test_registered_runtime_is_used_without_reloading_plugins():
    """memory-runtime.test.ts:301-320 + 322-363: an already-registered
    runtime serves search/backends/close without bootstrap."""
    _reset()
    from src.plugins.memory_state import register_memory_runtime_for_plugin

    runtime = _FakeRuntime()
    register_memory_runtime_for_plugin("memory-core", runtime)
    try:
        result = asyncio.run(
            get_active_memory_search_manager(
                {"cfg": {"plugins": {}}, "agentId": "main"}
            )
        )
        assert result == {"manager": None, "error": "no index"}
        assert resolve_active_memory_backend_config(
            {"cfg": {"plugins": {}}, "agentId": "main"}
        ) == {"backend": "builtin"}
        asyncio.run(close_active_memory_search_managers({}))
        assert runtime.close_all_calls == 1
        cfg = {"plugins": {}}
        asyncio.run(
            close_active_memory_search_manager({"cfg": cfg, "agentId": "main"})
        )
        assert runtime.close_one_calls == [{"cfg": cfg, "agentId": "main"}]
    finally:
        _reset()


def test_close_managers_does_not_bootstrap_runtime():
    """memory-runtime.test.ts:322-349 (case 1): closing with no runtime
    registered is a silent no-op."""
    _reset()
    asyncio.run(
        close_active_memory_search_managers(
            {"plugins": {}, "channels": {"memory": {"enabled": True}}}
        )
    )
    asyncio.run(
        close_active_memory_search_manager({"cfg": {}, "agentId": "main"})
    )


# ── registry-registrars-memory.ts (registrar gating) ────────────────


def _make_state():
    from src.plugins.state import create_plugin_registry_state

    return create_plugin_registry_state({"logger": None})


def _make_registrars(state):
    from src.plugins.registrars import create_plugin_registrars

    return create_plugin_registrars(state)


def _record(**over):
    base = {
        "id": "memory-core",
        "name": "Memory Core",
        "kind": "memory",
        "source": "bundled",
        "rootDir": "/plugins/memory-core",
    }
    base.update(over)
    return base


def test_memory_registrar_rejects_non_memory_plugin():
    """registry-registrars-memory.ts:22-25 requireMemorySlot throw."""
    _reset()
    state = _make_state()
    registrars = _make_registrars(state)
    try:
        registrars["registerMemoryCapability"](
            _record(kind="context-engine"), {"kind": "capability"}
        )
        raised = False
    except ValueError as err:
        raised = True
        assert "only memory plugins can register a memory capability" in str(
            err
        )
    assert raised
    _reset()


def test_memory_registrar_skips_unselected_dual_kind_plugin():
    """registry-registrars-memory.ts:26-34: dual-kind without
    memorySlotSelected warns + skips."""
    _reset()
    from src.plugins.memory_state import get_memory_capability_registration

    state = _make_state()
    registrars = _make_registrars(state)
    registrars["registerMemoryCapability"](
        _record(kind=["memory", "context-engine"]), {"kind": "capability"}
    )
    assert get_memory_capability_registration() is None
    diagnostics = state["registry"]["diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["level"] == "warn"
    assert (
        "dual-kind plugin not selected for memory slot" in diagnostics[0]["message"]
    )
    _reset()


def test_memory_registrar_registers_capability_for_selected_plugin():
    """registry-registrars-memory.ts:38-45 happy path."""
    _reset()
    from src.plugins.memory_state import get_memory_capability_registration

    state = _make_state()
    registrars = _make_registrars(state)
    capability = {"kind": "capability"}
    registrars["registerMemoryCapability"](_record(), capability)
    registration = get_memory_capability_registration()
    assert registration is not None
    assert registration[0] == "memory-core"
    _reset()


def test_memory_prompt_supplement_requires_callable_builder():
    """registry-registrars-memory.ts:56-70: non-function builder errors."""
    _reset()
    state = _make_state()
    registrars = _make_registrars(state)
    registrars["registerMemoryPromptSupplement"](_record(), "not-a-function")
    diagnostics = state["registry"]["diagnostics"]
    assert diagnostics[-1]["level"] == "error"
    assert (
        diagnostics[-1]["message"]
        == "memory prompt supplement registration missing builder"
    )
    _reset()


def test_embedding_provider_requires_slot_or_contract():
    """registry-registrars-memory.ts:113-129: non-memory plugin without a
    contracts.memoryEmbeddingProviders declaration errors."""
    _reset()
    state = _make_state()
    registrars = _make_registrars(state)
    registrars["registerMemoryEmbeddingProvider"](
        _record(id="other", kind="channel"), _adapter("voyage")
    )
    diagnostics = state["registry"]["diagnostics"]
    assert diagnostics[-1]["level"] == "error"
    assert (
        "plugin must own memory slot or declare "
        "contracts.memoryEmbeddingProviders for adapter: voyage"
        == diagnostics[-1]["message"]
    )
    assert get_registered_memory_embedding_provider("voyage") is None
    _reset()


def test_embedding_provider_contract_declared_plugin_registers():
    """registry-registrars-memory.ts:121 contract path + 141-148 registry
    append."""
    _reset()
    state = _make_state()
    registrars = _make_registrars(state)
    adapter = _adapter("voyage")
    registrars["registerMemoryEmbeddingProvider"](
        _record(
            id="voyage-plugin",
            kind="channel",
            contracts={"memoryEmbeddingProviders": ["voyage"]},
        ),
        adapter,
    )
    assert get_registered_memory_embedding_provider("voyage") == {
        "adapter": adapter,
        "ownerPluginId": "voyage-plugin",
    }
    entries = state["registry"]["memoryEmbeddingProviders"]
    assert entries[-1]["pluginId"] == "voyage-plugin"
    assert entries[-1]["provider"] is adapter
    _reset()


def test_embedding_provider_duplicate_reports_owner():
    """registry-registrars-memory.ts:130-140 duplicate diagnostics."""
    _reset()
    state = _make_state()
    registrars = _make_registrars(state)
    adapter = _adapter("openai")
    registrars["registerMemoryEmbeddingProvider"](_record(), adapter)
    registrars["registerMemoryEmbeddingProvider"](
        _record(id="second-memory", memorySlotSelected=True), _adapter("openai")
    )
    diagnostics = state["registry"]["diagnostics"]
    assert diagnostics[-1]["level"] == "error"
    assert (
        diagnostics[-1]["message"]
        == "memory embedding provider already registered: openai"
        " (owner: memory-core)"
    )
    _reset()


# ── root-memory-files.ts behavior ───────────────────────────────────


def test_normalize_workspace_relative_path_vectors():
    """root-memory-files.ts normalizeWorkspaceRelativePath semantics."""
    assert normalize_workspace_relative_path(" MEMORY.md ") == "MEMORY.md"
    assert normalize_workspace_relative_path("./memory.md") == "memory.md"
    assert (
        normalize_workspace_relative_path("a\\b\\memory.md") == "a/b/memory.md"
    )


async def test_resolve_canonical_root_memory_file(tmp_path):
    """root-memory-files.ts resolveCanonicalRootMemoryFile: exact-case
    regular file → absolute path; missing → None."""
    assert await resolve_canonical_root_memory_file(str(tmp_path)) is None
    target = tmp_path / CANONICAL_ROOT_MEMORY_FILENAME
    target.write_text("# Memory Index\n", encoding="utf-8")
    resolved = await resolve_canonical_root_memory_file(str(tmp_path))
    assert resolved is not None
    assert resolved.endswith(CANONICAL_ROOT_MEMORY_FILENAME)


async def test_should_skip_root_memory_auxiliary_path(tmp_path):
    """root-memory-files.ts shouldSkipRootMemoryAuxiliaryPath: legacy
    memory.md and repair-dir entries skip; canonical file does not."""
    workspace = str(tmp_path)
    legacy = str(tmp_path / LEGACY_ROOT_MEMORY_FILENAME)
    canonical = str(tmp_path / CANONICAL_ROOT_MEMORY_FILENAME)
    repair_entry = str(
        tmp_path / ".openclaw-repair" / "root-memory" / "MEMORY.md"
    )
    assert should_skip_root_memory_auxiliary_path(
        {"workspaceDir": workspace, "absolutePath": legacy}
    )
    assert should_skip_root_memory_auxiliary_path(
        {"workspaceDir": workspace, "absolutePath": repair_entry}
    )
    assert not should_skip_root_memory_auxiliary_path(
        {"workspaceDir": workspace, "absolutePath": canonical}
    )
    # Paths outside the workspace never skip.
    assert not should_skip_root_memory_auxiliary_path(
        {"workspaceDir": workspace, "absolutePath": "/elsewhere/memory.md"}
    )
