"""Plugin base classes — the ABCs plugins implement.

Mirrors OpenClaw's pattern where each plugin kind has a base interface
(``ToolPlugin``, ``ChannelPlugin``, ``ProviderPlugin``, ``MemoryHostPlugin``,
``MigrationProviderPlugin``). Plugins subclass these to get lifecycle hooks
(``init``/``shutdown``) and a typed contract.

For lightweight plugins (a single tool, a simple channel), it's also
acceptable to skip the subclass and just register a plain object via
``api.register_tool(instance, names=[...])`` — the ``PluginApi`` adapts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from jarvis_normalization_core.result import Err, Result

from .channel_actions import ChannelAction, TextAction
from .channel_capabilities import ChannelCapabilities

if TYPE_CHECKING:
    from .channel_adapters import (
        ChannelConversationBindings,
        ChannelOutboundAdapter,
        ChannelPairingAdapter,
        ChannelSecurityAdapter,
        ChannelThreadingAdapter,
    )
    from .manifest import ToolDecl

T = TypeVar("T")


class Plugin(ABC):
    """Base class for every plugin. Subclasses set identity attrs + init.

    Most plugins don't need to subclass this directly — they subclass
    ``ToolPlugin`` (or one of the other kind-specific classes). This base
    is for the small set of plugins that just need lifecycle hooks
    (e.g. an ``infra`` plugin that boots a sidecar).
    """

    # Identity (set by subclass; mirrors manifest fields)
    id: str
    kind: str
    version: str
    description: str

    @abstractmethod
    def init(self, ctx: Any) -> None:
        """Called once after the plugin is instantiated and the host
        has its context ready. Use this to acquire services, open
        connections, register callbacks. Never block forever here."""

    def register(self, api: Any) -> None:
        """Register plugin-owned services / hooks with the host ``PluginApi``.

        Mirrors OpenClaw's ``plugin.register(api)`` contract:
        the loader calls ``entry.register(api)`` once per plugin
        and the plugin's body wires its services / channels /
        tools / hooks / commands / etc. into the host.

        The default implementation is a no-op so that lightweight
        identity-only stubs (the 148 scaffold plugins) load
        without warnings. Real plugins (ToolPlugin / ChannelPlugin
        / ProviderPlugin / etc.) override this method and call
        ``api.registerService()`` / ``api.registerChannel()`` /
        ``api.registerTool()`` / etc. on the supplied ``api``.

        The ``api`` parameter is typed as ``Any`` because the
        ``PluginApi`` class is defined in ``api.py`` and we want
        to avoid a circular import; the runtime contract is
        ``api.registerX(...)`` style methods.
        """
        return None

    async def shutdown(self) -> None:
        """Optional async cleanup. Default is no-op. Called when the
        host stops. Must not raise."""
        return  # explicit no-op default; subclasses override


class ToolPlugin(Plugin):
    """A plugin that exposes one or more tools to the LLM.

    Implementations return a list of ``ToolDecl`` and a ``call(name, args)``
    method that dispatches to the right tool. ``call`` should return a
    ``Result`` (``Ok(value)`` or ``Err(message, code=...)``) — the host
    maps ``Err`` to a tool-error response for the LLM.
    """

    @property
    @abstractmethod
    def tools(self) -> list[ToolDecl]:
        """Tool declarations for the LLM (mirrors the manifest's tools[])."""

    @abstractmethod
    async def call(self, name: str, args: dict[str, Any]) -> Result[Any]:
        """Dispatch a tool call by name. Must not raise — return ``Err`` instead."""


class ChannelPlugin(Plugin):
    """A plugin that bridges a messaging surface to JARVIS.

    Implementations handle inbound (received) and outbound (sent)
    messages on a specific transport (Telegram, Discord, etc.). The
    host wires each channel into the message router; the plugin doesn't
    decide which conversations it owns (that's policy, owned by core).

    OpenClaw parity: mirrors ``ChannelPlugin<TResolvedAccount>`` from
    ``src/plugins/types.core.ts`` with optional adapter fields for
    security, pairing, threading, outbound, and conversation binding.

    Adapter fields (all optional — default to ``None`` / no-op):
        security             : ChannelSecurityAdapter
        pairing              : ChannelPairingAdapter
        threading            : ChannelThreadingAdapter
        outbound             : ChannelOutboundAdapter
        conversation_bindings: ChannelConversationBindings
        meta                 : dict — transport metadata (name, icon, etc.)
        config_schema        : dict — plugin config JSON schema
        commands             : list — transport-native command declarations
        agent_prompt         : dict — agent-prompt surface injection
        streaming            : dict — streaming config
        reload               : dict — reload descriptor
        gateway_methods      : list — gateway method declarations
        groups               : list[str] — capability groups
        setup                : dict — setup flow descriptor
        setup_wizard         : dict — setup wizard descriptor
    """

    # ── Adapter fields (all optional) ────────────────────────────────
    #: Security policy adapter; ``None`` = allow-all (transport-default).
    security: ChannelSecurityAdapter | None = None
    #: Account pairing adapter; ``None`` = no pairing UI.
    pairing: ChannelPairingAdapter | None = None
    #: Thread routing adapter; ``None`` = per-transport default.
    threading: ChannelThreadingAdapter | None = None
    #: Outbound rendering adapter; ``None`` = use abstract ``send()`` only.
    outbound: ChannelOutboundAdapter | None = None
    #: Conversation binding lifecycle adapter; ``None`` = no binding.
    conversation_bindings: ChannelConversationBindings | None = None
    #: Transport metadata dict (``{"name": str, "icon": str, ...}``).
    meta: dict[str, Any] | None = None
    #: Plugin config JSON schema dict (mirrors OpenClaw ``configSchema``).
    config_schema: dict[str, Any] | None = None
    #: Transport-native command declarations.
    commands: list[dict[str, Any]] | None = None
    #: Agent-prompt surface injection config.
    agent_prompt: dict[str, Any] | None = None
    #: Streaming config dict.
    streaming: dict[str, Any] | None = None
    #: Reload descriptor (forwarded to host).
    reload: dict[str, Any] | None = None
    #: Gateway method declarations.
    gateway_methods: list[dict[str, Any]] | None = None
    #: Capability group names.
    groups: list[str] | None = None
    #: Setup flow descriptor.
    setup: dict[str, Any] | None = None
    #: Setup wizard descriptor.
    setup_wizard: dict[str, Any] | None = None

    @abstractmethod
    async def send(self, target: str, message: Any) -> Result[None]:
        """Send a message to a specific target on this channel."""

    @abstractmethod
    async def listen(self, callback: Any) -> None:
        """Start listening for inbound messages. ``callback`` is invoked
        for each one. Returns when listen() is cancelled."""

    def capabilities(self) -> ChannelCapabilities:
        """Static capability flags. Default reports no optional capabilities."""
        return ChannelCapabilities()

    async def send_typed(self, target: str, action: ChannelAction) -> Result[None]:
        """Render one portable presentation action.

        Default routes ``TextAction`` through ``send()`` so minimal
        channels work unchanged; every other kind returns an honest
        ``not_implemented`` error instead of guessing a rendering.
        """
        if isinstance(action, TextAction):
            return await self.send(target, action.text)
        return Err(
            f"channel does not render {action.kind} actions",
            code="not_implemented",
        )

    def normalize_inbound(self, raw: Any) -> dict[str, Any]:
        """Map a native inbound envelope to a minimal event dict.

        Transports override this to fill ``target``/``text``/thread
        fields; the default keeps the raw envelope for inspection.
        """
        return {"target": "", "text": str(raw), "raw": raw}

    def register(self, api: Any) -> None:
        """Register this channel with the host plugin API."""
        if hasattr(api, "register_channel"):
            api.register_channel(self)
        elif hasattr(api, "registerChannel"):
            api.registerChannel(self)

    def doctor_contract(self) -> dict[str, Any]:
        """Describe channel health for ``jarvis doctor``.

        Override to report transport state; the default marks the
        contract unimplemented so the host skips it gracefully.
        """
        return {"status": "not_implemented"}


class ProviderPlugin(Plugin):
    """A plugin that adapts an LLM/model provider to the JARVIS LLM client.

    Implementations translate JARVIS's provider-agnostic message format
    into the provider's request shape and back. Each provider owns its
    own auth, catalog, and quirks.

    OpenClaw parity: mirrors ``ProviderPlugin`` from
    ``src/plugins/provider-plugin.types.ts``. Advanced methods
    (streaming, auth, catalog, replay, thinking, tool-schema) are
    optional and default to ``Err("not_implemented")``.
    """

    @abstractmethod
    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> Result[str]:
        """Run a one-shot completion (non-streaming). Returns the assistant text."""

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return the model identifiers this provider supports."""

    async def astream(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> AsyncIterator[Result[str]]:
        """Stream completion chunks. Default yields one honest error event."""
        yield Err("provider does not implement streaming", code="not_implemented")

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> Result[str]:
        """Run a completion with tool declarations. Default is unimplemented."""
        return Err("provider does not implement tool completions", code="not_implemented")

    def list_models_detail(self) -> list[dict[str, Any]]:
        """Return model declarations (id/label/context window). Default is empty."""
        return []

    def resolve_auth(self, ctx: dict[str, Any]) -> Result[dict[str, Any]]:
        """Resolve credentials for this provider. Default is unimplemented."""
        return Err("provider does not implement auth resolution", code="not_implemented")

    def build_catalog(self) -> Result[list[dict[str, Any]]]:
        """Build the provider-owned model catalog. Default is unimplemented."""
        return Err("provider does not implement catalog builds", code="not_implemented")

    # ── Advanced provider methods (OpenClaw parity) ───────────────────

    async def prepare_runtime_auth(self, ctx: dict[str, Any]) -> Result[dict[str, Any]]:
        """Prepare runtime auth tokens for an inference call.

        Mirrors OpenClaw's ``ProviderPlugin.prepareRuntimeAuth``.
        Return ``Ok({"token": "..."})`` or ``Err(...)``.
        Default is unimplemented.
        """
        return Err("provider does not implement prepare_runtime_auth", code="not_implemented")

    def normalize_tool_schemas(
        self, tools: list[dict[str, Any]], ctx: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Normalise/filter tool schemas before they are sent to the provider.

        Mirrors OpenClaw's ``ProviderPlugin.normalizeToolSchemas``.
        Default passes tools through unchanged.
        """
        return tools

    def thinking_policy(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """Return the provider's thinking / reasoning policy.

        Mirrors OpenClaw's ``ProviderPlugin.thinkingPolicy``.
        Default returns ``{"enabled": False}``.
        """
        return {"enabled": False}

    async def sanitize_replay_history(
        self, history: list[dict[str, Any]], ctx: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Strip or redact replay-session history before sending to the provider.

        Mirrors OpenClaw's ``ProviderPlugin.sanitizeReplayHistory``.
        Default passes history through unchanged.
        """
        return history

    async def validate_replay_turns(
        self, turns: list[dict[str, Any]], ctx: dict[str, Any]
    ) -> Result[None]:
        """Validate replay turns before a replay session starts.

        Mirrors OpenClaw's ``ProviderPlugin.validateReplayTurns``.
        Default accepts all turns.
        """
        return Result[None](None)  # type: ignore[call-arg]

    async def resolve_transport_turn_state(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """Resolve transport-level turn state (e.g. conversation_id for stateful APIs).

        Mirrors OpenClaw's ``ProviderPlugin.resolveTransportTurnState``.
        Default returns ``{}``.
        """
        return {}

    def resolve_usage_auth(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """Resolve usage-tracking auth tokens/metadata.

        Mirrors OpenClaw's ``ProviderPlugin.resolveUsageAuth``.
        Default returns ``{}``.
        """
        return {}

    def normalize_model_id(self, model_id: str, ctx: dict[str, Any]) -> str:
        """Normalise a user-supplied model id to the provider's canonical form.

        Mirrors OpenClaw's ``ProviderPlugin.normalizeModelId``.
        Default returns ``model_id`` unchanged.
        """
        return model_id

    def normalize_resolved_model(
        self, model: dict[str, Any], ctx: dict[str, Any]
    ) -> dict[str, Any]:
        """Post-process a resolved model descriptor.

        Mirrors OpenClaw's ``ProviderPlugin.normalizeResolvedModel``.
        Default returns ``model`` unchanged.
        """
        return model


class MemoryHostPlugin(Plugin):
    """A plugin that owns the memory store (single-active-slot pattern).

    Only one MemoryHostPlugin is active at a time; the host manages
    activation through the ``memory.active_host`` config field. The
    active host provides search, store, and get operations; other
    hosts can be installed but are dormant.
    """

    @abstractmethod
    async def search(self, query: str, k: int = 10) -> Result[list[Any]]:
        """Semantic search over the memory store."""

    @abstractmethod
    async def store(self, content: str, metadata: dict[str, Any]) -> Result[None]:
        """Persist a memory entry."""

    @abstractmethod
    async def get(self, memory_id: str) -> Result[Any]:
        """Fetch a memory entry by id."""


class MigrationProviderPlugin(Plugin):
    """A plugin that provides data/config migration logic.

    Mirrors OpenClaw's ``MigrationProviderPlugin`` type from
    ``src/plugins/migration-provider.types.ts``.

    Migration providers are invoked by ``jarvis doctor --fix`` and the
    host migration runner. They own the logic for transforming old state
    shapes into the current canonical shape.

    Each migration has a ``version`` key and a ``migrate`` coroutine that
    receives the old state and returns the new state. Migrations must be
    idempotent and must not raise — return ``Err`` on failure.
    """

    @abstractmethod
    def list_migrations(self) -> list[dict[str, Any]]:
        """Return an ordered list of migration descriptors.

        Each descriptor has at least:
        - ``"version"`` : str — the migration version key.
        - ``"description"`` : str — human-readable summary.
        - ``"scope"`` : str — what the migration touches (``"config"``,
          ``"state"``, ``"files"``, etc.)
        """

    @abstractmethod
    async def migrate(self, version: str, ctx: dict[str, Any]) -> Result[dict[str, Any]]:
        """Run the migration for ``version``.

        ``ctx`` carries the old state / config snapshot and environment
        facts. Return ``Ok(new_state)`` on success, ``Err(...)`` on
        failure. Must not raise.
        """

    def migration_applicable(self, version: str, ctx: dict[str, Any]) -> bool:
        """Return ``True`` if the given migration version should run.

        The host calls this before ``migrate()`` to let providers opt-out
        of migrations that are not applicable in the current environment.
        Default: always applicable.
        """
        return True


@runtime_checkable
class ToolCallable(Protocol):
    """Structural type for any object that can be called as a tool.

    Plugins can subclass ``ToolPlugin`` for the full lifecycle, OR
    implement just this protocol (with ``tools`` + ``call``) and
    register via ``api.register_tool(instance, names=[...])``. The host
    adapts either form.
    """

    @property
    def tools(self) -> list[ToolDecl]: ...
    async def call(self, name: str, args: dict[str, Any]) -> Result[Any]: ...


__all__ = [
    "ChannelPlugin",
    "MemoryHostPlugin",
    "MigrationProviderPlugin",
    "Plugin",
    "ProviderPlugin",
    "ToolCallable",
    "ToolPlugin",
]
