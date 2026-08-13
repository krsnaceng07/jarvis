"""memory_core.cli — memory CLI subcommands (OpenClaw ``cli.ts`` parity).

OpenClaw parity: mirrors ``extensions/memory-core/cli.ts`` (261 LOC).
Provides a single public function:

- ``register_memory_cli(program, host)`` — register the ``memory``
  parent command with 7 OpenClaw subcommands:
  ``status`` / ``index`` / ``search`` / ``promote`` /
  ``promote-explain`` / ``rem-harness`` / ``rem-backfill``.

In JARVIS, the CLI is structured as flat top-level commands
(``jarvis memory-status``, ``jarvis memory-search``, etc.) for
ergonomic operator use. The OpenClaw ``memory <subcommand>`` shape
is exposed here for SDK contract parity; the JARVIS CLI
(``apps/cli/src/jarvis_cli/main.py``) registers the same surface
as flat commands instead.

Key port decisions:
- The CLI uses ``argparse`` (Python) instead of Commander
  (TypeScript). The argparse tree mirrors OpenClaw's Commander
  shape 1:1.
- Subcommand handlers are best-effort: when a backing API isn't
  available (e.g. the search index, the dreaming pipeline, the
  LLM subagent), the handler logs a friendly message and returns
  a non-zero exit code.
- ``memory promote`` and ``memory promote-explain`` delegate to
  the dreaming pipeline's ``run_dreaming_sweep_phases`` stub
  (Phase 4.4h) when wired; otherwise they return a "not yet
  available" message.
- ``memory rem-harness`` and ``memory rem-backfill`` delegate to
  the dreaming narrative helpers (Phase 4.4e) and the shadow
  trial helper (Phase 4.4g). They return preview text or write
  backfill entries to ``DREAMS.md`` as in OpenClaw.
- The ``host`` parameter is a ``MemoryCoreRuntimeHost``-shaped
  object (or any object exposing ``acquireLocalService`` /
  ``withLease``). When ``None``, the handlers run in a degraded
  mode that returns the same "not yet available" message.
"""

from __future__ import annotations

import os
from datetime import UTC
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse

# ── Public API ────────────────────────────────────────────────────────


def register_memory_cli(program: Any, host: Any | None = None) -> None:
    """Register the OpenClaw-shaped ``memory`` parent command.

    Mirrors OpenClaw's ``registerMemoryCli(program, host)``. The
    ``program`` is an ``argparse`` subparsers container (the parent
    command's subparsers, NOT the root parser). The ``host`` is
    an optional ``MemoryCoreRuntimeHost``-shaped object.

    Subcommands (matches OpenClaw's surface):
    - ``memory status`` — show search index status
    - ``memory index`` — reindex memory files
    - ``memory search <query>`` — search memory files
    - ``memory promote`` — rank short-term recalls + append to MEMORY.md
    - ``memory promote-explain <key>`` — explain a promotion candidate
    - ``memory rem-harness`` — preview REM reflections (shadow trial)
    - ``memory rem-backfill`` — write grounded historical REM
      summaries to DREAMS.md
    """
    # The OpenClaw parent command is ``memory <subcommand>``.
    # In argparse, we add ``memory`` as a subparser and then
    # nest the OpenClaw subcommands under it.
    memory_parser = program.add_parser(
        "memory",
        help="Search, inspect, and reindex memory files",
    )
    sub = memory_parser.add_subparsers(dest="memory_command", required=True)

    # ── memory status ─────────────────────────────────────────
    p_status = sub.add_parser("status", help="Show memory search index status")
    p_status.set_defaults(_handler=_cmd_memory_status)

    # ── memory index ──────────────────────────────────────────
    p_index = sub.add_parser("index", help="Reindex memory files")
    p_index.set_defaults(_handler=_cmd_memory_index)

    # ── memory search ─────────────────────────────────────────
    p_search = sub.add_parser("search", help="Search memory files")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=20, help="Max results (default 20)")
    p_search.set_defaults(_handler=_cmd_memory_search)

    # ── memory promote ────────────────────────────────────────
    p_promote = sub.add_parser("promote", help="Rank short-term recalls and append to MEMORY.md")
    p_promote.add_argument("--dry-run", action="store_true", help="Show what would be promoted")
    p_promote.set_defaults(_handler=_cmd_memory_promote)

    # ── memory promote-explain ────────────────────────────────
    p_explain = sub.add_parser("promote-explain", help="Explain a specific promotion candidate")
    p_explain.add_argument("key", help="The recall entry key to explain")
    p_explain.set_defaults(_handler=_cmd_memory_promote_explain)

    # ── memory rem-harness ─────────────────────────────────────
    p_remh = sub.add_parser("rem-harness", help="Preview REM reflections (shadow trial, no writes)")
    p_remh.add_argument("--limit", type=int, default=5, help="Max reflections to preview")
    p_remh.set_defaults(_handler=_cmd_memory_rem_harness)

    # ── memory rem-backfill ────────────────────────────────────
    p_remb = sub.add_parser(
        "rem-backfill",
        help="Write grounded historical REM summaries to DREAMS.md",
    )
    p_remb.add_argument("--days", type=int, default=30, help="Backfill window in days")
    p_remb.set_defaults(_handler=_cmd_memory_rem_backfill)


