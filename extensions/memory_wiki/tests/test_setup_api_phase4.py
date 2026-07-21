"""Tests for extensions/memory_wiki/setup_api.py.

Phase 4.3g-mr6: ports the OpenClaw
``setup-api.ts`` test surface. The tests
focus on:

- ``register_memory_wiki_setup`` registers
  a config-migration hook on hosts that
  expose ``register_config_migration``.
- The migration hook calls
  ``normalize_compatibility_config`` so
  the legacy ``bridge.readMemoryCore``
  flag is renamed to the canonical
  ``bridge.readMemoryArtifacts``.
- The registrar is a no-op on hosts that
  don't expose ``register_config_migration``.
"""

# ruff: noqa: S108 — test fixtures mirror the OpenClaw TS source

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

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

from extensions.memory_wiki.setup_api import register_memory_wiki_setup  # noqa: E402


class _RecordingApi:
    """A minimal PluginApi stand-in that records
    the registered migration hook."""

    def __init__(self) -> None:
        self.migrations: list = []

    def register_config_migration(self, hook) -> None:
        self.migrations.append(hook)


class _NoHookApi:
    """An api stand-in that does NOT expose
    ``register_config_migration``."""


class TestRegisterMemoryWikiSetup:
    def test_registers_migration_on_capable_host(self) -> None:
        api = _RecordingApi()
        register_memory_wiki_setup(api)
        assert len(api.migrations) == 1
        # Run the registered migration on a
        # full app config that contains the
        # legacy ``bridge.readMemoryCore``
        # flag in the memory-wiki plugin
        # entry.
        result = api.migrations[0](
            {
                "plugins": {
                    "entries": {
                        "memory-wiki": {
                            "config": {
                                "bridge": {
                                    "indexMemoryRoot": True,
                                    "readMemoryCore": True,
                                }
                            }
                        }
                    }
                }
            }
        )
        assert "config" in result
        assert "changes" in result
        # The legacy flag is migrated to
        # ``bridge.readMemoryArtifacts``.
        wiki_cfg = (
            result["config"]
            .get("plugins", {})
            .get("entries", {})
            .get("memory-wiki", {})
            .get("config", {})
        )
        assert wiki_cfg.get("bridge", {}).get("readMemoryArtifacts") is True
        # No ``readMemoryCore`` remains.
        assert "readMemoryCore" not in wiki_cfg.get("bridge", {})
        # A change description was recorded.
        assert len(result["changes"]) >= 1

    def test_migration_is_idempotent(self) -> None:
        api = _RecordingApi()
        register_memory_wiki_setup(api)
        migration = api.migrations[0]
        cfg = {
            "plugins": {
                "entries": {"memory-wiki": {"config": {"bridge": {"readMemoryCore": True}}}}
            }
        }
        first = migration(cfg)
        # The migrated config (no legacy
        # flag) is already canonical.
        second = migration(first["config"])
        assert second["changes"] == []

    def test_noop_on_hosts_without_register_config_migration(self) -> None:
        # Should not raise even though
        # ``_NoHookApi`` lacks
        # ``register_config_migration``.
        register_memory_wiki_setup(_NoHookApi())
