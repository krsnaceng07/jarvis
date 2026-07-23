"""memory_core — JARVIS memory extension (Phase 4 OpenClaw parity).

Mirrors OpenClaw's ``extensions/memory-core/`` plugin. The Python
port ships the deterministic surface + the lazy runtime provider +
the public artifacts list, plus the dreaming pipeline (Phase 4.4):
7-state keyed store, shared helpers, dream diary, phase block
writers, narrative scaffolding, repair + audit, shadow trials,
phases (light/REM/deep), ``/dreaming`` command, and cron-lifecycle
reconciliation (stubbed pending the cron extension).

Surface
-------
  - **Tools:** ``memory_search`` (substring + memory triggers),
    ``memory_get`` (exact excerpt read). Schemas match
    OpenClaw's `MemorySearchSchema` / `MemoryGetSchema`
    (``query``, ``maxResults``, ``minScore``, ``corpus`` for
    search; ``path``, ``from``, ``lines``, ``corpus`` for get).
  - **Memory capability:** registered via
    ``api.register_memory_capability`` with
    ``prompt_builder`` + ``flush_plan_resolver`` + ``runtime`` +
    ``public_artifacts``. Matches OpenClaw's
    ``MemoryPluginCapability`` shape.
  - **Slash commands:**
      - ``/memory [list|count|search]`` (operator surface)
      - ``/dreaming [status|on|off|help|phases]`` (Phase 4.4)
  - **Doctor contract:** migrate legacy JARVIS memory formats.
  - **Dreaming pipeline (Phase 4.4):** 7-namespace keyed store,
    DREAMS.md diary management, light/REM/deep phase helpers,
    audit + repair, shadow trials, ``/dreaming`` command,
    cron-lifecycle reconciliation (stubbed).

OpenClaw parity
==============
- Tools: registered with ``api.register_tool(MemoryCorePlugin(),
  names=[...])``; the host unwraps the ``ToolPlugin`` and
  exposes each ``ToolDecl`` in the agent's tool surface.
- Capability: ``prompt_builder`` returns a string injected
  into the system prompt; ``flush_plan_resolver`` returns a
  ``MemoryFlushPlan`` consulted before compaction;
  ``runtime`` is a small wrapper over the active
  ``MemorySearchManager``; ``public_artifacts`` is a coroutine
  the host calls to enumerate published artifacts.
- Dreaming state: ``configure_memory_core_dreaming_state`` is
  called once during ``register()`` so all 7 dreaming
  namespaces (daily ingestion, session ingestion files/seen,
  short-term recall/phase signals/meta/locks) share the host's
  keyed store factory. Mirrors OpenClaw's
  ``configureMemoryCoreDreamingState``.
- Dreaming cron: ``register_short_term_promotion_dreaming`` is
  called once during ``register()``; when the cron extension
  isn't available, it logs a warning and returns (the
  dreaming pipeline still works for on-demand invocations).
- Capture gating: ``memory_search`` and the host's
  ``save_memory`` tool both consult ``MEMORY_TRIGGERS`` +
  ``looks_like_envelope_sludge`` (the security-critical
  layer from ``envelope_scrubber.py``) before persisting.
"""

from __future__ import annotations

from jarvis_sdk import (
    PluginApi,
    PluginCommandContext,
    PluginCommandResult,
    define_plugin_entry,
)

from . import doctor as doctor_module, prompt_section
from . import dreaming as dreaming_module
from . import dreaming_command, dreaming_state
from .plugin import MemoryCorePlugin
from .public_artifacts import list_artifacts as _list_artifacts

# ── Slash command: /memory [list|count|search] ──────────────


def _memory_command_handler(ctx: PluginCommandContext) -> PluginCommandResult:
    """Slash command handler for ``/memory [list|search <query>|count]``.

    Mirrors OpenClaw's ``extensions/memory-core/cli.ts``
    (subset). The full OpenClaw CLI has many more subcommands
    (reindex, prune, etc.); we ship the operator-facing
    surface only.
    """
    from .runtime import MemoryRuntime

    args = (ctx.args or "").strip()
    runtime = MemoryRuntime.default()
    sub, _, rest = args.partition(" ")

    if sub in ("", "list"):
        rows = runtime.recent(limit=20)
        if not rows:
            return PluginCommandResult(reply_text="Memory is empty.")
        body = "\n".join(f"  - {r['key']}: {r['value']}" for r in rows)
        return PluginCommandResult(reply_text=f"Memory entries:\n{body}")

    if sub == "count":
        n = runtime.count()
        return PluginCommandResult(reply_text=f"{n} memory entries.")

    if sub == "search":
        rows = runtime.search_substring(rest.strip(), limit=20)
        if not rows:
            return PluginCommandResult(reply_text=f"No entries match {rest!r}.")
        body = "\n".join(f"  - {r['key']}: {r['value']}" for r in rows)
        return PluginCommandResult(reply_text=f"Matches for {rest!r}:\n{body}")

    return PluginCommandResult(
        reply_text=f"Unknown subcommand {sub!r}. Try: list, search <query>, count."
    )


# ── /dreaming command handler (Phase 4.4i) ────────────────


