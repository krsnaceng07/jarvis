"""memory_core — JARVIS memory extension (Phase 4 OpenClaw parity).

Mirrors OpenClaw's ``extensions/memory-core/`` plugin (97
source files in the source; we ship the Python port as a
focused subset that meets the SDK contract).

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
  - **Slash command:** ``/memory list|count|search``.
  - **Doctor contract:** migrate legacy JARVIS memory formats.

Phase 4.0 ships the SQLite fallback backend (Phase 2's
``MemoryRuntime``). LanceDB + semantic search is a Phase 4.1+
extension (``extensions/memory_lancedb``); both plug into the
shared ``MemorySearchManager`` interface from the SDK.

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


def _register(api: PluginApi) -> None:
    """Register the memory plugin's surface with the host's PluginApi."""
    # Tools
    api.register_tool(
        MemoryCorePlugin(),
        names=["memory_search", "memory_get"],
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
        "File-backed memory tools (memory_search, memory_get), slash command, "
        "and the host's memory prompt section. Phase 4 OpenClaw parity "
        "with envelope-scrubbing + memory-trigger capture gating."
    ),
    register=_register,
    version="0.2.0",
    activation="on_startup",
    permissions=["fs:read:core", "fs:write:core"],
)
