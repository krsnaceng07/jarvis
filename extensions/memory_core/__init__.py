"""memory_core — JARVIS memory extension (Phase 2).

Mirrors OpenClaw's ``extensions/memory-core/`` plugin. Provides:

  - **Tools:** ``memory_search`` (semantic) + ``memory_get`` (exact).
  - **Memory capability:** registered via ``api.register_memory_capability``
    with ``prompt_builder`` + ``flush_plan_resolver`` + ``runtime``.
  - **Slash command:** ``/memory list``.
  - **Doctor contract:** ``memory_core.legacy_jarvis`` (migrate the
    legacy ``memory/memory.json`` file to the new SQLite backend).

The default backend is SQLite (Phase 2 ships stdlib-only). A
LanceDB backend is a Phase 2.5+ extension.
"""

from __future__ import annotations

from jarvis_sdk import (
    PluginApi,
    PluginCommandContext,
    PluginCommandResult,
    define_plugin_entry,
)

from . import doctor as doctor_module, prompt_section
from .plugin import MemoryCorePlugin


def _memory_command_handler(ctx: PluginCommandContext) -> PluginCommandResult:
    """Slash command handler for ``/memory [list|search <query>|count]``.

    Phase 2 keeps this simple: list entries by recency, or run a
    substring search. The richer query language lands in Phase 2.5
    once we have LanceDB-backed semantic search.
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


def _register(api: PluginApi) -> None:
    """Register the memory plugin's surface with the host's PluginApi."""
    # Tools
    api.register_tool(
        MemoryCorePlugin(),
        names=["memory_search", "memory_get"],
    )

    # Memory capability (single-active-slot)
    api.register_memory_capability(
        {
            "prompt_builder": prompt_section.build,
            "flush_plan_resolver": prompt_section.flush_plan,
            "runtime": {
                "name": "memory_core.sqlite",
                "get_search_manager": None,  # Phase 2 ships substring search only
                "close_all": None,
            },
        }
    )

    # Slash command
    api.register_command(
        {
            "name": "memory",
            "description": "List, search, or count memory entries.",
            "accepts_args": True,
            "expose_sender_is_owner": True,
            "handler": _memory_command_handler,
        }
    )

    # Doctor contract — migrate legacy memory.json
    api.register_doctor_contract(
        {
            "id": "memory_core.legacy_jarvis",
            "version": 1,
            "detect_label": "Legacy memory.json (pre-Phase-2 format)",
            "detect_path": "memory/memory.json",
            "detect": doctor_module.detect_legacy,
            "apply": None,  # Phase 2.5
        }
    )


# ── Plugin entry (mirrors OpenClaw's `definePluginEntry`) ───────────
entry = define_plugin_entry(
    id="memory_core",
    kind="memory",
    name="Memory (Core)",
    description=(
        "File-backed memory tools (memory_search, memory_get), slash command, "
        "and the host's memory prompt section."
    ),
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["fs:read:core", "fs:write:core"],
)
