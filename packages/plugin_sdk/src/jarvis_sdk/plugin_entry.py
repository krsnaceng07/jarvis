"""jarvis_sdk.plugin_entry — Plugin entry contracts & registration helper functions.

OpenClaw parity: mirrors
``openclaw-main/src/plugin-sdk/plugin-entry.ts``.

Features:
- ``PluginEntryDefinition``: Dataclass defining a plugin package entry point.
  Mirrors ``DefinePluginEntryOptions`` / ``DefinedPluginEntry`` from TS source.
  Includes ``reload``, ``node_host_commands``, and ``security_audit_collectors``
  fields that were previously missing.
- ``define_plugin_entry()``: Factory for non-channel plugins (provider, tool,
  command, service, memory, context-engine).
- ``define_channel_plugin_entry()``: Factory for channel plugins. Includes
  ``registration_mode`` gating so CLI scans don't activate full channel
  transport wiring (mirrors OpenClaw's ``defineChannelPluginEntry``).
- ``define_setup_plugin_entry()``: Factory for setup-only plugin entries
  (mirrors OpenClaw's ``defineSetupPluginEntry``).
- ``create_channel_plugin_base()``: Build a minimal channel plugin dict from
  per-adapter components (mirrors ``createChannelPluginBase``).
- ``create_chat_channel_plugin()``: Compose a full chat-capable channel plugin
  from security + pairing + threading + outbound adapters (mirrors
  ``createChatChannelPlugin``).

Legacy:
- ``JarvisPluginApi``: **Deprecated**. Use ``PluginApi`` from ``jarvis_sdk.api``
  instead. Kept for backwards compatibility with Phase 1–3 extensions.
  Will be removed in a future release.
- ``PluginToolDescriptor``: **Deprecated**. Use ``ToolDecl`` from ``jarvis_sdk``
  instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from ._plugin_api_init import RegistrationMode

# ---------------------------------------------------------------------------
# PluginEntryDefinition
# ---------------------------------------------------------------------------


@dataclass
class PluginEntryDefinition:
    """Normalized entry object that the JARVIS loader reads from a plugin module.

    Mirrors OpenClaw's ``DefinedPluginEntry`` shape. All fields that are
    not required for a minimal plugin default to ``None`` / ``[]`` so the
    loader can safely read them without isinstance-branching per plugin.

    Attributes
    ----------
    id : str
        Plugin identifier (matches ``openclaw.plugin.json``'s ``"id"``).
    name : str
        Human-readable plugin name.
    description : str
        One-line description.
    kind : str | None
        Deprecated manifest-level kind (use ``openclaw.plugin.json`` ``"kind"``
        field instead; this remains as a compatibility fallback for older entries).
    register : Callable
        The ``register(api)`` callable the loader invokes once per plugin.
    reload : dict | None
        Optional reload descriptor forwarded from ``definePluginEntry``'s
        ``reload`` option. Mirrors ``OpenClawPluginDefinition["reload"]``.
    node_host_commands : list[dict]
        Optional node-host-command declarations.
    security_audit_collectors : list[dict]
        Optional security audit collector declarations.
    """

    id: str
    name: str
    description: str
    register: Callable[[Any], None] = field(default_factory=lambda: lambda _api: None)
    kind: str | None = None
    reload: dict[str, Any] | None = None
    node_host_commands: list[dict[str, Any]] = field(default_factory=list)
    security_audit_collectors: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Entry factories — non-channel
# ---------------------------------------------------------------------------


def define_plugin_entry(
    *,
    id: str,
    name: str,
    description: str,
    register: Callable[[Any], None] | None = None,
    kind: str | None = None,
    reload: dict[str, Any] | None = None,
    node_host_commands: list[dict[str, Any]] | None = None,
    security_audit_collectors: list[dict[str, Any]] | None = None,
) -> PluginEntryDefinition:
    """Canonical entry helper for non-channel plugins.

    Use for provider, tool, command, service, memory, and context-engine
    plugins. Channel plugins should use ``define_channel_plugin_entry()``
    so they inherit channel-specific registration mode gating.

    Mirrors OpenClaw's ``definePluginEntry(...)`` from ``plugin-entry.ts``.

    Parameters
    ----------
    id : str
        Plugin identifier.
    name : str
        Human-readable name.
    description : str
        One-line description.
    register : Callable | None
        ``register(api)`` body — called once per plugin load.
    kind : str | None
        Deprecated kind field. Prefer ``openclaw.plugin.json`` ``"kind"``.
    reload : dict | None
        Reload configuration (forwarded to host).
    node_host_commands : list[dict] | None
        Node-host-command declarations.
    security_audit_collectors : list[dict] | None
        Security audit collector declarations.
    """
    return PluginEntryDefinition(
        id=id,
        name=name,
        description=description,
        register=register or (lambda _api: None),
        kind=kind or "standard",
        reload=reload,
        node_host_commands=list(node_host_commands or []),
        security_audit_collectors=list(security_audit_collectors or []),
    )


# ---------------------------------------------------------------------------
# Entry factory — channel
# ---------------------------------------------------------------------------


def define_channel_plugin_entry(
    *,
    id: str,
    name: str,
    description: str,
    register: Callable[[Any], None] | None = None,
    kind: str | None = None,
    reload: dict[str, Any] | None = None,
    node_host_commands: list[dict[str, Any]] | None = None,
    security_audit_collectors: list[dict[str, Any]] | None = None,
) -> PluginEntryDefinition:
    """Canonical entry helper for channel plugins.

    Channel plugins get an ``api`` whose ``api.registration_mode`` reflects
    the loader's current scope (``"full"``, ``"cli-metadata"``,
    ``"discovery"``, or ``"tool-discovery"``). The ``register`` function
    should gate non-CLI registrations behind ``api.registration_mode``:

    .. code-block:: python

        def register(api):
            # Always safe — CLI metadata is lightweight.
            api.register_cli(cli_descriptor)

            # Only on full startup — avoid transport connections during scans.
            if api.registration_mode == "full":
                api.register_channel(my_channel_plugin)

    Mirrors OpenClaw's ``defineChannelPluginEntry(...)`` from ``plugin-entry.ts``.
    """
    return PluginEntryDefinition(
        id=id,
        name=name,
        description=description,
        register=register or (lambda _api: None),
        kind=kind or "channel",
        reload=reload,
        node_host_commands=list(node_host_commands or []),
        security_audit_collectors=list(security_audit_collectors or []),
    )


# ---------------------------------------------------------------------------
# Entry factory — setup only
# ---------------------------------------------------------------------------


def define_setup_plugin_entry(
    *,
    id: str,
    name: str,
    description: str,
    register: Callable[[Any], None],
) -> PluginEntryDefinition:
    """Entry helper for setup-only plugins (no channel/tool registration).

    Mirrors OpenClaw's ``defineSetupPluginEntry({ plugin })`` from
    ``plugin-entry.ts``. These plugins only run during ``jarvis onboard``
    or ``jarvis configure`` flows and should not register channels or
    tools. The ``api.registration_mode`` will typically be ``"cli-metadata"``
    when invoked from the setup CLI.
    """
    return PluginEntryDefinition(
        id=id,
        name=name,
        description=description,
        register=register,
        kind="setup",
    )


# ---------------------------------------------------------------------------
# Channel plugin composition helpers
# ---------------------------------------------------------------------------


def create_channel_plugin_base(
    *,
    id: str,
    meta: dict[str, Any] | None = None,
    capabilities: Any = None,
    security: Any = None,
    pairing: Any = None,
    threading: Any = None,
    outbound: Any = None,
    commands: list[Any] | None = None,
    doctor: Any = None,
    agent_prompt: Any = None,
    streaming: Any = None,
    reload: Any = None,
    gateway_methods: list[Any] | None = None,
    groups: list[str] | None = None,
    setup: Any = None,
    setup_wizard: Any = None,
    conversation_bindings: Any = None,
) -> dict[str, Any]:
    """Build a channel plugin descriptor dict from per-adapter components.

    This is the Python equivalent of OpenClaw's ``createChannelPluginBase``
    helper. Callers assembling a channel plugin from its adapters use this
    to get the correct field names without memorising the full contract.

    All fields are optional so a minimal transport-only channel can be built
    with just ``id`` and the transport body via ``define_channel_plugin_entry``.

    Returns
    -------
    dict[str, Any]
        A channel plugin descriptor dict suitable for passing to
        ``api.register_channel()``.
    """
    plugin: dict[str, Any] = {"id": id}
    if meta is not None:
        plugin["meta"] = meta
    if capabilities is not None:
        plugin["capabilities"] = capabilities
    if security is not None:
        plugin["security"] = security
    if pairing is not None:
        plugin["pairing"] = pairing
    if threading is not None:
        plugin["threading"] = threading
    if outbound is not None:
        plugin["outbound"] = outbound
    if commands is not None:
        plugin["commands"] = commands
    if doctor is not None:
        plugin["doctor"] = doctor
    if agent_prompt is not None:
        plugin["agent_prompt"] = agent_prompt
    if streaming is not None:
        plugin["streaming"] = streaming
    if reload is not None:
        plugin["reload"] = reload
    if gateway_methods is not None:
        plugin["gateway_methods"] = gateway_methods
    if groups is not None:
        plugin["groups"] = groups
    if setup is not None:
        plugin["setup"] = setup
    if setup_wizard is not None:
        plugin["setup_wizard"] = setup_wizard
    if conversation_bindings is not None:
        plugin["conversation_bindings"] = conversation_bindings
    return plugin


def create_chat_channel_plugin(
    *,
    id: str,
    meta: dict[str, Any] | None = None,
    capabilities: Any = None,
    security: Any = None,
    pairing: Any = None,
    threading: Any = None,
    outbound: Any = None,
    commands: list[Any] | None = None,
    doctor: Any = None,
    agent_prompt: Any = None,
    streaming: Any = None,
    reload: Any = None,
    gateway_methods: list[Any] | None = None,
    groups: list[str] | None = None,
    setup: Any = None,
    setup_wizard: Any = None,
    conversation_bindings: Any = None,
) -> dict[str, Any]:
    """Compose a full chat-capable channel plugin from per-adapter components.

    Convenience wrapper over ``create_channel_plugin_base`` for the common
    case of a bidirectional chat channel. Mirrors OpenClaw's
    ``createChatChannelPlugin`` helper.

    Security, pairing, threading, and outbound adapters are the primary
    composition points; the caller supplies only what it implements and
    leaves the rest as ``None`` (host treats absent adapters as no-op /
    transport-default).

    Example
    -------
    .. code-block:: python

        entry = define_channel_plugin_entry(
            id="my-channel",
            name="My Channel",
            description="...",
            register=lambda api: (
                api.register_channel(
                    create_chat_channel_plugin(
                        id="my-channel",
                        security=MySecurityAdapter(),
                        outbound=MyOutboundAdapter(),
                    )
                )
                if api.registration_mode == "full" else None
            ),
        )
    """
    return create_channel_plugin_base(
        id=id,
        meta=meta,
        capabilities=capabilities,
        security=security,
        pairing=pairing,
        threading=threading,
        outbound=outbound,
        commands=commands,
        doctor=doctor,
        agent_prompt=agent_prompt,
        streaming=streaming,
        reload=reload,
        gateway_methods=gateway_methods,
        groups=groups,
        setup=setup,
        setup_wizard=setup_wizard,
        conversation_bindings=conversation_bindings,
    )


# ---------------------------------------------------------------------------
# Legacy surface — deprecated
# ---------------------------------------------------------------------------


@dataclass
class PluginToolDescriptor:
    """**Deprecated**. Use ``ToolDecl`` from ``jarvis_sdk`` instead.

    Kept for backwards compatibility with Phase 1–3 extensions.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[..., Coroutine[Any, Any, dict[str, Any]] | dict[str, Any]]
    outputSchema: dict[str, Any] | None = None
    optional: bool = False


