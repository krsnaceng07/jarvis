"""jarvis.agents.sessions.extensions.runner — extension runner.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/extensions/runner.ts``.

Phase 6.9b — ``ExtensionRunner`` + ``emitSessionShutdownEvent``
helper. The runner is the bridge between the
session runtime and the loaded extensions. It
owns the per-event dispatch (each ``emitXxx``
method iterates the extensions' handlers,
catches errors, and aggregates the results per
the OpenClaw contract).

Adaptations
-----------
- The OpenClaw source's ``structuredClone``
  is replaced with :func:`copy.deepcopy`
  (the standard Python equivalent).
- The OpenClaw source's chained-Promise
  :func:`emit` returns the chained result
  via ``await``; the Python port uses
  ``asyncio`` (a 1:1 port — every ``emitXxx``
  is a coroutine).
- The OpenClaw source's ``Object.defineProperties``
  (used to keep getters lazy on
  ``createCommandContext``) is replaced with
  the same approach via a fresh dict +
  the wrapped context's existing methods.
- The OpenClaw source's getter-style context
  properties (``get ui()``) become
  callable methods in Python (or are stored
  on the dict). The Python port preserves
  the same lazy-evaluation semantics by
  storing closures over the runner state.
- The OpenClaw source's
  ``getBuiltinKeybindings`` /
  ``RESERVED_KEYBINDINGS_FOR_EXTENSION_CONFLICTS``
  are kept as-is (the keybindings module
  lands in Phase 6.12).
"""
from __future__ import annotations

import copy
import logging
from typing import (
    Any,
    Awaitable,
    Callable,
    Optional,
    Union,
)

from .types import (
    AgentMessage,
    BeforeAgentStartEvent,
    BeforeProviderRequestEvent,
    CompactOptions,
    ContextEvent,
    ContextUsage,
    Extension,
    ExtensionActions,
    ExtensionCommandContext,
    ExtensionCommandContextActions,
    ExtensionContext,
    ExtensionContextActions,
    ExtensionError,
    ExtensionErrorListener,
    ExtensionFlag,
    ExtensionRuntime,
    ExtensionShortcut,
    ExtensionUIContext,
    ForkOptions,
    ImageContent,
    InputEvent,
    InputEventResult,
    InputSource,
    MessageEndEvent,
    MessageRenderer,
    Model,
    NavigateTreeOptions,
    NewSessionOptions,
    ProviderConfig,
    RegisteredCommand,
    RegisteredTool,
    ResolvedCommand,
    ResourcesDiscoverEvent,
    SessionManager,
    SessionShutdownEvent,
    ShutdownHandler,
    SwitchSessionOptions,
    ToolCallEvent,
    ToolResultEvent,
    UserBashEvent,
)


_log = logging.getLogger("jarvis.agents.sessions.extensions.runner")


# ============================================================================
# Built-in keybinding conflict surface
# ============================================================================


#: Reserved built-in keybinding names that
#: extension shortcuts may NOT override. Mirrors
#: ``RESERVED_KEYBINDINGS_FOR_EXTENSION_CONFLICTS``
#: (``runner.ts:62-80``).
RESERVED_KEYBINDINGS_FOR_EXTENSION_CONFLICTS = frozenset(
    (
        "app.interrupt",
        "app.clear",
        "app.exit",
        "app.suspend",
        "app.thinking.cycle",
        "app.model.cycleForward",
        "app.model.cycleBackward",
        "app.model.select",
        "app.tools.expand",
        "app.thinking.toggle",
        "app.editor.external",
        "app.message.followUp",
        "tui.input.submit",
        "tui.select.confirm",
        "tui.select.cancel",
        "tui.input.copy",
        "tui.editor.deleteToLineEnd",
    )
)


# ============================================================================
# Helper: emitSessionShutdownEvent
# ============================================================================


async def emit_session_shutdown_event(
    extension_runner: "ExtensionRunner",
    event: SessionShutdownEvent,
) -> bool:
    """Emit ``session_shutdown`` to extensions.
    Returns ``True`` if the event was emitted
    (at least one handler ran), ``False`` if
    no extensions had a handler. Mirrors
    ``emitSessionShutdownEvent``
    (``runner.ts:202-211``)."""
    if extension_runner.has_handlers("session_shutdown"):
        await extension_runner.emit(event)
        return True
    return False


# ============================================================================
# Built-in keybinding merge helper
# ============================================================================


def _build_builtin_keybindings(
    resolved_keybindings: dict,
) -> dict:
    """Build the built-in keybinding map
    from the resolved keybindings config.
    Returns ``{normalizedKey: {keybinding,
    restrictOverride}}``. Mirrors
    ``buildBuiltinKeybindings``
    (``runner.ts:84-109``).

    The OpenClaw source uses ``{KeyId: {…}}``
    where ``KeyId`` is a string; the Python
    port uses plain ``str`` keys.
    """
    out: dict = {}
    for keybinding, keys in (resolved_keybindings or {}).items():
        if keys is None:
            continue
        key_list = list(keys) if isinstance(keys, (list, tuple)) else [keys]
        restrict = keybinding in RESERVED_KEYBINDINGS_FOR_EXTENSION_CONFLICTS
        for key in key_list:
            normalized_key = str(key).lower()
            existing = out.get(normalized_key)
            if existing is not None and existing.get("restrictOverride") and not restrict:
                continue
            out[normalized_key] = {
                "keybinding": keybinding,
                "restrictOverride": restrict,
            }
    return out