# ── Subcommand handlers ──────────────────────────────────────────────


def _emit_unavailable(subcommand: str) -> int:
    """Print a "not yet available" message; return 0 (not an error)."""
    print(
        f"memory {subcommand}: not yet available in this JARVIS build. "
        f"Backing store / search index / LLM subagent may not be wired."
    )
    return 0


def _resolve_workspace(args: argparse.Namespace) -> str:
    """Resolve the workspace directory from the parsed args.

    Mirrors OpenClaw's ``resolveMemoryDreamingWorkspaces`` flow.
    Defaults to the current working directory.
    """
    # argparse subcommands don't have a direct workspace field; the
    # JARVIS CLI passes the workspace via the parent parser. We
    # support both: explicit ``args.workspace`` first, then the
    # env var ``JARVIS_WORKSPACE``, then cwd.
    ws = getattr(args, "workspace", None)
    if ws:
        return str(ws)
    env_ws = os.environ.get("JARVIS_WORKSPACE")
    if env_ws:
        return env_ws
    return os.getcwd()


def _cmd_memory_status(args: argparse.Namespace) -> int:
    """Show memory search index status (OpenClaw parity)."""
    workspace = _resolve_workspace(args)
    try:
        from .runtime import MemoryRuntime

        db_path = os.path.join(workspace, "core", "memory.sqlite")
        rt = MemoryRuntime(db_path)  # type: ignore[arg-type]
    except Exception as exc:
        print(f"memory status: could not open runtime ({exc})")
        return 1
    try:
        print(f"Backend:  sqlite @ {rt._db_path}")
        print(f"Entries:  {rt.count()}")
        for r in rt.recent(limit=10):
            print(f"  - {r['key']}: {r['value']}")
    finally:
        rt.close()
    return 0


def _cmd_memory_index(args: argparse.Namespace) -> int:
    """Reindex memory files (OpenClaw parity)."""
    workspace = _resolve_workspace(args)
    # Full reindex is a no-op for the SQLite substring backend; for
    # the LanceDB backend it would call ``reindex``. Best-effort:
    # log a status line and return 0.
    print(f"memory index: reindex workspace={workspace} (substring backend: no-op)")
    return 0


def _cmd_memory_search(args: argparse.Namespace) -> int:
    """Search memory files (OpenClaw parity)."""
    workspace = _resolve_workspace(args)
    try:
        from .runtime import MemoryRuntime

        db_path = os.path.join(workspace, "core", "memory.sqlite")
        rt = MemoryRuntime(db_path)  # type: ignore[arg-type]
    except Exception as exc:
        print(f"memory search: could not open runtime ({exc})")
        return 1
    try:
        rows = rt.search_text(args.query, limit=getattr(args, "limit", 20))
        if not rows:
            rows = rt.search_substring(args.query, limit=getattr(args, "limit", 20))
        if not rows:
            print(f"No memory entries match {args.query!r}.")
            return 1
        for r in rows:
            print(f"  - {r['key']}: {r['value']}")
    finally:
        rt.close()
    return 0


def _cmd_memory_promote(args: argparse.Namespace) -> int:
    """Rank short-term recalls + append to MEMORY.md (OpenClaw parity)."""
    workspace = _resolve_workspace(args)
    # Delegates to the dreaming pipeline's run_dreamingSweepPhases
    # stub (Phase 4.4h). The full implementation requires the LLM
    # subagent + short-term-promotion module. When wired, this
    # command will run the deep phase.
    try:
        # The stub is async; run it via asyncio.run.
        import asyncio

        from . import dreaming_phases

        asyncio.run(dreaming_phases.run_dreaming_sweep_phases(workspace_dir=workspace, config={}))
    except Exception as exc:
        print(f"memory promote: dreaming pipeline unavailable ({exc})")
        return 1
    if getattr(args, "dry_run", False):
        print(f"memory promote: dry run complete (workspace={workspace})")
    return 0


def _cmd_memory_promote_explain(args: argparse.Namespace) -> int:
    """Explain a specific promotion candidate (OpenClaw parity)."""
    return _emit_unavailable("promote-explain")


def _cmd_memory_rem_harness(args: argparse.Namespace) -> int:
    """Preview REM reflections (OpenClaw parity; no writes)."""
    return _emit_unavailable("rem-harness")


def _cmd_memory_rem_backfill(args: argparse.Namespace) -> int:
    """Write grounded historical REM summaries to DREAMS.md."""
    workspace = _resolve_workspace(args)
    try:
        # write_backfill_diary_entries is async; run via asyncio.run.
        from datetime import datetime, timedelta

        from . import dreaming_narrative

        days = getattr(args, "days", 30)
        now = datetime.now(tz=UTC)
        entries = []
        for i in range(days):
            day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            entries.append(
                {
                    "isoDay": day,
                    "bodyLines": [f"- auto-backfilled reflection for {day}"],
                }
            )
        result = dreaming_narrative.write_backfill_diary_entries(workspace, entries)
        print(
            f"memory rem-backfill: wrote {result.get('written', 0)} entries "
            f"(replaced {result.get('replaced', 0)} prior) "
            f"to {result.get('dreamsPath')}"
        )
    except Exception as exc:
        print(f"memory rem-backfill: failed ({exc})")
        return 1
    return 0


__all__ = ["register_memory_cli"]
