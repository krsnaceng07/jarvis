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

        # Phase 4.3h: 2 hardcoded (shutdown_jarvis, save_memory)
        # + 5 from OpenClaw extensions (memory_search, memory_get,
        # cron_schedule, cron_list, cron_cancel) = 7 total.
        # The 6 JARVIS-original tools (tool_weather, tool_reminder, tool_open_app,
        # tool_web_search, tool_send_message, tool_youtube_video) were removed in
        # Phase 4.3h per the "same to same" architect rule (none exist in OpenClaw).
        assert len(TOOL_DECLARATIONS) >= 7
        assert "agent_task" not in [d["name"] for d in TOOL_DECLARATIONS]
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


class TestPluginSdkLoader:
    """PR 1B: the SDK-driven plugin loader (app.py::_load_plugins).

    Verifies that the loader wires the new ``jarvis_sdk`` boundary
    correctly: it returns four parallel collections (tool_decls,
    plugin_dispatch, commands, cli_handlers) and never reaches into
    extensions directly.

    Phase 3 extended the return tuple from 8 to 10 elements to
    carry ``http_handlers`` and ``channel`` registrations.
    """

    def test_load_plugins_returns_eleven_collections(self) -> None:
        """_load_plugins returns the 11-tuple
        ``(decls, dispatch, commands, cli, skills, hooks, cron,
        doctor, http_handlers, gateway_methods, channel)``
        (Phase 3 added http+channel; Phase 5 added gateway_methods)."""
        from jarvis_desktop.app import _load_plugins

        result = _load_plugins()
        assert isinstance(result, tuple)
        assert len(result) == 11
        (
            tool_decls,
            dispatch,
            commands,
            cli,
            skills,
            hooks,
            cron_jobs,
            doctor_contracts,
            http_handlers,
            gateway_methods,
            channel,
        ) = result
        assert isinstance(tool_decls, list)
        assert isinstance(dispatch, dict)
        assert isinstance(commands, list)
        assert isinstance(cli, list)
        assert isinstance(skills, list)
        assert isinstance(hooks, list)
        assert isinstance(cron_jobs, list)
        assert isinstance(doctor_contracts, list)
        assert isinstance(http_handlers, list)
        assert (channel is None) or isinstance(channel, dict)

    def test_load_plugins_dispatch_values_are_pairs(self) -> None:
        """Each dispatch entry is (plugin_instance, call_name)."""
        from jarvis_desktop.app import _load_plugins

        (
            _decls,
            dispatch,
            _commands,
            _cli,
            _skills,
            _hooks,
            _cron,
            _doctor,
            _http,
            _gateway_methods,
            _channel,
        ) = _load_plugins()
        for tool_name, value in dispatch.items():
            assert isinstance(value, tuple)
            assert len(value) == 2
            _plugin_inst, call_name = value
            assert isinstance(call_name, str)
            assert call_name == tool_name  # dispatch key matches call name

    def test_load_plugins_tool_decls_have_required_fields(self) -> None:
        """Each tool decl has name + description + parameters OBJECT schema."""
        from jarvis_desktop.app import _load_plugins

        (
            tool_decls,
            _dispatch,
            _commands,
            _cli,
            _skills,
            _hooks,
            _cron,
            _doctor,
            _http,
            _gateway_methods,
            _channel,
        ) = _load_plugins()
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
        """``actions/reminder.py`` is gone (Phase 2 removed the entire ``actions/`` layer)."""
        legacy = REPO_ROOT / "actions" / "reminder.py"
        assert not legacy.exists(), (
            f"Legacy file still present: {legacy}. "
            "The entire actions/ directory was removed in Phase 2."
        )


class TestAppManifestLoader:
    """PR 1A+1B: `apps/desktop` reads tool decls from extensions/*/openclaw.plugin.json.

    The loader was renamed from `_load_plugin_manifests` (PR 1A) to
    `_load_plugins` (PR 1B) and now also returns a dispatch map, a
    commands list, and a CLI handler list. Phase 3 added two more
    fields (http_handlers, channel) for the gateway + telegram
    wiring.
    """

    def test_load_plugins_dispatch_maps_known_tools(self) -> None:
        """The dispatch map covers every tool declared by every loaded plugin."""
        from jarvis_desktop.app import _load_plugins

        (
            tool_decls,
            dispatch,
            _commands,
            _cli,
            _skills,
            _hooks,
            _cron,
            _doctor,
            _http,
            _gateway_methods,
            _channel,
        ) = _load_plugins()
        for d in tool_decls:
            assert d["name"] in dispatch, f"missing dispatch for {d['name']!r}"

    def test_load_plugins_commands_have_required_keys(self) -> None:
        """Each registered command carries name+description+handler."""
        from jarvis_desktop.app import _load_plugins
        from jarvis_sdk import CommandDecl

        (
            _tool_decls,
            _dispatch,
            commands,
            _cli,
            _skills,
            _hooks,
            _cron,
            _doctor,
            _http,
            _gateway_methods,
            _channel,
        ) = _load_plugins()
        # Phase 4.3h: removed 6 JARVIS-original tools (none in OpenClaw).
        # Only the 5 OpenClaw-parity extensions register commands today.
        for c in commands:
            assert isinstance(c, CommandDecl)
            assert c.name
            assert c.description
            # Phase 1C: handler is REQUIRED on every registered command.
            assert callable(c.handler), f"command {c.name!r} has no handler"

    def test_tool_declarations_includes_manifest_entries(self) -> None:
        """`TOOL_DECLARATIONS` is the union of hardcoded + manifest-loaded tools."""
        from jarvis_desktop.app import TOOL_DECLARATIONS

        names = [d["name"] for d in TOOL_DECLARATIONS]
        # 5 tools loaded from OpenClaw-parity extensions (Phase 4.3h):
        for expected in (
            "memory_search",  # memory_core
            "memory_get",  # memory_core
            "cron_schedule",  # cron
            "cron_list",  # cron
            "cron_cancel",  # cron
        ):
            assert expected in names, f"missing tool {expected!r} in TOOL_DECLARATIONS"
        # No duplicates.
        assert len(names) == len(set(names))


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