# ============================================================================
# No-op UI context
# ============================================================================


def _make_no_op_ui_context() -> ExtensionUIContext:
    """Build the no-op ``ExtensionUIContext``
    used when a real UI is not available
    (RPC / print mode). Mirrors
    ``noOpUIContext`` (``runner.ts:213-247``)."""
    return {
        "select": _async_undefined_str,
        "confirm": _async_false,
        "input": _async_undefined_str,
        "notify": _noop,
        "onTerminalInput": _unsubscribe,
        "setStatus": _noop,
        "setWorkingMessage": _noop,
        "setWorkingVisible": _noop,
        "setWorkingIndicator": _noop,
        "setHiddenThinkingLabel": _noop,
        "setWidget": _noop,
        "setFooter": _noop,
        "setHeader": _noop,
        "setTitle": _noop,
        "custom": _async_undefined,
        "pasteToEditor": _noop,
        "setEditorText": _noop,
        "getEditorText": _return_empty_string,
        "editor": _async_undefined_str,
        "addAutocompleteProvider": _noop,
        "setEditorComponent": _noop,
        "getEditorComponent": _return_undefined,
        "theme": None,
        "getAllThemes": _return_empty_list,
        "getTheme": _return_undefined,
        "setTheme": _set_theme_noop,
        "getToolsExpanded": _return_false,
        "setToolsExpanded": _noop,
    }


async def _async_undefined_str(*_args: Any, **_kwargs: Any) -> Optional[str]:
    return None


async def _async_false(*_args: Any, **_kwargs: Any) -> bool:
    return False


async def _async_undefined(*_args: Any, **_kwargs: Any) -> Any:
    return None


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


def _unsubscribe(_handler: Any) -> Callable[[], None]:
    return _noop


def _return_empty_string() -> str:
    return ""


def _return_undefined() -> Any:
    return None


def _return_empty_list() -> list:
    return []


def _set_theme_noop(_next_theme: Union[str, Any]) -> dict:
    return {"success": False, "error": "UI not available"}


def _return_false() -> bool:
    return False


#: Singleton no-op UI context (created on
#: first use).
_NO_OP_UI_CONTEXT: Optional[ExtensionUIContext] = None


def _get_no_op_ui_context() -> ExtensionUIContext:
    global _NO_OP_UI_CONTEXT
    if _NO_OP_UI_CONTEXT is None:
        _NO_OP_UI_CONTEXT = _make_no_op_ui_context()
    return _NO_OP_UI_CONTEXT


# ============================================================================
# ExtensionRunner
# ============================================================================


#: Union of ``ExtensionEvent`` types handled
#: by the generic ``emit()`` method. Events
#: with dedicated ``emitXxx()`` methods are
#: excluded for stronger type safety. Mirrors
#: ``RunnerEmitEvent`` (``runner.ts:121-132``).
#: The Python port uses ``dict``-shaped events
#: with a ``type`` discriminator; ``isinstance``
#: checks are replaced with ``event.get("type")``
#: dispatch.
_SESSION_BEFORE_EVENT_TYPES = frozenset(
    (
        "session_before_switch",
        "session_before_fork",
        "session_before_compact",
        "session_before_tree",
    )
)


