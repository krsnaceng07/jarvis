"""Phase 6.8a — Layer 2 settings manager foundation.

Tests for
:class:`jarvis.agents.sessions.settings_manager.SettingsManager`
+ the file / in-memory backends.

- ``SettingsManager.create`` + ``inMemory``
  + ``fromStorage`` factories.
- ``reload()`` re-reads + applies the
  modified-tracking reset.
- ``flush()`` waits for the in-flight write.
- ``getGlobalSettings`` /
  ``getProjectSettings`` /
  ``getSettings` (the merged view).
- ``applyOverrides`` (runtime, non-persisted
  overrides layered on top of global + project).
- ``getSessionDir`` (``~`` / ``~/foo`` /
  absolute).
- ``drainErrors`` returns + clears the errors.
- The file backend (read + write + create
  parent dir).
- The in-memory backend (per-scope storage).
- ``migrateSettings`` (queueMode →
  steeringMode, websockets bool → transport,
  old skills object → array, retry.maxDelayMs
  → retry.provider.maxRetryDelayMs).
- ``deepMerge`` (nested dict merge + replace).
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
    CONFIG_DIR_NAME,
    FileSettingsStorage,
    InMemorySettingsStorage,
    SettingsManager,
)


# ── Factories ─────────────────────────────────────────────────


class TestFactories:
    def test_in_memory(self) -> None:
        """``SettingsManager.inMemory`` builds a
        manager with no file I/O."""
        sm = SettingsManager.in_memory(
            settings={"defaultProvider": "anthropic"}
        )
        # The settings are loaded.
        assert sm.get_global_settings()["defaultProvider"] == "anthropic"

    def test_from_storage(self) -> None:
        """``SettingsManager.fromStorage`` wraps
        a custom backend."""
        storage = InMemorySettingsStorage()
        sm = SettingsManager.from_storage(storage)
        # The merged settings start empty.
        assert sm.get_settings() == {}

    def test_create_with_cwd(self, tmp_path) -> None:
        """``SettingsManager.create`` builds a
        file-backed manager with a project
        scope."""
        sm = SettingsManager.create(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
        )
        # The settings start empty.
        assert sm.get_settings() == {}


# ── getGlobalSettings / getProjectSettings / getSettings ───


class TestGetters:
    def test_get_global_settings(self) -> None:
        sm = SettingsManager.in_memory(
            settings={"defaultProvider": "anthropic"}
        )
        global_settings = sm.get_global_settings()
        assert global_settings["defaultProvider"] == "anthropic"
        # The returned object is a deep copy.
        global_settings["defaultProvider"] = "modified"
        assert sm.get_global_settings()["defaultProvider"] == "anthropic"

    def test_get_project_settings(self) -> None:
        sm = SettingsManager.in_memory(
            settings={"defaultProvider": "anthropic"}
        )
        project_settings = sm.get_project_settings()
        assert project_settings == {}

    def test_get_settings_merges(self) -> None:
        """``getSettings`` returns the merged
        view (global + project + runtime
        overrides)."""
        sm = SettingsManager.in_memory(
            settings={
                "defaultProvider": "anthropic",
                "defaultModel": "claude-3-5-sonnet",
            }
        )
        sm.apply_overrides({"defaultModel": "claude-3-opus"})
        merged = sm.get_settings()
        assert merged["defaultProvider"] == "anthropic"
        assert merged["defaultModel"] == "claude-3-opus"


# ── applyOverrides ──────────────────────────────────────────


class TestApplyOverrides:
    def test_runtime_overrides(self) -> None:
        sm = SettingsManager.in_memory(
            settings={"defaultProvider": "anthropic"}
        )
        # Apply a runtime override.
        sm.apply_overrides({"defaultModel": "claude-3-5-sonnet"})
        # The merged view picks up the override.
        assert sm.get_settings()["defaultModel"] == "claude-3-5-sonnet"
        # But the underlying global setting
        # is unchanged.
        assert "defaultModel" not in sm.get_global_settings()

    def test_multiple_overrides(self) -> None:
        sm = SettingsManager.in_memory()
        sm.apply_overrides({"a": 1})
        sm.apply_overrides({"b": 2})
        # The overrides are merged.
        merged = sm.get_settings()
        assert merged["a"] == 1
        assert merged["b"] == 2


# ── reload / flush ──────────────────────────────────────────


class TestReloadAndFlush:
    def test_reload_re_reads(self, tmp_path) -> None:
        """``reload()`` re-reads the global +
        project settings."""
        agent_dir = str(tmp_path / "agent")
        os.makedirs(agent_dir, exist_ok=True)
        global_path = os.path.join(agent_dir, "settings.json")
        with open(global_path, "w", encoding="utf-8") as f:
            json.dump({"defaultProvider": "anthropic"}, f)
        sm = SettingsManager.create(
            cwd=str(tmp_path), agent_dir=agent_dir
        )
        assert sm.get_global_settings()["defaultProvider"] == "anthropic"
        # Update the file.
        with open(global_path, "w", encoding="utf-8") as f:
            json.dump({"defaultProvider": "openai"}, f)
        # Reload.
        asyncio.run(sm.reload())
        assert sm.get_global_settings()["defaultProvider"] == "openai"

    def test_flush_waits(self) -> None:
        sm = SettingsManager.in_memory(
            settings={"defaultProvider": "anthropic"}
        )
        # ``flush`` should complete without
        # error (the in-memory backend has no
        # async writes).
        asyncio.run(sm.flush())


# ── getSessionDir ──────────────────────────────────────────


class TestGetSessionDir:
    def test_no_session_dir(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_session_dir() is None

    def test_tilde_only(self) -> None:
        sm = SettingsManager.in_memory(settings={"sessionDir": "~"})
        assert sm.get_session_dir() == os.path.expanduser("~")

    def test_tilde_slash(self) -> None:
        sm = SettingsManager.in_memory(
            settings={"sessionDir": "~/sessions"}
        )
        assert sm.get_session_dir() == os.path.join(
            os.path.expanduser("~"), "sessions"
        )

    def test_absolute_path(self) -> None:
        sm = SettingsManager.in_memory(
            settings={"sessionDir": "/var/sessions"}
        )
        assert sm.get_session_dir() == "/var/sessions"


# ── drainErrors ─────────────────────────────────────────────


class TestDrainErrors:
    def test_no_errors_initially(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.drain_errors() == []

    def test_drain_clears(self) -> None:
        sm = SettingsManager.in_memory()
        sm._record_error("global", RuntimeError("test"))
        errors = sm.drain_errors()
        assert len(errors) == 1
        assert errors[0]["scope"] == "global"
        # The error list is cleared.
        assert sm.drain_errors() == []


# ── FileSettingsStorage ──────────────────────────────────────


class TestFileSettingsStorage:
    def test_writes_global(self, tmp_path) -> None:
        agent_dir = str(tmp_path / "agent")
        os.makedirs(agent_dir, exist_ok=True)
        storage = FileSettingsStorage(
            cwd=str(tmp_path), agent_dir=agent_dir
        )
        written: list = []
        def _write(current):
            written.append(current)
            return "NEW"
        storage.with_lock("global", _write)
        # The file was created.
        assert os.path.exists(os.path.join(agent_dir, "settings.json"))
        with open(os.path.join(agent_dir, "settings.json"), "r") as f:
            assert f.read() == "NEW"

    def test_creates_parent_dir_for_project(self, tmp_path) -> None:
        """The project-scope write creates the
        ``.jarvis`` parent dir if missing."""
        storage = FileSettingsStorage(cwd=str(tmp_path))
        def _write(_current):
            return "PROJECT"
        storage.with_lock("project", _write)
        project_path = os.path.join(
            str(tmp_path), CONFIG_DIR_NAME, "settings.json"
        )
        assert os.path.exists(project_path)
        with open(project_path, "r") as f:
            assert f.read() == "PROJECT"

    def test_reads_existing(self, tmp_path) -> None:
        agent_dir = str(tmp_path / "agent")
        os.makedirs(agent_dir, exist_ok=True)
        global_path = os.path.join(agent_dir, "settings.json")
        with open(global_path, "w", encoding="utf-8") as f:
            f.write("EXISTING")
        storage = FileSettingsStorage(
            cwd=str(tmp_path), agent_dir=agent_dir
        )
        captured: list = []
        def _read(current):
            captured.append(current)
            return None
        storage.with_lock("global", _read)
        assert captured == ["EXISTING"]


# ── InMemorySettingsStorage ─────────────────────────────────


class TestInMemorySettingsStorage:
    def test_stores_per_scope(self) -> None:
        storage = InMemorySettingsStorage()
        storage.with_lock("global", lambda _c: "GLOBAL")
        storage.with_lock("project", lambda _c: "PROJECT")
        # The two scopes are stored separately.
        captured_global: list = []
        captured_project: list = []
        storage.with_lock("global", lambda c: (captured_global.append(c), None)[1])
        storage.with_lock(
            "project", lambda c: (captured_project.append(c), None)[1])
        assert captured_global == ["GLOBAL"]
        assert captured_project == ["PROJECT"]

    def test_no_write_returns_none(self) -> None:
        storage = InMemorySettingsStorage()
        storage.with_lock("global", lambda _c: None)
        # The storage is unchanged.
        assert storage.global_value is None


# ── migrateSettings ────────────────────────────────────────


class TestMigrateSettings:
    def test_queue_mode_to_steering_mode(self) -> None:
        from src.agents.sessions.settings_manager import (
            _migrate_settings,
        )
        result = _migrate_settings({"queueMode": "all"})
        assert result["steeringMode"] == "all"
        assert "queueMode" not in result

    def test_websockets_bool_to_transport(self) -> None:
        from src.agents.sessions.settings_manager import (
            _migrate_settings,
        )
        result = _migrate_settings({"websockets": True})
        assert result["transport"] == "websocket"
        assert "websockets" not in result

    def test_skills_object_to_array(self) -> None:
        from src.agents.sessions.settings_manager import (
            _migrate_settings,
        )
        result = _migrate_settings(
            {
                "skills": {
                    "enableSkillCommands": True,
                    "customDirectories": ["/path/a", "/path/b"],
                }
            }
        )
        assert result["skills"] == ["/path/a", "/path/b"]
        assert result["enableSkillCommands"] is True

    def test_retry_max_delay_to_provider(self) -> None:
        from src.agents.sessions.settings_manager import (
            _migrate_settings,
        )
        result = _migrate_settings(
            {"retry": {"maxDelayMs": 5000}}
        )
        assert result["retry"]["provider"]["maxRetryDelayMs"] == 5000
        assert "maxDelayMs" not in result["retry"]


# ── deepMerge ──────────────────────────────────────────────


class TestDeepMerge:
    def test_merges_nested_dicts(self) -> None:
        from src.agents.sessions.settings_manager import _deep_merge
        result = _deep_merge(
            {"a": 1, "b": {"c": 2, "d": 3}},
            {"b": {"c": 20, "e": 4}},
        )
        assert result == {"a": 1, "b": {"c": 20, "d": 3, "e": 4}}

    def test_replaces_non_dict(self) -> None:
        from src.agents.sessions.settings_manager import _deep_merge
        # A list in the base is replaced by
        # the override.
        result = _deep_merge({"a": [1, 2, 3]}, {"a": [4, 5]})
        assert result == {"a": [4, 5]}

    def test_replaces_with_dict(self) -> None:
        from src.agents.sessions.settings_manager import _deep_merge
        result = _deep_merge({"a": 1}, {"a": {"x": 1}})
        assert result == {"a": {"x": 1}}


# ── CONFIG_DIR_NAME ─────────────────────────────────────────


class TestConfigDirName:
    def test_config_dir_name(self) -> None:
        assert CONFIG_DIR_NAME == ".jarvis"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
