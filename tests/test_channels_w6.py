"""Wave 6 tests — jarvis_config_core: JarvisConfig + load/save/patch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis_config_core import (
    JarvisConfig,
    load_config,
    patch_config,
    save_config,
)


# ── JarvisConfig dataclass ──────────────────────────────────────────────────


class TestJarvisConfig:
    def test_defaults(self) -> None:
        c = JarvisConfig()
        assert c.gemini_api_key == ""
        assert c.model == "gemini-2.0-flash"
        assert c.gateway_port == 7433
        assert c.log_level == "INFO"
        assert c.extensions_dir is None
        assert c.state_dir is None

    def test_is_configured_false_on_empty_key(self) -> None:
        assert not JarvisConfig().is_configured

    def test_is_configured_true_with_key(self) -> None:
        c = JarvisConfig(gemini_api_key="abc123")
        assert c.is_configured

    def test_is_configured_false_on_whitespace(self) -> None:
        c = JarvisConfig(gemini_api_key="   ")
        assert not c.is_configured

    def test_validate_empty_key(self) -> None:
        issues = JarvisConfig().validate()
        assert any("gemini_api_key" in i for i in issues)

    def test_validate_bad_port(self) -> None:
        c = JarvisConfig(gemini_api_key="key", gateway_port=0)
        issues = c.validate()
        assert any("gateway_port" in i for i in issues)

    def test_validate_bad_log_level(self) -> None:
        c = JarvisConfig(gemini_api_key="key", log_level="VERBOSE")
        issues = c.validate()
        assert any("log_level" in i for i in issues)

    def test_validate_all_good(self) -> None:
        c = JarvisConfig(gemini_api_key="key")
        assert c.validate() == []

    def test_to_dict(self) -> None:
        c = JarvisConfig(gemini_api_key="k", model="gemini-pro", gateway_port=8080)
        d = c.to_dict()
        assert d["gemini_api_key"] == "k"
        assert d["model"] == "gemini-pro"
        assert d["gateway_port"] == 8080
        assert d["extensions_dir"] is None

    def test_to_dict_path_serialized_as_str(self) -> None:
        c = JarvisConfig(gemini_api_key="k", extensions_dir=Path("/ext"))
        d = c.to_dict()
        assert isinstance(d["extensions_dir"], str)

    def test_frozen(self) -> None:
        c = JarvisConfig()
        with pytest.raises((AttributeError, TypeError)):
            c.gemini_api_key = "new"  # type: ignore[misc]


# ── load_config ─────────────────────────────────────────────────────────────


class TestLoadConfig:
    def test_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        c = load_config(tmp_path / "missing.json")
        assert c.model == "gemini-2.0-flash"
        assert not c.is_configured

    def test_loads_api_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"gemini_api_key": "mykey"}))
        c = load_config(cfg)
        assert c.gemini_api_key == "mykey"
        assert c.is_configured

    def test_loads_all_fields(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "gemini_api_key": "k",
            "model": "gemini-pro",
            "gateway_port": 9000,
            "log_level": "debug",
            "extensions_dir": "/ext",
            "state_dir": "/state",
        }))
        c = load_config(cfg)
        assert c.model == "gemini-pro"
        assert c.gateway_port == 9000
        assert c.log_level == "DEBUG"
        assert c.extensions_dir == Path("/ext")
        assert c.state_dir == Path("/state")

    def test_ignores_unknown_keys(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"gemini_api_key": "k", "unknown_field": "x"}))
        c = load_config(cfg)
        assert c.gemini_api_key == "k"

    def test_bad_json_returns_defaults(self, tmp_path: Path) -> None:
        cfg = tmp_path / "bad.json"
        cfg.write_text("not json!!!")
        c = load_config(cfg)
        assert c.model == "gemini-2.0-flash"

    def test_non_dict_json_returns_defaults(self, tmp_path: Path) -> None:
        cfg = tmp_path / "list.json"
        cfg.write_text("[1, 2, 3]")
        c = load_config(cfg)
        assert not c.is_configured

    def test_falls_back_to_legacy_api_keys(self, tmp_path: Path) -> None:
        legacy_dir = tmp_path / "app"
        (legacy_dir / "config").mkdir(parents=True)
        (legacy_dir / "config" / "api_keys.json").write_text(
            json.dumps({"gemini_api_key": "legacy_key"})
        )
        c = load_config(tmp_path / "missing.json", legacy_app_dir=legacy_dir)
        assert c.gemini_api_key == "legacy_key"

    def test_canonical_takes_priority_over_legacy(self, tmp_path: Path) -> None:
        canonical = tmp_path / "config.json"
        canonical.write_text(json.dumps({"gemini_api_key": "canonical_key"}))
        legacy_dir = tmp_path / "app"
        (legacy_dir / "config").mkdir(parents=True)
        (legacy_dir / "config" / "api_keys.json").write_text(
            json.dumps({"gemini_api_key": "legacy_key"})
        )
        c = load_config(canonical, legacy_app_dir=legacy_dir)
        assert c.gemini_api_key == "canonical_key"

    def test_invalid_gateway_port_skipped(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"gemini_api_key": "k", "gateway_port": "bad"}))
        c = load_config(cfg)
        assert c.gateway_port == 7433  # default preserved


# ── save_config ──────────────────────────────────────────────────────────────


class TestSaveConfig:
    def test_save_and_reload(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        original = JarvisConfig(gemini_api_key="mykey", model="gemini-pro")
        save_config(original, cfg_path)
        loaded = load_config(cfg_path)
        assert loaded.gemini_api_key == "mykey"
        assert loaded.model == "gemini-pro"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "deep" / "nested" / "config.json"
        save_config(JarvisConfig(gemini_api_key="k"), cfg_path)
        assert cfg_path.exists()

    def test_saved_as_valid_json(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="k"), cfg_path)
        data = json.loads(cfg_path.read_text())
        assert isinstance(data, dict)


# ── patch_config ─────────────────────────────────────────────────────────────


class TestPatchConfig:
    def test_patch_single_field(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="old"), cfg_path)
        new = patch_config({"gemini_api_key": "new"}, cfg_path)
        assert new.gemini_api_key == "new"
        assert new.model == "gemini-2.0-flash"  # preserved

    def test_patch_persists_to_disk(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="old"), cfg_path)
        patch_config({"model": "gemini-pro"}, cfg_path)
        reloaded = load_config(cfg_path)
        assert reloaded.model == "gemini-pro"
        assert reloaded.gemini_api_key == "old"

    def test_patch_creates_config_if_missing(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        new = patch_config({"gemini_api_key": "newkey"}, cfg_path)
        assert new.gemini_api_key == "newkey"
        assert cfg_path.exists()
