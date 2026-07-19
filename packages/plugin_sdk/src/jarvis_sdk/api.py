"""PluginApi — the registration surface the host gives each plugin.

Mirrors OpenClaw's plugin-registration API. The host instantiates a
``PluginApi`` per plugin, calls ``register(api)`` (from the plugin's
``define_plugin_entry``), and then reads back the collected tools /
commands / CLI handlers.

Adding a new registration point:
1. Add a method on ``PluginApi`` here.
2. Add a private accumulator (``self._<thing>``).
3. Add a public property that returns a copy of the accumulator.
4. The host reads the property and wires the registered objects into
   its own subsystems.
5. Mirror the change in the host's loader (``apps/desktop/src/jarvis_desktop/app.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from .context import PluginContext


@dataclass
class CommandDecl:
    """A slash command a plugin registers. Mirrors OpenClaw's CommandReg.

    Attributes
    ----------
    name : str
        The slash-command name (without leading ``/``).
    description : str
        User-facing help text.
    accepts_args : bool
        Whether the command accepts trailing arguments.
    expose_sender_is_owner : bool
        If True, the command works only when the sender is the operator
        (vs a paired remote user). Used for security-sensitive commands.
    handler : Callable | None
        Async function with signature ``async (ctx, args, sender) -> Any``.
        Optional for stub commands (declaration-only until the handler
        lands in a later phase). Required for live command routing.
    """

    name: str
    description: str
    handler: Callable[..., Any] | None = None
    accepts_args: bool = True
    expose_sender_is_owner: bool = True


@dataclass
class CliDescriptor:
    """A CLI subcommand registration. Mirrors OpenClaw's CLI descriptor."""

    name: str
    description: str
    has_subcommands: bool = False


