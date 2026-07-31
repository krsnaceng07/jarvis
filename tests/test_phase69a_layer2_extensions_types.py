"""Phase 6.9a — extensions/types.py smoke tests.

Verifies the public surface of the extension
type system mirrors OpenClaw's `extensions/types.ts`:
- TypedDict shapes are importable
- dataclass shapes (Extension, ExtensionRuntime)
  work end-to-end (create, mutate, default
  action stubs raise)
- Type guards narrow correctly
- define_tool is an identity function
- Module barrel re-exports the full surface
- Default action stubs raise
  RuntimeError("not initialized") until bound
- ExtensionRuntime.invalidate/assertActive
  track the stale-message state correctly
"""
from __future__ import annotations

import pytest

from src.agents.sessions.extensions import (
    AbortSignal,
    AgentEndEvent,
    AgentMessage,
    AgentStartEvent,
    BeforeAgentStartEvent,
    BeforeProviderRequestEvent,
    Component,
    ContextEvent,
    ContextUsage,
    Extension,
    ExtensionAPI,
    ExtensionContext,
    ExtensionContextActions,
    ExtensionError,
    ExtensionFactory,
    ExtensionFlag,
    ExtensionRuntime,
    ExtensionShortcut,
    ExtensionUIContext,
    HandlerFn,
    ImageContent,
    InputEvent,
    KeyId,
    LoadExtensionsResult,
    MessageEndEvent,
    Model,
    ModelSelectEvent,
    NewSessionOptions,
    OAuthCredentials,
    ProviderConfig,
    ReadonlySessionManager,
    RegisteredCommand,
    RegisteredTool,
    ResourcesDiscoverEvent,
    SessionBeforeCompactEvent,
    SessionBeforeSwitchEvent,
    SessionManager,
    SessionShutdownEvent,
    SessionStartEvent,
    SourceInfo,
    TextContent,
    Theme,
    ToolCallEvent,
    ToolDefinition,
    ToolInfo,
    ToolResultEvent,
    TreePreparation,
    UserBashEvent,
    define_tool,
    is_bash_tool_result,
    is_edit_tool_result,
    is_find_tool_result,
    is_grep_tool_result,
    is_ls_tool_result,
    is_read_tool_result,
    is_tool_call_event_type,
    is_write_tool_result,
)
from src.agents.sessions.extensions.types import (
    DEFAULT_STALE_MESSAGE,
    InputSource,
    _not_initialized,
)


# ============================================================================
# Module surface
# ============================================================================


class TestModuleSurface:
    """All public types are importable from the
    barrel."""

    def test_extension_runtime_is_dataclass(self) -> None:
        from dataclasses import is_dataclass
        assert is_dataclass(ExtensionRuntime)

    def test_extension_is_dataclass(self) -> None:
        from dataclasses import is_dataclass
        assert is_dataclass(Extension)

    def test_all_typed_dicts_importable(self) -> None:
        # Spot-check a handful of TypedDict shapes
        for cls in (
            ContextUsage,
            ResourcesDiscoverEvent,
            SessionStartEvent,
            SessionBeforeSwitchEvent,
            SessionBeforeCompactEvent,
            SessionShutdownEvent,
            TreePreparation,
            ContextEvent,
            BeforeProviderRequestEvent,
            BeforeAgentStartEvent,
            AgentStartEvent,
            AgentEndEvent,
            MessageEndEvent,
            ToolCallEvent,
            ToolResultEvent,
            UserBashEvent,
            InputEvent,
            ModelSelectEvent,
            ExtensionContext,
            ExtensionUIContext,
            ExtensionContextActions,
            ToolDefinition,
            ToolInfo,
            RegisteredCommand,
            RegisteredTool,
            ExtensionFlag,
            ExtensionShortcut,
            ExtensionError,
            OAuthCredentials,
            ProviderConfig,
            NewSessionOptions,
        ):
            assert hasattr(cls, "__total__")


# ============================================================================
# Extension dataclass
# ============================================================================


