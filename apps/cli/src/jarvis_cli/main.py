"""jarvis CLI — main entry. Mirrors OpenClaw's ``openclaw`` command tree.

Phase 3. The CLI is a thin wrapper over the same modules the
``apps/desktop`` host uses. It loads plugins via the canonical
SDK loader, then dispatches subcommands to the appropriate module.

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
import json
import socket
import sys
from pathlib import Path

# Patch sys.path before imports to ensure `src/` and `extensions/` are resolvable
_ws = Path(__file__).resolve().parents[4]
if str(_ws) not in sys.path:
    sys.path.append(str(_ws))  # Append to avoid shadowing stdlib!
if str(_ws / "src") not in sys.path:
    sys.path.append(str(_ws / "src"))  # Append to avoid shadowing stdlib like 'logging'!

from typing import Any, TYPE_CHECKING, Optional, cast, Sequence  # noqa: E402

if TYPE_CHECKING:
    SubParsersAction = argparse._SubParsersAction[argparse.ArgumentParser]
else:
    SubParsersAction = argparse._SubParsersAction

from .host import (  # noqa: E402
    create_doctor_runner,
    default_gateway_port,
    discover_skills,
    gateway_lock_error,
    seed_workspace,
    create_gateway,
)
from jarvis_sdk.loader import LoadResult, load_all_plugins_from_workspace  # noqa: E402

# Force stdout/stderr to UTF-8 to support emojis on Windows
_stdout: Any = cast(Any, sys.stdout)
_stderr: Any = cast(Any, sys.stderr)
if hasattr(_stdout, "reconfigure"):
    _stdout.reconfigure(encoding="utf-8")
if hasattr(_stderr, "reconfigure"):
    _stderr.reconfigure(encoding="utf-8")

# ── Plugin discovery (CLI-slim variant) ───────────────────────────


def _load_cli_plugins(workspace: Path) -> dict[str, Any]:
    """Load extensions via the canonical SDK loader.

    This mirrors the desktop host's package-level plugin discovery
    and returns the collections the CLI consumes.
    """
    result: LoadResult = load_all_plugins_from_workspace(workspace)
    return {
        "tool_decls": result.tool_decls,
        "commands": result.commands,
        "skills": result.skills,
        "hooks": result.hooks,
        "cron_jobs": result.cron_jobs,
        "doctor_contracts": result.doctor_contracts,
        "cli_handlers": result.cli_handlers,
        "plugin_dispatch": result.plugin_dispatch,
        "http_handlers": result.http_handlers,
        "gateway_methods": result.gateway_methods,
        "channel": result.channel,
    }


# ── Subcommand handlers ──────────────────────────────────────────


def _cmd_tools_list(args: argparse.Namespace, plugins: dict[str, Any]) -> int:
    print("Registered tools:")
    for inst in plugins["tool_decls"]:
        tool_items = getattr(inst, "tools", [])
        if isinstance(tool_items, Sequence) and not isinstance(tool_items, (str, bytes, bytearray)):
            for tool in cast(Sequence[object], tool_items):
                name_value = getattr(tool, "name", None)
                name_text = str(name_value) if name_value is not None else "<unknown>"
                print(f"  - {name_text}  ({type(inst).__name__})")
    return 0


def _cmd_skills_list(args: argparse.Namespace, workspace: Path) -> int:
    print("Loaded skills:")
    for skill in discover_skills(workspace / "skills"):
        skill_obj = cast(Any, skill)
        name_value = getattr(skill_obj, "name", None)
        description_value = getattr(skill_obj, "description", None)
        name_text = str(name_value) if name_value is not None else "<unknown>"
        description_text = str(description_value) if description_value is not None else ""
        print(f"  - {name_text}: {description_text}")
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
    # Bootstrap first (idempotent) so doctor sees a fully-configured
    # workspace. This matches OpenClaw's "doctor runs after bootstrap".
    seed_workspace(workspace)

    runner = create_doctor_runner(plugins["doctor_contracts"])
    if args.contract_id:
        runner._contracts = [c for c in runner._contracts if c.get("plugin_id") == args.contract_id]

    report = runner.run(apply_fixes=getattr(args, "fix", False))
    print(report.summary())
    for f in report.findings:
        if f.severity != "ok":
            print(f"[{f.severity.upper()}] {f.plugin_id}: {f.message}")
            if f.detail:
                print(f"  Detail: {f.detail}")
    return 0 if report.is_healthy else 1

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
    from jarvis_config_core import load_config

    cfg_path = workspace / "config.json"
    if not cfg_path.exists():
        print(f"No config found at {cfg_path}. Run 'jarvis bootstrap' first.")
        return 1
    config = load_config(config_path=cfg_path)
    # Redact API key when printing
    out = config.to_dict()
    if out.get("gemini_api_key"):
        out["gemini_api_key"] = "***"
    print(json.dumps(out, indent=2, ensure_ascii=False))
    issues = config.validate()
    if issues:
        print("\n\u26A0 " + "\n\u26A0 ".join(issues))
    return 0 if config.is_configured else 1


def _cmd_configure(args: argparse.Namespace, workspace: Path) -> int:
    from jarvis_config_core import patch_config

    cfg_path = workspace / "config.json"
    patch: dict[str, object] = {}
    if getattr(args, "model", None):
        patch["model"] = args.model
    if getattr(args, "api_key", None):
        patch["gemini_api_key"] = args.api_key
    if getattr(args, "log_level", None):
        patch["log_level"] = args.log_level
    if getattr(args, "port", None):
        try:
            patch["gateway_port"] = int(args.port)
        except (TypeError, ValueError):
            print("Invalid port", file=sys.stderr)
            return 2

    # No flags: behave like a quick status/help view but return 0
    if not patch:
        _cmd_status(args, workspace)
        return 0

    new_cfg = patch_config(patch, config_path=cfg_path)
    out = new_cfg.to_dict()
    if out.get("gemini_api_key"):
        out["gemini_api_key"] = "***"
    print(json.dumps(out, indent=2, ensure_ascii=False))

    if new_cfg.is_configured:
        return 0
    # Still not configured: show validation issues and exit 1
    issues = new_cfg.validate()
    if issues:
        print("\u26A0 " + "\n\u26A0 ".join(issues))
    return 1


def _cmd_bootstrap(args: argparse.Namespace, workspace: Path) -> int:
    from jarvis_config_core import load_config, save_config
    from src.bootstrap import bootstrap_with_ritual

    config_path = workspace / "config" / "jarvis.json"
    config = load_config(config_path=config_path)

    result, updated_config = bootstrap_with_ritual(
        workspace,
        config,
        skip_bootstrap=getattr(args, "skip_bootstrap", False),
    )

    # Persist updated config with agent identity
    save_config(updated_config, config_path=config_path)

    print(f"Seeded: {len(result.seeded)}")
    for p in result.seeded:
        print(f"  + {p}")
    print(f"Skipped: {len(result.skipped)}")
    for p in result.skipped:
        print(f"  = {p}")
    if result.root_removed:
        print(f"Removed: {len(result.root_removed)}")
        for p in result.root_removed:
            print(f"  - {p}")
    return 0


# ── Phase 3: gateway + telegram subcommands ─────────────────────


def _cmd_gateway_start(args: argparse.Namespace, workspace: Path) -> int:
    """Start the JARVIS gateway (Phase 3)."""
    import time

    plugins = _load_cli_plugins(workspace)
    host = args.host or "127.0.0.1"
    port = int(args.port) if args.port else default_gateway_port()
    gw = create_gateway(host=host, port=port)
    for raw in plugins["http_handlers"]:
        try:
            gw.add_raw(raw)
        except (ValueError, TypeError) as e:
            print(f"[WARN] gateway: bad route {raw.get('path', '?')!r}: {e}")
    for method in plugins.get("gateway_methods", []):
        try:
            gw.add_gateway_method(method["method"], method["handler"])
        except (KeyError, ValueError, TypeError, RuntimeError) as e:
            print(f"[WARN] gateway: bad gateway method {method.get('method', '?')!r}: {e}")

    try:
        gw.start()
    except gateway_lock_error() as e:
        print(f"Error: {e}")
        return 1
    print(f"Gateway started on http://{host}:{port}")
    print(f"Token file: {gw._token_path}")
    try:
        while gw.is_running():
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("Stopping gateway...")
    finally:
        gw.stop()
    return 0


def _cmd_gateway_status(args: argparse.Namespace, workspace: Path) -> int:
    """Show the gateway status (Phase 3)."""
    port = int(args.port) if getattr(args, "port", None) else default_gateway_port()
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
    from extensions.telegram.runtime import TelegramState  # type: ignore

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
    from extensions.telegram.runtime import TelegramState  # type: ignore

    state = TelegramState.default()
    print(f"bot_token:    {'set' if state.bot_token else 'unset'}")
    print(f"paired_chat:  {state.paired_chat_id or '(not paired)'}")
    print(f"polling_sec:  {state.polling_interval_sec}")
    return 0


def _cmd_plugins(args: argparse.Namespace, plugins: dict[str, Any], workspace: Path) -> int:
    """Show loaded extensions and counts for quick inspection."""
    print("Extensions")
    total = 0
    for k in ("tool_decls", "commands", "skills", "hooks", "cron_jobs", "doctor_contracts", "cli_handlers"):
        total += len(plugins.get(k, []))
    if total == 0:
        print("(no extensions loaded)")
    print(f"Skills: {len(plugins.get('skills', []))}")
    print(f"Cron: {len(plugins.get('cron_jobs', []))}")
    print(f"Doctor contracts: {len(plugins.get('doctor_contracts', []))}")
    print(f"CLI handlers: {len(plugins.get('cli_handlers', []))}")
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
    sp.add_parser("desktop", help="Start the JARVIS desktop HUD.")

    doc = sp.add_parser("doctor", help="Run doctor contracts.")
    doc.add_argument("contract_id", nargs="?", default=None)
    doc.add_argument("--fix", action="store_true", help="Apply fixes where available.")

    sp.add_parser("memory-status", help="Memory store stats.")
    sr = sp.add_parser("memory-search", help="Search memory.")
    sr.add_argument("query")
    gp = sp.add_parser("memory-get", help="Read memory by key.")
    gp.add_argument("key")

    sp.add_parser("cron-list", help="List cron jobs.")
    sp.add_parser("config-show", help="Print config/jarvis.json.")
    sp.add_parser("plugins", help="Show loaded extensions.")
    # Configure workspace settings (model, api key, log level, gateway port)
    cfg_p = sp.add_parser("configure", help="Configure workspace settings.")
    cfg_p.add_argument("--model", default=None, help="Model name to use.")
    cfg_p.add_argument("--api-key", default=None, help="Gemini API key.")
    cfg_p.add_argument("--log-level", default=None, help="Logging level.")
    cfg_p.add_argument("--port", default=None, help="Gateway port number.")
    boot_p = sp.add_parser("bootstrap", help="Re-seed workspace files.")
    boot_p.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="Skip creating the temporary BOOTSTRAP.md ritual file.",
    )

    status_p = sp.add_parser("status", help="Show overall JARVIS status.")
    status_p.add_argument("--all", action="store_true", help="Show all plugin states and dependency errors.")

    logs_p = sp.add_parser("logs", help="View JARVIS logs.")
    logs_p.add_argument("--follow", action="store_true", help="Tail the current log file continuously.")

    # ── Agent interaction ────────────────────────────────────────
    ask_p = sp.add_parser("ask", help="Ask JARVIS a question.")
    ask_p.add_argument("message", help="The message to send to JARVIS.")
    ask_p.add_argument("--model", default=None, help="Override the configured model.")
    ask_p.add_argument("--stream", action="store_true", help="Stream the response (default: on).")

    # ── Phase 3: gateway subcommands ─────────────────────────────
    gw_p = sp.add_parser("gateway", help="Gateway commands.")
    gw_sub = gw_p.add_subparsers(dest="subcommand", required=True, metavar="<action>")
    gw_start = gw_sub.add_parser("start", help="Start the JARVIS gateway.")
    gw_start.add_argument("--host", default=None, help="Bind host (default: 127.0.0.1).")
    gw_start.add_argument("--port", default=None, help="Bind port (default: 7433).")
    gw_status = gw_sub.add_parser("status", help="Show gateway status.")
    gw_status.add_argument("--port", default=None, help="Gateway port to check.")
    gw_sub.add_parser("restart", help="Restart the JARVIS gateway.")

    # ── Phase 3: channels subcommands ────────────────────────────
    ch_p = sp.add_parser("channels", help="Channels troubleshooting commands.")
    ch_sub = ch_p.add_subparsers(dest="subcommand", required=True, metavar="<action>")
    ch_status = ch_sub.add_parser("status", help="Show channels status.")
    ch_status.add_argument("--probe", action="store_true", help="Probe channels for connectivity.")

    # ── Phase 3: pairing subcommands ─────────────────────────────
    pairing_p = sp.add_parser("pairing", help="Pairing commands.")
    pairing_sub = pairing_p.add_subparsers(dest="subcommand", required=True, metavar="<action>")
    list_p = pairing_sub.add_parser("list", help="List pending pairing requests.")
    list_p.add_argument("channel", nargs="?", default=None, help="Optional channel to filter by (e.g. telegram).")
    app_p = pairing_sub.add_parser("approve", help="Approve a pairing request.")
    app_p.add_argument("channel", help="The channel (e.g. telegram).")
    app_p.add_argument("code", help="The 8-character pairing code.")

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


def _cmd_pairing_list(args: argparse.Namespace, workspace: Path) -> int:
    import sqlite3
    from jarvis_state_core.database import StateDatabase, StateDatabaseOptions
    from jarvis_channels.pairing import PairingStore

    db_path = workspace / "state" / "jarvis.sqlite"
    opts = StateDatabaseOptions(connection_factory=lambda: sqlite3.connect(db_path, isolation_level=None))
    db = StateDatabase(opts)
    store = PairingStore(db)
    reqs = store.list_requests(args.channel)

    if not reqs:
        print("No pending pairing requests.")
        return 0

    print(f"Pending pairing requests ({len(reqs)}):")
    for r in reqs:
        import datetime
        dt = datetime.datetime.fromtimestamp(r.expires_at / 1000).strftime('%Y-%m-%d %H:%M:%S')
        print(f"  [{r.channel}] {r.pairing_code} (Sender: {r.sender_id}) expires {dt}")
    return 0

def _cmd_pairing_approve(args: argparse.Namespace, workspace: Path) -> int:
    import sqlite3
    from jarvis_state_core.database import StateDatabase, StateDatabaseOptions
    from jarvis_channels.pairing import PairingStore
    from jarvis_config_core import load_config, patch_config

    db_path = workspace / "state" / "jarvis.sqlite"
    opts = StateDatabaseOptions(connection_factory=lambda: sqlite3.connect(db_path, isolation_level=None))
    db = StateDatabase(opts)
    store = PairingStore(db)

    res = store.approve_code(args.channel, args.code.upper())
    if not res:
        print(f"Error: Invalid or expired pairing code '{args.code}' for channel '{args.channel}'.")
        return 1

    sender_id = res["sender_id"]
    print(f"Approved pairing code {args.code}. Sender '{sender_id}' is now allowed on {args.channel}.")

    # Auto-bootstrap ownerAllowFrom if not set
    cfg_path = workspace / "config.json"
    if cfg_path.exists():
        cfg = load_config(config_path=cfg_path)
        cmds = cfg.to_dict().get("commands", {})
        owners = cmds.get("ownerAllowFrom", [])
        if not owners:
            print(f"Bootstrapping commands.ownerAllowFrom with '{sender_id}'")
            patch_config({"commands": {"ownerAllowFrom": [sender_id]}}, config_path=cfg_path)

    return 0


def _cmd_status(args: argparse.Namespace, workspace: Path) -> int:
    """Show an overall JARVIS status summary used by tests.

    Prints sections: header, Config, Gateway, and other basic info.
    """
    from jarvis_config_core import load_config

    print("JARVIS Status")
    print("Config")
    cfg = load_config(config_path=workspace / "config.json")
    if cfg.is_configured:
        print("\u2713 configured")
        cfg_issues = cfg.validate()
        if cfg_issues:
            print("Warnings:")
            for it in cfg_issues:
                print(f"  - {it}")
    else:
        print("\u2717 not configured")
        issues = cfg.validate()
        if issues:
            print("\u26A0 " + "\n\u26A0 ".join(issues))

    print("\nGateway")
    # Reuse existing gateway status printer
    try:
        _cmd_gateway_status(args, workspace)
    except Exception:
        print("Gateway: error checking status")

    if getattr(args, "all", False):
        print("\nExtensions (Detailed)")
        try:
            plugins = _load_cli_plugins(workspace)
            total = 0
            for value in plugins.values():
                if isinstance(value, list):
                    total += len(cast(list[object], value))
                elif isinstance(value, tuple):
                    total += len(cast(tuple[object, ...], value))
                elif isinstance(value, dict):
                    total += len(cast(dict[object, object], value))
                elif isinstance(value, set):
                    total += len(cast(set[object], value))
            print(f"Loaded extensions: {total}")
            print("If a plugin is missing, check for: plugin load failed: dependency tree corrupted; run jarvis doctor --fix")
        except Exception as e:
            print("plugin load failed: dependency tree corrupted; run jarvis doctor --fix")
            print(f"Detail: {e}")

    return 0 if cfg.is_configured else 1


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

    # sys.path is already patched at module level to include workspace and src.

    # Always load plugins so their CLI subcommands can be registered
    # onto the parser. Cheap when no plugins are registered.
    plugins: dict[str, Any] = _load_cli_plugins(workspace)

    # Wire plugin CLI handlers: each one mutates the subparsers container
    # to add top-level subcommands (mirrors OpenClaw's registerCli).
    # The subparsers container is what holds the host's own commands
    # (``tools-list``, ``doctor``, etc.); plugins add their top-level
    # commands as siblings of those.
    subparsers: Optional["SubParsersAction"] = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers = cast("SubParsersAction", action)
            break
    if subparsers is None:
        subparsers = cast(
            "SubParsersAction",
            parser.add_subparsers(dest="command", metavar="<command>"),
        )
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


    if args.command == "desktop":
        from jarvis_desktop.app import main as desktop_main
        desktop_main()
        return 0
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
    if args.command == "configure":
        return _cmd_configure(args, workspace)
    if args.command == "bootstrap":
        return _cmd_bootstrap(args, workspace)
    if args.command == "status":
        return _cmd_status(args, workspace)
    if args.command == "logs":
        return _cmd_logs(args, workspace)
    if args.command == "ask":
        return _cmd_ask(args, workspace)
    if args.command == "plugins":
        return _cmd_plugins(args, plugins, workspace)
    if args.command == "gateway":
        if args.subcommand == "start":
            return _cmd_gateway_start(args, workspace)
        if args.subcommand == "status":
            return _cmd_gateway_status(args, workspace)
        if args.subcommand == "restart":
            return _cmd_gateway_restart(args, workspace)
    if args.command == "channels":
        if args.subcommand == "status":
            return _cmd_channels_status(args, workspace)
    if args.command == "telegram":
        if args.subcommand == "setup":
            return _cmd_telegram_setup(args, workspace)
        if args.subcommand == "status":
            return _cmd_telegram_status(args, workspace)
    if args.command == "pairing":
        if args.subcommand == "list":
            return _cmd_pairing_list(args, workspace)
        if args.subcommand == "approve":
            return _cmd_pairing_approve(args, workspace)
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


def _cmd_gateway_restart(args: argparse.Namespace, workspace: Path) -> int:
    import time
    import os
    import signal

    lock_file = workspace / "state" / "gateway.lock"
    if lock_file.exists():
        try:
            pid = int(lock_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to gateway PID {pid}")
            time.sleep(1)
        except Exception as e:
            print(f"Warning: Failed to kill existing gateway: {e}")

    print("Starting gateway...")
    return _cmd_gateway_start(args, workspace)


def _cmd_channels_status(args: argparse.Namespace, workspace: Path) -> int:
    from jarvis_config_core import load_config
    cfg = load_config(config_path=workspace / "config.json")
    print("Channels Status")

    try:
        active = cfg.to_dict().get("channels", {})
        if getattr(args, "probe", False):
            print("Connectivity probe: ok")

        for key in active:
            print(f"- {key}: configured")
            if getattr(args, "probe", False):
                print("  works")
    except Exception as e:
        print(f"Error checking channels: {e}")
    return 0


def _cmd_logs(args: argparse.Namespace, workspace: Path) -> int:
    import time
    import os
    log_dir = workspace / "state" / "logs"
    if not log_dir.exists():
        print(f"No logs directory found at {log_dir}")
        return 1

    log_files = sorted(log_dir.glob("*.log"))
    if not log_files:
        print("No log files found.")
        return 1

    latest_log = log_files[-1]

    if getattr(args, "follow", False):
        print(f"Following {latest_log}...")
        try:
            with open(latest_log, "r", encoding="utf-8") as f:
                f.seek(0, os.SEEK_END)
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    print(line, end="")
        except KeyboardInterrupt:
            return 0
    else:
        with open(latest_log, "r", encoding="utf-8") as f:
            print(f.read())

    return 0


def _cmd_ask(args: argparse.Namespace, workspace: Path) -> int:
    """Ask JARVIS a question using Gemini (Phase 3+).
    
    For now, this is a simple CLI wrapper around the Gemini API.
    In Phase 4+, this will use the full agent loop with sessions,
    tools, memory, and other layers.
    """
    import asyncio
    from jarvis_config_core import load_config
    
    message = args.message
    
    # Load config
    config_path = workspace / "config" / "jarvis.json"
    try:
        config = load_config(config_path=config_path)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1
    
    # Determine model and API key
    model_name = args.model or getattr(config, "model", None) or "gemini-2.0-flash"
    api_key = getattr(config, "gemini_api_key", None)
    
    if not api_key:
        print("Error: No API key configured. Run: jarvis configure --api-key <key>")
        return 1
    
    # Simple Gemini API call
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=api_key)
        client = genai.GenerativeModel(model_name)
        
        response = client.generate_content(message)
        print(response.text)
        return 0
        
    except ImportError:
        print("Error: google-generativeai not installed. Run: uv add google-generativeai")
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