class PluginApi:
    """The host gives one of these to each plugin's ``register(api)`` callback.

    Plugins use the methods to register their capabilities; the host
    reads the public properties afterward to wire them into its
    subsystems (the LLM, the slash-command router, the CLI entry, etc.).
    """

    def __init__(self, ctx: PluginContext, logger: Any = None) -> None:
        self._ctx = ctx
        self._logger = logger or ctx.logger

        # ── Accumulators (private) ────────────────────────────────────
        self._tools: list[tuple[Any, list[str] | None]] = []
        self._commands: list[CommandDecl] = []
        self._cli_handlers: list[tuple[Callable[..., Any], list[CliDescriptor]]] = []
        self._memory_capability: dict[str, Any] | None = None
        self._provider: dict[str, Any] | None = None
        self._channel: dict[str, Any] | None = None
        self._doctor_contracts: list[dict[str, Any]] = []
        self._http_handlers: list[dict[str, Any]] = []

    # ── Identity / accessors ──────────────────────────────────────────
    @property
    def ctx(self) -> PluginContext:
        return self._ctx

    @property
    def logger(self) -> Any:
        return self._logger

    # ── Registration methods (plugins call these) ────────────────────

    def register_tool(
        self,
        tool: Any,
        *,
        names: list[str] | None = None,
    ) -> None:
        """Register a tool instance. ``tool`` is any object with
        ``.tools`` and ``.call`` (matches ``ToolCallable`` protocol,
        or a ``ToolPlugin`` subclass).

        ``names`` (optional): explicit tool-name list to register this
        instance under. If None, all names from ``tool.tools`` are used.
        """
        self._tools.append((tool, names))

    def register_command(self, command: CommandDecl | dict) -> None:
        """Register a slash command. ``command`` is a ``CommandDecl`` or
        a dict with the same fields (for ergonomic plugin definitions)."""
        if isinstance(command, dict):
            command = CommandDecl(**command)
        self._commands.append(command)

    def register_cli(
        self,
        register_fn: Callable[..., Any],
        *,
        descriptors: list[CliDescriptor | dict] | None = None,
    ) -> None:
        """Register a CLI subcommand.

        ``register_fn`` signature: ``async ({program, config, ...}) -> None``.
        It mutates ``program`` (an argparse-like subparser) to add the
        subcommand's CLI surface.

        ``descriptors`` (optional): list of CLI descriptors that describe
        the subcommand in the global help / completion.
        """
        norm_descriptors: list[CliDescriptor] = []
        for d in descriptors or []:
            if isinstance(d, dict):
                norm_descriptors.append(CliDescriptor(**d))
            else:
                norm_descriptors.append(d)
        self._cli_handlers.append((register_fn, norm_descriptors))

    def register_memory_capability(self, capability: dict[str, Any]) -> None:
        """Register a memory-host capability. Only one plugin per
        process can register this (single-active-slot pattern). Mirrors
        OpenClaw's ``registerMemoryCapability``.

        ``capability`` keys:
        - ``prompt_builder``: ``Callable[[config, ctx], str]`` — inject
          memory context into the system prompt.
        - ``flush_plan_resolver``: ``Callable[[session_ctx], Plan]`` —
          decide when/how to flush short-term memory to long-term.
        - ``runtime``: object exposing ``getMemorySearchManager(...)``
          and ``closeAllMemorySearchManagers()``.
        - ``public_artifacts``: optional dict of introspection endpoints
          (used by ``jarvis doctor`` and the control UI).
        """
        if self._memory_capability is not None:
            raise RuntimeError(
                f"Plugin {self._ctx.plugin_id!r} tried to register a memory "
                f"capability but {self._memory_capability.get('_owner_id')!r} "
                f"already registered one. Memory is single-active-slot."
            )
        capability["_owner_id"] = self._ctx.plugin_id
        self._memory_capability = capability

    def register_provider(self, provider: dict[str, Any]) -> None:
        """Register an LLM provider. The host uses ``provider['complete']``
        and ``provider['list_models']`` to route completions."""
        provider["_owner_id"] = self._ctx.plugin_id
        self._provider = provider

    def register_channel(self, channel: dict[str, Any]) -> None:
        """Register a messaging channel. Mirrors OpenClaw's
        ``registerChannel``.

        ``channel`` keys:
        - ``id`` (str): channel id (e.g. ``"telegram"``).
        - ``send``: ``async (target, message) -> Result[None]``.
        - ``listen``: ``async (callback) -> None``.
        - ``config_schema``: JSON Schema for the channel's config block.
        - ``account_resolution``: optional account-snapshot helper.
        """
        channel["_owner_id"] = self._ctx.plugin_id
        self._channel = channel

    def register_doctor_contract(self, contract: dict[str, Any]) -> None:
        """Register a doctor / migration contract. Mirrors OpenClaw's
        ``PluginDoctorStateMigration``.

        ``contract`` keys:
        - ``id``: unique migration id.
        - ``version``: target schema version this migration brings to.
        - ``detect``: ``Callable[[state_dir, config], list[Finding]]`` —
          find legacy data the plugin can migrate.
        - ``apply``: ``Callable[[state_dir, config], list[Change]]`` —
          perform the migration (archive the legacy file, rewrite state).
        """
        contract["_owner_id"] = self._ctx.plugin_id
        self._doctor_contracts.append(contract)

    def register_http_handler(self, handler: dict[str, Any]) -> None:
        """Register an HTTP handler for the gateway's admin surface
        (e.g. ``POST /v1/extensions/<id>/...``)."""
        handler["_owner_id"] = self._ctx.plugin_id
        self._http_handlers.append(handler)

    # ── Read-back accessors (host uses these) ─────────────────────────

    @property
    def tools(self) -> list[tuple[Any, list[str] | None]]:
        """All registered ``(tool_instance, names_or_none)`` pairs."""
        return list(self._tools)

    @property
    def tool_instances(self) -> list[Any]:
        """Just the tool instances (drops the optional name list)."""
        return [t for t, _ in self._tools]

    @property
    def commands(self) -> list[CommandDecl]:
        return list(self._commands)

    @property
    def cli_handlers(self) -> list[tuple[Callable[..., Any], list[CliDescriptor]]]:
        return list(self._cli_handlers)

    @property
    def memory_capability(self) -> dict[str, Any] | None:
        return self._memory_capability

    @property
    def provider(self) -> dict[str, Any] | None:
        return self._provider

    @property
    def channel(self) -> dict[str, Any] | None:
        return self._channel

    @property
    def doctor_contracts(self) -> list[dict[str, Any]]:
        return list(self._doctor_contracts)

    @property
    def http_handlers(self) -> list[dict[str, Any]]:
        return list(self._http_handlers)


__all__ = [
    "CliDescriptor",
    "CommandDecl",
    "PluginApi",
]