class TestExtensionDataclass:
    """Extension dataclass can be constructed
    with all required fields."""

    def _make_extension(self) -> Extension:
        return Extension(
            path="/test/ext",
            resolvedPath="/test/ext/index.py",
            sourceInfo={"source": "local", "baseDir": "/test/ext"},
            handlers={},
            tools={},
            messageRenderers={},
            commands={},
            flags={},
            shortcuts={},
        )

    def test_create_empty(self) -> None:
        ext = self._make_extension()
        assert ext.path == "/test/ext"
        assert ext.resolvedPath == "/test/ext/index.py"
        assert ext.handlers == {}
        assert ext.tools == {}
        assert ext.commands == {}
        assert ext.flags == {}
        assert ext.shortcuts == {}

    def test_register_handler(self) -> None:
        ext = self._make_extension()
        handler: HandlerFn = lambda *a, **k: None
        ext.handlers.setdefault("session_start", []).append(handler)
        assert ext.handlers["session_start"] == [handler]

    def test_register_tool(self) -> None:
        ext = self._make_extension()
        tool: ToolDefinition = {"name": "t", "label": "T", "description": "d"}
        ext.tools[tool["name"]] = {
            "definition": tool,
            "sourceInfo": ext.sourceInfo,
        }
        assert ext.tools["t"]["definition"]["name"] == "t"


# ============================================================================
# ExtensionRuntime (default action stubs + invalidation)
# ============================================================================


class TestExtensionRuntimeDefaults:
    """Default action stubs raise RuntimeError
    until ``bindCore()`` replaces them. Mirrors
    the OpenClaw ``notInitialized`` shim
    (``extensions/types.ts`` via
    ``loader.ts:247-251``)."""

    def test_default_send_message_raises(self) -> None:
        rt = ExtensionRuntime()
        with pytest.raises(RuntimeError, match="not initialized"):
            rt.sendMessage({"customType": "x"})

    def test_default_set_session_name_raises(self) -> None:
        rt = ExtensionRuntime()
        with pytest.raises(RuntimeError, match="not initialized"):
            rt.setSessionName("foo")

    def test_default_get_active_tools_raises(self) -> None:
        rt = ExtensionRuntime()
        with pytest.raises(RuntimeError, match="not initialized"):
            rt.getActiveTools()

    def test_default_refresh_tools_is_noop(self) -> None:
        """``refreshTools`` is the one exception —
        the OpenClaw source ships it as a no-op
        pre-bind so ``registerTool`` can call it
        during loading (``loader.ts:269-270``)."""
        rt = ExtensionRuntime()
        # Must not raise.
        assert rt.refreshTools() is None

    def test_default_register_provider_queues(self) -> None:
        """Pre-bind ``registerProvider`` queues
        the registration so ``bindCore()`` can
        flush it once the model registry is
        available (``loader.ts:285-292``)."""
        rt = ExtensionRuntime()
        rt.registerProvider("p", {"name": "P"}, "/ext/p")
        assert len(rt.pendingProviderRegistrations) == 1
        assert rt.pendingProviderRegistrations[0]["name"] == "p"

    def test_default_unregister_provider_removes_from_queue(self) -> None:
        rt = ExtensionRuntime()
        rt.registerProvider("p", {"name": "P"}, "/ext/p")
        rt.registerProvider("q", {"name": "Q"}, "/ext/q")
        rt.unregisterProvider("p")
        assert len(rt.pendingProviderRegistrations) == 1
        assert rt.pendingProviderRegistrations[0]["name"] == "q"


class TestExtensionRuntimeStaleness:
    """``invalidate`` + ``assertActive`` track
    the stale-instance state. Mirrors
    ``runner.ts:491-504``."""

    def test_default_active(self) -> None:
        rt = ExtensionRuntime()
        # Must not raise.
        rt.assertActive()

    def test_invalidate_sets_message(self) -> None:
        rt = ExtensionRuntime()
        rt.invalidate("stale!")
        assert rt._stale_message == "stale!"

    def test_invalidate_default_uses_canonical_message(self) -> None:
        rt = ExtensionRuntime()
        rt.invalidate()
        assert rt._stale_message == DEFAULT_STALE_MESSAGE

    def test_invalidate_first_message_wins(self) -> None:
        rt = ExtensionRuntime()
        rt.invalidate("first")
        rt.invalidate("second")
        assert rt._stale_message == "first"

    def test_assert_active_raises_after_invalidate(self) -> None:
        rt = ExtensionRuntime()
        rt.invalidate("stale!")
        with pytest.raises(RuntimeError, match="stale!"):
            rt.assertActive()

    def test_invalidate_callable(self) -> None:
        """``invalidate`` is a method on
        ``ExtensionRuntime`` (the OpenClaw
        source has it on the runtime interface)."""
        rt = ExtensionRuntime()
        assert callable(rt.invalidate)
        assert callable(rt.assertActive)


