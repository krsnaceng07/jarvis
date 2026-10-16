"""Phase 6.9b — extensions/runner.py tests.

Verifies the ExtensionRunner class mirrors
OpenClaw's `extensions/runner.ts`:
- Construction + bindCore / bindCommandContext
- Tool/flag/shortcut aggregation + conflict
  resolution
- Command name + invocation-name resolution
- createContext / createCommandContext lazy
  getters + assertActive guards
- emit() generic dispatch + cancel-on-result
  semantics for session_before_* events
- emitMessageEnd / emitToolResult chained
  replacement + role-check
- emitToolCall short-circuit on block
- emitUserBash short-circuit on first result
- emitContext chained transformation
- emitBeforeProviderRequest chained payload
- emitBeforeAgentStart chained system prompt
  + message collection
- emitResourcesDiscover path collection
- emitInput transform/handled chain
- invalidate / assertActive / onError
  / emitError
- emit_session_shutdown_event helper
- _build_builtin_keybindings reserved detection
"""
from __future__ import annotations

import asyncio
import pytest

from src.agents.sessions.extensions import (
    Extension,
    ExtensionActions,
    ExtensionContextActions,
    ExtensionError,
    ExtensionRuntime,
    ExtensionUIContext,
    ToolDefinition,
)
from src.agents.sessions.extensions.runner import (
    ExtensionRunner,
    RESERVED_KEYBINDINGS_FOR_EXTENSION_CONFLICTS,
    emit_session_shutdown_event,
    _build_builtin_keybindings,
)


# ============================================================================
# Fixtures
# ============================================================================


def _make_extension(
    path: str = "/ext/a",
    name: str = "a",
) -> Extension:
    return Extension(
        path=path,
        resolvedPath=path,
        sourceInfo={"source": "local", "baseDir": "/ext"},
        handlers={},
        tools={},
        messageRenderers={},
        commands={},
        flags={},
        shortcuts={},
    )


def _make_runtime() -> ExtensionRuntime:
    return ExtensionRuntime()


# ============================================================================
# Module surface
# ============================================================================


class TestModuleSurface:
    def test_reserved_set(self) -> None:
        assert "app.interrupt" in RESERVED_KEYBINDINGS_FOR_EXTENSION_CONFLICTS
        assert "app.exit" in RESERVED_KEYBINDINGS_FOR_EXTENSION_CONFLICTS
        assert "tui.input.submit" in RESERVED_KEYBINDINGS_FOR_EXTENSION_CONFLICTS

    def test_emit_session_shutdown_event_importable(self) -> None:
        assert callable(emit_session_shutdown_event)


# ============================================================================
# Construction + bindCore
# ============================================================================


