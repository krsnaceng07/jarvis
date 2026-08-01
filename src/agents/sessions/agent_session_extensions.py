"""jarvis.agents.sessions.agent_session_extensions — extension-binding layer.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/agent-session-extensions.ts``.

Binds the extension runner to the
session + wires up the tool registry.

Public surface (mirrors the OpenClaw
source):

- :meth:`AgentSessionExtensions.bind_extensions` — bind the
  extension runner + emit the
  ``session_start`` event + extend the
  resources from extensions.
- :meth:`AgentSessionExtensions.build_runtime` — build the
  extension runtime (the tool
  registry + the extension runner +
  the bindings). Called by the
  factory in 6.12h.
- :meth:`AgentSessionExtensions.reload` — reload the
  session (emits ``session_shutdown``
  + reloads settings + resources +
  rebuilds the runtime).

The OpenClaw source's ``bindExtensionCore``
+ ``refreshToolRegistry`` + private
helpers are ported faithfully.

The OpenClaw source inherits from
``AgentSessionCompaction`` (which
lands in 6.12g). The Python port
inherits from :class:`AgentSessionExecution`
directly — the missing intermediate
subclass is collapsed (the compaction
methods land in 6.12g).

Phase 6.12f — focused port.
"""
from __future__ import annotations

import logging
import os
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Optional,
    Union,
)

from .agent_session_base import ToolDefinitionEntry
from .agent_session_execution import AgentSessionExecution
from .agent_session_types import ExtensionBindings
from .extensions.runner import ExtensionRunner, emit_session_shutdown_event
from .extensions.types import (
    ReplacedSessionContext,
    SourceInfo,
    ToolDefinition,
)
from .extensions.wrapper import wrap_registered_tools
from .resource_loader import ResourceExtensionPaths
from .source_info import create_synthetic_source_info


if TYPE_CHECKING:
    from packages.jarvis_agent_runtime.src.jarvis_agent.types import (  # type: ignore[import-not-found]
        AgentMessage,
        AgentTool,
    )
else:
    AgentMessage = Any
    AgentTool = Any


_LOG = logging.getLogger("jarvis.agents.sessions.agent_session_extensions")


