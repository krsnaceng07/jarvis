"""jarvis CLI — main entry. Mirrors OpenClaw's ``openclaw`` command tree.

Phase 2. The CLI is a thin wrapper over the same modules the
``apps/desktop`` host uses. It loads plugins (via the same
``_load_plugins()`` machinery the desktop uses, but a slimmed
CLI-only loader), then dispatches subcommands to the
appropriate module.

Why a separate CLI loader? Because the desktop host has a
PyQt6 UI to wire (slash commands, hooks, cron runner) and the
CLI doesn't. We share the SDK + extensions; the wiring is what
differs.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any

# ── Plugin discovery (CLI-slim variant) ───────────────────────────


def _load_cli_plugins(workspace: Path) -> dict[str, Any]:
    """Discover extensions and call their ``entry.register(api)``.

    Returns a dict of ``name -> registered collections``. The CLI
    only consumes the bits it needs (tools, doctor contracts, etc.).
    """
    from jarvis_sdk import (
        PluginApi,
        PluginContext,
    )

    # Add the workspace root to sys.path so ``import extensions.X``
    # and ``import jarvis.*`` work regardless of where the CLI was
    # invoked from. This mirrors the desktop host's bootstrap path.
    workspace_str = str(workspace)
    if workspace_str not in sys.path:
        sys.path.insert(0, workspace_str)

    extensions_dir = workspace / "extensions"
    if not extensions_dir.exists():
        return _empty_collections()

    ctx_template = lambda ext: PluginContext(  # noqa: E731
        plugin_id=ext,
        plugin_kind="tool",
        data_dir=workspace / ".jarvis" / "extensions" / ext,
        workspace=workspace,
    )

    out = _empty_collections()
    for manifest_path in sorted(extensions_dir.glob("*/openclaw.plugin.json")):
        ext_name = manifest_path.parent.name
        try:
            module = importlib.import_module(f"extensions.{ext_name}")
            entry = module.entry
        except (ImportError, AttributeError) as e:
            print(f"[WARN] could not load {ext_name}: {e}", file=sys.stderr)
            continue
        api = PluginApi(ctx_template(ext_name))
        try:
            entry.register(api)
        except Exception as e:
            print(f"[WARN] {ext_name}.register() failed: {e}", file=sys.stderr)
            continue
        out["tool_decls"].extend(api.tool_instances)
        out["commands"].extend(api.commands)
        out["skills"].extend(api.skills)
        out["hooks"].extend(api.hooks)
        out["cron_jobs"].extend(api.cron_jobs)
        out["doctor_contracts"].extend(api.doctor_contracts)
    return out


def _empty_collections() -> dict[str, list]:
    return {
        "tool_decls": [],
        "commands": [],
        "skills": [],
        "hooks": [],
        "cron_jobs": [],
        "doctor_contracts": [],
    }


# ── Subcommand handlers ──────────────────────────────────────────


def _cmd_tools_list(args: argparse.Namespace, plugins: dict[str, Any]) -> int:
    print("Registered tools:")
    for inst in plugins["tool_decls"]:
        for tool in getattr(inst, "tools", []):
            print(f"  - {tool.name}  ({type(inst).__name__})")
    return 0


def _cmd_skills_list(args: argparse.Namespace, workspace: Path) -> int:
    from jarvis.skills import discover_skills

    print("Loaded skills:")
    for s in discover_skills(workspace / "skills"):
        print(f"  - {s.name}: {s.description}")
    return 0


def _cmd_hooks_list(args: argparse.Namespace, plugins: dict[str, Any]) -> int:
    print("Registered hooks:")
    if not plugins["hooks"]:
        print("  (none)")
        return 0
    for h in plugins["hooks"]:
        print(f"  - {h.name}  (priority={h.priority})  {h.handler}")
    return 0


def _cmd_doctor(args: argparse.Namespace, plugins: dict[str, Any], workspace: Path) -> int:
    from jarvis.bootstrap import seed_workspace
    from jarvis.doctor import DoctorRunner

    # Bootstrap first (idempotent) so doctor sees a fully-configured
    # workspace. This matches OpenClaw's "doctor runs after bootstrap".
    seed_workspace(workspace)

    runner = DoctorRunner()
    runner.add_raws(plugins["doctor_contracts"])
    if args.contract_id:
        report = runner.run_one(args.contract_id, workspace)
    else:
        report = runner.run_all(workspace)
    print(report.to_text())
    return 0 if not report.contract_errors else 1


def _cmd_memory_status(args: argparse.Namespace, workspace: Path) -> int:
    from extensions.memory_core.runtime import MemoryRuntime

    rt = MemoryRuntime(workspace / "core" / "memory.sqlite")
    try:
        print(f"Backend:  sqlite @ {rt._db_path}")
        print(f"Entries:  {rt.count()}")
        for r in rt.recent(limit=10):
            print(f"  - {r['key']}: {r['value']}")
    finally:
        rt.close()
    return 0


def _cmd_memory_search(args: argparse.Namespace, workspace: Path) -> int:
    from extensions.memory_core.runtime import MemoryRuntime

    rt = MemoryRuntime(workspace / "core" / "memory.sqlite")
    try:
        rows = rt.search_substring(args.query, limit=20)
        if not rows:
            print(f"No memory entries match {args.query!r}.")
            return 1
        for r in rows:
            print(f"  - {r['key']}: {r['value']}")
    finally:
        rt.close()
    return 0


def _cmd_memory_get(args: argparse.Namespace, workspace: Path) -> int:
    from extensions.memory_core.runtime import MemoryRuntime

    rt = MemoryRuntime(workspace / "core" / "memory.sqlite")
    try:
        value = rt.get(args.key)
        if value is None:
            print(f"No memory entry with key {args.key!r}.")
            return 1
        print(f"{args.key}: {value}")
    finally:
        rt.close()
    return 0


def _cmd_cron_list(args: argparse.Namespace, workspace: Path) -> int:
    from extensions.cron.runtime import CronTable

    table = CronTable(workspace / "core" / "cron.json")
    rows = table.list()
    if not rows:
        print("No cron jobs scheduled.")
        return 0
    print("Registered cron jobs:")
    for r in rows:
        print(
            f"  - {r['id']}: schedule={r['schedule']!r} enabled={r['enabled']} ({r['description']})"
        )
    return 0


def _cmd_config_show(args: argparse.Namespace, workspace: Path) -> int:
    cfg_path = workspace / "config" / "jarvis.json"
    if not cfg_path.exists():
        print(f"No config found at {cfg_path}. Run 'jarvis bootstrap' first.")
        return 1
    print(cfg_path.read_text(encoding="utf-8"))
    return 0


def _cmd_bootstrap(args: argparse.Namespace, workspace: Path) -> int:
    from jarvis.bootstrap import seed_workspace

    result = seed_workspace(workspace)
    print(f"Seeded: {len(result.seeded)}")
    for p in result.seeded:
        print(f"  + {p}")
    print(f"Skipped: {len(result.skipped)}")
    for p in result.skipped:
        print(f"  = {p}")
    return 0


# ── argparse setup ───────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jarvis",
        description=(
            "JARVIS headless CLI — mirrors OpenClaw's `openclaw` command tree. " "Phase 2."
        ),
    )
    p.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Path to the JARVIS workspace (default: cwd).",
    )
    sub = p.add_subparsers(dest="command", required=True, metavar="<subcommand>")

    sub.add_parser("tools", help="Tool commands.").add_subparsers(dest="subcommand", required=True)
    sub.choices["tools"].add_parser("list", help="List every registered tool.")

    skills_p = sub.add_parser("skills", help="Skill commands.")
    skills_p.add_subparsers(dest="subcommand", required=True)
    skills_p.choices["list"] = skills_p.choices["subcommand"]  # type: ignore
    sub.choices["skills"] = sub.choices["skills"]  # type: ignore

    sub.add_parser("hooks", help="Hook commands.").add_subparsers(dest="subcommand", required=True)

    doctor_p = sub.add_parser("doctor", help="Run doctor contracts.")
    doctor_p.add_argument(
        "contract_id",
        nargs="?",
        default=None,
        help="Optional contract id (default: run all).",
    )

    memory_p = sub.add_parser("memory", help="Memory commands.")
    memory_sub = memory_p.add_subparsers(dest="subcommand", required=True)
    memory_sub.add_parser("status", help="Show memory store stats.")
    search_p = memory_sub.add_parser("search", help="Search memory.")
    search_p.add_argument("query", help="Substring to search for.")
    get_p = memory_sub.add_parser("get", help="Read a memory entry by key.")
    get_p.add_argument("key", help="Memory key.")

    cron_p = sub.add_parser("cron", help="Cron commands.")
    cron_sub = cron_p.add_subparsers(dest="subcommand", required=True)
    cron_sub.add_parser("list", help="List registered cron jobs.")

    sub.add_parser("config", help="Config commands.").add_subparsers(
        dest="subcommand", required=True
    )
    sub.add_parser("bootstrap", help="Re-seed workspace files.")

    return p


# Phase 2 hack: argparse sub-subparsers are messy; use a simpler layout
# where each top-level command has its own subcommand list. The above
# tree is overly complex; simplify to flat command names.


def _build_parser_v2() -> argparse.ArgumentParser:
    """Simpler parser: each top-level command is a verb."""
    p = argparse.ArgumentParser(prog="jarvis", description="JARVIS CLI (Phase 2).")
    p.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="JARVIS workspace root (default: cwd).",
    )
    sp = p.add_subparsers(dest="command", required=True, metavar="<command>")

    sp.add_parser("tools-list", help="List every registered tool.")
    sp.add_parser("skills-list", help="List every loaded skill.")
    sp.add_parser("hooks-list", help="List every registered hook.")

    doc = sp.add_parser("doctor", help="Run doctor contracts.")
    doc.add_argument("contract_id", nargs="?", default=None)

    sp.add_parser("memory-status", help="Memory store stats.")
    sr = sp.add_parser("memory-search", help="Search memory.")
    sr.add_argument("query")
    gp = sp.add_parser("memory-get", help="Read memory by key.")
    gp.add_argument("key")

    sp.add_parser("cron-list", help="List cron jobs.")
    sp.add_parser("config-show", help="Print config/jarvis.json.")
    sp.add_parser("bootstrap", help="Re-seed workspace files.")
    return p


# ── main ──────────────────────────────────────────────────────────


# ruff: noqa: PLR0911
# The CLI main() has 11 returns — one per subcommand. Consolidating
# into a dispatch table would lose the per-command error handling
# (memory-status can raise, doctor returns 0/1, etc.). Each return
# is a clear, distinct branch.


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser_v2()
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()

    # Add workspace to sys.path so ``import extensions.X`` and
    # ``import jarvis.*`` work from any cwd. The desktop host gets
    # the workspace via its cwd; the CLI is a real binary and
    # may be invoked from anywhere.
    ws_str = str(workspace)
    if ws_str not in sys.path:
        sys.path.insert(0, ws_str)

    # Subcommands that need plugin discovery.
    plugin_cmds = {
        "tools-list",
        "hooks-list",
        "doctor",
    }
    plugins: dict[str, Any] = _empty_collections()
    if args.command in plugin_cmds:
        plugins = _load_cli_plugins(workspace)

    if args.command == "tools-list":
        return _cmd_tools_list(args, plugins)
    if args.command == "skills-list":
        return _cmd_skills_list(args, workspace)
    if args.command == "hooks-list":
        return _cmd_hooks_list(args, plugins)
    if args.command == "doctor":
        return _cmd_doctor(args, plugins, workspace)
    if args.command == "memory-status":
        return _cmd_memory_status(args, workspace)
    if args.command == "memory-search":
        return _cmd_memory_search(args, workspace)
    if args.command == "memory-get":
        return _cmd_memory_get(args, workspace)
    if args.command == "cron-list":
        return _cmd_cron_list(args, workspace)
    if args.command == "config-show":
        return _cmd_config_show(args, workspace)
    if args.command == "bootstrap":
        return _cmd_bootstrap(args, workspace)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
