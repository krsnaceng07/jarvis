"""Tests for extensions/memory_wiki/config_compat.py.

Phase 4.3b: ports the OpenClaw
``migrateMemoryWikiLegacyConfig`` /
``normalizeCompatibilityConfig`` /
``hasLegacyBridgeArtifactToggle`` helpers. The
tests focus on:

- The legacy key is detected.
- The migration renames ``bridge.readMemoryCore`` to
  ``bridge.readMemoryArtifacts`` when no canonical
  key is present.
- The migration drops ``readMemoryCore`` and keeps
  the explicit ``readMemoryArtifacts`` when both are
  present.
- The migration is a no-op on a config without the
  legacy key.
- ``LEGACY_CONFIG_RULES`` exposes the documented
  rule with the OpenClaw field path + message.
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

import copy
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

from extensions.memory_wiki.config_compat import (  # noqa: E402
    LEGACY_CONFIG_RULES,
    has_legacy_bridge_artifact_toggle,
    migrate_memory_wiki_legacy_config,
    normalize_compatibility_config,
)


class TestHasLegacyBridgeArtifactToggle:
    def test_dict_with_legacy_key_returns_true(self) -> None:
        assert has_legacy_bridge_artifact_toggle({"readMemoryCore": True}) is True

    def test_dict_without_legacy_key_returns_false(self) -> None:
        assert has_legacy_bridge_artifact_toggle({"readMemoryArtifacts": True}) is False

    def test_non_dict_returns_false(self) -> None:
        assert has_legacy_bridge_artifact_toggle(None) is False
        assert has_legacy_bridge_artifact_toggle("string") is False
        assert has_legacy_bridge_artifact_toggle(42) is False
        assert has_legacy_bridge_artifact_toggle(["array"]) is False


class TestLegacyConfigRules:
    def test_exposes_single_rule(self) -> None:
        assert len(LEGACY_CONFIG_RULES) == 1
        rule = LEGACY_CONFIG_RULES[0]
        assert rule["path"] == [
            "plugins",
            "entries",
            "memory-wiki",
            "config",
            "bridge",
        ]
        assert "readMemoryCore" in rule["message"]
        assert callable(rule["match"])


class TestMigrateMemoryWikiLegacyConfig:
    def test_no_legacy_returns_none(self) -> None:
        cfg = {"plugins": {"entries": {"memory-wiki": {"config": {}}}}}
        assert migrate_memory_wiki_legacy_config(cfg) is None

    def test_legacy_key_renamed_when_no_canonical(self) -> None:
        cfg = {
            "plugins": {
                "entries": {"memory-wiki": {"config": {"bridge": {"readMemoryCore": True}}}}
            }
        }
        result = migrate_memory_wiki_legacy_config(cfg)
        assert result is not None
        migrated = result["config"]
        bridge = migrated["plugins"]["entries"]["memory-wiki"]["config"]["bridge"]
        assert "readMemoryCore" not in bridge
        assert bridge["readMemoryArtifacts"] is True
        assert len(result["changes"]) == 1
        assert "Moved" in result["changes"][0]

    def test_legacy_key_dropped_when_canonical_present(self) -> None:
        cfg = {
            "plugins": {
                "entries": {
                    "memory-wiki": {
                        "config": {
                            "bridge": {
                                "readMemoryCore": True,
                                "readMemoryArtifacts": False,
                            }
                        }
                    }
                }
            }
        }
        result = migrate_memory_wiki_legacy_config(cfg)
        assert result is not None
        bridge = result["config"]["plugins"]["entries"]["memory-wiki"]["config"]["bridge"]
        assert "readMemoryCore" not in bridge
        assert bridge["readMemoryArtifacts"] is False
        assert "Removed" in result["changes"][0]

    def test_does_not_mutate_input(self) -> None:
        cfg = {
            "plugins": {
                "entries": {"memory-wiki": {"config": {"bridge": {"readMemoryCore": True}}}}
            }
        }
        snapshot = copy.deepcopy(cfg)
        migrate_memory_wiki_legacy_config(cfg)
        assert cfg == snapshot


class TestNormalizeCompatibilityConfig:
    def test_no_migration_returns_empty_changes(self) -> None:
        cfg = {"plugins": {"entries": {"memory-wiki": {"config": {}}}}}
        result = normalize_compatibility_config(cfg=cfg)
        assert result["changes"] == []
        assert result["config"] is cfg

    def test_with_migration_returns_changes(self) -> None:
        cfg = {
            "plugins": {
                "entries": {"memory-wiki": {"config": {"bridge": {"readMemoryCore": True}}}}
            }
        }
        result = normalize_compatibility_config(cfg=cfg)
        assert len(result["changes"]) == 1
        assert "Moved" in result["changes"][0]
