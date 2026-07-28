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

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from .context import PluginContext

from .cli import CliDescriptor  # used at runtime in register_cli()
from .cron import CronDecl  # noqa: TCH001  (used in instance annotations below)
from .hook import HookRegistration

_log = logging.getLogger("jarvis_sdk.api")


def _normalize_plugin_tool_names(names: list[str] | None) -> list[str]:
    """Mirror OpenClaw's ``normalizePluginToolNames``.

    Trims whitespace, drops empty strings, deduplicates while preserving order.
    Does not change case or convert kebab→snake.
    """
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
    """Mirror OpenClaw's ``findUndeclaredPluginToolNames``.

    Returns the tool names that are NOT in the ``declared`` set.
    """
    declared_set = set(declared or ())
    return [n for n in tool_names if n not in declared_set]


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
class PluginRuntimeConfigApi:
    """``api.runtime.config`` — live config + mutator surface.

    Mirrors OpenClaw's ``api.runtime.config`` namespace. The
    host wires each method up; the default implementations
    are no-ops so plugins that only read config still work
    when the host hasn't wired the live mutator yet.
    """

    def current(self) -> Any:
        """Return the most recent config (any mapping) or ``None``."""
        return None

    def mutate_config_file(self, params: dict[str, Any]) -> Any:
        """Atomically rewrite the config file with a draft.

        Mirrors OpenClaw's ``api.runtime.config.mutateConfigFile``.
        ``params`` carries:
        - ``mutate``: callable ``(draft) -> None`` (mutates in place).
        - ``afterWrite``: optional ``{"mode": "auto"}``.

        Returns the new config or ``None`` if the host
        hasn't wired the mutator.
        """
        return None


@dataclass
class PluginRuntimeStateApi:
    """``api.runtime.state`` — host state dir + keyed store surface.

    Mirrors OpenClaw's ``api.runtime.state`` namespace. The
    host wires each method up; the default implementations
    are no-ops so plugins still work when the host hasn't
    wired the state surface yet.
    """

    def resolve_state_dir(self) -> str:
        """Return the host's state dir (e.g. ``~/.jarvis``)."""
        import os
        from pathlib import Path

        env = os.environ.get("JARVIS_DATA_DIR")
        if env:
            return env
        return str(Path.home() / ".jarvis")

    def open_keyed_store(self, params: dict[str, Any]) -> Any:
        """Open a per-namespace keyed store.

        Mirrors OpenClaw's ``api.runtime.state.openKeyedStore``.
        ``params`` carries ``namespace`` (str) and ``maxEntries``
        (int, optional). Returns ``None`` when the host hasn't
        wired a store implementation.
        """
        return None


@dataclass
class PluginAgentSessionApi:
    """``api.runtime.agent.session`` — per-agent session registry.

    Mirrors OpenClaw's ``api.runtime.agent.session`` namespace.
    Phase 4.2 ships ``getSessionEntry`` (harness-skip), plus
    the registry helpers ``listSessionEntries`` and
    ``patchSessionEntry`` used by the recall-flow
    status-line persistence and canonical-session-key
    resolution.
    """

    def get_session_entry(self, params: dict[str, Any]) -> Any:
        """Return the session registry entry or ``None`` if missing.

        Mirrors OpenClaw's
        ``api.runtime.agent.session.getSessionEntry``.
        Recognized params: ``agentId``, ``sessionKey``,
        ``sessionId``, ``readConsistency`` (e.g. ``"latest"``).
        """
        return None

    def list_session_entries(self, params: dict[str, Any]) -> list[tuple[str, Any]]:
        """List the agent's session entries.

        Mirrors OpenClaw's
        ``api.runtime.agent.session.listSessionEntries``.
        Returns a list of ``(sessionKey, entry)`` pairs;
        empty list when the host hasn't wired the registry.
        Recognized params: ``agentId``, ``limit``,
        ``readConsistency`` (e.g. ``"latest"``).
        """
        return []

    def patch_session_entry(self, params: dict[str, Any]) -> Any:
        """Atomically patch a session entry.

        Mirrors OpenClaw's
        ``api.runtime.agent.session.patchSessionEntry``.
        The ``update`` callback receives the existing entry
        and returns the patch to apply. Returns the updated
        entry or ``None`` when the host hasn't wired the
        registry. Recognized params: ``agentId``,
        ``sessionKey``, ``update``, ``preserveActivity``,
        ``skipMaintenance``, ``replaceEntry``,
        ``fallbackEntry``, ``storePath``.
        """
        return None


