"""Smoke tests — verify the JARVIS dev toolchain works end-to-end.

This file exists to prove PR 0.2 (build/test infrastructure) is functional.
It does NOT test product behavior — that comes in later phases.

Removed once Phase 1 ships its first real test suite.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestToolchain:
    """Verify uv-managed dev tools (ruff, pyright, pytest) work."""

    @pytest.mark.parametrize(
        "tool",
        ["ruff", "pyright", "pytest"],
    )
    def test_tool_available(self, tool: str) -> None:
        """Each dev tool must be on the PATH via `uv run`."""
        uv = shutil.which("uv")
        assert uv is not None, "uv not found in PATH"
        result = subprocess.run(
            [uv, "run", tool, "--version"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert (
            result.returncode == 0
        ), f"{tool} failed: stdout={result.stdout!r} stderr={result.stderr!r}"
        assert tool in result.stdout.lower() or tool in result.stderr.lower()

    def test_python_version(self) -> None:
        """Repo targets Python 3.12+ (per AGENTS.md)."""
        assert sys.version_info >= (3, 12), f"Python {sys.version_info} < 3.12"

    def test_pyproject_toml_valid(self) -> None:
        """pyproject.toml exists and parses."""
        import tomllib

        with (REPO_ROOT / "pyproject.toml").open("rb") as f:
            data = tomllib.load(f)
        assert data["project"]["name"] == "jarvis"
        assert data["project"]["requires-python"] == ">=3.12"
        assert "dev" in data["dependency-groups"]
        dev_deps = data["dependency-groups"]["dev"]
        # Dependency specifiers include version constraints, so use prefix match.
        assert any(dep.startswith("ruff") for dep in dev_deps)
        assert any(dep.startswith("pyright") for dep in dev_deps)
        assert any(dep.startswith("pytest") for dep in dev_deps)


class TestRepoLayout:
    """Verify the OpenClaw-shaped tier directories are scaffolded (or planned)."""

    def test_openclaw_reference_present(self) -> None:
        """OpenClaw source is available as a reference (not a dependency)."""
        assert (REPO_ROOT / "openclaw-main").is_dir()

    def test_gitignore_covers_uv(self) -> None:
        """.gitignore excludes uv-managed venv and cache dirs."""
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert ".venv" in text
        assert ".ruff_cache" in text
        assert ".pyright_cache" in text

    def test_vscode_settings_use_ruff(self) -> None:
        """.vscode/settings.json points at ruff as the Python formatter."""
        import json

        settings = json.loads((REPO_ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8"))
        py = settings.get("[python]", {})
        assert "charliermarsh.ruff" in py.get("editor.defaultFormatter", "")

    def test_precommit_config_present(self) -> None:
        """.pre-commit-config.yaml wires the four CI helpers."""
        text = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        for hook in ("check-imports", "check-cycles", "check-max-lines", "check-manifests"):
            assert hook in text, f"pre-commit hook {hook} not wired"

    def test_legacy_root_files_removed(self) -> None:
        """PR 0.4: legacy root-level files (main.py, ui.py, setup.py, requirements.txt) are gone."""
        for legacy in ("main.py", "ui.py", "setup.py", "requirements.txt"):
            assert not (REPO_ROOT / legacy).exists(), f"{legacy} should be removed in PR 0.4"

    def test_apps_desktop_layout(self) -> None:
        """apps/desktop/ has the expected src-layout package."""
        desktop = REPO_ROOT / "apps" / "desktop"
        assert (desktop / "pyproject.toml").is_file()
        pkg = desktop / "src" / "jarvis_desktop"
        assert (pkg / "__init__.py").is_file()
        assert (pkg / "__main__.py").is_file()
        assert (pkg / "app.py").is_file()
        assert (pkg / "ui.py").is_file()


class TestJarvisDesktopImport:
    """PR 0.4: the moved desktop app package imports cleanly."""

    def test_jarvis_desktop_package(self) -> None:
        """`import jarvis_desktop` works and exposes the package version."""
        import jarvis_desktop

        assert jarvis_desktop.__version__ == "0.1.0-rc1"

    def test_jarvis_desktop_ui_module(self) -> None:
        """`from jarvis_desktop.ui import JarvisUI` works (PyQt6 wired)."""
        from jarvis_desktop.ui import JarvisUI

        assert JarvisUI.__name__ == "JarvisUI"

    def test_jarvis_desktop_app_module(self) -> None:
        """`from jarvis_desktop.app import main, JarvisLive, TOOL_DECLARATIONS` works."""
        from jarvis_desktop.app import TOOL_DECLARATIONS, JarvisLive, main

        # 20 tools: 19 hardcoded + 1 from extensions/tool_weather manifest.
        # Phase 2 will replace the hardcoded set with extensions too.
        assert len(TOOL_DECLARATIONS) == 20
        assert callable(main)
        assert JarvisLive.__name__ == "JarvisLive"

    def test_legacy_workspace_root_paths(self) -> None:
        """PR 0.4: BASE_DIR resolves to the workspace root, not the package dir."""
        from jarvis_desktop.app import API_CONFIG_PATH, BASE_DIR, PROMPT_PATH

        assert BASE_DIR == REPO_ROOT
        assert API_CONFIG_PATH == REPO_ROOT / "config" / "api_keys.json"
        assert PROMPT_PATH == REPO_ROOT / "core" / "prompt.txt"
        # PROMPT_PATH exists (we kept core/prompt.txt at the workspace root).
        assert PROMPT_PATH.exists()


class TestToolWeatherPlugin:
    """PR 1A: extensions/tool_weather/ — first proof consumer.

    The plugin's shape is the contract that Phase 1C formalizes into
    `packages/plugin_sdk/`. These tests pin the contract for the weather
    tool; Phase 1B (tool_reminder) will use the same shape.
    """

    def test_manifest_file_exists(self) -> None:
        """extensions/tool_weather/jarvis.plugin.json is present and well-formed."""
        import json

        path = REPO_ROOT / "extensions" / "tool_weather" / "jarvis.plugin.json"
        assert path.is_file()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["id"] == "tool_weather"
        assert manifest["kind"] == "tool"
        assert manifest["version"] == "0.1.0"
        assert "tools" in manifest
        assert len(manifest["tools"]) == 1
        assert manifest["tools"][0]["name"] == "weather_report"

    def test_plugin_instantiates_and_has_identity(self) -> None:
        """`from extensions.tool_weather.plugin import WeatherPlugin` works."""
        from extensions.tool_weather.plugin import WeatherPlugin

        p = WeatherPlugin()
        assert p.id == "tool_weather"
        assert p.kind == "tool"
        assert p.version == "0.1.0"
        # init() not yet called; _player is None.
        assert p._player is None

    def test_plugin_init_sets_player(self) -> None:
        """`init(player)` stashes the UI handle for log/speak."""

        class _FakePlayer:
            def write_log(self, _msg: str) -> None:
                pass

        from extensions.tool_weather.plugin import WeatherPlugin

        p = WeatherPlugin()
        player = _FakePlayer()
        p.init(player)
        assert p._player is player

    def test_plugin_tools_declaration(self) -> None:
        """`plugin.tools` returns the LLM-facing tool declaration list."""
        from extensions.tool_weather.plugin import WeatherPlugin

        p = WeatherPlugin()
        tools = p.tools
        assert len(tools) == 1
        tool = tools[0]
        assert tool["name"] == "weather_report"
        assert "description" in tool
        assert "city" in tool["parameters"]["properties"]
        assert tool["parameters"]["required"] == ["city"]

    def test_plugin_call_unknown_tool(self) -> None:
        """`call('foo', {})` returns a clear error message (not an exception)."""
        from extensions.tool_weather.plugin import WeatherPlugin

        p = WeatherPlugin()
        result = p.call("not_a_real_tool", {})
        assert "Unknown tool" in result

    def test_plugin_call_weather_opens_browser(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`call('weather_report', {city: 'London'})` calls `webbrowser.open` once.

        Uses pytest's `monkeypatch` to stub out `webbrowser.open` so the test
        doesn't actually open a browser window. The plugin's `_player.write_log`
        is also stubbed via the `init` path.
        """
        from extensions.tool_weather import plugin as weather_plugin_module
        from extensions.tool_weather.plugin import WeatherPlugin

        opened_urls: list[str] = []
        monkeypatch.setattr(
            weather_plugin_module.webbrowser,
            "open",
            lambda url: opened_urls.append(url) or True,
        )

        logged: list[str] = []

        class _FakePlayer:
            def write_log(self, msg: str) -> None:
                logged.append(msg)

        p = WeatherPlugin()
        p.init(_FakePlayer())
        result = p.call("weather_report", {"city": "London", "time": "tomorrow"})

        assert len(opened_urls) == 1
        assert "London" in opened_urls[0]
        assert "tomorrow" in opened_urls[0]
        assert "Showing the weather" in result
        assert len(logged) == 1
        assert "London" in logged[0]

    def test_plugin_call_weather_missing_city(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing city returns a clear error without opening a browser."""
        from extensions.tool_weather import plugin as weather_plugin_module
        from extensions.tool_weather.plugin import WeatherPlugin

        opened: list[str] = []
        monkeypatch.setattr(
            weather_plugin_module.webbrowser, "open", lambda url: opened.append(url)
        )

        p = WeatherPlugin()
        result = p.call("weather_report", {"city": ""})
        assert opened == []
        assert "city is missing" in result.lower()


class TestAppManifestLoader:
    """PR 1A: `apps/desktop` reads tool decls from extensions/*/jarvis.plugin.json."""

    def test_load_plugin_manifests_returns_weather(self) -> None:
        """The manifest loader finds extensions/tool_weather/jarvis.plugin.json."""
        from jarvis_desktop.app import _load_plugin_manifests

        decls = _load_plugin_manifests()
        names = [d["name"] for d in decls]
        assert "weather_report" in names

    def test_tool_declarations_includes_manifest_entries(self) -> None:
        """`TOOL_DECLARATIONS` is the union of hardcoded + manifest-loaded tools."""
        from jarvis_desktop.app import TOOL_DECLARATIONS

        names = [d["name"] for d in TOOL_DECLARATIONS]
        assert "weather_report" in names
        # No duplicates.
        assert len(names) == len(set(names))


class TestCiHelpers:
    """Verify the four CI helpers exit 0 in the empty repo (no plugins yet)."""

    @pytest.mark.parametrize(
        "script",
        [
            "tools/ci/check_imports.py",
            "tools/ci/check_cycles.py",
            "tools/ci/check_max_lines.py",
            "tools/ci/check_manifests.py",
        ],
    )
    def test_ci_helper_clean(self, script: str) -> None:
        """Each CI helper should exit 0 in PR 0.2 (no extensions yet)."""
        result = subprocess.run(
            [sys.executable, script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert (
            result.returncode == 0
        ), f"{script} exited {result.returncode}: stderr={result.stderr}"
