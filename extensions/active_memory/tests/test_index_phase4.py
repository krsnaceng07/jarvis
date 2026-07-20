"""Tests for extensions/active_memory/{index, doctor_contract_api}.py.

Phase 4.2c: ports the active-memory entry + slash command +
doctor state migration. The tests focus on:

- ``register_active_memory`` registers the slash command
  and ``before_prompt_build`` hook without raising.
- The doctor state migration reads the legacy
  ``session-toggles.json`` file and imports missing
  entries into the plugin-state keyed store.
- The doctor state migration is a no-op when no legacy
  file / no entries.
- ``state_migrations`` returns the expected migration
  entries.
"""

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportReturnType=false
# pyright: reportTypedDictNotRequiredAccess=false

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.active_memory.doctor_contract_api import (  # noqa: E402
    MAX_TOGGLE_ENTRIES,
    SESSION_TOGGLES_NAMESPACE,
    active_memory_toggle_key,
    resolve_toggle_state_path,
    state_migrations,
)
from extensions.active_memory.index import (  # noqa: E402
    MEMORY_CORE_PLUGIN_ID,
    register_active_memory,
)

# ── index: register_active_memory ─────────────────────────────────


class TestRegisterActiveMemory:
    def test_register_does_not_raise_on_minimal_api(self) -> None:
        from jarvis_sdk import PluginApi, PluginContext

        ctx = PluginContext(
            plugin_id="active_memory",
            plugin_kind="memory",
            data_dir=Path("C:/tmp/jarvis"),
            workspace=ROOT,
        )
        api = PluginApi(ctx)
        # Should not raise even though the api has no
        # ``register_command`` / ``on`` / ``runtime`` etc.
        register_active_memory(api)


# ── doctor_contract_api: state_migrations shape ─────────────────


class TestStateMigrations:
    def test_returns_expected_migration(self) -> None:
        migrations = state_migrations()
        assert len(migrations) == 1
        migration = migrations[0]
        assert migration["id"] == "active-memory-session-toggles-json-to-plugin-state"
        assert migration["label"] == "Active Memory session toggles"
        assert callable(migration["detectLegacyState"])
        assert callable(migration["migrateLegacyState"])


# ── doctor_contract_api: resolve_toggle_state_path ──────────────


class TestResolveToggleStatePath:
    def test_state_dir_joins_plugins_active_memory(self) -> None:
        out = resolve_toggle_state_path("C:/tmp/state")
        assert out.endswith("session-toggles.json")
        assert "active-memory" in out
        assert "plugins" in out


# ── doctor_contract_api: active_memory_toggle_key ────────────────


class TestActiveMemoryToggleKey:
    def test_deterministic_hex_64(self) -> None:
        key1 = active_memory_toggle_key("agent:a:k")
        key2 = active_memory_toggle_key("agent:a:k")
        assert key1 == key2
        assert len(key1) == 64
        assert all(c in "0123456789abcdef" for c in key1)

    def test_different_session_keys_differ(self) -> None:
        assert active_memory_toggle_key("a") != active_memory_toggle_key("b")


# ── doctor_contract_api: detectLegacyState ──────────────────────