@dataclass
class PluginAgentApi:
    """``api.runtime.agent`` — per-agent capability surface.

    Mirrors OpenClaw's ``api.runtime.agent`` namespace. The
    default implementations are no-ops so plugins that only
    need a subset still work when the host hasn't wired the
    rest yet.
    """

    resolve_agent_dir: Any = None  # set by host on init
    resolve_agent_workspace_dir: Any = None  # set by host on init
    resolve_cli_backend_dispatch_eligibility: Any = None
    session: PluginAgentSessionApi = field(default_factory=PluginAgentSessionApi)

    def __getattr__(self, item: str) -> Any:
        # Tolerate attribute lookups for properties the host
        # hasn't wired yet.
        return None


@dataclass
class PluginSessionApi:
    """Grouped facade for session-state registrations. Stubs in 1C."""

    state: Any = None  # registerSessionExtension (Phase 2)
    workflow: Any = None  # enqueueNextTurnInjection (Phase 2)
    controls: Any = None  # registerSessionAction (Phase 2)


@dataclass
class PluginRunContextApi:
    """Grouped facade for run-scoped scratch state. Stubs in 1C."""

    def set_run_context(self, patch: dict[str, object]) -> bool:
        return False

    def get_run_context(self, params: dict[str, object]) -> Any:
        return None

    def clear_run_context(self, params: dict[str, object]) -> None:
        return None


@dataclass
class PluginLifecycleApi:
    """Grouped facade for runtime cleanup hooks. Stubs in 1C."""

    def register_runtime_lifecycle(self, lifecycle: dict[str, object]) -> None:
        return None


# ── Main PluginApi ───────────────────────────────────────────────────


