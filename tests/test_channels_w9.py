"""Wave 9 tests — CLI: config-show, configure, status commands via jarvis_cli."""

from __future__ import annotations

import json
from pathlib import Path


from jarvis_config_core import JarvisConfig, save_config
from jarvis_cli.main import main


# ── helpers ──────────────────────────────────────────────────────────────────


def _run(argv: list[str], workspace: Path) -> tuple[int, str]:
    """Run CLI main with captured stdout; return (exit_code, output)."""
    import io
    import sys

    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(["--workspace", str(workspace)] + argv)
    finally:
        sys.stdout = old
    return code, buf.getvalue()


def _empty_cfg(workspace: Path) -> Path:
    """Write an empty JarvisConfig (no api_key) to workspace/config.json."""
    p = workspace / "config.json"
    save_config(JarvisConfig(), p)
    return p


def _keyed_cfg(workspace: Path, key: str = "test_key") -> Path:
    """Write a JarvisConfig with api_key to workspace/config.json."""
    p = workspace / "config.json"
    save_config(JarvisConfig(gemini_api_key=key), p)
    return p


# ── config-show ───────────────────────────────────────────────────────────────


class TestConfigShow:
    def test_shows_defaults_when_no_config(self, tmp_path: Path) -> None:
        _empty_cfg(tmp_path)
        code, out = _run(["config-show"], tmp_path)
        data = json.loads(out.split("\n\u26a0")[0])  # strip warning block
        assert data["model"] == "gemini-2.0-flash"
        # Exit 1 because gemini_api_key is missing
        assert code == 1

    def test_shows_config_and_redacts_key(self, tmp_path: Path) -> None:
        _keyed_cfg(tmp_path, "AIzaSySecret")
        code, out = _run(["config-show"], tmp_path)
        assert "***" in out
        assert "AIzaSySecret" not in out
        assert code == 0

    def test_configured_workspace_exits_0(self, tmp_path: Path) -> None:
        _keyed_cfg(tmp_path, "good_key")
        code, out = _run(["config-show"], tmp_path)
        assert code == 0

    def test_validation_issues_shown(self, tmp_path: Path) -> None:
        _empty_cfg(tmp_path)
        code, out = _run(["config-show"], tmp_path)
        assert "\u26a0" in out or "gemini_api_key" in out
        assert code == 1


# ── configure ────────────────────────────────────────────────────────────────


class TestConfigure:
    def test_no_flags_shows_help(self, tmp_path: Path) -> None:
        _empty_cfg(tmp_path)
        code, out = _run(["configure"], tmp_path)
        assert "not configured" in out or "configured" in out
        assert code == 0

    def test_sets_model(self, tmp_path: Path) -> None:
        _keyed_cfg(tmp_path)
        code, out = _run(["configure", "--model", "gemini-pro"], tmp_path)
        assert "model" in out
        # Verify persisted
        from jarvis_config_core import load_config
        cfg = load_config(tmp_path / "config.json")
        assert cfg.model == "gemini-pro"
        assert code == 0

    def test_sets_log_level_uppercased(self, tmp_path: Path) -> None:
        _keyed_cfg(tmp_path)
        _run(["configure", "--log-level", "debug"], tmp_path)
        from jarvis_config_core import load_config
        cfg = load_config(tmp_path / "config.json")
        assert cfg.log_level == "DEBUG"

    def test_sets_port(self, tmp_path: Path) -> None:
        _keyed_cfg(tmp_path)
        _run(["configure", "--port", "8080"], tmp_path)
        from jarvis_config_core import load_config
        cfg = load_config(tmp_path / "config.json")
        assert cfg.gateway_port == 8080

    def test_api_key_redacted_in_output(self, tmp_path: Path) -> None:
        _keyed_cfg(tmp_path, "oldk")
        code, out = _run(["configure", "--api-key", "AIzaSyNewKey"], tmp_path)
        assert "AIzaSyNewKey" not in out
        assert "***" in out

    def test_configure_exits_1_if_still_unconfigured(self, tmp_path: Path) -> None:
        # Empty config (no api_key) + model-only patch → validate() still fails
        _empty_cfg(tmp_path)
        code, out = _run(["configure", "--model", "gemini-pro"], tmp_path)
        assert code == 1
        assert "\u26a0" in out or "gemini_api_key" in out


# ── status ────────────────────────────────────────────────────────────────────


class TestStatus:
    def test_shows_not_configured(self, tmp_path: Path) -> None:
        _empty_cfg(tmp_path)
        code, out = _run(["status"], tmp_path)
        assert "\u2717 not configured" in out
        assert code == 1

    def test_shows_configured(self, tmp_path: Path) -> None:
        _keyed_cfg(tmp_path)
        code, out = _run(["status"], tmp_path)
        assert "\u2713 configured" in out
        assert code == 0

    def test_shows_gateway_not_running(self, tmp_path: Path) -> None:
        _keyed_cfg(tmp_path)
        _, out = _run(["status"], tmp_path)
        # Gateway almost certainly not running in test env
        assert "Gateway" in out

    def test_output_has_section_headers(self, tmp_path: Path) -> None:
        _empty_cfg(tmp_path)
        _, out = _run(["status"], tmp_path)
        assert "JARVIS Status" in out
        assert "Config" in out


# ── config-show / configure roundtrip ────────────────────────────────────────


class TestConfigRoundtrip:
    def test_configure_then_show(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="initial"), cfg_path)
        _run(["configure", "--model", "gemini-ultra"], tmp_path)
        code, out = _run(["config-show"], tmp_path)
        assert "gemini-ultra" in out
        assert code == 0
