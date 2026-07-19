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

        # 20 tools: 18 hardcoded + 2 from extensions/*/openclaw.plugin.json
        # (tool_weather + tool_reminder). Phase 2 will replace the rest.
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
    """PR 1A+1B: extensions/tool_weather/ — first proof consumer (now SDK-driven).

    The plugin's shape is the contract that Phase 1C formalizes into
    `packages/plugin_sdk/`. These tests pin the contract for the weather
    tool; ``TestToolReminderPlugin`` (PR 1B) uses the same shape.
    """

    def test_manifest_file_exists(self) -> None:
        """extensions/tool_weather/openclaw.plugin.json is present and well-formed."""
        import json

        path = REPO_ROOT / "extensions" / "tool_weather" / "openclaw.plugin.json"
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
        """`plugin.tools` returns a list of SDK `ToolDecl`."""
        from extensions.tool_weather.plugin import WeatherPlugin
        from jarvis_sdk import ToolDecl

        p = WeatherPlugin()
        tools = p.tools
        assert len(tools) == 1
        tool = tools[0]
        assert isinstance(tool, ToolDecl)
        assert tool.name == "weather_report"
        param_names = [pp.name for pp in tool.parameters]
        assert "city" in param_names
        # `city` is required; `time` is not.
        required = [pp.name for pp in tool.parameters if pp.required]
        assert required == ["city"]

    @pytest.mark.asyncio
    async def test_plugin_call_unknown_tool(self) -> None:
        """`call('foo', {})` returns `Err('Unknown tool: foo', code='UNKNOWN_TOOL')`."""
        from extensions.tool_weather.plugin import WeatherPlugin
        from jarvis_sdk import Err

        p = WeatherPlugin()
        result = await p.call("not_a_real_tool", {})
        assert isinstance(result, Err)
        assert "Unknown tool" in result.error
        assert result.code == "UNKNOWN_TOOL"

    @pytest.mark.asyncio
    async def test_plugin_call_weather_opens_browser(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`call('weather_report', {city: 'London'})` opens the browser once.

        Returns ``Ok(...)`` with a "Showing the weather" message. The
        plugin's ``_player.write_log`` is also stubbed via ``init``.
        """
        from extensions.tool_weather import plugin as weather_plugin_module
        from extensions.tool_weather.plugin import WeatherPlugin
        from jarvis_sdk import Ok

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
        result = await p.call("weather_report", {"city": "London", "time": "tomorrow"})

        assert isinstance(result, Ok)
        assert len(opened_urls) == 1
        assert "London" in opened_urls[0]
        assert "tomorrow" in opened_urls[0]
        assert "Showing the weather" in result.value
        assert len(logged) == 1
        assert "London" in logged[0]

    @pytest.mark.asyncio
    async def test_plugin_call_weather_missing_city(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing city returns ``Err(..., code='MISSING_ARG')`` without opening a browser."""
        from extensions.tool_weather import plugin as weather_plugin_module
        from extensions.tool_weather.plugin import WeatherPlugin
        from jarvis_sdk import Err

        opened: list[str] = []
        monkeypatch.setattr(
            weather_plugin_module.webbrowser, "open", lambda url: opened.append(url)
        )

        p = WeatherPlugin()
        result = await p.call("weather_report", {"city": ""})
        assert opened == []
        assert isinstance(result, Err)
        assert result.code == "MISSING_ARG"
        assert "city is missing" in result.error.lower()


class TestToolReminderPlugin:
    """PR 1B: extensions/tool_reminder/ — second consumer.

    This mirrors the shape pinned by ``TestToolWeatherPlugin`` and
    validates the SDK-driven plugin loader contract: manifest +
    ``entry`` + ``Plugin`` subclass + ``Result`` returns.
    """

    def test_manifest_file_exists(self) -> None:
        """extensions/tool_reminder/openclaw.plugin.json is present + well-formed."""
        import json

        path = REPO_ROOT / "extensions" / "tool_reminder" / "openclaw.plugin.json"
        assert path.is_file()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["id"] == "tool_reminder"
        assert manifest["kind"] == "tool"
        assert manifest["version"] == "0.1.0"
        assert "tools" in manifest
        assert len(manifest["tools"]) == 1
        assert manifest["tools"][0]["name"] == "reminder"

    def test_plugin_instantiates_and_has_identity(self) -> None:
        """`from extensions.tool_reminder.plugin import ReminderPlugin` works."""
        from extensions.tool_reminder.plugin import ReminderPlugin

        p = ReminderPlugin()
        assert p.id == "tool_reminder"
        assert p.kind == "tool"
        assert p.version == "0.1.0"

    def test_plugin_init_is_noop(self) -> None:
        """`init(ctx)` is a no-op for reminder (no persistent state)."""
        from extensions.tool_reminder.plugin import ReminderPlugin

        p = ReminderPlugin()
        # Should not raise.
        p.init({"any": "ctx"})

    def test_plugin_tools_declaration(self) -> None:
        """`plugin.tools` returns the LLM-facing tool declaration list."""
        from extensions.tool_reminder.plugin import ReminderPlugin

        p = ReminderPlugin()
        tools = p.tools
        assert len(tools) == 1
        tool = tools[0]
        assert tool.name == "reminder"
        assert "date" in [pp.name for pp in tool.parameters]
        assert "time" in [pp.name for pp in tool.parameters]

    @pytest.mark.asyncio
    async def test_plugin_call_unknown_tool_returns_err(self) -> None:
        """`call('foo', {})` returns ``Err('Unknown tool: foo', code='UNKNOWN_TOOL')``."""
        from extensions.tool_reminder.plugin import ReminderPlugin
        from jarvis_sdk import Err

        p = ReminderPlugin()
        result = await p.call("not_a_real_tool", {})
        assert isinstance(result, Err)
        assert result.is_err is True
        assert "Unknown tool" in result.error
        assert result.code == "UNKNOWN_TOOL"

    @pytest.mark.asyncio
    async def test_plugin_call_reminder_past_time(self) -> None:
        """`call('reminder', {date: yesterday, time: 00:00})` returns Err TIME_IN_PAST."""
        from extensions.tool_reminder.plugin import ReminderPlugin
        from jarvis_sdk import Err

        p = ReminderPlugin()
        result = await p.call(
            "reminder",
            {"date": "2020-01-01", "time": "00:00", "message": "test"},
        )
        assert isinstance(result, Err)
        assert result.is_err is True
        assert result.code == "TIME_IN_PAST"
        assert "past" in result.error.lower()

    @pytest.mark.asyncio
    async def test_plugin_call_reminder_missing_args(self) -> None:
        """`call('reminder', {})` returns Err MISSING_ARG (no date/time)."""
        from extensions.tool_reminder.plugin import ReminderPlugin
        from jarvis_sdk import Err

        p = ReminderPlugin()
        result = await p.call("reminder", {})
        assert isinstance(result, Err)
        assert result.is_err is True
        assert result.code == "MISSING_ARG"

    @pytest.mark.asyncio
    async def test_plugin_call_reminder_bad_format(self) -> None:
        """Malformed date returns Err BAD_FORMAT (not a crash)."""
        from extensions.tool_reminder.plugin import ReminderPlugin
        from jarvis_sdk import Err

        p = ReminderPlugin()
        result = await p.call(
            "reminder", {"date": "not-a-date", "time": "99:99", "message": "test"}
        )
        assert isinstance(result, Err)
        assert result.is_err is True
        assert result.code == "BAD_FORMAT"

    def test_entry_module_exposes_entry(self) -> None:
        """`from extensions.tool_reminder import entry` works and has .register()."""
        from extensions import tool_reminder

        assert hasattr(tool_reminder, "entry")
        assert hasattr(tool_reminder.entry, "register")
        assert hasattr(tool_reminder.entry, "id")
        assert tool_reminder.entry.id == "tool_reminder"
        assert tool_reminder.entry.kind == "tool"


class TestPluginSdkLoader:
    """PR 1B: the SDK-driven plugin loader (app.py::_load_plugins).

    Verifies that the loader wires the new ``jarvis_sdk`` boundary
    correctly: it returns four parallel collections (tool_decls,
    plugin_dispatch, commands, cli_handlers) and never reaches into
    extensions directly.
    """

    def test_load_plugins_returns_four_collections(self) -> None:
        """_load_plugins returns a 4-tuple of (decls, dispatch, commands, cli)."""
        from jarvis_desktop.app import _load_plugins

        result = _load_plugins()
        assert isinstance(result, tuple)
        assert len(result) == 4
        tool_decls, dispatch, commands, cli = result
        assert isinstance(tool_decls, list)
        assert isinstance(dispatch, dict)
        assert isinstance(commands, list)
        assert isinstance(cli, list)

    def test_load_plugins_dispatch_values_are_pairs(self) -> None:
        """Each dispatch entry is (plugin_instance, call_name)."""
        from jarvis_desktop.app import _load_plugins

        _decls, dispatch, _commands, _cli = _load_plugins()
        for tool_name, value in dispatch.items():
            assert isinstance(value, tuple)
            assert len(value) == 2
            _plugin_inst, call_name = value
            assert isinstance(call_name, str)
            assert call_name == tool_name  # dispatch key matches call name

    def test_load_plugins_tool_decls_have_required_fields(self) -> None:
        """Each tool decl has name + description + parameters OBJECT schema."""
        from jarvis_desktop.app import _load_plugins

        tool_decls, _dispatch, _commands, _cli = _load_plugins()
        for d in tool_decls:
            assert "name" in d
            assert "description" in d
            assert "parameters" in d
            params = d["parameters"]
            assert params["type"] == "OBJECT"
            assert "properties" in params
            assert "required" in params
            assert isinstance(params["required"], list)

    def test_legacy_actions_reminder_file_removed(self) -> None:
        """``actions/reminder.py`` is gone (migrated to extensions/tool_reminder/)."""
        legacy = REPO_ROOT / "actions" / "reminder.py"
        assert not legacy.exists(), (
            f"Legacy file still present: {legacy}. "
            "Reminder tool has fully migrated to extensions/tool_reminder/."
        )


class TestAppManifestLoader:
    """PR 1A+1B: `apps/desktop` reads tool decls from extensions/*/openclaw.plugin.json.

    The loader was renamed from `_load_plugin_manifests` (PR 1A) to
    `_load_plugins` (PR 1B) and now also returns a dispatch map, a
    commands list, and a CLI handler list.
    """

    def test_load_plugins_returns_weather(self) -> None:
        """The plugin loader finds extensions/tool_weather/openclaw.plugin.json."""
        from jarvis_desktop.app import _load_plugins

        tool_decls, _dispatch, _commands, _cli = _load_plugins()
        names = [d["name"] for d in tool_decls]
        assert "weather_report" in names

    def test_load_plugins_returns_reminder(self) -> None:
        """The plugin loader finds extensions/tool_reminder/openclaw.plugin.json."""
        from jarvis_desktop.app import _load_plugins

        tool_decls, _dispatch, _commands, _cli = _load_plugins()
        names = [d["name"] for d in tool_decls]
        assert "reminder" in names

    def test_load_plugins_dispatch_maps_known_tools(self) -> None:
        """The dispatch map covers every tool declared by every loaded plugin."""
        from jarvis_desktop.app import _load_plugins

        tool_decls, dispatch, _commands, _cli = _load_plugins()
        for d in tool_decls:
            assert d["name"] in dispatch, f"missing dispatch for {d['name']!r}"

    def test_load_plugins_commands_have_required_keys(self) -> None:
        """Each registered command carries name+description+handler."""
        from jarvis_desktop.app import _load_plugins
        from jarvis_sdk import CommandDecl

        _tool_decls, _dispatch, commands, _cli = _load_plugins()
        assert len(commands) >= 1, "at least the reminders command must be registered"
        for c in commands:
            assert isinstance(c, CommandDecl)
            assert c.name
            assert c.description
            # Phase 1C: handler is REQUIRED on every registered command.
            assert callable(c.handler), f"command {c.name!r} has no handler"
        # The reminders command from tool_reminder.
        assert any(c.name == "reminders" for c in commands)

    def test_tool_declarations_includes_manifest_entries(self) -> None:
        """`TOOL_DECLARATIONS` is the union of hardcoded + manifest-loaded tools."""
        from jarvis_desktop.app import TOOL_DECLARATIONS

        names = [d["name"] for d in TOOL_DECLARATIONS]
        # 6 tools loaded from extensions (PR 1A + 1B + 1C):
        for expected in (
            "weather_report",
            "reminder",
            "open_app",
            "web_search",
            "send_message",
            "youtube_video",
        ):
            assert expected in names, f"missing tool {expected!r} in TOOL_DECLARATIONS"
        # No duplicates.
        assert len(names) == len(set(names))


class TestToolOpenAppPlugin:
    """PR 1C: extensions/tool_open_app/ — 4th consumer (alias table + per-OS launch)."""

    def test_manifest_file_exists(self) -> None:
        import json

        path = REPO_ROOT / "extensions" / "tool_open_app" / "openclaw.plugin.json"
        assert path.is_file()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["id"] == "tool_open_app"
        assert manifest["kind"] == "tool"
        assert manifest["tools"][0]["name"] == "open_app"

    def test_plugin_instantiates_and_has_identity(self) -> None:
        from extensions.tool_open_app.plugin import OpenAppPlugin

        p = OpenAppPlugin()
        assert p.id == "tool_open_app"
        assert p.kind == "tool"
        assert p.version == "0.1.0"

    @pytest.mark.asyncio
    async def test_plugin_call_unknown_tool(self) -> None:
        from extensions.tool_open_app.plugin import OpenAppPlugin
        from jarvis_sdk import Err

        p = OpenAppPlugin()
        result = await p.call("not_a_tool", {})
        assert isinstance(result, Err)
        assert result.code == "UNKNOWN_TOOL"

    @pytest.mark.asyncio
    async def test_plugin_call_open_app_missing_arg(self) -> None:
        from extensions.tool_open_app.plugin import OpenAppPlugin
        from jarvis_sdk import Err

        p = OpenAppPlugin()
        result = await p.call("open_app", {})
        assert isinstance(result, Err)
        assert result.code == "MISSING_ARG"

    def test_resolve_alias_known(self) -> None:
        from extensions.tool_open_app import runtime

        # Chrome resolves to "Google Chrome" on macOS, "chrome" on Windows.
        assert runtime.resolve_alias("chrome", system="Windows") == "chrome"
        assert runtime.resolve_alias("chrome", system="Darwin") == "Google Chrome"
        assert runtime.resolve_alias("vscode", system="Linux") == "code"

    def test_resolve_alias_unknown_returns_input(self) -> None:
        from extensions.tool_open_app import runtime

        # Unknown app names pass through unchanged.
        assert runtime.resolve_alias("my-custom-app", system="Windows") == "my-custom-app"


class TestToolWebSearchPlugin:
    """PR 1C: extensions/tool_web_search/ — 5th consumer (OpenRouter → DDG)."""

    def test_manifest_file_exists(self) -> None:
        import json

        path = REPO_ROOT / "extensions" / "tool_web_search" / "openclaw.plugin.json"
        assert path.is_file()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["id"] == "tool_web_search"
        assert manifest["kind"] == "tool"

    def test_plugin_instantiates_and_has_identity(self) -> None:
        from extensions.tool_web_search.plugin import WebSearchPlugin

        p = WebSearchPlugin()
        assert p.id == "tool_web_search"
        assert p.kind == "tool"

    @pytest.mark.asyncio
    async def test_plugin_call_missing_query(self) -> None:
        from extensions.tool_web_search.plugin import WebSearchPlugin
        from jarvis_sdk import Err

        p = WebSearchPlugin()
        result = await p.call("web_search", {})
        assert isinstance(result, Err)
        assert result.code == "MISSING_ARG"

    @pytest.mark.asyncio
    async def test_plugin_call_compare_mode_auto(self) -> None:
        """Items present + no explicit mode → compare (auto)."""
        from extensions.tool_web_search.plugin import WebSearchPlugin
        from jarvis_sdk import Ok

        p = WebSearchPlugin()
        # items is a list of strings.
        result = await p.call("web_search", {"items": ["iPhone 15", "Pixel 8"]})
        # Even if backends fail, the dispatch should land on compare and
        # return an Ok with a human-readable comparison text.
        assert isinstance(result, Ok)
        assert "Comparison" in result.value or "iPhone" in result.value

    def test_format_ddg_empty(self) -> None:
        from extensions.tool_web_search import runtime

        assert runtime.format_ddg("nothing", []) == "No results found for: nothing"


class TestToolSendMessagePlugin:
    """PR 1C: extensions/tool_send_message/ — 6th consumer (pyautogui messenger)."""

    def test_manifest_file_exists(self) -> None:
        import json

        path = REPO_ROOT / "extensions" / "tool_send_message" / "openclaw.plugin.json"
        assert path.is_file()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["id"] == "tool_send_message"
        assert manifest["kind"] == "tool"

    def test_plugin_instantiates_and_has_identity(self) -> None:
        from extensions.tool_send_message.plugin import SendMessagePlugin

        p = SendMessagePlugin()
        assert p.id == "tool_send_message"
        assert p.kind == "tool"

    @pytest.mark.asyncio
    async def test_plugin_call_missing_receiver(self) -> None:
        from extensions.tool_send_message.plugin import SendMessagePlugin
        from jarvis_sdk import Err

        p = SendMessagePlugin()
        result = await p.call("send_message", {"message_text": "hi"})
        assert isinstance(result, Err)
        assert result.code == "MISSING_ARG"

    @pytest.mark.asyncio
    async def test_plugin_call_missing_message(self) -> None:
        from extensions.tool_send_message.plugin import SendMessagePlugin
        from jarvis_sdk import Err

        p = SendMessagePlugin()
        result = await p.call("send_message", {"receiver": "Alice"})
        assert isinstance(result, Err)
        assert result.code == "MISSING_ARG"

    def test_route_platform(self) -> None:
        from extensions.tool_send_message.plugin import _route_platform

        # Aliases
        assert _route_platform("whatsapp")[0] == "whatsapp"
        assert _route_platform("wp")[0] == "whatsapp"
        assert _route_platform("wapp")[0] == "whatsapp"
        assert _route_platform("instagram")[0] == "instagram"
        assert _route_platform("ig")[0] == "instagram"
        assert _route_platform("insta")[0] == "instagram"
        assert _route_platform("telegram")[0] == "telegram"
        assert _route_platform("tg")[0] == "telegram"
        # Generic fallback
        assert _route_platform("discord")[0] == "generic"
        assert _route_platform("signal")[0] == "generic"
        assert _route_platform("messenger")[0] == "generic"


class TestToolYouTubeVideoPlugin:
    """PR 1C: extensions/tool_youtube_video/ — 7th consumer (scraper + summarizer)."""

    def test_manifest_file_exists(self) -> None:
        import json

        path = REPO_ROOT / "extensions" / "tool_youtube_video" / "openclaw.plugin.json"
        assert path.is_file()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["id"] == "tool_youtube_video"
        assert manifest["kind"] == "tool"

    def test_plugin_instantiates_and_has_identity(self) -> None:
        from extensions.tool_youtube_video.plugin import YouTubeVideoPlugin

        p = YouTubeVideoPlugin()
        assert p.id == "tool_youtube_video"
        assert p.kind == "tool"

    def test_extract_video_id_from_url(self) -> None:
        from extensions.tool_youtube_video import runtime

        assert (
            runtime.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        )
        assert runtime.extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert (
            runtime.extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        )
        assert runtime.extract_video_id("https://example.com/") is None

    def test_is_valid_youtube_url(self) -> None:
        from extensions.tool_youtube_video import runtime

        assert runtime.is_valid_youtube_url("https://www.youtube.com/watch?v=abc")
        assert runtime.is_valid_youtube_url("https://youtu.be/abc")
        assert not runtime.is_valid_youtube_url("https://example.com/")
        assert not runtime.is_valid_youtube_url("")

    @pytest.mark.asyncio
    async def test_plugin_call_unknown_action(self) -> None:
        from extensions.tool_youtube_video.plugin import YouTubeVideoPlugin
        from jarvis_sdk import Err

        p = YouTubeVideoPlugin()
        result = await p.call("youtube_video", {"action": "not_a_real_action"})
        assert isinstance(result, Err)
        assert result.code == "UNKNOWN_ACTION"

    @pytest.mark.asyncio
    async def test_plugin_call_play_missing_query(self) -> None:
        from extensions.tool_youtube_video.plugin import YouTubeVideoPlugin
        from jarvis_sdk import Err

        p = YouTubeVideoPlugin()
        result = await p.call("youtube_video", {"action": "play"})
        assert isinstance(result, Err)
        assert result.code == "MISSING_ARG"

    @pytest.mark.asyncio
    async def test_plugin_call_get_info_bad_url(self) -> None:
        from extensions.tool_youtube_video.plugin import YouTubeVideoPlugin
        from jarvis_sdk import Err

        p = YouTubeVideoPlugin()
        result = await p.call("youtube_video", {"action": "get_info", "url": "not a url"})
        assert isinstance(result, Err)
        assert result.code == "BAD_URL"


class TestSlashCommandRouter:
    """PR 1C: apps/desktop/src/jarvis_desktop/commands.py (the slash-command router).

    Mirrors OpenClaw's command-routing flow. Free text falls through
    (returns None); `/name` routes to the plugin-registered handler.
    """

    def test_router_dispatches_to_handler(self) -> None:
        from jarvis_desktop.commands import CommandRouter
        from jarvis_sdk import CommandDecl, PluginCommandContext, PluginCommandResult

        async def my_handler(ctx: PluginCommandContext) -> PluginCommandResult:
            return PluginCommandResult(reply_text=f"hello from {ctx.command_body!r}")

        router = CommandRouter(
            [CommandDecl(name="hello", description="say hi", handler=my_handler)]
        )
        # We can't await in a sync test, so use asyncio.run.
        import asyncio

        result = asyncio.run(router.dispatch("/hello there"))
        assert result is not None
        assert "hello" in result.reply_text
        assert "/hello there" in result.reply_text

    def test_router_falls_through_on_free_text(self) -> None:
        from jarvis_desktop.commands import CommandRouter
        from jarvis_sdk import CommandDecl, PluginCommandContext, PluginCommandResult

        async def my_handler(ctx: PluginCommandContext) -> PluginCommandResult:  # pragma: no cover
            return PluginCommandResult(reply_text="never called")

        router = CommandRouter([CommandDecl(name="x", description="x", handler=my_handler)])
        import asyncio

        result = asyncio.run(router.dispatch("free text without slash"))
        assert result is None

    def test_router_unknown_command_returns_helpful_msg(self) -> None:
        from jarvis_desktop.commands import CommandRouter
        from jarvis_sdk import CommandDecl, PluginCommandContext, PluginCommandResult

        async def my_handler(ctx: PluginCommandContext) -> PluginCommandResult:  # pragma: no cover
            return PluginCommandResult(reply_text="never called")

        router = CommandRouter([CommandDecl(name="known", description="x", handler=my_handler)])
        import asyncio

        result = asyncio.run(router.dispatch("/unknown"))
        assert result is not None
        assert "Unknown command" in result.reply_text
        assert "/known" in result.reply_text

    def test_router_names_returns_sorted_list(self) -> None:
        from jarvis_desktop.commands import CommandRouter
        from jarvis_sdk import CommandDecl, PluginCommandContext, PluginCommandResult

        async def my_handler(ctx: PluginCommandContext) -> PluginCommandResult:  # pragma: no cover
            return PluginCommandResult(reply_text="x")

        router = CommandRouter(
            [
                CommandDecl(name="zeta", description="x", handler=my_handler),
                CommandDecl(name="alpha", description="x", handler=my_handler),
                CommandDecl(name="mid", description="x", handler=my_handler),
            ]
        )
        assert router.names() == ["alpha", "mid", "zeta"]


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
