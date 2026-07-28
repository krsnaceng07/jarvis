"""jarvis CLI — main entry. Mirrors OpenClaw's ``openclaw`` command tree.

Phase 3. The CLI is a thin wrapper over the same modules the
``apps/desktop`` host uses. It loads plugins (via the same
``_load_plugins()`` machinery the desktop uses, but a slimmed
CLI-only loader), then dispatches subcommands to the
appropriate module.

Why a separate CLI loader? Because the desktop host has a
PyQt6 UI to wire (slash commands, hooks, cron runner) and the
CLI doesn't. We share the SDK + extensions; the wiring is what
differs.

Phase 3 subcommands: ``gateway start|status`` (HTTP server on
127.0.0.1:7433), ``telegram setup|status`` (Telegram channel
configuration).
"""

from __future__ import annotations

import argparse
import importlib
import json
import socket
import sys
from pathlib import Path
from typing import Any

# Force stdout/stderr to UTF-8 to support emojis on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

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
    src_str = str(workspace / "src")
    if src_str not in sys.path:
        sys.path.insert(0, src_str)

    extensions_dir = workspace / "extensions"
    if not extensions_dir.exists():
        return _empty_collections()

    def ctx_template(ext: str) -> PluginContext:
        return PluginContext(
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
        # Load the manifest so the PluginApi can validate ``contracts.tools``.
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] could not parse {manifest_path}: {e}", file=sys.stderr)
            manifest = {}
        api = PluginApi(ctx_template(ext_name))
        if hasattr(api, "set_manifest"):
            api.set_manifest(manifest)
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
        out["cli_handlers"].extend(api.cli_handlers)
    return out


def _empty_collections() -> dict[str, list[Any]]:
    return {
        "tool_decls": [],
        "commands": [],
        "skills": [],
        "hooks": [],
        "cron_jobs": [],
        "doctor_contracts": [],
        "cli_handlers": [],
    }


# ── Subcommand handlers ──────────────────────────────────────────


def _cmd_tools_list(args: argparse.Namespace, plugins: dict[str, Any]) -> int:
    print("Registered tools:")
    for inst in plugins["tool_decls"]:
        for tool in getattr(inst, "tools", []):
            print(f"  - {tool.name}  ({type(inst).__name__})")
    return 0


def _cmd_skills_list(args: argparse.Namespace, workspace: Path) -> int:
    from src.skills import discover_skills

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
    from src.bootstrap import seed_workspace
    from src.doctor import DoctorRunner

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
    from src.bootstrap import seed_workspace

    result = seed_workspace(workspace)
    print(f"Seeded: {len(result.seeded)}")
    for p in result.seeded:
        print(f"  + {p}")
    print(f"Skipped: {len(result.skipped)}")
    for p in result.skipped:
        print(f"  = {p}")
    return 0


# ── Phase 3: gateway + telegram subcommands ─────────────────────


def _cmd_gateway_start(args: argparse.Namespace, workspace: Path) -> int:
    """Start the JARVIS gateway (Phase 3)."""
    from src.gateway import DEFAULT_PORT, Gateway, GatewayLockError

    host = args.host or "127.0.0.1"
    port = int(args.port) if args.port else DEFAULT_PORT
    gw = Gateway(host=host, port=port)
    try:
        gw.start()
    except GatewayLockError as e:
        print(f"Error: {e}")
        return 1
    print(f"Gateway started on http://{host}:{port}")
    print(f"Token file: {gw._token_path}")
    return 0


def _cmd_gateway_status(args: argparse.Namespace, workspace: Path) -> int:
    """Show the gateway status (Phase 3)."""
    from src.gateway import DEFAULT_PORT

    port = DEFAULT_PORT
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                print(f"Gateway: RUNNING on 127.0.0.1:{port}")
                return 0
            except OSError:
                print(f"Gateway: NOT RUNNING (port {port} is free)")
                return 1
    except Exception as e:
        print(f"Gateway: error checking status: {e}")
        return 1