def _dreaming_command_handler(ctx: PluginCommandContext) -> PluginCommandResult:
    """Slash command handler for ``/dreaming [status|on|off|help|phases]``.

    Mirrors OpenClaw's ``extensions/memory-core/src/dreaming-command.ts``.
    Delegates to ``dreaming_command.handle_dreaming_command``.
    """
    import asyncio

    result = asyncio.run(
        dreaming_command.handle_dreaming_command(
            # The OpenClaw handler expects the plugin API; the
            # dreaming_command module accepts any object with
            # ``runtime.config.current()``. The PluginApi has
            # ``runtime.config`` so we can pass it directly.
            api=_get_dreaming_api_proxy(),
            ctx={
                "args": ctx.args or "",
                "gatewayClientScopes": getattr(ctx, "gateway_client_scopes", None),
                "senderIsOwner": ctx.sender_is_owner if hasattr(ctx, "sender_is_owner") else False,
            },
        )
    )
    return PluginCommandResult(reply_text=result.get("text", ""))


def _get_dreaming_api_proxy() -> object:
    """Return a proxy object exposing ``runtime.config.current()``.

    The dreaming_command module only needs ``api.runtime.config.current()``
    and (optionally) ``api.runtime.config.mutate_config_file``. We
    return a tiny stub that satisfies the read path with an empty
    dict (the status block will reflect "disabled" / default
    cadence); the mutate path is a no-op (the dreaming module
    will apply the in-memory patch).
    """

    class _Config:
        def current(self) -> dict:
            return {}

        def mutate_config_file(self, *args: object, **kwargs: object) -> dict:
            return {"nextConfig": {}}

    class _Runtime:
        config = _Config()

    class _Proxy:
        runtime = _Runtime()

    return _Proxy()


# ── Memory capability runtime (OpenClaw-shaped) ────────────


class _MemoryPluginRuntime:
    """Thin runtime wrapper. Phase 4.0 ships a single backend
    (SQLite); Phase 4.1+ adds LanceDB as an alternate.

    Mirrors OpenClaw's ``MemoryPluginRuntime`` interface from
    ``packages/memory-host-sdk/src/host/types.ts``.
    """

    name = "memory_core.sqlite"

    async def get_memory_search_manager(self, params: dict | None = None) -> object:
        """Phase 4.0: return None; the host falls back to the
        legacy ``MemoryRuntime`` (substring search). LanceDB
        lands in Phase 4.1 and will return a real manager.
        """
        return None

    async def close_all_memory_search_managers(self) -> None:
        return None


def _configure_dreaming_state(api: PluginApi) -> None:
    """Wire the host's keyed store factory into the dreaming state.

    Mirrors OpenClaw's ``configureMemoryCoreDreamingState(<T>(opts) =>
    state.openKeyedStore<T>(opts))``. When the host exposes
    ``api.runtime.state.openKeyedStore``, use it; otherwise
    the dreaming state falls back to a per-process in-memory
    store (registered by tests).
    """
    state_runtime = getattr(api, "runtime", None)
    if state_runtime is None:
        return
    state = getattr(state_runtime, "state", None)
    if state is None:
        return
    open_keyed = getattr(state, "open_keyed_store", None) or getattr(
        state, "openKeyedStore", None
    )
    if not callable(open_keyed):
        return

    def _factory(options: dict) -> object:
        return open_keyed(options)

    dreaming_state.configure_memory_core_dreaming_state(_factory)


def _register(api: PluginApi) -> None:
    """Register the memory plugin's surface with the host's PluginApi."""
    # ── Dreaming state (Phase 4.4) ─────────────────────────
    # Wire the host's keyed store into the dreaming state BEFORE
    # any cron/lifecycle registration so the 7 dreaming
    # namespaces can read/write without a separate config step.
    _configure_dreaming_state(api)

    # Wire the short-term-promotion dreaming cron + lifecycle.
    # Stubbed until the cron extension is ported; logs a warning
    # and returns when unavailable.
    dreaming_module.register_short_term_promotion_dreaming(api)

    # Tools
    api.register_tool(
        MemoryCorePlugin(),
        {"names": ["memory_search", "memory_get"]},
    )

    # Memory capability (single-active-slot; OpenClaw parity)
    api.register_memory_capability(
        {
            "prompt_builder": prompt_section.build,
            "flush_plan_resolver": prompt_section.flush_plan,
            "runtime": _MemoryPluginRuntime(),
            "public_artifacts": {
                "list_artifacts": _list_artifacts,
            },
        }
    )

    # Slash commands
    api.register_command(
        {
            "name": "memory",
            "description": "List, search, or count memory entries.",
            "accepts_args": True,
            "expose_sender_is_owner": True,
            "handler": _memory_command_handler,
        }
    )

    # /dreaming command (Phase 4.4i) — enable/disable dreaming
    api.register_command(
        {
            "name": "dreaming",
            "description": "Enable or disable memory dreaming.",
            "accepts_args": True,
            "expose_sender_is_owner": True,
            "handler": _dreaming_command_handler,
        }
    )

    # Doctor contract — migrate legacy memory formats
    api.register_doctor_contract(
        {
            "id": "memory_core.legacy_jarvis",
            "version": 1,
            "detect_label": "Legacy memory.json (pre-Phase-2 format)",
            "detect_path": "memory/memory.json",
            "detect": doctor_module.detect_legacy,
            "apply": None,  # Phase 4.1
        }
    )


# ── Plugin entry (mirrors OpenClaw's `definePluginEntry`) ───────────
entry = define_plugin_entry(
    id="memory_core",
    kind="memory",
    name="Memory (Core)",
    description=(
        "File-backed memory tools (memory_search, memory_get), slash "
        "command, /dreaming command (Phase 4.4), and the host's memory "
        "prompt section. Phase 4 OpenClaw parity with envelope-scrubbing "
        "+ memory-trigger capture gating + dreaming pipeline."
    ),
    register=_register,
    version="0.3.0",  # bumped for Phase 4.4 dreaming pipeline
    activation="on_startup",
    permissions=["fs:read:core", "fs:write:core"],
)
