"""PluginApi registration helpers for the internal SDK implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, cast

if TYPE_CHECKING:
    from .api import CommandDecl
    from ._plugin_api_init import PluginApiInit
else:
    PluginApiInit = object

from .cli import CliDescriptor

JSON = dict[str, Any]


def _normalize_plugin_tool_names(names: list[Any] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in names or ():
        if not isinstance(raw, str):
            continue
        trimmed = raw.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        out.append(trimmed)
    return out


def _find_undeclared_plugin_tool_names(declared: list[str], tool_names: list[str]) -> list[str]:
    declared_set = set(declared or ())
    return [n for n in tool_names if n not in declared_set]


_log = logging.getLogger("jarvis_sdk.api")


class PluginApiRegistrationsA(PluginApiInit):
    def register_tool(
        self,
        tool: Any = None,
        opts: dict[str, Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        parameters: dict[str, Any] | None = None,
        execute: Callable[..., Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        optional: bool = False,
    ) -> None:
        """Register a tool. Mirrors OpenClaw's ``registerTool``."""
        if tool is None and name is not None:

            class _DynamicTool:
                def __init__(
                    self,
                    t_name: str,
                    t_desc: str,
                    t_params: Any,
                    t_exec: Callable[..., Any] | None = None,
                ):
                    self.name = t_name
                    self.description = t_desc
                    self.parameters = t_params
                    self.execute = t_exec

                async def call(self, name: str, args: dict[str, Any]) -> Any:
                    if self.execute:
                        import inspect

                        res = self.execute(args)
                        if inspect.isawaitable(res):
                            res = await res
                        return res
                    return None

            tool = _DynamicTool(
                t_name=name,
                t_desc=description or "",
                t_params=parameters or {"type": "OBJECT", "properties": {}},
                t_exec=execute,
            )
            opts = opts or {"name": name}
        elif tool is not None and name is not None and opts is None:
            opts = {"name": name}

        opts = opts or {}
        declared = self._declared_tool_names()
        merged: list[str] = []
        if isinstance(opts.get("name"), str):
            merged.append(opts["name"])
        if isinstance(opts.get("names"), list):
            merged.extend(opts["names"])
        if tool is not None and not callable(tool) and hasattr(tool, "name"):
            tool_name = getattr(tool, "name", None)
            if tool_name is not None:
                merged.append(str(tool_name))
        normalized = _normalize_plugin_tool_names(merged)
        undeclared = _find_undeclared_plugin_tool_names(declared, normalized)
        if undeclared:
            _log.warning(
                "register_tool: plugin %r declared undeclared tool names: %s "
                "(declared=%s); skipping",
                self._ctx.plugin_id,
                undeclared,
                declared or "(no contracts.tools declared)",
            )
            return
        self._tools.append((tool, normalized))

    def register_command(
        self,
        command: CommandDecl | dict[str, Any],
    ) -> None:
        """Register a slash command. ``handler`` is required."""
        if isinstance(command, dict):
            command_dict = cast(dict[str, Any], command)
            d = dict(command_dict)
            if "acceptsArgs" in d:
                d["accepts_args"] = d.pop("acceptsArgs")
            if "requiredScopes" in d:
                d["expose_sender_is_owner"] = "operator.pairing" in d.pop("requiredScopes", [])
            if "description" not in d:
                d["description"] = d.get("name", "")
            from .api import CommandDecl

            command = CommandDecl(**d)
        if not callable(command.handler):
            raise TypeError(
                f"CommandDecl({command.name!r}).handler must be callable; "
                f"got {type(command.handler).__name__}. Use an async function "
                f"returning PluginCommandResult."
            )
        self._commands.append(command)

    def register_cli(
        self,
        register_fn: Callable[..., Any],
        *,
        descriptors: list[CliDescriptor | dict[str, object]] | None = None,
        parent_path: list[str] | None = None,
        commands: list[str] | None = None,
    ) -> None:
        """Register a CLI subcommand. Mirrors OpenClaw's ``registerCli``."""
        norm_descriptors: list[CliDescriptor] = []
        for d in descriptors or []:
            if isinstance(d, CliDescriptor):
                norm_descriptors.append(d)
            elif isinstance(d, dict):
                d_typed: dict[str, object] = d
                name_value: str = str(d_typed.get("name", ""))
                desc_value: str = str(d_typed.get("description", ""))
                has_sub_value: bool = bool(d_typed.get("has_subcommands", False))
                norm_descriptors.append(
                    CliDescriptor(
                        name=name_value,
                        description=desc_value,
                        has_subcommands=has_sub_value,
                    )
                )
            else:
                norm_descriptors.append(d)
        norm_parent_path = list(parent_path or [])
        norm_commands: list[str] = list(commands or [])
        self._cli_handlers.append((register_fn, norm_descriptors, norm_parent_path, norm_commands))

    def register_memory_capability(self, capability: dict[str, Any]) -> None:
        """Register a memory-host capability. Only one plugin per process."""
        if self._memory_capability is not None:
            raise RuntimeError(
                f"Plugin {self._ctx.plugin_id!r} tried to register a memory "
                f"capability but {self._memory_capability.get('_owner_id')!r} "
                f"already registered one. Memory is single-active-slot."
            )
        capability["_owner_id"] = self._ctx.plugin_id
        self._memory_capability = capability

    def register_memory_prompt_section(self, builder: Any) -> None:
        """Register a memory prompt-section builder through the OpenClaw plugin API."""
        if not callable(builder):
            raise ValueError("memory prompt section registration requires a callable builder")
        payload: JSON = {"builder": builder, "_owner_id": self._ctx.plugin_id}
        self._memory_prompt_sections.append(payload)

    def register_memory_prompt_supplement(self, builder: Any) -> None:
        """Register a memory prompt-supplement builder through the OpenClaw plugin API."""
        if not callable(builder):
            raise ValueError("memory prompt supplement registration requires a callable builder")
        payload: JSON = {"builder": builder, "_owner_id": self._ctx.plugin_id}
        self._memory_prompt_supplements.append(payload)

    def register_memory_prompt_preparation(self, preparer: Any) -> None:
        """Register a memory prompt-preparation async callback through the OpenClaw API."""
        if not callable(preparer):
            raise ValueError("memory prompt preparation registration requires a callable preparer")
        payload: JSON = {"preparer": preparer, "_owner_id": self._ctx.plugin_id}
        self._memory_prompt_preparations.append(payload)

    def register_memory_corpus_supplement(self, supplement: Any) -> None:
        """Register a memory corpus-supplement payload through the OpenClaw API."""
        payload: JSON = {"supplement": supplement, "_owner_id": self._ctx.plugin_id}
        self._memory_corpus_supplements.append(payload)

    def register_memory_flush_plan(self, resolver: Any) -> None:
        """Register a memory flush-plan resolver through the OpenClaw API."""
        if not callable(resolver):
            raise ValueError("memory flush plan registration requires a callable resolver")
        payload: JSON = {"resolver": resolver, "_owner_id": self._ctx.plugin_id}
        self._memory_flush_plans.append(payload)

    def register_memory_runtime(self, runtime: Any) -> None:
        """Register a memory runtime bridge through the OpenClaw API."""
        payload: JSON = {"runtime": runtime, "_owner_id": self._ctx.plugin_id}
        self._memory_runtimes.append(payload)

    def register_provider(self, provider: dict[str, Any]) -> None:
        """Register an LLM provider (text-inference capability)."""
        provider["_owner_id"] = self._ctx.plugin_id
        self._provider = provider

    def register_channel(self, channel: dict[str, Any] | Any) -> None:
        """Register a messaging channel (channel capability)."""
        if isinstance(channel, dict):
            channel_dict = cast(dict[str, Any], channel)
            channel_dict["_owner_id"] = self._ctx.plugin_id
            self._channel = channel_dict
            return

        channel_dict: dict[str, Any] = {
            "id": getattr(channel, "id", self._ctx.plugin_id),
            "kind": getattr(channel, "kind", "channel"),
            "plugin": channel,
            "_owner_id": self._ctx.plugin_id,
        }
        for method_name in ("send", "listen", "shutdown"):
            method = getattr(channel, method_name, None)
            if callable(method):
                channel_dict[method_name] = method
        self._channel = channel_dict

    def register_context_engine(self, engine: dict[str, Any] | Any) -> None:
        """Register a pluggable context engine implementation."""
        if isinstance(engine, dict):
            engine_dict = cast(dict[str, Any], engine)
            engine_id = engine_dict.get("id")
            factory = engine_dict.get("factory")
            if not engine_id or not isinstance(engine_id, str):
                raise ValueError("context engine registration requires a non-empty 'id'")
            if not callable(factory):
                raise ValueError("context engine registration requires a callable 'factory'")
            engine_obj: dict[str, Any] = dict(engine_dict)
        else:
            engine_value = cast(Any, engine)
            engine_id = cast(str | None, getattr(engine_value, "id", None))
            factory = cast(Callable[..., Any] | None, getattr(engine_value, "factory", None))
            info_obj = getattr(engine_value, "info", None)
            engine_info: dict[str, Any] | None = None
            if isinstance(info_obj, dict):
                engine_info = cast(dict[str, Any], info_obj)
            if not engine_id and engine_info is not None:
                engine_id = cast(str | None, engine_info.get("id"))
            if not callable(factory):
                factory = cast(Callable[..., Any] | None, getattr(engine_value, "create", None))
            if not engine_id or not isinstance(engine_id, str):
                raise ValueError("context engine registration requires a non-empty 'id'")
            if not callable(factory):
                raise ValueError("context engine registration requires a callable 'factory'")
            engine_obj = {
                "id": engine_id,
                "factory": factory,
                "info": info_obj or {},
                "metadata": getattr(engine, "metadata", None) or {},
            }
        for existing in self._context_engines:
            if existing.get("id") == engine_id:
                raise RuntimeError(
                    f"Plugin {self._ctx.plugin_id!r} tried to register context engine "
                    f"{engine_id!r} but it's already registered by "
                    f"{existing.get('_owner_id')!r}."
                )
        engine_obj["_owner_id"] = self._ctx.plugin_id
        self._context_engines.append(engine_obj)

    def register_compaction_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register a context-compaction provider for the host runtime."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            compact = provider_dict.get("compact")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("compaction provider requires a non-empty 'id'")
            if not callable(compact):
                raise ValueError("compaction provider requires a callable 'compact'")
            provider_obj: dict[str, Any] = dict(provider_dict)
        else:
            provider_value = cast(Any, provider)
            provider_id = getattr(provider_value, "id", None)
            compact = getattr(provider_value, "compact", None) or getattr(
                provider_value, "handler", None
            )
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("compaction provider requires a non-empty 'id'")
            if not callable(compact):
                raise ValueError("compaction provider requires a callable 'compact'")
            provider_obj = {
                "id": provider_id,
                "compact": compact,
                "meta": getattr(provider_value, "meta", None) or {},
            }
        for existing in self._compaction_providers:
            if existing.get("id") == provider_id:
                raise RuntimeError(
                    f"Plugin {self._ctx.plugin_id!r} tried to register compaction provider "
                    f"{provider_id!r} but it's already registered by "
                    f"{existing.get('_owner_id')!r}."
                )
        provider_obj["_owner_id"] = self._ctx.plugin_id
        self._compaction_providers.append(provider_obj)

    def register_session_catalog(self, catalog: dict[str, Any] | Any) -> None:
        """Register a session catalog adapter for the runtime."""
        if isinstance(catalog, dict):
            catalog_dict = cast(dict[str, Any], catalog)
            catalog_id = catalog_dict.get("id")
            handler = catalog_dict.get("handler")
            is_stub = catalog_dict.get("stub") is True
            has_methods = bool(
                callable(catalog_dict.get("list"))
                or callable(catalog_dict.get("list_sessions"))
                or callable(catalog_dict.get("read"))
                or callable(catalog_dict.get("get_session"))
            )
            if not catalog_id or not isinstance(catalog_id, str):
                raise ValueError("session catalog requires a non-empty 'id'")
            if not callable(handler) and not is_stub and not has_methods:
                raise ValueError(
                    "session catalog requires a callable 'handler' or provider methods"
                )
            payload: dict[str, Any] = dict(catalog_dict)
        else:
            catalog_id = getattr(catalog, "id", None)
            handler = getattr(catalog, "handler", None)
            list_fn = getattr(catalog, "list", None) or getattr(catalog, "list_sessions", None)
            read_fn = getattr(catalog, "read", None) or getattr(catalog, "get_session", None)
            is_stub = getattr(catalog, "stub", False) is True
            has_methods = bool(callable(list_fn) or callable(read_fn))
            if not catalog_id or not isinstance(catalog_id, str):
                raise ValueError("session catalog requires a non-empty 'id'")
            if not callable(handler) and not is_stub and not has_methods:
                raise ValueError(
                    "session catalog requires a callable 'handler' or provider methods"
                )
            payload = {"id": catalog_id, "provider": catalog}
            label = getattr(catalog, "label", None)
            if label is not None:
                payload["label"] = label
            if callable(handler):
                payload["handler"] = handler
            if callable(list_fn):
                payload["list"] = list_fn
            if callable(read_fn):
                payload["read"] = read_fn
            if is_stub:
                payload["stub"] = True
            kind = getattr(catalog, "kind", None)
            if kind is not None:
                payload["kind"] = kind
        payload["_owner_id"] = self._ctx.plugin_id
        self._session_catalogs.append(payload)

    def register_cli_backend(self, backend: dict[str, Any] | Any) -> None:
        """Register a CLI backend / CLI host adapter."""
        if isinstance(backend, dict):
            backend_dict = cast(dict[str, Any], backend)
            backend_id = backend_dict.get("id")
            handler = backend_dict.get("handler")
            if not backend_id or not isinstance(backend_id, str):
                raise ValueError("cli backend requires a non-empty 'id'")
            if not callable(handler):
                raise ValueError("cli backend requires a callable 'handler'")
            payload: dict[str, Any] = dict(backend_dict)
        else:
            backend_id = getattr(backend, "id", None)
            handler = getattr(backend, "handler", None)
            if not backend_id or not isinstance(backend_id, str):
                raise ValueError("cli backend requires a non-empty 'id'")
            if not callable(handler):
                raise ValueError("cli backend requires a callable 'handler'")
            payload: dict[str, Any] = {"id": backend_id, "handler": handler}
        payload["_owner_id"] = self._ctx.plugin_id
        self._cli_backends.append(payload)

    def register_text_transform(self, transform: dict[str, Any] | Any) -> None:
        """Register a text transform operation."""
        if isinstance(transform, dict):
            transform_dict = cast(dict[str, Any], transform)
            transform_id = transform_dict.get("id")
            handler = transform_dict.get("handler")
            if not transform_id or not isinstance(transform_id, str):
                raise ValueError("text transform requires a non-empty 'id'")
            if not callable(handler):
                raise ValueError("text transform requires a callable 'handler'")
            payload: dict[str, Any] = dict(transform_dict)
        else:
            transform_id = getattr(transform, "id", None)
            handler = getattr(transform, "handler", None)
            if not transform_id or not isinstance(transform_id, str):
                raise ValueError("text transform requires a non-empty 'id'")
            if not callable(handler):
                raise ValueError("text transform requires a callable 'handler'")
            payload: dict[str, Any] = {"id": transform_id, "handler": handler}
        payload["_owner_id"] = self._ctx.plugin_id
        self._text_transforms.append(payload)

    def register_session_extension(self, extension: dict[str, Any] | Any) -> None:
        """Register a session extension runtime hook."""
        if isinstance(extension, dict):
            extension_dict = cast(dict[str, Any], extension)
            extension_id = extension_dict.get("id")
            handler = extension_dict.get("handler")
            if not extension_id or not isinstance(extension_id, str):
                raise ValueError("session extension requires a non-empty 'id'")
            if not callable(handler):
                raise ValueError("session extension requires a callable 'handler'")
            payload: dict[str, Any] = dict(extension_dict)
        else:
            extension_id = getattr(extension, "id", None)
            handler = getattr(extension, "handler", None)
            if not extension_id or not isinstance(extension_id, str):
                raise ValueError("session extension requires a non-empty 'id'")
            if not callable(handler):
                raise ValueError("session extension requires a callable 'handler'")
            payload: dict[str, Any] = {"id": extension_id, "handler": handler}
        payload["_owner_id"] = self._ctx.plugin_id
        self._session_extensions.append(payload)

    def register_codex_app_server_extension_factory(self, factory: dict[str, Any] | Any) -> None:
        """Register a Codex app-server extension factory."""
        if isinstance(factory, dict):
            factory_dict = cast(dict[str, Any], factory)
            factory_id = factory_dict.get("id")
            entry_factory = factory_dict.get("factory")
            if not factory_id or not isinstance(factory_id, str):
                raise ValueError("codex extension factory requires a non-empty 'id'")
            if not callable(entry_factory):
                raise ValueError("codex extension factory requires a callable 'factory'")
            payload: dict[str, Any] = dict(factory_dict)
        else:
            factory_id = getattr(factory, "id", None)
            entry_factory = getattr(factory, "factory", None)
            if not factory_id or not isinstance(factory_id, str):
                raise ValueError("codex extension factory requires a non-empty 'id'")
            if not callable(entry_factory):
                raise ValueError("codex extension factory requires a callable 'factory'")
            payload: dict[str, Any] = {"id": factory_id, "factory": entry_factory}
        payload["_owner_id"] = self._ctx.plugin_id
        self._codex_app_server_extension_factories.append(payload)

    def register_interactive_handler(self, handler: dict[str, Any] | Any) -> None:
        """Register an interactive handler for the host command UI."""
        if isinstance(handler, dict):
            handler_dict = cast(dict[str, Any], handler)
            handler_id = handler_dict.get("id")
            callback = handler_dict.get("handler")
            if not handler_id or not isinstance(handler_id, str):
                raise ValueError("interactive handler requires a non-empty 'id'")
            if not callable(callback):
                raise ValueError("interactive handler requires a callable 'handler'")
            payload: dict[str, Any] = dict(handler_dict)
        else:
            handler_id = getattr(handler, "id", None)
            callback = getattr(handler, "handler", None)
            if not handler_id or not isinstance(handler_id, str):
                raise ValueError("interactive handler requires a non-empty 'id'")
            if not callable(callback):
                raise ValueError("interactive handler requires a callable 'handler'")
            payload: dict[str, Any] = {"id": handler_id, "handler": callback}
        payload["_owner_id"] = self._ctx.plugin_id
        self._interactive_handlers.append(payload)