class TestDetectLegacyToggleState:
    @pytest.mark.asyncio
    async def test_no_legacy_file_returns_none(self, tmp_path: Path) -> None:
        migrations = state_migrations()
        result = await migrations[0]["detectLegacyState"]({"stateDir": str(tmp_path)})
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_legacy_file_returns_none(self, tmp_path: Path) -> None:
        legacy_path = Path(resolve_toggle_state_path(tmp_path))
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text("{}", encoding="utf-8")
        migrations = state_migrations()
        result = await migrations[0]["detectLegacyState"]({"stateDir": str(tmp_path)})
        assert result is None

    @pytest.mark.asyncio
    async def test_with_disabled_entries_returns_preview(self, tmp_path: Path) -> None:
        legacy_path = Path(resolve_toggle_state_path(tmp_path))
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text(
            json.dumps(
                {
                    "sessions": {
                        "agent:a:k1": {"disabled": True, "updatedAt": 12345},
                        "agent:a:k2": {"disabled": True, "updatedAt": 12346},
                    }
                }
            ),
            encoding="utf-8",
        )
        migrations = state_migrations()
        result = await migrations[0]["detectLegacyState"]({"stateDir": str(tmp_path)})
        assert result is not None
        assert "2 entries" in result["preview"][0]

    @pytest.mark.asyncio
    async def test_skips_entries_with_disabled_false(self, tmp_path: Path) -> None:
        legacy_path = Path(resolve_toggle_state_path(tmp_path))
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text(
            json.dumps(
                {
                    "sessions": {
                        "agent:a:k1": {"disabled": False, "updatedAt": 12345},
                        "agent:a:k2": {"disabled": True, "updatedAt": 12346},
                    }
                }
            ),
            encoding="utf-8",
        )
        migrations = state_migrations()
        result = await migrations[0]["detectLegacyState"]({"stateDir": str(tmp_path)})
        assert result is not None
        # Only 1 entry should be detected (the disabled one).
        assert "1 entry" in result["preview"][0]


# ── doctor_contract_api: migrateLegacyState ────────────────────


class TestMigrateLegacyToggleState:
    @pytest.mark.asyncio
    async def test_migrate_empty_legacy_returns_empty(self, tmp_path: Path) -> None:
        migrations = state_migrations()
        result = await migrations[0]["migrateLegacyState"](
            {
                "stateDir": str(tmp_path),
                "context": {},
            }
        )
        assert result["changes"] == []
        assert result["warnings"] == []

    @pytest.mark.asyncio
    async def test_migrate_with_store_no_keyed_store(self, tmp_path: Path) -> None:
        legacy_path = Path(resolve_toggle_state_path(tmp_path))
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text(
            json.dumps({"sessions": {"agent:a:k1": {"disabled": True, "updatedAt": 12345}}}),
            encoding="utf-8",
        )
        migrations = state_migrations()
        result = await migrations[0]["migrateLegacyState"](
            {
                "stateDir": str(tmp_path),
                "context": {},  # no openPluginStateKeyedStore
            }
        )
        # No keyed store → warning, no changes
        assert "Skipped" in (result["warnings"][0] if result["warnings"] else "")

    @pytest.mark.asyncio
    async def test_migrate_happy_path(self, tmp_path: Path) -> None:
        legacy_path = Path(resolve_toggle_state_path(tmp_path))
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text(
            json.dumps(
                {
                    "sessions": {
                        "agent:a:k1": {"disabled": True, "updatedAt": 12345},
                        "agent:a:k2": {"disabled": True, "updatedAt": 12346},
                    }
                }
            ),
            encoding="utf-8",
        )

        # Stub keyed store that records register() calls.
        class _StubStore:
            def __init__(self) -> None:
                self._entries: list[tuple[str, Any]] = []

            async def entries(self) -> list[dict[str, Any]]:
                return [{"key": k, "value": v} for k, v in self._entries]

            async def register(self, key: str, value: Any) -> None:
                self._entries.append((key, value))

        store = _StubStore()

        def _open(params: dict[str, Any]) -> _StubStore:
            assert params.get("namespace") == SESSION_TOGGLES_NAMESPACE
            assert params.get("maxEntries") == MAX_TOGGLE_ENTRIES
            return store

        migrations = state_migrations()
        result = await migrations[0]["migrateLegacyState"](
            {
                "stateDir": str(tmp_path),
                "context": {"openPluginStateKeyedStore": _open},
            }
        )
        assert len(result["changes"]) >= 1
        assert "Migrated 2" in result["changes"][0]
        assert "entries" in result["changes"][0]
        assert len(store._entries) == 2
        # Verify the keys are SHA-256 hashes of the session keys
        for key, value in store._entries:
            assert key == active_memory_toggle_key(value["sessionKey"])


# ── index: MEMORY_CORE_PLUGIN_ID constant ───────────────────────


class TestMemoryCorePluginId:
    def test_value(self) -> None:
        assert MEMORY_CORE_PLUGIN_ID == "memory-core"
