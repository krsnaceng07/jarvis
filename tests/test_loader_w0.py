"""Smoke tests for jarvis_sdk.loader — W0.1 verification.

Verifies that the canonical loader:
- Can be imported
- ``MANIFEST_FILENAME`` is the correct string
- ``LoadResult`` has the expected fields
- ``load_all_plugins`` handles a missing directory gracefully
- ``load_all_plugins`` correctly skips bad manifests
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis_sdk.loader import (
    MANIFEST_FILENAME,
    LoadResult,
    load_all_plugins,
    load_all_plugins_from_workspace,
)


class TestLoaderImport:
    def test_manifest_filename(self) -> None:
        assert MANIFEST_FILENAME == "openclaw.plugin.json"

    def test_load_result_fields(self) -> None:
        fields = set(LoadResult.__dataclass_fields__.keys())
        assert "tool_decls" in fields
        assert "plugin_dispatch" in fields
        assert "hooks" in fields
        assert "commands" in fields
        assert "skipped" in fields
        assert "plugin_count" in fields
        assert "channel" in fields
        assert "gateway_methods" in fields

    def test_load_result_defaults(self) -> None:
        r = LoadResult()
        assert r.tool_decls == []
        assert r.plugin_dispatch == {}
        assert r.hooks == []
        assert r.plugin_count == 0
        assert r.channel is None
        assert r.gateway_methods == []
        assert r.skipped == []


class TestLoadAllPluginsMissingDir:
    def test_returns_empty_on_missing_dir(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent_extensions"
        result = load_all_plugins(missing)
        assert isinstance(result, LoadResult)
        assert result.plugin_count == 0
        assert result.tool_decls == []
        assert result.skipped == []

    def test_workspace_variant_also_handles_missing(self, tmp_path: Path) -> None:
        # tmp_path has no extensions/ subdir
        result = load_all_plugins_from_workspace(tmp_path)
        assert result.plugin_count == 0


class TestLoadAllPluginsBadManifest:
    def test_skips_invalid_json(self, tmp_path: Path) -> None:
        ext_dir = tmp_path / "bad_ext"
        ext_dir.mkdir()
        (ext_dir / MANIFEST_FILENAME).write_text("NOT JSON {{{", encoding="utf-8")
        result = load_all_plugins(tmp_path)
        assert "bad_ext" in result.skipped
        assert result.plugin_count == 0

    def test_skips_manifest_without_id(self, tmp_path: Path) -> None:
        ext_dir = tmp_path / "no_id_ext"
        ext_dir.mkdir()
        (ext_dir / MANIFEST_FILENAME).write_text(
            json.dumps({"kind": "tool", "activation": "on_demand"}),
            encoding="utf-8",
        )
        result = load_all_plugins(tmp_path)
        assert "no_id_ext" in result.skipped

    def test_skips_non_importable_extension(self, tmp_path: Path) -> None:
        # Valid manifest but no Python module to import.
        ext_dir = tmp_path / "ghost_ext"
        ext_dir.mkdir()
        (ext_dir / MANIFEST_FILENAME).write_text(
            json.dumps({"id": "ghost_ext", "kind": "tool", "activation": "on_demand"}),
            encoding="utf-8",
        )
        # No __init__.py, so import will fail.
        result = load_all_plugins(tmp_path)
        assert "ghost_ext" in result.skipped
        assert result.plugin_count == 0


class TestLoadAllPluginsOnlyStartup:
    def test_only_startup_filters_on_demand(self, tmp_path: Path) -> None:
        """Plugins with activation='on_demand' are skipped when only_startup=True."""
        ext_dir = tmp_path / "lazy_ext"
        ext_dir.mkdir()
        (ext_dir / MANIFEST_FILENAME).write_text(
            json.dumps({"id": "lazy_ext", "kind": "tool", "activation": "on_demand"}),
            encoding="utf-8",
        )
        # Even if we could import it, it should not appear in plugin_count.
        result = load_all_plugins(tmp_path, only_startup=True)
        assert result.plugin_count == 0
        # Not skipped (filtered, not failed).
        assert "lazy_ext" not in result.skipped

    def test_only_startup_includes_on_startup(self, tmp_path: Path) -> None:
        """Plugins with activation='on_startup' are included when only_startup=True."""
        ext_dir = tmp_path / "eager_ext"
        ext_dir.mkdir()
        (ext_dir / MANIFEST_FILENAME).write_text(
            json.dumps({"id": "eager_ext", "kind": "tool", "activation": "on_startup"}),
            encoding="utf-8",
        )
        # No __init__.py — will be skipped, but only after passing the filter.
        result = load_all_plugins(tmp_path, only_startup=True)
        # The extension passed the activation filter but failed to import.
        assert "eager_ext" in result.skipped

    def test_only_startup_filters_on_demand_dict_activation(self, tmp_path: Path) -> None:
        """Plugins with an OpenClaw activation dict and no startup signal are skipped."""
        ext_dir = tmp_path / "lazy_ext"
        ext_dir.mkdir()
        (ext_dir / MANIFEST_FILENAME).write_text(
            json.dumps(
                {
                    "id": "lazy_ext",
                    "kind": "tool",
                    "activation": {"onStartup": False, "onDemand": True},
                }
            ),
            encoding="utf-8",
        )
        result = load_all_plugins(tmp_path, only_startup=True)
        assert result.plugin_count == 0
        assert "lazy_ext" not in result.skipped