class AgentSessionExtensions(AgentSessionExecution):
    """The extension-binding layer of the
    :class:`AgentSession` family. Mirrors
    :class:`AgentSessionExtensions`
    (``agent-session-extensions.ts:17-420``).

    Phase 6.12f port.

    Note
    ----
    The OpenClaw source inherits from
    :class:`AgentSessionCompaction`. The
    Python port inherits from
    :class:`AgentSessionExecution` (the
    compaction intermediate lands in
    6.12g).
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def bind_extensions(self, bindings: ExtensionBindings) -> None:
        """Bind the extension runner +
        emit the ``session_start`` event +
        extend the resources from
        extensions. Mirrors
        :meth:`bindExtensions`
        (``agent-session-extensions.ts:18-40``)."""
        if getattr(bindings, "ui_context", None) is not None:
            self.extension_ui_context = bindings.ui_context
        if getattr(bindings, "command_context_actions", None) is not None:
            self.extension_command_context_actions = (
                bindings.command_context_actions
            )
        if getattr(bindings, "abort_handler", None) is not None:
            self.extension_abort_handler = bindings.abort_handler
        if getattr(bindings, "shutdown_handler", None) is not None:
            self.extension_shutdown_handler = bindings.shutdown_handler
        if getattr(bindings, "on_error", None) is not None:
            self.extension_error_listener = bindings.on_error
        self._apply_extension_bindings(self.current_extension_runner)
        await self.current_extension_runner.emit(
            self.session_start_event
        )
        reason = (
            "reload"
            if self.session_start_event.get("reason") == "reload"
            else "startup"
        )
        await self._extend_resources_from_extensions(reason)

    async def reload(self) -> None:
        """Reload the session. Mirrors
        :meth:`reload`
        (``agent-session-extensions.ts:393-419``)."""
        previous_flag_values = self.current_extension_runner.get_flag_values()
        await emit_session_shutdown_event(
            self.current_extension_runner,
            {"type": "session_shutdown", "reason": "reload"},
        )
        await self.settings_manager.reload()
        # Apply the steering / follow-up
        # modes from the freshly-reloaded
        # settings. Mirrors the OpenClaw
        # source's direct writes to
        # ``this.agent.steeringMode`` /
        # ``this.agent.followUpMode``
        # (``agent-session-extensions.ts:400-401``).
        setattr(
            self.agent,
            "steeringMode",
            self.settings_manager.get_steering_mode(),
        )
        setattr(
            self.agent,
            "followUpMode",
            self.settings_manager.get_follow_up_mode(),
        )
        self.steering_mode = self.settings_manager.get_steering_mode()
        self.follow_up_mode = self.settings_manager.get_follow_up_mode()
        # Reload the resource loader.
        reload_resource_loader = getattr(
            self.session_resource_loader, "reload", None
        )
        if callable(reload_resource_loader):
            await reload_resource_loader()
        # Refresh the model registry.
        refresh = getattr(self.session_model_registry, "refresh", None)
        if callable(refresh):
            refresh()
        # Rebuild the runtime.
        self.build_runtime(
            {
                "activeToolNames": self.get_active_tool_names(),
                "flagValues": previous_flag_values,
                "includeAllExtensionTools": True,
            }
        )
        # Re-bind the extensions + emit
        # the session_start event + extend
        # the resources.
        has_bindings = (
            self.extension_ui_context
            or self.extension_command_context_actions
            or self.extension_shutdown_handler
            or self.extension_error_listener
        )
        if has_bindings:
            self._apply_extension_bindings(self.current_extension_runner)
            await self.current_extension_runner.emit(
                {
                    "type": "session_start",
                    "reason": "reload",
                }
            )
            await self._extend_resources_from_extensions("reload")

    def build_runtime(
        self,
        options: Optional[dict] = None,
    ) -> None:
        """Build the extension runtime.
        Mirrors :meth:`buildRuntime`
        (``agent-session-extensions.ts:339-391``)."""
        options = options or {}
        # Build the base tool definitions.
        # The OpenClaw source uses
        # ``createAllToolDefinitions`` (a
        # registry of every built-in tool).
        # The Python port reads them from
        # the resource loader.
        extensions_result = self.session_resource_loader.get_extensions()
        self.current_extension_runner = ExtensionRunner(
            extensions_result.extensions,
            extensions_result.runtime,
            self.cwd,
            self.session_manager,
            self.session_model_registry,
        )
        if self.extension_runner_ref is not None:
            self.extension_runner_ref["current"] = self.current_extension_runner
        # Bind the core (the actions +
        # state + provider registration
        # object).
        self._bind_extension_core(self.current_extension_runner)
        # Apply the bindings (UI context +
        # command context + error
        # listener).
        self._apply_extension_bindings(self.current_extension_runner)
        # Apply the flag values (if any).
        flag_values = options.get("flagValues")
        if flag_values:
            for name, value in flag_values.items():
                extensions_result.runtime.flagValues[name] = value
        # Default active tool names.
        default_active = ["read", "bash", "edit", "write"]
        base_active = options.get("activeToolNames") or default_active
        self._refresh_tool_registry(
            active_tool_names=base_active,
            include_all_extension_tools=options.get(
                "includeAllExtensionTools", False
            ),
        )

    # ------------------------------------------------------------------
    # Tool registry (mirrors agent-session-base + extensions.ts)
    # ------------------------------------------------------------------

    def get_active_tool_names(self) -> list[str]:
        """Return the names of the active
        tools. Mirrors
        :meth:`getActiveToolNames` (the
        OpenClaw source's helper at the
        base of the extensions class)."""
        state = self.agent.state
        if isinstance(state, dict):
            return list(state.get("activeTools", []))
        return list(
            getattr(state, "activeTools", None)
            or getattr(state, "active_tools", [])
            or []
        )

    def get_all_tools(self) -> list[str]:
        """Return the names of all
        registered tools. Mirrors
        :meth:`getAllTools`."""
        return list(self.tool_registry.keys())

    def set_active_tools_by_name(self, tool_names: list[str]) -> None:
        """Set the active tool list.
        Mirrors :meth:`setActiveToolsByName`."""
        state = self.agent.state
        deduped = list(dict.fromkeys(tool_names))
        if isinstance(state, dict):
            state["activeTools"] = deduped
        else:
            setattr(state, "activeTools", deduped)

    # ------------------------------------------------------------------
    # Private: extension bindings
    # ------------------------------------------------------------------

    async def _extend_resources_from_extensions(
        self, reason: str
    ) -> None:
        """Emit the ``resources_discover``
        event + extend the resources.
        Mirrors :meth:`extendResourcesFromExtensions`
        (``agent-session-extensions.ts:42-63``)."""
        if not self.current_extension_runner.has_handlers("resources_discover"):
            return
        discovered = await self.current_extension_runner.emit_resources_discover(
            self.cwd, reason
        )
        skill_paths = discovered.get("skillPaths", []) or []
        prompt_paths = discovered.get("promptPaths", []) or []
        theme_paths = discovered.get("themePaths", []) or []
        if (
            not skill_paths
            and not prompt_paths
            and not theme_paths
        ):
            return
        extension_paths: ResourceExtensionPaths = {
            "skillPaths": self._build_extension_resource_paths(skill_paths),
            "promptPaths": self._build_extension_resource_paths(prompt_paths),
            "themePaths": self._build_extension_resource_paths(theme_paths),
        }
        self.session_resource_loader.extend_resources(extension_paths)

    def _build_extension_resource_paths(
        self, entries: list
    ) -> list:
        """Wrap the extension-provided
        resource entries as
        :class:`ResourceExtensionPaths`
        entries. Mirrors
        :meth:`buildExtensionResourcePaths`
        (``agent-session-extensions.ts:65-86``)."""
        out: list = []
        for entry in entries or []:
            extension_path = entry.get("extensionPath", "")
            source = self._get_extension_source_label(extension_path)
            path = entry.get("path", "")
            base_dir = None
            if extension_path and not extension_path.startswith("<"):
                base_dir = os.path.dirname(extension_path)
            out.append({
                "path": path,
                "metadata": {
                    "source": source,
                    "scope": "temporary",
                    "origin": "top-level",
                    "baseDir": base_dir,
                },
            })
        return out

    def _get_extension_source_label(self, extension_path: str) -> str:
        """Build the source label for an
        extension path. Mirrors
        :meth:`getExtensionSourceLabel`
        (``agent-session-extensions.ts:88-95``)."""
        if not extension_path:
            return "extension:unknown"
        if extension_path.startswith("<"):
            return f"extension:{extension_path.strip('<>')}"
        base = os.path.basename(extension_path)
        name = base.rsplit(".", 1)[0] if "." in base else base
        return f"extension:{name}"

    def _apply_extension_bindings(self, runner: ExtensionRunner) -> None:
        """Apply the UI context + command
        context + error listener to the
        extension runner. Mirrors
        :meth:`applyExtensionBindings`
        (``agent-session-extensions.ts:97-105``)."""
        if self.extension_ui_context is not None:
            runner.set_ui_context(self.extension_ui_context)
        if self.extension_command_context_actions is not None:
            runner.bind_command_context(self.extension_command_context_actions)
        # (Un)bind the error listener.
        if self.extension_error_unsubscriber is not None:
            try:
                self.extension_error_unsubscriber()
            except Exception:
                pass
            self.extension_error_unsubscriber = None
        if self.extension_error_listener is not None:
            self.extension_error_unsubscriber = runner.on_error(
                self.extension_error_listener
            )

    def _refresh_current_model_from_registry(self) -> None:
        """Re-read the current model from
        the registry (after a
        register / unregister). Mirrors
        :meth:`refreshCurrentModelFromRegistry`
        (``agent-session-extensions.ts:107-119``)."""
        current_model = self.model
        if not current_model:
            return
        find = getattr(
            self.session_model_registry, "find", None
        )
        if not callable(find):
            return
        provider = (
            current_model.get("provider", "")
            if isinstance(current_model, dict)
            else getattr(current_model, "provider", "")
        )
        model_id = (
            current_model.get("id", "")
            if isinstance(current_model, dict)
            else getattr(current_model, "id", "")
        )
        refreshed = find(provider, model_id)
        if refreshed is None or refreshed is current_model:
            return
        state = self.agent.state
        if isinstance(state, dict):
            state["model"] = refreshed
        else:
            setattr(state, "model", refreshed)
        # Mirror on the session.
        self.model = refreshed

    def _bind_extension_core(self, runner: ExtensionRunner) -> None:
        """Bind the extension core (the
        `core` + `actions` + `registration`
        object). Mirrors
        :meth:`bindExtensionCore`
        (``agent-session-extensions.ts:121-238``).

        Phase 6.12f — STUB. The OpenClaw
        source's full core object exposes
        ~30 methods (sendMessage, sendUserMessage,
        getCommands, setModel, ...). The
        Python port binds the subset
        needed for the public surface; the
        rest land with the SDK factory in
        6.12h.
        """
        core = {
            "sendMessage": self._core_send_message,
            "sendUserMessage": self._core_send_user_message,
            "appendEntry": self._core_append_entry,
            "setSessionName": self._core_set_session_name,
            "getSessionName": self._core_get_session_name,
            "setLabel": self._core_set_label,
            "getActiveTools": self.get_active_tool_names,
            "getAllTools": self.get_all_tools,
            "setActiveTools": self.set_active_tools_by_name,
            "refreshTools": self._refresh_tool_registry,
            "getCommands": self._core_get_commands,
            "setModel": self._core_set_model,
            "getThinkingLevel": lambda: self.thinking_level,
            "setThinkingLevel": self.set_thinking_level,
        }
        actions = {
            "getModel": lambda: self.model,
            "isIdle": lambda: not self.is_streaming,
            "getSignal": lambda: getattr(self.agent, "signal", None),
            "abort": self._core_abort,
            "hasPendingMessages": lambda: self.pending_message_count > 0,
            "shutdown": self._core_shutdown,
            "getContextUsage": self._core_get_context_usage,
            "compact": self._core_compact,
            "getSystemPrompt": lambda: self.system_prompt,
        }
        registration = {
            "registerProvider": self._core_register_provider,
            "unregisterProvider": self._core_unregister_provider,
        }
        runner.bind_core(core, actions, registration)

    async def _core_send_message(
        self,
        message: dict,
        options: Optional[dict] = None,
    ) -> None:
        try:
            await self.send_custom_message(message, options)
        except Exception as exc:
            self.current_extension_runner.emit_error({
                "extensionPath": "<runtime>",
                "event": "send_message",
                "error": str(exc) if exc else "unknown",
            })

    async def _core_send_user_message(
        self,
        content: Union[str, list],
        options: Optional[dict] = None,
    ) -> None:
        try:
            await self.send_user_message(content, options)
        except Exception as exc:
            self.current_extension_runner.emit_error({
                "extensionPath": "<runtime>",
                "event": "send_user_message",
                "error": str(exc) if exc else "unknown",
            })

    def _core_append_entry(self, custom_type: str, data: Any) -> None:
        append = getattr(
            self.session_manager, "append_custom_entry", None
        )
        if callable(append):
            append(custom_type, data)

    def _core_set_session_name(self, name: str) -> None:
        """Set the session name. Mirrors
        the OpenClaw source's
        :func:`setSessionName` delegate
        inside :meth:`bindExtensionCore`.

        The OpenClaw source calls
        :meth:`this.setSessionName`
        (defined on the inspection
        class). The Python port's
        :class:`AgentSessionExtensions`
        chain doesn't include
        :class:`AgentSessionInspection`
        (6.12e — a sibling), so we
        delegate straight to the
        session_manager's
        :meth:`set_session_name` + emit
        the :class:`SessionInfoChangedEvent`
        on behalf of the inspection
        class.
        """
        set_name = getattr(
            self.session_manager, "set_session_name", None
        )
        if callable(set_name):
            set_name(name)
        self.emit({
            "type": "session_info_changed",
            "name": name,
        })

    def _core_get_session_name(self) -> Optional[str]:
        """Get the session name. Mirrors
        the OpenClaw source's
        :func:`getSessionName` delegate
        inside :meth:`bindExtensionCore`."""
        get_name = getattr(
            self.session_manager, "get_session_name", None
        )
        if callable(get_name):
            return get_name()
        return None

    def _core_set_label(self, entry_id: str, label: str) -> None:
        append_label = getattr(
            self.session_manager, "append_label_change", None
        )
        if callable(append_label):
            append_label(entry_id, label)

    def _core_get_commands(self) -> list:
        """Build the slash-command list
        (extension commands + prompt
        templates + skills). Mirrors the
        :func:`getCommands` helper inside
        :meth:`bindExtensionCore`."""
        commands: list = []
        extension_commands = (
            self.current_extension_runner.get_registered_commands()
        )
        for command in extension_commands:
            commands.append({
                "name": command.get("invocationName", ""),
                "description": command.get("description", ""),
                "source": "extension",
                "sourceInfo": command.get("sourceInfo"),
            })
        for template in self.prompt_templates:
            commands.append({
                "name": template.get("name", ""),
                "description": template.get("description", ""),
                "source": "prompt",
                "sourceInfo": template.get("sourceInfo"),
            })
        for skill in self.session_resource_loader.get_skills().get(
            "skills", []
        ):
            commands.append({
                "name": f"skill:{skill.name}",
                "description": skill.description,
                "source": "skill",
                "sourceInfo": skill.source_info,
            })
        return commands

    def _core_get_context_usage(self) -> Optional[dict]:
        """Return the context usage. Mirrors
        the OpenClaw source's
        :func:`getContextUsage` delegate
        inside :meth:`bindExtensionCore`.

        The OpenClaw source calls
        :meth:`this.getContextUsage()`
        (defined on the inspection
        class). The Python port's
        :class:`AgentSessionExtensions`
        chain doesn't include
        :class:`AgentSessionInspection`
        (6.12e — a sibling), so we
        delegate via the same path: read
        the model from the agent state +
        the model registry. Returns
        ``None`` when the inspection
        helper is unavailable (e.g. the
        consumer didn't include
        :class:`AgentSessionInspection`).
        """
        get_ctx = getattr(self, "get_context_usage", None)
        if callable(get_ctx):
            return get_ctx()
        return None

    async def _core_set_model(self, model: Any) -> bool:
        if not self.session_model_registry.has_configured_auth(model):
            return False
        await self.set_model(model)
        return True

    def _core_abort(self) -> None:
        if self.extension_abort_handler is not None:
            self.extension_abort_handler()
            return
        import asyncio

        asyncio.create_task(self.abort())

    def _core_shutdown(self) -> None:
        if self.extension_shutdown_handler is not None:
            self.extension_shutdown_handler()

    def _core_compact(self, options: Optional[dict] = None) -> None:
        # The OpenClaw source kicks off
        # the compaction asynchronously
        # + dispatches to onComplete /
        # onError. The Python port follows
        # the same shape.
        options = options or {}
        custom_instructions = options.get("customInstructions")
        on_complete = options.get("onComplete")
        on_error = options.get("onError")
        import asyncio

        async def run() -> None:
            try:
                result = await self.compact(custom_instructions)
                if callable(on_complete):
                    on_complete(result)
            except Exception as exc:
                if callable(on_error):
                    on_error(exc if isinstance(exc, Exception) else Exception(str(exc)))

        asyncio.create_task(run())

    def _core_register_provider(self, name: str, config: Any) -> None:
        register = getattr(
            self.session_model_registry, "register_provider", None
        )
        if callable(register):
            register(name, config)
        self._refresh_current_model_from_registry()

    def _core_unregister_provider(self, name: str) -> None:
        unregister = getattr(
            self.session_model_registry, "unregister_provider", None
        )
        if callable(unregister):
            unregister(name)
        self._refresh_current_model_from_registry()

    def _refresh_tool_registry(
        self,
        active_tool_names: Optional[list[str]] = None,
        include_all_extension_tools: bool = False,
    ) -> None:
        """Refresh the tool registry. Mirrors
        :meth:`refreshToolRegistry`
        (``agent-session-extensions.ts:240-337``).

        Phase 6.12f — STUB. The full
        refresh includes the OpenClaw
        source's wrapping + filter
        pipeline. The Python port
        refreshes the registered tool
        map + updates the active tool
        list.
        """
        allowed = self.allowed_tool_names
        is_allowed: Callable[[str], bool] = lambda name: (
            allowed is None or name in allowed
        )
        registered_tools = self.current_extension_runner.get_all_registered_tools()
        custom = list(registered_tools)
        for definition in self.custom_tools:
            custom.append({
                "definition": definition,
                "sourceInfo": create_synthetic_source_info(
                    f"<sdk:{definition.get('name', 'unknown')}>",
                    source="sdk",
                ),
            })
        # Filter by the allowlist.
        custom = [
            tool
            for tool in custom
            if is_allowed(
                tool.get("definition", {}).get("name", "")
            )
        ]
        # Build the definition map.
        definition_registry: dict[str, ToolDefinitionEntry] = {}
        for name, definition in self.base_tool_definitions.items():
            if not is_allowed(name):
                continue
            definition_registry[name] = ToolDefinitionEntry(
                definition=definition,
                sourceInfo=create_synthetic_source_info(
                    f"<builtin:{name}>",
                    source="builtin",
                ),
            )
        for tool in custom:
            name = tool.get("definition", {}).get("name", "")
            definition_registry[name] = ToolDefinitionEntry(
                definition=tool["definition"],
                sourceInfo=tool.get("sourceInfo", {}),
            )
        self.tool_definitions = definition_registry
        # Wrap + register.
        wrapped_extension = wrap_registered_tools(
            custom, self.current_extension_runner
        )
        tool_registry: dict[str, Any] = {
            tool.name: tool for tool in wrapped_extension
        }
        self.tool_registry = tool_registry
        # Active tool list.
        previous_active = set(self.get_active_tool_names())
        new_active: list[str] = []
        if active_tool_names is not None:
            new_active.extend(active_tool_names)
        if allowed is not None:
            for tool_name in tool_registry.keys():
                if tool_name in allowed:
                    new_active.append(tool_name)
        elif include_all_extension_tools:
            for tool in wrapped_extension:
                new_active.append(tool.name)
        else:
            for tool_name in tool_registry.keys():
                if tool_name not in previous_active:
                    new_active.append(tool_name)
        self.set_active_tools_by_name(list(dict.fromkeys(new_active)))


__all__ = [
    "AgentSessionExtensions",
]