class ExtensionRunner:
    """Extension runner — executes extensions
    and manages their lifecycle. Mirrors
    ``ExtensionRunner``
    (``runner.ts:249-1147``).

    The Python port keeps the same public
    surface (the bound actions, the ``emitXxx``
    methods, the ``createContext`` /
    ``createCommandContext`` factories) but
    uses ``dict`` + closure storage instead of
    private fields. The instance is mutable
    after construction (the OpenClaw source
    allows :meth:`bindCore` / :meth:`bindCommandContext`
    / :meth:`setUIContext` to swap the
    bound functions at runtime).
    """

    def __init__(
        self,
        extensions: list[Extension],
        runtime: ExtensionRuntime,
        cwd: str,
        session_manager: SessionManager,
        model_registry: Any,
    ) -> None:
        self._extensions = list(extensions)
        self._runtime = runtime
        self._cwd = cwd
        self._session_manager = session_manager
        self._model_registry = model_registry
        self._ui_context: ExtensionUIContext = _get_no_op_ui_context()
        self._error_listeners: list[ExtensionErrorListener] = []
        self._get_model: Callable[[], Optional[Model]] = lambda: None
        self._is_idle: Callable[[], bool] = lambda: True
        self._get_signal: Callable[[], Optional[Any]] = lambda: None
        self._wait_for_idle: Callable[[], Awaitable[None]] = _async_noop
        self._abort: Callable[[], None] = _noop
        self._has_pending: Callable[[], bool] = lambda: False
        self._get_context_usage: Callable[[], Optional[ContextUsage]] = lambda: None
        self._compact: Callable[[Optional[CompactOptions]], None] = _noop
        self._get_system_prompt: Callable[[], str] = lambda: ""
        self._new_session: NewSessionHandler = _async_cancelled_false
        self._fork: ForkHandler = _async_cancelled_false
        self._navigate_tree: NavigateTreeHandler = _async_cancelled_false
        self._switch_session: SwitchSessionHandler = _async_cancelled_false
        self._reload_handler: ReloadHandler = _async_noop
        self._shutdown_handler: ShutdownHandler = _noop
        self._shortcut_diagnostics: list[dict] = []
        self._command_diagnostics: list[dict] = []
        self._stale_message: Optional[str] = None

    # ------------------------------------------------------------------
    # bindCore — wire action implementations
    # ------------------------------------------------------------------

    def bind_core(
        self,
        actions: ExtensionActions,
        context_actions: ExtensionContextActions,
        provider_actions: Optional[dict] = None,
    ) -> None:
        """Copy the host's action implementations
        into the shared runtime + flush any
        provider registrations queued during
        loading. Mirrors ``bindCore``
        (``runner.ts:291-361``)."""
        self._runtime.sendMessage = actions["sendMessage"]
        self._runtime.sendUserMessage = actions["sendUserMessage"]
        self._runtime.appendEntry = actions["appendEntry"]
        self._runtime.setSessionName = actions["setSessionName"]
        self._runtime.getSessionName = actions["getSessionName"]
        self._runtime.setLabel = actions["setLabel"]
        self._runtime.getActiveTools = actions["getActiveTools"]
        self._runtime.getAllTools = actions["getAllTools"]
        self._runtime.setActiveTools = actions["setActiveTools"]
        self._runtime.refreshTools = actions["refreshTools"]
        self._runtime.getCommands = actions["getCommands"]
        self._runtime.setModel = actions["setModel"]
        self._runtime.getThinkingLevel = actions["getThinkingLevel"]
        self._runtime.setThinkingLevel = actions["setThinkingLevel"]

        # Context actions
        self._get_model = context_actions["getModel"]
        self._is_idle = context_actions["isIdle"]
        self._get_signal = context_actions["getSignal"]
        self._abort = context_actions["abort"]
        self._has_pending = context_actions["hasPendingMessages"]
        self._shutdown_handler = context_actions["shutdown"]
        self._get_context_usage = context_actions["getContextUsage"]
        self._compact = context_actions["compact"]
        self._get_system_prompt = context_actions["getSystemPrompt"]

        # Flush pending provider registrations
        for entry in list(self._runtime.pendingProviderRegistrations):
            name = entry["name"]
            config = entry["config"]
            ext_path = entry["extensionPath"]
            try:
                register = (
                    provider_actions["registerProvider"]
                    if provider_actions and "registerProvider" in provider_actions
                    else None
                )
                if register is not None:
                    register(name, config)
                else:
                    self._model_registry.registerProvider(name, config)
            except Exception as exc:
                self.emit_error(
                    {
                        "extensionPath": ext_path,
                        "event": "register_provider",
                        "error": str(exc),
                        "stack": getattr(exc, "stack", None),
                    }
                )
        self._runtime.pendingProviderRegistrations = []

        # From this point on, register/unregister takes effect immediately
        register_provider = (
            provider_actions["registerProvider"]
            if provider_actions and "registerProvider" in provider_actions
            else None
        )
        unregister_provider = (
            provider_actions["unregisterProvider"]
            if provider_actions and "unregisterProvider" in provider_actions
            else None
        )

        def _post_bind_register(
            name: str, config: ProviderConfig, *args: Any, **kwargs: Any
        ) -> None:
            del args, kwargs
            if register_provider is not None:
                register_provider(name, config)
                return
            self._model_registry.registerProvider(name, config)

        def _post_bind_unregister(
            name: str, *args: Any, **kwargs: Any
        ) -> None:
            del args, kwargs
            if unregister_provider is not None:
                unregister_provider(name)
                return
            self._model_registry.unregisterProvider(name)

        self._runtime.registerProvider = _post_bind_register
        self._runtime.unregisterProvider = _post_bind_unregister

    # ------------------------------------------------------------------
    # bindCommandContext
    # ------------------------------------------------------------------

    def bind_command_context(
        self,
        actions: Optional[ExtensionCommandContextActions] = None,
    ) -> None:
        """Wire (or reset) the command-context
        action implementations. Mirrors
        ``bindCommandContext``
        (``runner.ts:363-380``)."""
        if actions is not None:
            self._wait_for_idle = actions["waitForIdle"]
            self._new_session = actions["newSession"]
            self._fork = actions["fork"]
            self._navigate_tree = actions["navigateTree"]
            self._switch_session = actions["switchSession"]
            self._reload_handler = actions["reload"]
            return
        self._wait_for_idle = _async_noop
        self._new_session = _async_cancelled_false
        self._fork = _async_cancelled_false
        self._navigate_tree = _async_cancelled_false
        self._switch_session = _async_cancelled_false
        self._reload_handler = _async_noop

    # ------------------------------------------------------------------
    # UI context
    # ------------------------------------------------------------------

    def set_ui_context(
        self, ui_context: Optional[ExtensionUIContext] = None
    ) -> None:
        self._ui_context = ui_context or _get_no_op_ui_context()

    def get_ui_context(self) -> ExtensionUIContext:
        return self._ui_context

    def has_ui(self) -> bool:
        return self._ui_context is not _get_no_op_ui_context()

    # ------------------------------------------------------------------
    # Tools / flags / shortcuts
    # ------------------------------------------------------------------

    def get_extension_paths(self) -> list[str]:
        return [ext.path for ext in self._extensions]

    def get_all_registered_tools(self) -> list[RegisteredTool]:
        """First registration per tool name wins.
        Mirrors ``getAllRegisteredTools``
        (``runner.ts:399-409``)."""
        seen: dict[str, RegisteredTool] = {}
        for ext in self._extensions:
            for tool in ext.tools.values():
                if tool["definition"]["name"] not in seen:
                    seen[tool["definition"]["name"]] = tool
        return list(seen.values())

    def get_tool_definition(
        self, tool_name: str
    ) -> Optional[dict]:
        for ext in self._extensions:
            tool = ext.tools.get(tool_name)
            if tool is not None:
                return tool["definition"]
        return None

    def get_flags(self) -> dict[str, ExtensionFlag]:
        out: dict[str, ExtensionFlag] = {}
        for ext in self._extensions:
            for name, flag in ext.flags.items():
                if name not in out:
                    out[name] = flag
        return out

    def set_flag_value(self, name: str, value: Union[bool, str]) -> None:
        self._runtime.flagValues[name] = value

    def get_flag_values(self) -> dict[str, Union[bool, str]]:
        return dict(self._runtime.flagValues)

    def get_shortcuts(
        self, resolved_keybindings: dict
    ) -> dict[str, ExtensionShortcut]:
        """Resolve the final shortcut map,
        handling built-in conflicts and
        extension-vs-extension collisions.
        Mirrors ``getShortcuts``
        (``runner.ts:442-485``)."""
        self._shortcut_diagnostics = []
        builtin = _build_builtin_keybindings(resolved_keybindings)
        out: dict[str, ExtensionShortcut] = {}

        def _add_diagnostic(message: str, ext_path: str) -> None:
            self._shortcut_diagnostics.append(
                {"type": "warning", "message": message, "path": ext_path}
            )
            if not self.has_ui():
                _log.warning(message)

        for ext in self._extensions:
            for key, shortcut in ext.shortcuts.items():
                normalized = str(key).lower()
                builtin_match = builtin.get(normalized)
                if (
                    builtin_match is not None
                    and builtin_match.get("restrictOverride") is True
                ):
                    _add_diagnostic(
                        f"Extension shortcut '{key}' from {shortcut['extensionPath']} "
                        f"conflicts with built-in shortcut. Skipping.",
                        shortcut["extensionPath"],
                    )
                    continue
                if (
                    builtin_match is not None
                    and builtin_match.get("restrictOverride") is False
                ):
                    _add_diagnostic(
                        f"Extension shortcut conflict: '{key}' is built-in shortcut for "
                        f"{builtin_match['keybinding']} and {shortcut['extensionPath']}. "
                        f"Using {shortcut['extensionPath']}.",
                        shortcut["extensionPath"],
                    )
                existing = out.get(normalized)
                if existing is not None:
                    _add_diagnostic(
                        f"Extension shortcut conflict: '{key}' registered by both "
                        f"{existing['extensionPath']} and {shortcut['extensionPath']}. "
                        f"Using {shortcut['extensionPath']}.",
                        shortcut["extensionPath"],
                    )
                out[normalized] = shortcut
        return out

    def get_shortcut_diagnostics(self) -> list[dict]:
        return list(self._shortcut_diagnostics)

    # ------------------------------------------------------------------
    # Invalidation + error listeners
    # ------------------------------------------------------------------

    def invalidate(self, message: Optional[str] = None) -> None:
        """Mark this runner (and the shared
        runtime) as stale. Mirrors ``invalidate``
        (``runner.ts:491-498``). The stale
        message is set on first call only —
        subsequent calls do not overwrite it.
        """
        if not self._stale_message:
            from .types import DEFAULT_STALE_MESSAGE

            self._stale_message = message or DEFAULT_STALE_MESSAGE
        self._runtime.invalidate(self._stale_message)

    def _assert_active(self) -> None:
        if self._stale_message:
            raise RuntimeError(self._stale_message)

    def on_error(self, listener: ExtensionErrorListener) -> Callable[[], None]:
        self._error_listeners.append(listener)

        def _unsubscribe() -> None:
            try:
                self._error_listeners.remove(listener)
            except ValueError:
                pass

        return _unsubscribe

    def emit_error(self, error: ExtensionError) -> None:
        for listener in self._error_listeners:
            try:
                listener(error)
            except Exception:
                # Never let an error listener kill the dispatch.
                _log.exception("Extension error listener raised")

    def has_handlers(self, event_type: str) -> bool:
        for ext in self._extensions:
            handlers = ext.handlers.get(event_type)
            if handlers:
                return True
        return False

    def get_message_renderer(self, custom_type: str) -> Optional[MessageRenderer]:
        for ext in self._extensions:
            renderer = ext.messageRenderers.get(custom_type)
            if renderer is not None:
                return renderer
        return None

    # ------------------------------------------------------------------
    # Commands (name + invocation collision)
    # ------------------------------------------------------------------

    def _resolve_registered_commands(self) -> list[ResolvedCommand]:
        """Collect all commands + assign
        invocation names. Duplicate names get
        ``<name>:N`` suffixes. Mirrors
        ``resolveRegisteredCommands``
        (``runner.ts:537-569``)."""
        commands: list[RegisteredCommand] = []
        counts: dict[str, int] = {}
        for ext in self._extensions:
            for command in ext.commands.values():
                commands.append(command)
                counts[command["name"]] = counts.get(command["name"], 0) + 1

        seen: dict[str, int] = {}
        taken: set[str] = set()
        resolved: list[ResolvedCommand] = []
        for command in commands:
            occurrence = seen.get(command["name"], 0) + 1
            seen[command["name"]] = occurrence
            invocation = command["name"]
            if counts.get(command["name"], 0) > 1:
                invocation = f"{command['name']}:{occurrence}"
            if invocation in taken:
                suffix = occurrence
                while f"{command['name']}:{suffix}" in taken:
                    suffix += 1
                invocation = f"{command['name']}:{suffix}"
            taken.add(invocation)
            resolved.append(dict(command, invocationName=invocation))
        return resolved

    def get_registered_commands(self) -> list[ResolvedCommand]:
        self._command_diagnostics = []
        return self._resolve_registered_commands()

    def get_command_diagnostics(self) -> list[dict]:
        return list(self._command_diagnostics)

    def get_command(self, name: str) -> Optional[ResolvedCommand]:
        for command in self._resolve_registered_commands():
            if command["invocationName"] == name:
                return command
        return None

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        self._shutdown_handler()

    # ------------------------------------------------------------------
    # Context factories
    # ------------------------------------------------------------------

    def create_context(self) -> ExtensionContext:
        """Build an :class:`ExtensionContext`
        for use in event handlers and tool
        execution. Context values are resolved
        at call time, so changes via
        :meth:`bindCore` / :meth:`setUIContext`
        are reflected. Mirrors ``createContext``
        (``runner.ts:596-670``).

        The OpenClaw source uses getter
        properties (``get ui()``) to make
        staleness checks lazy. The Python port
        mirrors the same lazy semantics with
        ``@property`` + ``assertActive``
        checks on the returned ``ExtensionContext``
        dict (or — for methods — closures over
        ``self._assert_active``).
        """
        get_model = self._get_model
        get_ui = lambda: self._ui_context
        has_ui = self.has_ui
        get_cwd = lambda: self._cwd
        get_session_manager = lambda: self._session_manager
        get_model_registry = lambda: self._model_registry
        is_idle_fn = self._is_idle
        get_signal_fn = self._get_signal
        abort_fn = self._abort
        has_pending_fn = self._has_pending
        shutdown_fn = self._shutdown_handler
        get_context_usage_fn = self._get_context_usage
        compact_fn = self._compact
        get_system_prompt_fn = self._get_system_prompt
        assert_active = self._assert_active

        class _ContextView:
            """Read-only view returned by
            :meth:`createContext`. The Python
            port wraps the lazy getters + the
            methods so a fresh instance is
            cheap to construct (the OpenClaw
            source returns a fresh object
            literal each time)."""

            @property
            def ui(self) -> ExtensionUIContext:
                assert_active()
                return get_ui()

            @property
            def hasUI(self) -> bool:
                assert_active()
                return has_ui()

            @property
            def cwd(self) -> str:
                assert_active()
                return get_cwd()

            @property
            def sessionManager(self) -> SessionManager:
                assert_active()
                return get_session_manager()

            @property
            def modelRegistry(self) -> Any:
                assert_active()
                return get_model_registry()

            @property
            def model(self) -> Optional[Model]:
                assert_active()
                return get_model()

            def isIdle(self) -> bool:
                assert_active()
                return is_idle_fn()

            @property
            def signal(self) -> Optional[Any]:
                assert_active()
                return get_signal_fn()

            def abort(self) -> None:
                assert_active()
                abort_fn()

            def hasPendingMessages(self) -> bool:
                assert_active()
                return has_pending_fn()

            def shutdown(self) -> None:
                assert_active()
                shutdown_fn()

            def getContextUsage(self) -> Optional[ContextUsage]:
                assert_active()
                return get_context_usage_fn()

            def compact(
                self, options: Optional[CompactOptions] = None
            ) -> None:
                assert_active()
                compact_fn(options)

            def getSystemPrompt(self) -> str:
                assert_active()
                return get_system_prompt_fn()

        return _ContextView()  # type: ignore[return-value]

    def create_command_context(self) -> ExtensionCommandContext:
        """Build an :class:`ExtensionCommandContext`
        by wrapping the base context + adding
        the command-only methods. Mirrors
        ``createCommandContext``
        (``runner.ts:672-705``)."""
        base = self.create_context()
        # We re-use the same _ContextView class
        # + add the command-only methods on a
        # subclass so the underlying getters
        # stay lazy.
        wait_for_idle = self._wait_for_idle
        new_session = self._new_session
        fork = self._fork
        navigate_tree = self._navigate_tree
        switch_session = self._switch_session
        reload_handler = self._reload_handler
        assert_active = self._assert_active

        class _CommandContextView(type(base)):  # type: ignore[misc]
            def waitForIdle(self) -> Awaitable[None]:
                assert_active()
                return wait_for_idle()

            def newSession(
                self, options: Optional[NewSessionOptions] = None
            ) -> Awaitable[dict]:
                assert_active()
                return new_session(options)

            def fork(
                self, entry_id: str, options: Optional[ForkOptions] = None
            ) -> Awaitable[dict]:
                assert_active()
                return fork(entry_id, options)

            def navigateTree(
                self,
                target_id: str,
                options: Optional[NavigateTreeOptions] = None,
            ) -> Awaitable[dict]:
                assert_active()
                return navigate_tree(target_id, options)

            def switchSession(
                self,
                session_path: str,
                options: Optional[SwitchSessionOptions] = None,
            ) -> Awaitable[dict]:
                assert_active()
                return switch_session(session_path, options)

            def reload(self) -> Awaitable[None]:
                assert_active()
                return reload_handler()

        return _CommandContextView()  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Emit: generic + specialised
    # ------------------------------------------------------------------

    @staticmethod
    def _is_session_before_event(event: dict) -> bool:
        return event.get("type") in _SESSION_BEFORE_EVENT_TYPES

    async def emit(self, event: dict) -> Any:
        """Generic emit — used for events
        without a dedicated ``emitXxx`` method.
        Mirrors ``emit``
        (``runner.ts:716-750``).

        For ``session_before_*`` events,
        handlers may return a result that
        cancels the operation (``{cancel: true}``)
        — the first such result wins.
        """
        ctx = self.create_context()
        result: Optional[dict] = None
        for ext in self._extensions:
            handlers = ext.handlers.get(event.get("type"))
            if not handlers:
                continue
            for handler in handlers:
                try:
                    handler_result = await handler(event, ctx)
                    if self._is_session_before_event(event) and handler_result:
                        result = handler_result
                        if result.get("cancel"):
                            return result
                except Exception as exc:
                    self.emit_error(
                        {
                            "extensionPath": ext.path,
                            "event": str(event.get("type")),
                            "error": str(exc),
                            "stack": getattr(exc, "stack", None),
                        }
                    )
        return result

    async def emit_message_end(
        self, event: MessageEndEvent
    ) -> Optional[AgentMessage]:
        """Chained message-end event. Returns
        the (possibly replaced) message, or
        ``None`` if no handler mutated it.
        Mirrors ``emitMessageEnd``
        (``runner.ts:752-798``)."""
        ctx = self.create_context()
        current_message = event["message"]
        modified = False
        for ext in self._extensions:
            handlers = ext.handlers.get("message_end")
            if not handlers:
                continue
            for handler in handlers:
                try:
                    current_event = dict(event, message=current_message)
                    handler_result = await handler(current_event, ctx)
                    # TypedDict types are dicts at
                    # runtime — skip the isinstance
                    # check and accept any non-None
                    # mapping.
                    result = (
                        handler_result
                        if isinstance(handler_result, dict)
                        else None
                    )
                    if not result or not result.get("message"):
                        continue
                    replacement = result["message"]
                    if replacement.get("role") != current_message.get("role"):
                        self.emit_error(
                            {
                                "extensionPath": ext.path,
                                "event": "message_end",
                                "error": (
                                    "message_end handlers must return a message "
                                    "with the same role"
                                ),
                            }
                        )
                        continue
                    current_message = replacement
                    modified = True
                except Exception as exc:
                    self.emit_error(
                        {
                            "extensionPath": ext.path,
                            "event": "message_end",
                            "error": str(exc),
                            "stack": getattr(exc, "stack", None),
                        }
                    )
        return current_message if modified else None

    async def emit_tool_result(
        self, event: ToolResultEvent
    ) -> Optional[ToolResultEventResult]:
        """Chained tool-result event. Returns
        the (possibly mutated) result fields, or
        ``None`` if no handler mutated anything.
        Mirrors ``emitToolResult``
        (``runner.ts:800-854``)."""
        ctx = self.create_context()
        current = dict(event)
        modified = False
        for ext in self._extensions:
            handlers = ext.handlers.get("tool_result")
            if not handlers:
                continue
            for handler in handlers:
                try:
                    handler_result = await handler(current, ctx)
                    # TypedDict types are dicts at
                    # runtime — accept any non-None
                    # mapping.
                    result = (
                        handler_result
                        if isinstance(handler_result, dict)
                        else None
                    )
                    if not result:
                        continue
                    if "content" in result:
                        current["content"] = result["content"]
                        modified = True
                    if "details" in result:
                        current["details"] = result["details"]
                        modified = True
                    if "isError" in result:
                        current["isError"] = result["isError"]
                        modified = True
                except Exception as exc:
                    self.emit_error(
                        {
                            "extensionPath": ext.path,
                            "event": "tool_result",
                            "error": str(exc),
                            "stack": getattr(exc, "stack", None),
                        }
                    )
        if not modified:
            return None
        return {
            "content": current.get("content"),
            "details": current.get("details"),
            "isError": current.get("isError"),
        }

    async def emit_tool_call(
        self, event: ToolCallEvent
    ) -> Optional[ToolCallEventResult]:
        """Tool-call event. Returns the (first)
        non-empty result, or ``None`` if no
        handler returned. Short-circuits on
        ``{block: true}``. Mirrors
        ``emitToolCall``
        (``runner.ts:856-879``)."""
        ctx = self.create_context()
        result: Optional[ToolCallEventResult] = None
        for ext in self._extensions:
            handlers = ext.handlers.get("tool_call")
            if not handlers:
                continue
            for handler in handlers:
                handler_result = await handler(event, ctx)
                if handler_result:
                    result = (
                        handler_result
                        if isinstance(handler_result, dict)
                        else None
                    )
                    if result and result.get("block"):
                        return result
        return result

    async def emit_user_bash(
        self, event: UserBashEvent
    ) -> Optional[UserBashEventResult]:
        """User-bash event. Returns the first
        non-empty handler result (short-circuit).
        Mirrors ``emitUserBash``
        (``runner.ts:881-910``)."""
        ctx = self.create_context()
        for ext in self._extensions:
            handlers = ext.handlers.get("user_bash")
            if not handlers:
                continue
            for handler in handlers:
                try:
                    handler_result = await handler(event, ctx)
                    if handler_result:
                        return (
                            handler_result
                            if isinstance(handler_result, dict)
                            else None
                        )
                except Exception as exc:
                    self.emit_error(
                        {
                            "extensionPath": ext.path,
                            "event": "user_bash",
                            "error": str(exc),
                            "stack": getattr(exc, "stack", None),
                        }
                    )
        return None

    async def emit_context(
        self, messages: list[AgentMessage]
    ) -> list[AgentMessage]:
        """Chained context transformation.
        Mirrors ``emitContext``
        (``runner.ts:912-944``)."""
        ctx = self.create_context()
        current = copy.deepcopy(messages)
        for ext in self._extensions:
            handlers = ext.handlers.get("context")
            if not handlers:
                continue
            for handler in handlers:
                try:
                    event: ContextEvent = {"type": "context", "messages": current}
                    handler_result = await handler(event, ctx)
                    if (
                        handler_result
                        and isinstance(handler_result, dict)
                        and handler_result.get("messages")
                    ):
                        current = handler_result["messages"]
                except Exception as exc:
                    self.emit_error(
                        {
                            "extensionPath": ext.path,
                            "event": "context",
                            "error": str(exc),
                            "stack": getattr(exc, "stack", None),
                        }
                    )
        return current

    async def emit_before_provider_request(
        self, payload: Any
    ) -> Any:
        """Chained provider-payload replacement.
        Mirrors ``emitBeforeProviderRequest``
        (``runner.ts:946-980``)."""
        ctx = self.create_context()
        current = payload
        for ext in self._extensions:
            handlers = ext.handlers.get("before_provider_request")
            if not handlers:
                continue
            for handler in handlers:
                try:
                    event: BeforeProviderRequestEvent = {
                        "type": "before_provider_request",
                        "payload": current,
                    }
                    handler_result = await handler(event, ctx)
                    if handler_result is not None:
                        current = handler_result
                except Exception as exc:
                    self.emit_error(
                        {
                            "extensionPath": ext.path,
                            "event": "before_provider_request",
                            "error": str(exc),
                            "stack": getattr(exc, "stack", None),
                        }
                    )
        return current

    async def emit_before_agent_start(
        self,
        prompt: str,
        images: Optional[list[ImageContent]],
        system_prompt: str,
        system_prompt_options: Any,
    ) -> Optional[dict]:
        """Chained system-prompt + message
        override. Returns a combined result
        with ``messages`` (collected from all
        handlers) + ``systemPrompt`` (chained
        replacement). Mirrors
        ``emitBeforeAgentStart``
        (``runner.ts:982-1048``)."""
        current_system_prompt = system_prompt

        # The base context's getSystemPrompt is
        # overridden to return the chained
        # system prompt. Mirrors the OpenClaw
        # source's Object.defineProperties
        # redefinition (``runner.ts:989-996``).
        base = self.create_context()

        def _get_system_prompt_chained() -> str:
            self._assert_active()
            return current_system_prompt

        # The OpenClaw source uses property
        # descriptors; the Python port just
        # monkey-patches the bound method on
        # the instance.
        base.getSystemPrompt = _get_system_prompt_chained  # type: ignore[method-assign]

        messages: list[dict] = []
        system_prompt_modified = False
        for ext in self._extensions:
            handlers = ext.handlers.get("before_agent_start")
            if not handlers:
                continue
            for handler in handlers:
                try:
                    event: BeforeAgentStartEvent = {
                        "type": "before_agent_start",
                        "prompt": prompt,
                        "images": images,
                        "systemPrompt": current_system_prompt,
                        "systemPromptOptions": system_prompt_options,
                    }
                    handler_result = await handler(event, base)
                    if not handler_result:
                        continue
                    # TypedDict is dict at runtime.
                    result = (
                        handler_result
                        if isinstance(handler_result, dict)
                        else None
                    )
                    if not result:
                        continue
                    if result.get("message"):
                        messages.append(result["message"])
                    if result.get("systemPrompt") is not None:
                        current_system_prompt = result["systemPrompt"]
                        system_prompt_modified = True
                except Exception as exc:
                    self.emit_error(
                        {
                            "extensionPath": ext.path,
                            "event": "before_agent_start",
                            "error": str(exc),
                            "stack": getattr(exc, "stack", None),
                        }
                    )
        if not messages and not system_prompt_modified:
            return None
        return {
            "messages": messages or None,
            "systemPrompt": current_system_prompt
            if system_prompt_modified
            else None,
        }

    async def emit_resources_discover(
        self,
        cwd: str,
        reason: str,
    ) -> dict:
        """Collect skill/prompt/theme paths
        from ``resources_discover`` handlers.
        Mirrors ``emitResourcesDiscover``
        (``runner.ts:1050-1104``)."""
        ctx = self.create_context()
        skill_paths: list[dict] = []
        prompt_paths: list[dict] = []
        theme_paths: list[dict] = []
        for ext in self._extensions:
            handlers = ext.handlers.get("resources_discover")
            if not handlers:
                continue
            for handler in handlers:
                try:
                    event: ResourcesDiscoverEvent = {
                        "type": "resources_discover",
                        "cwd": cwd,
                        "reason": reason,  # type: ignore[typeddict-item]
                    }
                    handler_result = await handler(event, ctx)
                    # TypedDict is dict at runtime.
                    result = (
                        handler_result
                        if isinstance(handler_result, dict)
                        else None
                    )
                    if not result:
                        continue
                    if result.get("skillPaths"):
                        skill_paths.extend(
                            {"path": p, "extensionPath": ext.path}
                            for p in result["skillPaths"]
                        )
                    if result.get("promptPaths"):
                        prompt_paths.extend(
                            {"path": p, "extensionPath": ext.path}
                            for p in result["promptPaths"]
                        )
                    if result.get("themePaths"):
                        theme_paths.extend(
                            {"path": p, "extensionPath": ext.path}
                            for p in result["themePaths"]
                        )
                except Exception as exc:
                    self.emit_error(
                        {
                            "extensionPath": ext.path,
                            "event": "resources_discover",
                            "error": str(exc),
                            "stack": getattr(exc, "stack", None),
                        }
                    )
        return {
            "skillPaths": skill_paths,
            "promptPaths": prompt_paths,
            "themePaths": theme_paths,
        }

    async def emit_input(
        self,
        text: str,
        images: Optional[list[ImageContent]],
        source: InputSource,
    ) -> InputEventResult:
        """Input event. Transformations chain;
        ``handled`` short-circuits. Mirrors
        ``emitInput``
        (``runner.ts:1107-1146``)."""
        ctx = self.create_context()
        current_text = text
        current_images = images
        for ext in self._extensions:
            for handler in ext.handlers.get("input") or []:
                try:
                    event: InputEvent = {
                        "type": "input",
                        "text": current_text,
                        "images": current_images,
                        "source": source,
                    }
                    result = await handler(event, ctx)
                    if not result or not isinstance(result, dict):
                        continue
                    action = result.get("action")
                    if action == "handled":
                        return result  # type: ignore[return-value]
                    if action == "transform":
                        current_text = result.get("text", current_text)
                        if "images" in result:
                            current_images = result["images"]
                except Exception as exc:
                    self.emit_error(
                        {
                            "extensionPath": ext.path,
                            "event": "input",
                            "error": str(exc),
                            "stack": getattr(exc, "stack", None),
                        }
                    )
        if current_text != text or current_images != images:
            return {
                "action": "transform",
                "text": current_text,
                "images": current_images,
            }
        return {"action": "continue"}


# ============================================================================
# Handler type aliases (used by createCommandContext)
# ============================================================================


NewSessionHandler = Callable[[Optional[NewSessionOptions]], Awaitable[dict]]
ForkHandler = Callable[[str, Optional[ForkOptions]], Awaitable[dict]]
NavigateTreeHandler = Callable[[str, Optional[NavigateTreeOptions]], Awaitable[dict]]
SwitchSessionHandler = Callable[[str, Optional[SwitchSessionOptions]], Awaitable[dict]]
ReloadHandler = Callable[[], Awaitable[None]]


async def _async_noop(*_args: Any, **_kwargs: Any) -> None:
    return None


async def _async_cancelled_false(
    *_args: Any, **_kwargs: Any
) -> dict:
    return {"cancelled": False}


__all__ = [
    "ExtensionErrorListener",
    "ExtensionRunner",
    "RESERVED_KEYBINDINGS_FOR_EXTENSION_CONFLICTS",
    "ShutdownHandler",
    "emit_session_shutdown_event",
]