@dataclass
class _PluginRuntimeNamespace:
    """Mirror of OpenClaw's ``api.runtime`` nested namespace.

    Holds the three runtime sub-namespaces (config, state,
    agent) and forwards attribute access to the
    ``PluginApi`` instance. The host wires each sub-namespace
    by setting ``self.runtime._config`` etc. after
    construction.
    """

    config: PluginRuntimeConfigApi
    state: PluginRuntimeStateApi
    agent: PluginAgentApi

    def __init__(self, owner: PluginApi) -> None:
        self.config = PluginRuntimeConfigApi()
        self.state = PluginRuntimeStateApi()
        self.agent = PluginAgentApi()
        self._owner = owner

    def __getattr__(self, item: str) -> Any:
        # Tolerate attribute lookups for runtime sub-namespaces
        # the host hasn't wired yet (returns None for forward
        # compatibility — plugins must check for None before
        # calling).
        return None


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
        self._cli_handlers: list[
            tuple[Callable[..., Any], list[CliDescriptor], list[str], list[str]]
        ] = []
        self._memory_capability: dict[str, Any] | None = None
        self._provider: dict[str, Any] | None = None
        self._channel: dict[str, Any] | None = None
        self._doctor_contracts: list[dict[str, Any]] = []
        self._http_handlers: list[dict[str, Any]] = []
        self._skills: list[SkillDecl] = []
        self._hooks: list[HookRegistration] = []
        self._cron_jobs: list[CronDecl] = []
        # Gateway discovery service registrations (Phase 5.15+). Mirrors
        # OpenClaw's ``api.registerGatewayDiscoveryService({...})``. Each
        # plugin can register at most one gateway discovery service
        # (e.g. bonjour); the host wires it to the actual gateway start
        # sequence on the host's chosen platform.
        self._gateway_discovery_service: dict[str, Any] | None = None
        # Plugin manifest (for contracts.tools validation). Populated by the
        # loader via ``set_manifest``; safe default is empty.
        self._manifest: dict[str, Any] = {}

        # ── Grouped facades (mirror OpenClaw) ───────────────────────
        # Top-level grouped facades (Phase 1C).
        self.session = PluginSessionApi()
        self.agent = PluginAgentApi()
        self.run_context = PluginRunContextApi()
        self.lifecycle = PluginLifecycleApi()

        # Nested runtime facade (Phase 4.2). Mirrors OpenClaw's
        # `api.runtime.{config, state, agent}` namespace.
        self.runtime: Any = _PluginRuntimeNamespace(self)

    def set_manifest(self, manifest: dict[str, Any]) -> None:
        """Provide the plugin manifest (used for ``contracts.tools`` validation)."""
        self._manifest = manifest or {}

    def _declared_tool_names(self) -> list[str]:
        """Return the tool names declared in ``contracts.tools`` (manifest)."""
        try:
            contracts = self._manifest.get("contracts") or {}
            return _normalize_plugin_tool_names(contracts.get("tools"))
        except Exception:
            return []

        # ── Grouped facades (mirror OpenClaw) ───────────────────────
        # Top-level grouped facades (Phase 1C).
        self.session = PluginSessionApi()
        self.agent = PluginAgentApi()
        self.run_context = PluginRunContextApi()
        self.lifecycle = PluginLifecycleApi()

        # Nested runtime facade (Phase 4.2). Mirrors OpenClaw's
        # `api.runtime.{config, state, agent}` namespace.
        self.runtime: Any = _PluginRuntimeNamespace(self)

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
        opts: dict[str, Any] | None = None,
    ) -> None:
        """Register a tool. Mirrors OpenClaw's ``registerTool``.

        ``opts`` is a dict matching OpenClaw's ``OpenClawPluginToolOptions``:
          - ``name``: single tool name (str)
          - ``names``: list of tool names
          - ``optional``: whether the tool is optional (bool, default False)

        The contract:
          1. ``name`` and ``names`` get merged into a single normalized
             names list (trimmed, deduplicated — matches OpenClaw's
             ``normalizePluginToolNames``).
          2. If the tool is not a factory (i.e. has its own ``.name``), that
             name is appended to the merged list.
          3. If the plugin manifest declared ``contracts.tools``, all
             registered names must be in that list — otherwise
             ``findUndeclaredPluginToolNames`` rejects the call (matches
             OpenClaw's behavior).
        """
        opts = opts or {}
        declared = self._declared_tool_names()
        merged: list[str] = []
        if isinstance(opts.get("name"), str):
            merged.append(opts["name"])
        if isinstance(opts.get("names"), list):
            merged.extend(opts["names"])
        if not callable(tool) and hasattr(tool, "name"):
            merged.append(tool.name)
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
        descriptors: list[CliDescriptor | dict[str, object]] | None = None,
        parent_path: list[str] | None = None,
        commands: list[str] | None = None,
    ) -> None:
        """Register a CLI subcommand. Mirrors OpenClaw's ``registerCli``.

        The host invokes the stored registrar with a context dict matching
        OpenClaw's ``OpenClawPluginCliContext`` shape::

            {
                "program": argparse.ArgumentParser | subparsers-container,
                "parentPath": list[str],
                "config": object,
                "workspaceDir": str | None,
                "logger": PluginLogger,
            }

        Plugins destructure what they need, e.g.
        ``api.register_cli(({program}) => registerWikiCli(program, ...))``.

        ``descriptors`` advertises the top-level commands for global help.
        ``parent_path`` is a list of nested command segments (default: empty).
        ``commands`` is an explicit list of command roots (otherwise derived
        from the descriptors).
        """
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

    def register_http_handler(self, handler: dict[str, Any] | Any) -> None:
        """Register an HTTP handler for the gateway's admin surface.

        Mirrors OpenClaw's ``api.registerHttpRoute(params)``. Accepts
        a dict with the same keys OpenClaw uses:
          - ``path`` (required)   URL path
          - ``handler`` (required) callable(method, url, body, headers) -> dict
          - ``auth``              ``"gateway"`` (default) or ``"plugin"``
          - ``match``             ``"exact"`` (default) or ``"prefix"``
        """
        if isinstance(handler, dict):
            if "path" not in handler or "handler" not in handler:
                raise ValueError(f"http route missing required keys (path, handler): {handler!r}")
            handler["_owner_id"] = self._ctx.plugin_id
            self._http_handlers.append(handler)
        else:
            # Typed object path (HttpRoute).
            path = getattr(handler, "path", None)
            cb = getattr(handler, "handler", None)
            if not path or not callable(cb):
                raise ValueError(f"http route missing path/handler: {handler!r}")
            self._http_handlers.append(
                {
                    "path": path,
                    "handler": cb,
                    "auth": getattr(handler, "auth", "gateway"),
                    "match": getattr(handler, "match", "exact"),
                    "_owner_id": self._ctx.plugin_id,
                }
            )

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

    def register_gateway_discovery_service(self, service: dict[str, Any]) -> None:
        """Register a gateway discovery service (mDNS / Bonjour / etc.).

        Mirrors OpenClaw's ``api.registerGatewayDiscoveryService``.
        The service is a dict with:
          - ``id`` (required, str): the service id (e.g. ``"bonjour"``)
          - ``advertise`` (required, callable): an async function
            ``async (ctx) -> {stop: Callable}`` that starts the
            discovery. ``ctx`` carries gateway port, TLS fingerprint,
            machine display name, etc.

        Only one gateway discovery service can be registered per
        process (the host picks the one to use). Registering a
        second one raises ``RuntimeError`` (matches OpenClaw's
        behavior of "only one discovery backend active").
        """
        if not isinstance(service, dict):
            raise TypeError(
                f"gateway discovery service must be a dict; got {type(service).__name__}"
            )
        if "id" not in service or not service["id"]:
            raise ValueError("gateway discovery service must have a non-empty 'id'")
        if "advertise" not in service or not callable(service["advertise"]):
            raise ValueError(
                "gateway discovery service must have a callable 'advertise' "
                "(async function taking ctx and returning a stop handle)"
            )
        if self._gateway_discovery_service is not None:
            raise RuntimeError(
                f"Plugin {self._ctx.plugin_id!r} tried to register a gateway "
                f"discovery service but {self._gateway_discovery_service.get('id')!r} "
                f"is already registered. Only one discovery backend is supported."
            )
        service["_owner_id"] = self._ctx.plugin_id
        self._gateway_discovery_service = service

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
    def cli_handlers(
        self,
    ) -> list[tuple[Callable[..., Any], list[CliDescriptor], list[str], list[str]]]:
        """All registered CLI handlers (OpenClaw 4-tuple shape).

        Each entry is ``(register_fn, descriptors, parent_path, commands)``.
        The host invokes ``register_fn`` with the OpenClaw context dict
        ``{program, parentPath, config, workspaceDir, logger}``.
        """
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

    @property
    def gateway_discovery_service(self) -> dict[str, Any] | None:
        """The single registered gateway discovery service, or ``None``."""
        return self._gateway_discovery_service


__all__ = [
    "CliDescriptor",
    "CommandDecl",
    "PluginAgentApi",
    "PluginApi",
    "PluginLifecycleApi",
    "PluginRunContextApi",
    "PluginSessionApi",
]