# ============================================================================
# Type guards
# ============================================================================


class TestToolResultGuards:
    """ToolResultEvent type guards narrow by
    ``toolName``. Mirrors
    ``extensions/types.ts:972-992``."""

    def test_is_bash(self) -> None:
        e: ToolResultEvent = {"toolName": "bash", "toolCallId": "x"}
        assert is_bash_tool_result(e) is True

    def test_is_read(self) -> None:
        e: ToolResultEvent = {"toolName": "read", "toolCallId": "x"}
        assert is_read_tool_result(e) is True

    def test_is_edit(self) -> None:
        e: ToolResultEvent = {"toolName": "edit", "toolCallId": "x"}
        assert is_edit_tool_result(e) is True

    def test_is_write(self) -> None:
        e: ToolResultEvent = {"toolName": "write", "toolCallId": "x"}
        assert is_write_tool_result(e) is True

    def test_is_grep(self) -> None:
        e: ToolResultEvent = {"toolName": "grep", "toolCallId": "x"}
        assert is_grep_tool_result(e) is True

    def test_is_find(self) -> None:
        e: ToolResultEvent = {"toolName": "find", "toolCallId": "x"}
        assert is_find_tool_result(e) is True

    def test_is_ls(self) -> None:
        e: ToolResultEvent = {"toolName": "ls", "toolCallId": "x"}
        assert is_ls_tool_result(e) is True

    def test_wrong_tool_returns_false(self) -> None:
        e: ToolResultEvent = {"toolName": "bash", "toolCallId": "x"}
        assert is_read_tool_result(e) is False
        assert is_write_tool_result(e) is False
        assert is_grep_tool_result(e) is False
        assert is_find_tool_result(e) is False
        assert is_ls_tool_result(e) is False
        assert is_edit_tool_result(e) is False


class TestIsToolCallEventType:
    """``is_tool_call_event_type`` is a generic
    tool-name matcher. Mirrors
    ``extensions/types.ts:1014-1045``."""

    def test_matches_builtin(self) -> None:
        e: ToolCallEvent = {"toolName": "bash", "toolCallId": "x"}
        assert is_tool_call_event_type("bash", e) is True

    def test_matches_custom(self) -> None:
        e: ToolCallEvent = {"toolName": "my_tool", "toolCallId": "x"}
        assert is_tool_call_event_type("my_tool", e) is True

    def test_no_match(self) -> None:
        e: ToolCallEvent = {"toolName": "bash", "toolCallId": "x"}
        assert is_tool_call_event_type("read", e) is False


# ============================================================================
# defineTool
# ============================================================================


class TestDefineTool:
    """``define_tool`` is an identity function
    in Python (no TS type-narrowing to
    preserve). Mirrors
    ``extensions/types.ts:559-563``."""

    def test_identity(self) -> None:
        tool: ToolDefinition = {"name": "t", "label": "T"}
        assert define_tool(tool) is tool

    def test_with_all_fields(self) -> None:
        tool: ToolDefinition = {
            "name": "t",
            "label": "T",
            "description": "d",
            "parameters": {"type": "object", "properties": {}},
            "promptSnippet": "snippet",
            "promptGuidelines": ["g1", "g2"],
        }
        out = define_tool(tool)
        assert out == tool


# ============================================================================
# _not_initialized helper
# ============================================================================


class TestNotInitializedHelper:
    """The internal ``_not_initialized`` raises
    a canonical error when called. Mirrors
    ``loader.ts:247-251``."""

    def test_raises_runtime_error(self) -> None:
        with pytest.raises(RuntimeError, match="not initialized"):
            _not_initialized()


# ============================================================================
# Constants
# ============================================================================


class TestConstants:
    def test_default_stale_message(self) -> None:
        # The stale-instance message is a long,
        # stable string. We don't snapshot the
        # exact text — we just confirm the
        # OpenClaw-faithful "Do not use a
        # captured api or command ctx" hint is
        # present.
        assert "stale after session replacement" in DEFAULT_STALE_MESSAGE
        assert "Do not use a captured api" in DEFAULT_STALE_MESSAGE

    def test_input_source_string(self) -> None:
        # The InputSource type alias is a plain
        # str (the Python port doesn't use
        # typing.Literal for these — same as
        # how the rest of Layer 2 handles
        # union types).
        assert InputSource == str
