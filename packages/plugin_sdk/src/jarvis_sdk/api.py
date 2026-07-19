"""PluginApi — the registration surface the host gives each plugin.

Mirrors OpenClaw's ``OpenClawPluginApi`` from
``src/plugins/plugin-api.types.ts``. The host instantiates a
``PluginApi`` per plugin, calls ``register(api)`` (from the plugin's
``define_plugin_entry``), and then reads back the collected tools /
commands / CLI handlers / etc.

Grouped facades (``api.session``, ``api.agent``, ``api.run_context``,
``api.lifecycle``) mirror OpenClaw's namespace layout. Flat methods on
``api`` are kept for backwards compatibility with the Phase 1B SDK
shape — Phase 2 will deprecate them and migrate plugins to the grouped
form.

Adding a new registration point:
1. Add the accumulator + public property here.
2. Mirror the change in the host's loader
   (``apps/desktop/src/jarvis_desktop/app.py::_load_plugins``).
3. Wire the collected registration into the host subsystem that
   consumes it (e.g. command router, CLI parser, doctor runner).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from .context import PluginContext

from .cli import CliDescriptor  # used at runtime in register_cli()
from .cron import CronDecl  # noqa: TCH001  (used in instance annotations below)
from .hook import HookRegistration
from .skill import SkillDecl  # noqa: TCH001

# ── Command + CLI registration descriptors ──────────────────────────


@dataclass
class CommandDecl:
    """A slash command a plugin registers. Mirrors OpenClaw's CommandReg.

    Attributes
    ----------
    name : str
        The slash-command name (without leading ``/``).
    description : str
        User-facing help text.
    handler : Callable
        **Required.** Async function with signature
        ``async (ctx) -> PluginCommandResult``. The host invokes
        ``handler(ctx)`` and uses the result to drive the agent loop.
    accepts_args : bool
        Whether the command accepts trailing arguments. Default: True.
    expose_sender_is_owner : bool
        If True, the command works only when the sender is the operator
        (vs a paired remote user). Used for security-sensitive commands.
    """

    name: str
    description: str
    handler: Callable[..., Any]
    accepts_args: bool = True
    expose_sender_is_owner: bool = True

    def __post_init__(self) -> None:
        # Validate the handler is callable at construction time so
        # plugins can't ship a stub and the host only has to check
        # once.
        if not callable(self.handler):
            raise TypeError(
                f"CommandDecl({self.name!r}).handler must be callable; "
                f"got {type(self.handler).__name__}. Use an async function "
                f"returning PluginCommandResult."
            )


# `CliDescriptor` is defined in `cli.py` (single source of truth).
# It is re-exported from `__init__.py` for plugin convenience.


# ── Grouped facades (mirror OpenClaw's namespace layout) ────────────


@dataclass
class PluginSessionApi:
    """Grouped facade for session-state registrations. Stubs in 1C."""

    state: Any = None  # registerSessionExtension (Phase 2)
    workflow: Any = None  # enqueueNextTurnInjection (Phase 2)
    controls: Any = None  # registerSessionAction (Phase 2)


@dataclass
class PluginAgentApi:
    """Grouped facade for agent-event registrations. Stubs in 1C."""

    events: Any = None  # registerAgentEventSubscription (Phase 2)


@dataclass
class PluginRunContextApi:
    """Grouped facade for run-scoped scratch state. Stubs in 1C."""

    def set_run_context(self, patch: dict) -> bool:
        return False

    def get_run_context(self, params: dict) -> Any:
        return None

    def clear_run_context(self, params: dict) -> None:
        return None


@dataclass
class PluginLifecycleApi:
    """Grouped facade for runtime cleanup hooks. Stubs in 1C."""

    def register_runtime_lifecycle(self, lifecycle: dict) -> None:
        return None


# ── Main PluginApi ───────────────────────────────────────────────────


class PluginApi:
    """The host gives one of these to each plugin's ``register(api)`` callback.

    Mirrors OpenClaw's ``OpenClawPluginApi``. Plugins use the methods
    to register their capabilities; the host reads the public
    properties afterward to wire them into its subsystems (the LLM,
    the slash-command router, the CLI entry, etc.).
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
        self._skills: list[SkillDecl] = []
        self._hooks: list[HookRegistration] = []
        self._cron_jobs: list[CronDecl] = []

        # ── Grouped facades (mirror OpenClaw) ───────────────────────
        self.session = PluginSessionApi()
        self.agent = PluginAgentApi()
        self.run_context = PluginRunContextApi()
        self.lifecycle = PluginLifecycleApi()

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
        """Register a tool. ``tool`` is any object with ``.tools`` and
        ``.call`` (matches ``ToolCallable`` protocol, or a
        ``ToolPlugin`` subclass). ``names`` is the explicit tool-name
        list; if None, all names from ``tool.tools`` are used."""
        self._tools.append((tool, names))

    def register_command(
        self,
        command: CommandDecl | dict,
    ) -> None:
        """Register a slash command. ``handler`` is required.

        Mirrors OpenClaw's ``registerCommand``. Plugins must supply a
        callable ``handler`` (async fn returning a ``PluginCommandResult``)
        so the host can route invocations without a stub.
        """
        if isinstance(command, dict):
            command = CommandDecl(**command)
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
        descriptors: list[CliDescriptor | dict] | None = None,
    ) -> None:
        """Register a CLI subcommand.

        ``register_fn`` mutates ``ctx.program`` (argparse) to add the
        plugin's subcommands. ``descriptors`` advertises the
        top-level commands for global help. Mirrors OpenClaw's
        ``registerCli``.
        """
        norm_descriptors: list[CliDescriptor] = []
        for d in descriptors or []:
            if isinstance(d, dict):
                norm_descriptors.append(CliDescriptor(**d))
            else:
                norm_descriptors.append(d)
        self._cli_handlers.append((register_fn, norm_descriptors))

    def register_memory_capability(self, capability: dict[str, Any]) -> None:
        """Register a memory-host capability. Only one plugin per process.

        Mirrors OpenClaw's ``registerMemoryCapability``. The capability
        is a dict that may include ``prompt_builder``, ``flush_plan_resolver``,
        ``runtime``, and ``public_artifacts``.
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
        """Register an LLM provider (text-inference capability)."""
        provider["_owner_id"] = self._ctx.plugin_id
        self._provider = provider

    def register_channel(self, channel: dict[str, Any]) -> None:
        """Register a messaging channel (channel capability)."""
        channel["_owner_id"] = self._ctx.plugin_id
        self._channel = channel

    def register_doctor_contract(self, contract: dict[str, Any]) -> None:
        """Register a doctor / migration contract.

        Mirrors OpenClaw's ``PluginDoctorStateMigration``. The contract
        is a dict with ``id``, ``version``, and a ``detect`` + ``apply``
        callable for finding/rewriting legacy data.
        """
        contract["_owner_id"] = self._ctx.plugin_id
        self._doctor_contracts.append(contract)

    def register_http_handler(self, handler: dict[str, Any]) -> None:
        """Register an HTTP handler for the gateway's admin surface."""
        handler["_owner_id"] = self._ctx.plugin_id
        self._http_handlers.append(handler)

    def register_skill(self, skill: SkillDecl) -> None:
        """Register a declarative skill (markdown frontmatter + body).

        Mirrors OpenClaw's ``skills/<name>/SKILL.md`` pattern. The host
        injects the skill's body into the system prompt and uses the
        description to drive tool-selection hints.
        """
        if not skill.name or not skill.description:
            raise ValueError(
                f"SkillDecl must have non-empty name and description; "
                f"got name={skill.name!r}, description={skill.description!r}"
            )
        self._skills.append(skill)

    def register_hook(
        self,
        name: str,
        handler: Callable[..., Any],
        *,
        priority: int = 0,
        timeout_ms: int | None = None,
    ) -> None:
        """Register a hook handler for the named event.

        Mirrors OpenClaw's ``api.on(hookName, handler, opts)``. The
        host fires events at well-defined points in the agent loop
        and dispatches to every subscriber in priority order.
        """
        if not callable(handler):
            raise TypeError(
                f"Hook handler for {name!r} must be callable; " f"got {type(handler).__name__}"
            )
        self._hooks.append(
            HookRegistration(
                name=name,
                handler=handler,
                priority=priority,
                timeout_ms=timeout_ms,
            )
        )

    def register_cron(self, job: CronDecl) -> None:
        """Register a scheduled job (cron expression or one-shot)."""
        if not job.id or not job.schedule or not callable(job.handler):
            raise ValueError(
                f"CronDecl must have id, schedule, and callable handler; "
                f"got id={job.id!r}, schedule={job.schedule!r}"
            )
        self._cron_jobs.append(job)

    # ── Read-back accessors (host uses these) ─────────────────────────

    @property
    def tools(self) -> list[tuple[Any, list[str] | None]]:
        return list(self._tools)

    @property
    def tool_instances(self) -> list[Any]:
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

    @property
    def skills(self) -> list[SkillDecl]:
        return list(self._skills)

    @property
    def hooks(self) -> list[HookRegistration]:
        return list(self._hooks)

    @property
    def cron_jobs(self) -> list[CronDecl]:
        return list(self._cron_jobs)


__all__ = [
    "CliDescriptor",
    "CommandDecl",
    "PluginAgentApi",
    "PluginApi",
    "PluginLifecycleApi",
    "PluginRunContextApi",
    "PluginSessionApi",
]
