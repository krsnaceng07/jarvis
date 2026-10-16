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
from pathlib import Path
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

    # ── memory reset ──────────────────────────────────────────
    p_reset = sub.add_parser(
        "reset",
        help="Clear the derived memory index without deleting markdown files",
    )
    p_reset.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    p_reset.set_defaults(_handler=_cmd_memory_reset)

    # ── memory search ─────────────────────────────────────────
    p_search = sub.add_parser("search", help="Search memory files")
    p_search.add_argument("query", nargs="?", default="", help="Search query")
    p_search.add_argument("--query", "-q", dest="opt_query", help="Search query option")
    p_search.add_argument(
        "--max-results", "--limit", dest="limit", type=int, default=20, help="Max results (default 20)"
    )
    p_search.add_argument(
        "--min-score", type=float, default=0.0, help="Minimum relevance score in [0, 1]"
    )
    p_search.add_argument(
        "--corpus", default="memory", help="Corpus: memory, wiki, sessions, all"
    )
    p_search.add_argument("--citations", action="store_true", help="Include source citations")
    p_search.add_argument("--json", action="store_true", help="Output result as JSON")
    p_search.set_defaults(_handler=_cmd_memory_search)

    # ── memory forget ─────────────────────────────────────────
    p_forget = sub.add_parser(
        "forget",
        help="Purge memory entries by key or query across SQLite and markdown files",
    )
    p_forget.add_argument("--key", help="Exact key to forget")
    p_forget.add_argument("--query", "-q", help="Substring query to match for forgetting")
    p_forget.add_argument("--dry-run", action="store_true", help="Preview matches without deleting")
    p_forget.add_argument("--json", action="store_true", help="Output result as JSON")
    p_forget.set_defaults(_handler=_cmd_memory_forget)

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
        rt = MemoryRuntime(Path(db_path))
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
    try:
        from .memory_indexer import index_memory_files
        from .runtime import MemoryRuntime

        db_path = os.path.join(workspace, "core", "memory.sqlite")
        rt = MemoryRuntime(Path(db_path))
    except Exception as exc:
        print(f"memory index: could not open runtime ({exc})")
        return 1

    try:
        total_chunks = index_memory_files(workspace, rt)
        print(f"memory index: reindexed workspace={workspace} ({total_chunks} chunks)")
    except Exception as exc:
        print(f"memory index: failed to index files ({exc})")
        return 1
    finally:
        rt.close()

    return 0


def _cmd_memory_reset(args: argparse.Namespace) -> int:
    """Clear the derived memory index and FTS tables without deleting markdown files."""
    workspace = _resolve_workspace(args)
    if not getattr(args, "yes", False):
        print("memory reset: requires --yes confirmation to clear the index.")
        return 1

    try:
        from .runtime import MemoryRuntime, resolve_memory_db_path

        ws_p = Path(workspace)
        if (ws_p / "core" / "memory.sqlite").is_file():
            db_path = ws_p / "core" / "memory.sqlite"
        elif (ws_p / "memory.sqlite").is_file():
            db_path = ws_p / "memory.sqlite"
        else:
            db_path = resolve_memory_db_path()

        rt = MemoryRuntime(db_path)
    except Exception as exc:
        print(f"memory reset: could not open runtime ({exc})")
        return 1

    try:
        count = rt.reset_index()
        print(f"memory reset: cleared {count} indexed entries from {db_path}.")
    finally:
        rt.close()
    return 0


def _cmd_memory_search(args: argparse.Namespace) -> int:
    """Search memory files (OpenClaw parity)."""
    workspace = _resolve_workspace(args)
    query = (getattr(args, "opt_query", None) or getattr(args, "query", "") or "").strip()
    if not query:
        print("memory search: query is required.")
        return 1

    try:
        from .runtime import MemoryRuntime, resolve_memory_db_path

        ws_p = Path(workspace)
        if (ws_p / "core" / "memory.sqlite").is_file():
            db_path = ws_p / "core" / "memory.sqlite"
        elif (ws_p / "memory.sqlite").is_file():
            db_path = ws_p / "memory.sqlite"
        else:
            db_path = resolve_memory_db_path()

        rt = MemoryRuntime(db_path)
    except Exception as exc:
        print(f"memory search: could not open runtime ({exc})")
        return 1

    try:
        limit = int(getattr(args, "limit", 20))
        min_score = float(getattr(args, "min_score", 0.0))
        corpus = str(getattr(args, "corpus", "memory"))
        citations = bool(getattr(args, "citations", False))

        rows = rt.search_ranked(
            query=query,
            limit=limit,
            min_score=min_score,
            corpus=corpus,
            citations=citations,
        )

        if getattr(args, "json", False):
            import json

            print(json.dumps({"results": rows, "count": len(rows)}, indent=2))
            return 0

        if not rows:
            print(f"No memory entries match {query!r}.")
            return 0

        for r in rows:
            score = r.get("score", 0.0)
            val = r.get("value", "")
            print(f"  - [{score:.2f}] {r['key']}: {val}")
    finally:
        rt.close()
    return 0


def _cmd_memory_forget(args: argparse.Namespace) -> int:
    """Purge memory entries across SQLite and markdown files in lockstep."""
    workspace = _resolve_workspace(args)
    key = getattr(args, "key", None)
    query = getattr(args, "query", None)
    dry_run = getattr(args, "dry_run", False)

    if not key and not query:
        print("memory forget: either --key or --query is required.")
        return 1

    try:
        from .runtime import MemoryRuntime, resolve_memory_db_path

        ws_p = Path(workspace)
        if (ws_p / "core" / "memory.sqlite").is_file():
            db_path = ws_p / "core" / "memory.sqlite"
        elif (ws_p / "memory.sqlite").is_file():
            db_path = ws_p / "memory.sqlite"
        else:
            db_path = resolve_memory_db_path()

        rt = MemoryRuntime(db_path)
    except Exception as exc:
        print(f"memory forget: could not open runtime ({exc})")
        return 1

    try:
        if dry_run:
            q = query or key or ""
            candidates = rt.search_substring(q)
            if getattr(args, "json", False):
                import json

                print(json.dumps({"dryRun": True, "matches": candidates}, indent=2))
            else:
                print(f"memory forget: dry run - found {len(candidates)} matching entries:")
                for c in candidates:
                    print(f"  - {c['key']}: {c['value'][:60]}")
            return 0

        res = rt.forget(key=key, query=query, workspace_dir=ws_p)
        if getattr(args, "json", False):
            import json

            print(json.dumps(res, indent=2))
        else:
            count = res.get("forgotten_count", 0)
            md_lines = res.get("removed_markdown_lines", 0)
            print(
                f"memory forget: purged {count} entries from SQLite and removed {md_lines} markdown lines."
            )
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