class TestConstruction:
    def test_basic(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner._extensions == [ext]
        assert runner._runtime is rt
        assert runner._cwd == "/cwd"

    def test_no_ui_initially(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner.has_ui() is False

    def test_default_idle(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner._is_idle() is True


class TestBindCore:
    @pytest.mark.asyncio
    async def test_wires_actions(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        sent: list[dict] = []

        actions: ExtensionActions = {
            "sendMessage": lambda m, o=None: sent.append({"m": m, "o": o}),
            "sendUserMessage": lambda c, o=None: sent.append({"c": c}),
            "appendEntry": lambda t, d=None: sent.append({"t": t, "d": d}),
            "setSessionName": lambda n: sent.append({"n": n}),
            "getSessionName": lambda: "current",
            "setLabel": lambda i, l: sent.append({"i": i, "l": l}),
            "getActiveTools": lambda: ["bash"],
            "getAllTools": lambda: [],
            "setActiveTools": lambda names: sent.append({"names": names}),
            "refreshTools": lambda: None,
            "getCommands": lambda: [],
            "setModel": lambda m: asyncio.sleep(0, result=True),
            "getThinkingLevel": lambda: "high",
            "setThinkingLevel": lambda lvl: sent.append({"lvl": lvl}),
        }
        context_actions: ExtensionContextActions = {
            "getModel": lambda: None,
            "isIdle": lambda: True,
            "getSignal": lambda: None,
            "abort": lambda: None,
            "hasPendingMessages": lambda: False,
            "shutdown": lambda: None,
            "getContextUsage": lambda: None,
            "compact": lambda o=None: None,
            "getSystemPrompt": lambda: "sys",
        }

        runner.bind_core(actions, context_actions)
        # After binding, the runtime shares the same action instances.
        assert runner._runtime.sendMessage is actions["sendMessage"]
        assert runner._runtime.getActiveTools is actions["getActiveTools"]
        assert runner._is_idle is context_actions["isIdle"]
        assert runner._abort is context_actions["abort"]

    @pytest.mark.asyncio
    async def test_flushes_pending_provider_registrations(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        # Queue a registration BEFORE bind.
        rt.registerProvider("p", {"name": "P"}, "/ext/p")
        assert len(rt.pendingProviderRegistrations) == 1

        registered: list[dict] = []

        def _register(name: str, config: dict) -> None:
            registered.append({"name": name, "config": config})

        # Minimal actions
        actions: ExtensionActions = {
            "sendMessage": lambda *a, **k: None,
            "sendUserMessage": lambda *a, **k: None,
            "appendEntry": lambda *a, **k: None,
            "setSessionName": lambda *a, **k: None,
            "getSessionName": lambda *a, **k: None,
            "setLabel": lambda *a, **k: None,
            "getActiveTools": lambda *a, **k: [],
            "getAllTools": lambda *a, **k: [],
            "setActiveTools": lambda *a, **k: None,
            "refreshTools": lambda *a, **k: None,
            "getCommands": lambda *a, **k: [],
            "setModel": lambda *a, **k: asyncio.sleep(0, result=True),
            "getThinkingLevel": lambda *a, **k: "high",
            "setThinkingLevel": lambda *a, **k: None,
        }
        context_actions: ExtensionContextActions = {
            "getModel": lambda *a, **k: None,
            "isIdle": lambda *a, **k: True,
            "getSignal": lambda *a, **k: None,
            "abort": lambda *a, **k: None,
            "hasPendingMessages": lambda *a, **k: False,
            "shutdown": lambda *a, **k: None,
            "getContextUsage": lambda *a, **k: None,
            "compact": lambda *a, **k: None,
            "getSystemPrompt": lambda *a, **k: "",
        }
        provider_actions = {"registerProvider": _register}
        runner.bind_core(actions, context_actions, provider_actions)

        # After bind, the queue is flushed.
        assert len(rt.pendingProviderRegistrations) == 0
        assert len(registered) == 1
        assert registered[0]["name"] == "p"

    @pytest.mark.asyncio
    async def test_post_bind_register_calls_provider_directly(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        registered: list[dict] = []

        def _register(name: str, config: dict) -> None:
            registered.append({"name": name, "config": config})

        actions = self._make_actions()
        context_actions = self._make_context_actions()
        provider_actions = {"registerProvider": _register}
        runner.bind_core(actions, context_actions, provider_actions)

        # After bind, registerProvider should call _register directly
        # (NOT queue again).
        runner._runtime.registerProvider("p2", {"name": "P2"})
        assert len(registered) == 1
        assert registered[0]["name"] == "p2"

    @staticmethod
    def _make_actions() -> ExtensionActions:
        return {
            "sendMessage": lambda *a, **k: None,
            "sendUserMessage": lambda *a, **k: None,
            "appendEntry": lambda *a, **k: None,
            "setSessionName": lambda *a, **k: None,
            "getSessionName": lambda *a, **k: None,
            "setLabel": lambda *a, **k: None,
            "getActiveTools": lambda *a, **k: [],
            "getAllTools": lambda *a, **k: [],
            "setActiveTools": lambda *a, **k: None,
            "refreshTools": lambda *a, **k: None,
            "getCommands": lambda *a, **k: [],
            "setModel": lambda *a, **k: asyncio.sleep(0, result=True),
            "getThinkingLevel": lambda *a, **k: "high",
            "setThinkingLevel": lambda *a, **k: None,
        }

    @staticmethod
    def _make_context_actions() -> ExtensionContextActions:
        return {
            "getModel": lambda *a, **k: None,
            "isIdle": lambda *a, **k: True,
            "getSignal": lambda *a, **k: None,
            "abort": lambda *a, **k: None,
            "hasPendingMessages": lambda *a, **k: False,
            "shutdown": lambda *a, **k: None,
            "getContextUsage": lambda *a, **k: None,
            "compact": lambda *a, **k: None,
            "getSystemPrompt": lambda *a, **k: "",
        }


class TestBindCommandContext:
    def test_wires_command_handlers(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _wait() -> None:
            return None

        async def _new_session(*_a: object, **_k: object) -> dict:
            return {"cancelled": True}

        from src.agents.sessions.extensions.types import (
            ExtensionCommandContextActions,
        )

        actions: ExtensionCommandContextActions = {
            "waitForIdle": _wait,
            "newSession": _new_session,
            "fork": lambda *a, **k: asyncio.sleep(0, result={"cancelled": False}),
            "navigateTree": lambda *a, **k: asyncio.sleep(0, result={"cancelled": False}),
            "switchSession": lambda *a, **k: asyncio.sleep(0, result={"cancelled": False}),
            "reload": lambda *a, **k: asyncio.sleep(0, result=None),
        }
        runner.bind_command_context(actions)
        assert runner._wait_for_idle is _wait
        assert runner._new_session is _new_session

    def test_reset_to_noop_when_none(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        runner.bind_command_context(None)
        # New sessions should return cancelled=False
        result = asyncio.run(runner._new_session(None))
        assert result == {"cancelled": False}


# ============================================================================
# UI context
# ============================================================================


class TestUIContext:
    def test_default_is_no_op(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner.has_ui() is False
        ctx = runner.get_ui_context()
        assert callable(ctx["select"])

    def test_set_ui_context(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        def _fake_select(*args: object, **kwargs: object) -> "asyncio.Future[str]":
            fut: "asyncio.Future[str]" = asyncio.Future()
            fut.set_result("opt")
            return fut

        ui: ExtensionUIContext = {"select": _fake_select}
        runner.set_ui_context(ui)
        assert runner.has_ui() is True
        assert runner.get_ui_context() is ui

    def test_set_ui_context_none_resets_to_no_op(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        runner.set_ui_context(None)
        assert runner.has_ui() is False


# ============================================================================
# Tools / flags / shortcuts
# ============================================================================


class TestGetAllRegisteredTools:
    def test_first_wins(self) -> None:
        ext_a = _make_extension(path="/a")
        ext_b = _make_extension(path="/b")
        tool: ToolDefinition = {"name": "shared", "label": "T"}
        ext_a.tools["shared"] = {"definition": tool, "sourceInfo": ext_a.sourceInfo}
        ext_b.tools["shared"] = {"definition": tool, "sourceInfo": ext_b.sourceInfo}
        rt = _make_runtime()
        runner = ExtensionRunner([ext_a, ext_b], rt, "/cwd", "sm", "mr")
        result = runner.get_all_registered_tools()
        assert len(result) == 1
        assert result[0]["sourceInfo"] is ext_a.sourceInfo

    def test_empty(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner.get_all_registered_tools() == []


class TestGetToolDefinition:
    def test_found(self) -> None:
        ext = _make_extension()
        tool: ToolDefinition = {"name": "bash", "label": "Bash"}
        ext.tools["bash"] = {"definition": tool, "sourceInfo": ext.sourceInfo}
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner.get_tool_definition("bash") == tool

    def test_not_found(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner.get_tool_definition("nope") is None


class TestFlags:
    def test_set_and_get_values(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        runner.set_flag_value("verbose", True)
        runner.set_flag_value("model", "gpt-4")
        assert runner.get_flag_values() == {"verbose": True, "model": "gpt-4"}

    def test_get_flags_first_wins(self) -> None:
        ext_a = _make_extension(path="/a")
        ext_b = _make_extension(path="/b")
        ext_a.flags["v"] = {
            "name": "v",
            "type": "boolean",
            "extensionPath": "/a",
        }
        ext_b.flags["v"] = {
            "name": "v",
            "type": "string",
            "extensionPath": "/b",
        }
        rt = _make_runtime()
        runner = ExtensionRunner([ext_a, ext_b], rt, "/cwd", "sm", "mr")
        out = runner.get_flags()
        assert out["v"]["extensionPath"] == "/a"


class TestShortcuts:
    def test_no_conflicts(self) -> None:
        ext = _make_extension()
        ext.shortcuts["ctrl+x"] = {
            "shortcut": "ctrl+x",
            "extensionPath": "/a",
            "handler": lambda *a, **k: None,
        }
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        out = runner.get_shortcuts({})
        assert "ctrl+x" in out

    def test_reserved_builtin_skips(self) -> None:
        ext = _make_extension()
        ext.shortcuts["ctrl+c"] = {
            "shortcut": "ctrl+c",
            "extensionPath": "/a",
            "handler": lambda *a, **k: None,
        }
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        # ``app.interrupt`` is a reserved keybinding;
        # any extension trying to bind ``ctrl+c`` (the
        # same key) gets skipped.
        out = runner.get_shortcuts({"app.interrupt": "ctrl+c"})
        assert "ctrl+c" not in out
        # Diagnostic was recorded.
        diag = runner.get_shortcut_diagnostics()
        assert any("built-in shortcut" in d["message"] for d in diag)

    def test_collision_last_wins(self) -> None:
        ext_a = _make_extension(path="/a")
        ext_b = _make_extension(path="/b")
        ext_a.shortcuts["ctrl+k"] = {
            "shortcut": "ctrl+k",
            "extensionPath": "/a",
            "handler": lambda *a, **k: None,
        }
        ext_b.shortcuts["ctrl+k"] = {
            "shortcut": "ctrl+k",
            "extensionPath": "/b",
            "handler": lambda *a, **k: None,
        }
        rt = _make_runtime()
        runner = ExtensionRunner([ext_a, ext_b], rt, "/cwd", "sm", "mr")
        out = runner.get_shortcuts({})
        assert out["ctrl+k"]["extensionPath"] == "/b"

    def test_builtin_non_reserved_logs_diagnostic_but_overrides(self) -> None:
        ext = _make_extension()
        ext.shortcuts["my-key"] = {
            "shortcut": "my-key",
            "extensionPath": "/a",
            "handler": lambda *a, **k: None,
        }
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        out = runner.get_shortcuts({"my-binding": "my-key"})
        assert "my-key" in out
        diag = runner.get_shortcut_diagnostics()
        assert any("Using /a" in d["message"] for d in diag)


# ============================================================================
# Commands
# ============================================================================


class TestCommands:
    def test_unique_name(self) -> None:
        ext = _make_extension()
        ext.commands["hello"] = {
            "name": "hello",
            "sourceInfo": ext.sourceInfo,
            "handler": lambda *a, **k: asyncio.sleep(0),
        }
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        out = runner.get_registered_commands()
        assert len(out) == 1
        assert out[0]["invocationName"] == "hello"

    def test_duplicate_name_gets_suffix(self) -> None:
        ext_a = _make_extension(path="/a")
        ext_b = _make_extension(path="/b")
        ext_a.commands["hello"] = {
            "name": "hello",
            "sourceInfo": ext_a.sourceInfo,
            "handler": lambda *a, **k: asyncio.sleep(0),
        }
        ext_b.commands["hello"] = {
            "name": "hello",
            "sourceInfo": ext_b.sourceInfo,
            "handler": lambda *a, **k: asyncio.sleep(0),
        }
        rt = _make_runtime()
        runner = ExtensionRunner([ext_a, ext_b], rt, "/cwd", "sm", "mr")
        out = runner.get_registered_commands()
        names = sorted(c["invocationName"] for c in out)
        # OpenClaw: when a name has >1 registration,
        # EVERY occurrence gets the `:N` suffix
        # (occurrence is 1-indexed).
        assert names == ["hello:1", "hello:2"]

    def test_get_command(self) -> None:
        ext = _make_extension()
        ext.commands["hello"] = {
            "name": "hello",
            "sourceInfo": ext.sourceInfo,
            "handler": lambda *a, **k: asyncio.sleep(0),
        }
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        cmd = runner.get_command("hello")
        assert cmd is not None
        assert cmd["invocationName"] == "hello"

    def test_get_command_not_found(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner.get_command("nope") is None


# ============================================================================
# Invalidation + error listeners
# ============================================================================


class TestInvalidation:
    def test_default_active(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        runner._assert_active()  # should not raise

    def test_invalidate_first_message_wins(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        runner.invalidate("first")
        runner.invalidate("second")
        assert runner._stale_message == "first"
        with pytest.raises(RuntimeError, match="first"):
            runner._assert_active()


class TestOnError:
    def test_subscribe_and_emit(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        received: list[ExtensionError] = []

        unsub = runner.on_error(lambda e: received.append(e))
        runner.emit_error({"extensionPath": "/a", "event": "x", "error": "boom"})
        assert len(received) == 1
        assert received[0]["error"] == "boom"
        unsub()
        runner.emit_error({"extensionPath": "/a", "event": "x", "error": "boom2"})
        assert len(received) == 1

    def test_error_listener_exception_does_not_kill_dispatch(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        def _bad(_e: ExtensionError) -> None:
            raise RuntimeError("listener boom")

        runner.on_error(_bad)
        # Must not raise.
        runner.emit_error({"extensionPath": "/a", "event": "x", "error": "y"})


class TestHasHandlers:
    def test_true(self) -> None:
        ext = _make_extension()
        ext.handlers["session_start"] = [lambda *a, **k: None]
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner.has_handlers("session_start") is True

    def test_false(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner.has_handlers("session_start") is False


class TestGetMessageRenderer:
    def test_found(self) -> None:
        ext = _make_extension()
        ext.messageRenderers["my_custom"] = lambda *a, **k: None
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner.get_message_renderer("my_custom") is not None

    def test_not_found(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        assert runner.get_message_renderer("nope") is None


# ============================================================================
# Shutdown
# ============================================================================


class TestShutdown:
    def test_calls_handler(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        called: list[bool] = []
        runner._shutdown_handler = lambda: called.append(True)
        runner.shutdown()
        assert called == [True]


# ============================================================================
# createContext / createCommandContext
# ============================================================================


class TestCreateContext:
    def test_returns_view(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        ctx = runner.create_context()
        assert ctx.cwd == "/cwd"
        assert ctx.sessionManager == "sm"
        assert ctx.modelRegistry == "mr"
        assert ctx.isIdle() is True
        assert ctx.hasPendingMessages() is False

    def test_get_model(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        runner._get_model = lambda: {"id": "gpt-4"}
        ctx = runner.create_context()
        assert ctx.model == {"id": "gpt-4"}

    def test_assert_active_after_invalidate(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        ctx = runner.create_context()
        runner.invalidate("stale!")
        with pytest.raises(RuntimeError, match="stale!"):
            ctx.cwd  # noqa: B018

    def test_compact_with_options(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        seen: list[object] = []
        runner._compact = lambda o=None: seen.append(o)
        ctx = runner.create_context()
        ctx.compact({"customInstructions": "summarize"})
        assert seen == [{"customInstructions": "summarize"}]

    def test_compact_default_none(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        seen: list[object] = []
        runner._compact = lambda o=None: seen.append(o)
        ctx = runner.create_context()
        ctx.compact()
        assert seen == [None]

    def test_get_context_usage(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        runner._get_context_usage = lambda: {"tokens": 100, "contextWindow": 1000, "percent": 10.0}
        ctx = runner.create_context()
        assert ctx.getContextUsage() == {
            "tokens": 100,
            "contextWindow": 1000,
            "percent": 10.0,
        }

    def test_get_system_prompt(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        runner._get_system_prompt = lambda: "Hello."
        ctx = runner.create_context()
        assert ctx.getSystemPrompt() == "Hello."

    def test_abort_calls_handler(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        aborted: list[bool] = []
        runner._abort = lambda: aborted.append(True)
        ctx = runner.create_context()
        ctx.abort()
        assert aborted == [True]


class TestCreateCommandContext:
    @pytest.mark.asyncio
    async def test_command_methods_wired(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        ctx = runner.create_command_context()
        # Inherits the base context
        assert ctx.cwd == "/cwd"
        # Command methods are present
        assert callable(ctx.waitForIdle)
        assert callable(ctx.newSession)
        assert callable(ctx.fork)
        assert callable(ctx.navigateTree)
        assert callable(ctx.switchSession)
        assert callable(ctx.reload)

    @pytest.mark.asyncio
    async def test_new_session_calls_handler(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        seen: list[object] = []

        async def _new_session(options: object) -> dict:
            seen.append(options)
            return {"cancelled": True}

        runner._new_session = _new_session
        ctx = runner.create_command_context()
        result = await ctx.newSession({"parentSession": "p"})
        assert seen == [{"parentSession": "p"}]
        assert result == {"cancelled": True}

    @pytest.mark.asyncio
    async def test_reload(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        called: list[bool] = []

        async def _reload() -> None:
            called.append(True)

        runner._reload_handler = _reload
        ctx = runner.create_command_context()
        await ctx.reload()
        assert called == [True]

    def test_assert_active_after_invalidate(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        ctx = runner.create_command_context()
        runner.invalidate("stale!")
        with pytest.raises(RuntimeError, match="stale!"):
            ctx.waitForIdle()  # type: ignore[func-returns-value]


# ============================================================================
# emit: generic
# ============================================================================


class TestEmit:
    @pytest.mark.asyncio
    async def test_no_handlers(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        result = await runner.emit({"type": "session_start"})
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_result_from_session_before(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> dict:
            return {"cancel": True}

        ext.handlers["session_before_switch"] = [_handler]
        result = await runner.emit({"type": "session_before_switch"})
        assert result == {"cancel": True}

    @pytest.mark.asyncio
    async def test_continues_on_non_cancel_result(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> dict:
            return {"cancel": False}

        ext.handlers["session_before_switch"] = [_handler]
        result = await runner.emit({"type": "session_before_switch"})
        assert result == {"cancel": False}

    @pytest.mark.asyncio
    async def test_handler_error_emits_error(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> None:
            raise RuntimeError("boom")

        ext.handlers["session_start"] = [_handler]
        errors: list[ExtensionError] = []
        runner.on_error(lambda e: errors.append(e))
        await runner.emit({"type": "session_start"})
        assert any(e["error"] == "boom" for e in errors)


# ============================================================================
# emitMessageEnd
# ============================================================================


class TestEmitMessageEnd:
    @pytest.mark.asyncio
    async def test_no_handler_returns_none(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        out = await runner.emit_message_end(
            {"type": "message_end", "message": {"role": "assistant", "content": []}}
        )
        assert out is None

    @pytest.mark.asyncio
    async def test_handler_replaces_message(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> dict:
            new_msg = dict(event["message"], content=["hi"])
            return {"message": new_msg}

        ext.handlers["message_end"] = [_handler]
        out = await runner.emit_message_end(
            {"type": "message_end", "message": {"role": "assistant", "content": []}}
        )
        assert out is not None
        assert out["content"] == ["hi"]

    @pytest.mark.asyncio
    async def test_role_mismatch_emits_error(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> dict:
            return {"message": {"role": "user", "content": []}}

        ext.handlers["message_end"] = [_handler]
        errors: list[ExtensionError] = []
        runner.on_error(lambda e: errors.append(e))
        out = await runner.emit_message_end(
            {"type": "message_end", "message": {"role": "assistant", "content": []}}
        )
        assert out is None
        assert any("same role" in e["error"] for e in errors)


# ============================================================================
# emitToolResult
# ============================================================================


class TestEmitToolResult:
    @pytest.mark.asyncio
    async def test_no_handler_returns_none(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        out = await runner.emit_tool_result(
            {"type": "tool_result", "toolCallId": "1", "toolName": "bash", "content": [], "isError": False}
        )
        assert out is None

    @pytest.mark.asyncio
    async def test_handler_mutates_content(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> dict:
            return {"content": ["mutated"]}

        ext.handlers["tool_result"] = [_handler]
        out = await runner.emit_tool_result(
            {"type": "tool_result", "toolCallId": "1", "toolName": "bash", "content": [], "isError": False}
        )
        assert out is not None
        assert out["content"] == ["mutated"]


# ============================================================================
# emitToolCall
# ============================================================================


class TestEmitToolCall:
    @pytest.mark.asyncio
    async def test_no_handler_returns_none(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        out = await runner.emit_tool_call(
            {"type": "tool_call", "toolCallId": "1", "toolName": "bash", "input": {}}
        )
        assert out is None

    @pytest.mark.asyncio
    async def test_block_short_circuits(self) -> None:
        ext_a = _make_extension(path="/a")
        ext_b = _make_extension(path="/b")
        rt = _make_runtime()
        runner = ExtensionRunner([ext_a, ext_b], rt, "/cwd", "sm", "mr")

        b_called: list[bool] = []

        async def _a(event: dict, ctx: object) -> dict:
            return {"block": True, "reason": "denied"}

        async def _b(event: dict, ctx: object) -> dict:
            b_called.append(True)
            return {}

        ext_a.handlers["tool_call"] = [_a]
        ext_b.handlers["tool_call"] = [_b]
        out = await runner.emit_tool_call(
            {"type": "tool_call", "toolCallId": "1", "toolName": "bash", "input": {}}
        )
        assert out == {"block": True, "reason": "denied"}
        assert b_called == []  # second extension NOT called

    @pytest.mark.asyncio
    async def test_no_block_returns_last(self) -> None:
        ext_a = _make_extension(path="/a")
        ext_b = _make_extension(path="/b")
        rt = _make_runtime()
        runner = ExtensionRunner([ext_a, ext_b], rt, "/cwd", "sm", "mr")

        async def _a(event: dict, ctx: object) -> dict:
            return {"reason": "first"}

        async def _b(event: dict, ctx: object) -> dict:
            return {"reason": "second"}

        ext_a.handlers["tool_call"] = [_a]
        ext_b.handlers["tool_call"] = [_b]
        out = await runner.emit_tool_call(
            {"type": "tool_call", "toolCallId": "1", "toolName": "bash", "input": {}}
        )
        assert out is not None
        assert out["reason"] == "second"


# ============================================================================
# emitUserBash
# ============================================================================


class TestEmitUserBash:
    @pytest.mark.asyncio
    async def test_no_handler(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        out = await runner.emit_user_bash(
            {"type": "user_bash", "command": "ls", "excludeFromContext": False, "cwd": "/"}
        )
        assert out is None

    @pytest.mark.asyncio
    async def test_first_result_wins(self) -> None:
        ext_a = _make_extension(path="/a")
        ext_b = _make_extension(path="/b")
        rt = _make_runtime()
        runner = ExtensionRunner([ext_a, ext_b], rt, "/cwd", "sm", "mr")

        b_called: list[bool] = []

        async def _a(event: dict, ctx: object) -> dict:
            return {"result": {"exitCode": 0}}

        async def _b(event: dict, ctx: object) -> dict:
            b_called.append(True)
            return {"result": {"exitCode": 1}}

        ext_a.handlers["user_bash"] = [_a]
        ext_b.handlers["user_bash"] = [_b]
        out = await runner.emit_user_bash(
            {"type": "user_bash", "command": "ls", "excludeFromContext": False, "cwd": "/"}
        )
        assert out is not None
        assert out["result"]["exitCode"] == 0
        assert b_called == []


# ============================================================================
# emitContext
# ============================================================================


class TestEmitContext:
    @pytest.mark.asyncio
    async def test_no_handler(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        msgs = [{"role": "user", "content": "hi"}]
        out = await runner.emit_context(msgs)
        assert out == msgs

    @pytest.mark.asyncio
    async def test_handler_replaces_messages(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> dict:
            return {"messages": [{"role": "user", "content": "transformed"}]}

        ext.handlers["context"] = [_handler]
        out = await runner.emit_context([{"role": "user", "content": "hi"}])
        assert out == [{"role": "user", "content": "transformed"}]

    @pytest.mark.asyncio
    async def test_chained_transforms(self) -> None:
        ext_a = _make_extension(path="/a")
        ext_b = _make_extension(path="/b")
        rt = _make_runtime()
        runner = ExtensionRunner([ext_a, ext_b], rt, "/cwd", "sm", "mr")

        async def _a(event: dict, ctx: object) -> dict:
            return {"messages": [{"role": "user", "content": "from-a"}]}

        async def _b(event: dict, ctx: object) -> dict:
            return {"messages": [{"role": "user", "content": "from-b"}]}

        ext_a.handlers["context"] = [_a]
        ext_b.handlers["context"] = [_b]
        out = await runner.emit_context([{"role": "user", "content": "orig"}])
        assert out == [{"role": "user", "content": "from-b"}]


# ============================================================================
# emitBeforeProviderRequest
# ============================================================================


class TestEmitBeforeProviderRequest:
    @pytest.mark.asyncio
    async def test_no_handler_returns_payload(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        out = await runner.emit_before_provider_request({"x": 1})
        assert out == {"x": 1}

    @pytest.mark.asyncio
    async def test_handler_replaces_payload(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> dict:
            return {"x": 2}

        ext.handlers["before_provider_request"] = [_handler]
        out = await runner.emit_before_provider_request({"x": 1})
        assert out == {"x": 2}


# ============================================================================
# emitBeforeAgentStart
# ============================================================================


class TestEmitBeforeAgentStart:
    @pytest.mark.asyncio
    async def test_no_handler(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        out = await runner.emit_before_agent_start("hi", None, "sys", None)
        assert out is None

    @pytest.mark.asyncio
    async def test_handler_replaces_system_prompt(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> dict:
            return {"systemPrompt": "REPLACED"}

        ext.handlers["before_agent_start"] = [_handler]
        out = await runner.emit_before_agent_start("hi", None, "sys", None)
        assert out is not None
        assert out["systemPrompt"] == "REPLACED"

    @pytest.mark.asyncio
    async def test_handler_collects_messages(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> dict:
            return {"message": {"customType": "t", "content": "x"}}

        ext.handlers["before_agent_start"] = [_handler]
        out = await runner.emit_before_agent_start("hi", None, "sys", None)
        assert out is not None
        assert out["messages"] == [{"customType": "t", "content": "x"}]

    @pytest.mark.asyncio
    async def test_handler_gets_chained_system_prompt(self) -> None:
        ext_a = _make_extension(path="/a")
        ext_b = _make_extension(path="/b")
        rt = _make_runtime()
        runner = ExtensionRunner([ext_a, ext_b], rt, "/cwd", "sm", "mr")
        received: list[str] = []

        async def _a(event: dict, ctx: object) -> dict:
            received.append(event["systemPrompt"])
            return {"systemPrompt": "AFTER-A"}

        async def _b(event: dict, ctx: object) -> dict:
            received.append(event["systemPrompt"])
            return {}

        ext_a.handlers["before_agent_start"] = [_a]
        ext_b.handlers["before_agent_start"] = [_b]
        await runner.emit_before_agent_start("hi", None, "ORIGINAL", None)
        assert received == ["ORIGINAL", "AFTER-A"]


# ============================================================================
# emitResourcesDiscover
# ============================================================================


class TestEmitResourcesDiscover:
    @pytest.mark.asyncio
    async def test_no_handler(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        out = await runner.emit_resources_discover("/cwd", "startup")
        assert out == {"skillPaths": [], "promptPaths": [], "themePaths": []}

    @pytest.mark.asyncio
    async def test_handler_collects_paths(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> dict:
            return {
                "skillPaths": ["/p/s1", "/p/s2"],
                "promptPaths": ["/p/p1"],
                "themePaths": ["/p/t1", "/p/t2"],
            }

        ext.handlers["resources_discover"] = [_handler]
        out = await runner.emit_resources_discover("/cwd", "startup")
        assert out["skillPaths"] == [
            {"path": "/p/s1", "extensionPath": "/ext/a"},
            {"path": "/p/s2", "extensionPath": "/ext/a"},
        ]
        assert out["promptPaths"] == [{"path": "/p/p1", "extensionPath": "/ext/a"}]
        assert out["themePaths"] == [
            {"path": "/p/t1", "extensionPath": "/ext/a"},
            {"path": "/p/t2", "extensionPath": "/ext/a"},
        ]


# ============================================================================
# emitInput
# ============================================================================


class TestEmitInput:
    @pytest.mark.asyncio
    async def test_no_handler_returns_continue(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        out = await runner.emit_input("hi", None, "interactive")
        assert out == {"action": "continue"}

    @pytest.mark.asyncio
    async def test_handled_short_circuits(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> dict:
            return {"action": "handled"}

        ext.handlers["input"] = [_handler]
        out = await runner.emit_input("hi", None, "interactive")
        assert out == {"action": "handled"}

    @pytest.mark.asyncio
    async def test_transform_chain(self) -> None:
        ext_a = _make_extension(path="/a")
        ext_b = _make_extension(path="/b")
        rt = _make_runtime()
        runner = ExtensionRunner([ext_a, ext_b], rt, "/cwd", "sm", "mr")

        async def _a(event: dict, ctx: object) -> dict:
            return {"action": "transform", "text": "A"}

        async def _b(event: dict, ctx: object) -> dict:
            # Sees the chained text from A
            assert event["text"] == "A"
            return {"action": "transform", "text": "B"}

        ext_a.handlers["input"] = [_a]
        ext_b.handlers["input"] = [_b]
        out = await runner.emit_input("orig", None, "interactive")
        assert out == {"action": "transform", "text": "B", "images": None}

    @pytest.mark.asyncio
    async def test_no_change_returns_continue(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> None:
            return None

        ext.handlers["input"] = [_handler]
        out = await runner.emit_input("hi", None, "interactive")
        assert out == {"action": "continue"}


# ============================================================================
# emit_session_shutdown_event helper
# ============================================================================


class TestEmitSessionShutdownEvent:
    @pytest.mark.asyncio
    async def test_emitted(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")

        async def _handler(event: dict, ctx: object) -> None:
            return None

        ext.handlers["session_shutdown"] = [_handler]
        result = await emit_session_shutdown_event(
            runner, {"type": "session_shutdown", "reason": "quit"}
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_not_emitted_when_no_handlers(self) -> None:
        ext = _make_extension()
        rt = _make_runtime()
        runner = ExtensionRunner([ext], rt, "/cwd", "sm", "mr")
        result = await emit_session_shutdown_event(
            runner, {"type": "session_shutdown", "reason": "quit"}
        )
        assert result is False


# ============================================================================
# _build_builtin_keybindings
# ============================================================================


class TestBuildBuiltinKeybindings:
    def test_empty(self) -> None:
        assert _build_builtin_keybindings({}) == {}

    def test_reserved_marked(self) -> None:
        out = _build_builtin_keybindings({"app.interrupt": "ctrl+c"})
        assert "ctrl+c" in out
        assert out["ctrl+c"]["restrictOverride"] is True

    def test_non_reserved_marked_false(self) -> None:
        out = _build_builtin_keybindings({"my.binding": "ctrl+x"})
        assert out["ctrl+x"]["restrictOverride"] is False

    def test_reserved_takes_precedence(self) -> None:
        out = _build_builtin_keybindings(
            {"app.exit": "ctrl+d", "my.action": "ctrl+d"}
        )
        # The reserved action wins.
        assert out["ctrl+d"]["keybinding"] == "app.exit"
        assert out["ctrl+d"]["restrictOverride"] is True

    def test_normalizes_lowercase(self) -> None:
        out = _build_builtin_keybindings({"app.exit": "Ctrl+D"})
        assert "ctrl+d" in out

    def test_none_keys_skipped(self) -> None:
        out = _build_builtin_keybindings({"app.exit": None})
        assert out == {}

    def test_list_keys(self) -> None:
        out = _build_builtin_keybindings({"app.exit": ["ctrl+d", "ctrl+x"]})
        assert "ctrl+d" in out
        assert "ctrl+x" in out


# ============================================================================
# getExtensionPaths
# ============================================================================


class TestGetExtensionPaths:
    def test_returns_paths(self) -> None:
        ext_a = _make_extension(path="/a")
        ext_b = _make_extension(path="/b")
        rt = _make_runtime()
        runner = ExtensionRunner([ext_a, ext_b], rt, "/cwd", "sm", "mr")
        assert runner.get_extension_paths() == ["/a", "/b"]