def _cmd_telegram_setup(args: argparse.Namespace, workspace: Path) -> int:
    """Configure the Telegram channel (Phase 3)."""
    from extensions.telegram.runtime import TelegramState

    state = TelegramState.default()
    if args.reset:
        state.bot_token = ""
        state.paired_chat_id = ""
        state._save()
        print("Telegram state reset.")
        return 0
    if args.token:
        state.set_bot_token(args.token)
        print("Bot token set. Send a message to your bot to complete pairing.")
        return 0
    # No flag: show current state.
    print(f"bot_token:    {'set' if state.bot_token else 'unset'}")
    print(f"paired_chat:  {state.paired_chat_id or '(not paired)'}")
    print(f"polling_sec:  {state.polling_interval_sec}")
    return 0


def _cmd_telegram_status(args: argparse.Namespace, workspace: Path) -> int:
    """Show Telegram channel state."""
    from extensions.telegram.runtime import TelegramState

    state = TelegramState.default()
    print(f"bot_token:    {'set' if state.bot_token else 'unset'}")
    print(f"paired_chat:  {state.paired_chat_id or '(not paired)'}")
    print(f"polling_sec:  {state.polling_interval_sec}")
    return 0


# ── argparse setup ───────────────────────────────────────────────


def _build_parser_v2() -> argparse.ArgumentParser:
    """Simpler parser: each top-level command is a verb."""
    p = argparse.ArgumentParser(prog="jarvis", description="JARVIS CLI (Phase 3).")
    p.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="JARVIS workspace root (default: cwd).",
    )
    sp = p.add_subparsers(dest="command", required=False, metavar="<command>")

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

    # ── Phase 3: gateway subcommands ─────────────────────────────
    gw_p = sp.add_parser("gateway", help="Gateway commands.")
    gw_sub = gw_p.add_subparsers(dest="subcommand", required=True, metavar="<action>")
    gw_start = gw_sub.add_parser("start", help="Start the JARVIS gateway.")
    gw_start.add_argument("--host", default=None, help="Bind host (default: 127.0.0.1).")
    gw_start.add_argument("--port", default=None, help="Bind port (default: 7433).")
    gw_sub.add_parser("status", help="Show gateway status.")

    # ── Phase 3: telegram subcommands ────────────────────────────
    tg_p = sp.add_parser("telegram", help="Telegram channel commands.")
    tg_sub = tg_p.add_subparsers(dest="subcommand", required=True, metavar="<action>")
    tg_setup = tg_sub.add_parser("setup", help="Configure the Telegram channel.")
    tg_setup.add_argument(
        "--token",
        default=None,
        help="Telegram Bot API token (from @BotFather).",
    )
    tg_setup.add_argument(
        "--reset",
        action="store_true",
        help="Clear all telegram state (token + paired chat).",
    )
    tg_sub.add_parser("status", help="Show Telegram channel state.")

    return p


# ── main ──────────────────────────────────────────────────────────


