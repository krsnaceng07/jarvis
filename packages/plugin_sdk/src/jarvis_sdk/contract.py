"""Plugin base classes — the ABCs plugins implement.

Mirrors OpenClaw's pattern where each plugin kind has a base interface
(``ToolPlugin``, ``ChannelPlugin``, ``ProviderPlugin``, ``MemoryHostPlugin``).
Plugins subclass these to get lifecycle hooks (``init``/``shutdown``)
and a typed contract.

For lightweight plugins (a single tool, a simple channel), it's also
acceptable to skip the subclass and just register a plain object via
``api.register_tool(instance, names=[...])`` — the ``PluginApi`` adapts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from .manifest import ToolDecl
    from jarvis_normalization_core.result import Result

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
    """

    @abstractmethod
    async def send(self, target: str, message: Any) -> Result[None]:
        """Send a message to a specific target on this channel."""

    @abstractmethod
    async def listen(self, callback: Any) -> None:
        """Start listening for inbound messages. ``callback`` is invoked
        for each one. Returns when listen() is cancelled."""


class ProviderPlugin(Plugin):
    """A plugin that adapts an LLM/model provider to the JARVIS LLM client.

    Implementations translate JARVIS's provider-agnostic message format
    into the provider's request shape and back. Each provider owns its
    own auth, catalog, and quirks.
    """

    @abstractmethod
    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> Result[str]:
        """Run a one-shot completion (non-streaming). Returns the assistant text."""

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return the model identifiers this provider supports."""


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
    "Plugin",
    "ProviderPlugin",
    "ToolCallable",
    "ToolPlugin",
]