class JarvisPluginApi:
    """**Deprecated**. Use ``PluginApi`` from ``jarvis_sdk.api`` instead.

    The canonical API facade is ``jarvis_sdk.api.PluginApi``. This stub is
    kept only so Phase 1–3 extensions that import ``JarvisPluginApi`` do
    not break. It will be removed in a future release.

    Migration:
        Replace ``from jarvis_sdk.plugin_entry import JarvisPluginApi``
        with ``from jarvis_sdk import PluginApi``.
    """

    def __init__(self, plugin_id: str) -> None:
        self.plugin_id = plugin_id
        self.registered_tools: list[PluginToolDescriptor] = []
        self.registered_providers: list[dict[str, Any]] = []
        self.registered_channels: list[dict[str, Any]] = []

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        execute: Callable[..., Any],
        output_schema: dict[str, Any] | None = None,
        optional: bool = False,
    ) -> PluginToolDescriptor:
        """Register an agent tool. **Deprecated** — use ``PluginApi.register_tool``."""
        desc = PluginToolDescriptor(
            name=name,
            description=description,
            parameters=parameters,
            execute=execute,
            outputSchema=output_schema,
            optional=optional,
        )
        self.registered_tools.append(desc)
        return desc

    def register_provider(self, provider_config: dict[str, Any]) -> None:
        """Register a provider. **Deprecated** — use ``PluginApi.register_provider``."""
        self.registered_providers.append(provider_config)

    def register_channel(self, channel_config: dict[str, Any]) -> None:
        """Register a channel. **Deprecated** — use ``PluginApi.register_channel``."""
        self.registered_channels.append(channel_config)

    def on(
        self,
        hook_name: str,
        handler: Callable[..., Any],
        priority: int = 0,
        registration_id: str | None = None,
        timeout_ms: int = 15000,
        eligible_triggers: list[str] | None = None,
        matcher: list[str] | None = None,
    ) -> None:
        """Register a hook. **Deprecated** — use ``PluginApi.on``."""
        from .hook_bus import HookBus  # noqa: PLC0415

        if not hasattr(self, "_hook_bus"):
            self._hook_bus = HookBus()
        self._hook_bus.on(
            hook_name=hook_name,
            handler=handler,
            plugin_id=self.plugin_id,
            priority=priority,
            registration_id=registration_id,
            timeout_ms=timeout_ms,
            eligible_triggers=eligible_triggers,
            matcher=matcher,
        )


__all__ = [
    # Current public surface
    "PluginEntryDefinition",
    "RegistrationMode",
    "create_channel_plugin_base",
    "create_chat_channel_plugin",
    "define_channel_plugin_entry",
    "define_plugin_entry",
    "define_setup_plugin_entry",
    # Legacy / deprecated — do not add new callsites
    "JarvisPluginApi",
    "PluginToolDescriptor",
]