# ruff: noqa: PLR0911, PLR0912
# The CLI main() has 15+ returns + 18 branches — one per subcommand
# (Phase 3 adds gateway + telegram). Consolidating into a dispatch
# table would lose the per-command error handling (memory-status can
# raise, doctor returns 0/1, etc.). Each return is a clear, distinct
# branch.


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser_v2()
    workspace_default = Path.cwd()
    # Always need workspace to load plugins, even for parser build.
    if argv is None:
        argv = sys.argv[1:]
    # Cheap pre-parse to find --workspace without full parser run.
    workspace = workspace_default
    for i, a in enumerate(argv):
        if a == "--workspace" and i + 1 < len(argv):
            workspace = Path(argv[i + 1])
            break
        if a.startswith("--workspace="):
            workspace = Path(a.split("=", 1)[1])
            break
    workspace = workspace.resolve()

    # Add workspace to sys.path so ``import extensions.X`` and
    # ``import jarvis.*`` work from any cwd. The desktop host gets
    # the workspace via its cwd; the CLI is a real binary and
    # may be invoked from anywhere.
    ws_str = str(workspace)
    if ws_str not in sys.path:
        sys.path.insert(0, ws_str)
    src_str = str(workspace / "src")
    if src_str not in sys.path:
        sys.path.insert(0, src_str)

    # Always load plugins so their CLI subcommands can be registered
    # onto the parser. Cheap when no plugins are registered.
    plugins: dict[str, Any] = _load_cli_plugins(workspace)

    # Wire plugin CLI handlers: each one mutates the subparsers container
    # to add top-level subcommands (mirrors OpenClaw's registerCli).
    # The subparsers container is what holds the host's own commands
    # (``tools-list``, ``doctor``, etc.); plugins add their top-level
    # commands as siblings of those.
    subparsers = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers = action
            break
    if subparsers is None:
        subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    # Wire plugin CLI handlers with the OpenClaw-shaped context dict
    # ``{program, parentPath, config, workspaceDir, logger}``. Plugins
    # destructure what they need.
    #
    # Note on the host pattern: OpenClaw's host passes the ROOT program as
    # ``program`` (no pre-existing subparsers). The JARVIS host here has
    # hardcoded top-level commands (tools-list / doctor / etc.) so we pass
    # the subparsers container — same destination, different starting
    # point. The plugin's ``register_wiki_cli`` checks ``hasattr(program,
    # 'add_parser')`` and uses the subparsers-container path here, or the
    # root-program path in OpenClaw. Both yield ``wiki`` as a sibling of
    # the host's other top-level commands.
    cli_handlers = plugins.get("cli_handlers", [])
    for entry in cli_handlers:
        # OpenClaw-aligned 4-tuple shape: (register_fn, descriptors, parent_path, commands).
        register_fn, _descriptors, parent_path, _commands = entry
        ctx: dict[str, Any] = {
            "program": subparsers,
            "parentPath": parent_path,
            "config": getattr(workspace, "config", None),
            "workspaceDir": str(workspace),
            "logger": None,
        }
        try:
            register_fn(ctx)
        except Exception as e:
            print(f"[WARN] cli handler failed: {e}", file=sys.stderr)

    args = parser.parse_args(argv)

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
    if args.command == "gateway":
        if args.subcommand == "start":
            return _cmd_gateway_start(args, workspace)
        if args.subcommand == "status":
            return _cmd_gateway_status(args, workspace)
    if args.command == "telegram":
        if args.subcommand == "setup":
            return _cmd_telegram_setup(args, workspace)
        if args.subcommand == "status":
            return _cmd_telegram_status(args, workspace)
    # Plugin-registered CLI command dispatch (e.g. ``jarvis wiki ...``).
    # The plugin's ``register_fn`` typically sets ``func`` on the parent
    # subparser (a dispatcher) and ``__handler`` on the leaf subparser
    # (the actual handler with the resolved context). Try ``func`` first
    # (the dispatcher pattern used by ``register_wiki_cli``); fall back
    # to ``__handler`` for plugins that wire a single-arg handler.
    func = getattr(args, "func", None)
    handler = getattr(args, "__handler", None)
    if callable(func):
        try:
            result = func(args)
        except SystemExit as e:
            return int(e.code) if e.code is not None else 0
        except Exception as e:
            print(f"[ERROR] {args.command}: {e}", file=sys.stderr)
            return 1
        if isinstance(result, int):
            return result
        return 0
    if callable(handler):
        try:
            result = handler(args)
        except SystemExit as e:
            return int(e.code) if e.code is not None else 0
        except Exception as e:
            print(f"[ERROR] {args.command}: {e}", file=sys.stderr)
            return 1
        if isinstance(result, int):
            return result
        return 0
    parser.print_help()
    return 0 if args.command is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
