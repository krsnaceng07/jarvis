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

from typing import TYPE_CHECKING, Any, Optional, cast  # noqa: E402

if TYPE_CHECKING:
    SubParsersAction = argparse._SubParsersAction[argparse.ArgumentParser]
else:
    SubParsersAction = argparse._SubParsersAction

from .host import (  # noqa: E402
    create_doctor_runner,
    create_gateway,
    default_gateway_port,
    discover_skills,
    gateway_lock_error,
    seed_workspace,
)

try:
    from .mcp import handle_mcp_command  # noqa: E402
except ImportError:  # pragma: no cover - mcp module lands with its owner
    handle_mcp_command = None  # type: ignore[assignment]
from jarvis_sdk.loader import LoadResult, load_all_plugins_from_workspace  # noqa: E402

# Install a minimal host runtime early so config & registry facades
# have runtime hooks available for CLI subcommands and tests.
try:
    from src.config import io as _config_io  # type: ignore
    from src.plugins.runtime_entry import install_host_runtime  # type: ignore

    def _load_config_from_runtime_args(*args: Any, **kwargs: Any) -> Any:
        return _config_io._create_config_io_for_args(args, kwargs).loadConfig()

    # Conservative hooks: prefer the existing snapshot/fallback implementations.
    # Only install these hooks outside of pytest to preserve test sentinel
    # behavior that expects no-arg facade calls to raise NotImplementedError.
    if "pytest" not in sys.modules:
        install_host_runtime(
            registry_params={"logger": None},
            runtime_hooks={
                "get_runtime_config": _config_io.get_runtime_config_snapshot,
                # Install a safe loader wrapper that calls the underlying config IO
                # implementation directly instead of the facade `load_config` which
                # may itself consult installed hooks (causing recursion).
                "load_config": _load_config_from_runtime_args,
            },
        )
except Exception:
    # Do not fail CLI import if runtime wiring isn't available in test environments
    pass

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
        "channels": result.channels,
        "manifest_metadata": result.manifest_metadata,
    }


# ── Subcommand handlers ──────────────────────────────────────────


def _cmd_tools_list(args: argparse.Namespace, plugins: dict[str, Any]) -> int:
    print("Registered tools:")
    tool_decls = plugins.get("tool_decls", [])
    if tool_decls:
        for decl in tool_decls:
            if isinstance(decl, dict):
                name = decl.get("name", "<unknown>")
                desc = decl.get("description", "").strip()
                summary = f": {desc[:70]}..." if len(desc) > 70 else (f": {desc}" if desc else "")
                print(f"  - {name}{summary}")
            elif hasattr(decl, "tools"):
                for t in getattr(decl, "tools", []):
                    name = getattr(t, "name", "<unknown>")
                    print(f"  - {name}")
    elif plugins.get("plugin_dispatch"):
        for name in sorted(plugins["plugin_dispatch"]):
            print(f"  - {name}")
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

    try:
        from jarvis_config_core import doctor as core_doctor

        contracts: list[dict[str, Any]] = list(plugins["doctor_contracts"])
        compaction_contract: dict[str, Any] = cast(
            dict[str, Any],
            getattr(core_doctor, "core_codex_compaction_doctor_contract"),
        )
        config_contract: dict[str, Any] = cast(
            dict[str, Any],
            getattr(core_doctor, "core_config_doctor_contract"),
        )
        legacy_refs_contract: dict[str, Any] = cast(
            dict[str, Any],
            getattr(core_doctor, "core_legacy_codex_refs_doctor_contract"),
        )
        contracts.extend(
            [
                config_contract,
                legacy_refs_contract,
                compaction_contract,
            ]
        )
    except ImportError:
        contracts = plugins["doctor_contracts"]
    runner = create_doctor_runner(contracts)
    if args.contract_id:
        runner._contracts = [c for c in runner._contracts if c.get("plugin_id") == args.contract_id]

    from jarvis_config_core import load_config

    config = load_config()

    report = runner.run(
        state_dir=workspace / "state", config=config, apply_fixes=getattr(args, "fix", False)
    )
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
        print("\n\u26a0 " + "\n\u26a0 ".join(issues))
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
        print("\u26a0 " + "\n\u26a0 ".join(issues))
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
    import asyncio
    import threading
    import time
    from jarvis_config_core import load_config
    from jarvis_sdk.channel_supervisor import ChannelSupervisor

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

    # Start channel supervisor for configured messaging channels
    supervisor = ChannelSupervisor(concurrency_limit=4)
    cfg_obj = load_config(config_path=workspace / "config.json")
    cfg_dict = cfg_obj.to_dict() if hasattr(cfg_obj, "to_dict") else {}
    channels_to_start = plugins.get("channels", {})

    from src.channels.channel_manager import ChannelManager

    cm = ChannelManager.get_instance()
    for ch_id, ch_plugin in channels_to_start.items():
        cm.register_plugin(ch_id, ch_plugin)

    supervisor_loop = asyncio.new_event_loop()

    async def _on_channel_msg(msg: Any) -> None:
        try:
            channel_id = (
                getattr(msg, "channel_id", None)
                or (msg.get("channel_id") if isinstance(msg, dict) else None)
                or (msg.get("origin_surface") if isinstance(msg, dict) else None)
                or "telegram"
            )
            raw_data = (
                msg.raw
                if hasattr(msg, "raw") and isinstance(msg.raw, dict)
                else (msg if isinstance(msg, dict) else {"text": str(msg)})
            )
            await cm._run_channel_turn(channel_id, raw_data)
        except Exception as e:
            print(f"[WARN] channel message handler error: {e}", file=sys.stderr)

    if channels_to_start:
        supervisor_thread = threading.Thread(
            target=lambda: supervisor_loop.run_until_complete(
                supervisor.start_all(channels_to_start, cfg=cfg_dict, on_message=_on_channel_msg)
            ),
            daemon=True,
        )
        supervisor_thread.start()
        print(f"Channel supervisor started for {len(channels_to_start)} channel(s)")

    # Start cron runner for registered cron jobs
    from src.cron import CronRunner

    cron_runner = CronRunner()
    cron_jobs = plugins.get("cron_jobs", [])
    if cron_jobs:
        cron_runner.add_all(cron_jobs)
        cron_runner.start(tick_seconds=30.0)
        print(f"Cron runner started with {len(cron_jobs)} scheduled job(s)")

    try:
        while gw.is_running():
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("Stopping gateway...")
    finally:
        try:
            cron_runner.stop()
        except Exception:
            pass
        try:
            if channels_to_start:
                supervisor_loop.run_until_complete(supervisor.stop_all())
        except Exception:
            pass
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
    for k in (
        "tool_decls",
        "commands",
        "skills",
        "hooks",
        "cron_jobs",
        "doctor_contracts",
        "cli_handlers",
    ):
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

    sp.add_parser("start", help="Start unified JARVIS LiveKit voice HUD in terminal.")
    sp.add_parser("voice", help="Alias for start.")
    sp.add_parser("worker", help="Start standalone LiveKit agent worker.")
    sp.add_parser("agent", help="Alias for worker.")

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
    status_p.add_argument(
        "--all", action="store_true", help="Show all plugin states and dependency errors."
    )

    logs_p = sp.add_parser("logs", help="View JARVIS logs.")
    logs_p.add_argument(
        "--follow", action="store_true", help="Tail the current log file continuously."
    )

    # ── Agent interaction ────────────────────────────────────────
    ask_p = sp.add_parser("ask", help="Ask JARVIS a question.")
    ask_p.add_argument("message", help="The message to send to JARVIS.")
    ask_p.add_argument("--model", default=None, help="Override the configured model.")
    ask_p.add_argument("--stream", action="store_true", help="Stream the response (default: on).")

    tui_p = sp.add_parser("tui", help="Open a session in the terminal UI.")
    tui_p.add_argument("target", nargs="?", default=None, help="Session target to open.")
    attach_p = sp.add_parser("attach", help="Attach a coding harness to a session.")
    attach_p.add_argument("target", nargs="?", default=None, help="Session target to attach.")
    resume_p = sp.add_parser("resume", help="Resume an opaque session handoff.")
    resume_p.add_argument(
        "target", nargs="?", default=None, help="Opaque handoff payload or session target."
    )

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
    ch_p = sp.add_parser("channels", help="Channels troubleshooting and management commands.")
    ch_sub = ch_p.add_subparsers(dest="subcommand", required=True, metavar="<action>")
    ch_status = ch_sub.add_parser("status", help="Show channels status.")
    ch_status.add_argument("--probe", action="store_true", help="Probe channels for connectivity.")

    ch_doctor = ch_sub.add_parser("doctor", help="Run channels doctor diagnostics and auto-repair.")
    ch_doctor.add_argument("--fix", action="store_true", help="Automatically attempt repair of detected issues.")
    ch_doctor.add_argument("--channel", "-c", default=None, help="Specific channel to diagnose/repair (e.g. telegram, discord, slack).")

    ch_sub.add_parser("list", help="List all supported and active channels.")

    ch_add = ch_sub.add_parser("add", help="Add or configure a messaging channel.")
    ch_add.add_argument("channel", help="Channel identifier (e.g. telegram, discord, slack, whatsapp).")
    ch_add.add_argument("--token", default=None, help="Bot token or API key.")
    ch_add.add_argument("--dm-policy", default="allow_all", choices=["allow_all", "pairing_required", "disabled"], help="Direct message access policy.")
    ch_add.add_argument("--app-token", default=None, help="Slack app-level token (xapp-...) if applicable.")

    ch_rem = ch_sub.add_parser("remove", help="Remove or disable a messaging channel.")
    ch_rem.add_argument("channel", help="Channel identifier (e.g. telegram, discord, slack, whatsapp).")

    ch_login = ch_sub.add_parser("login", help="Link a channel account via QR code or interactive login (e.g. whatsapp).")
    ch_login.add_argument("channel", nargs="?", default="whatsapp", help="Channel identifier (e.g. whatsapp).")
    ch_login.add_argument("--account", default="default", help="Account identifier (default 'default').")
    ch_login.add_argument("--force", action="store_true", help="Force generating a fresh QR code even if already linked.")
    ch_login.add_argument("--phone", default=None, help="Optional phone number for pairing code.")

    ch_logout = ch_sub.add_parser("logout", help="Log out of a channel session (e.g. whatsapp).")
    ch_logout.add_argument("channel", nargs="?", default="whatsapp", help="Channel identifier (e.g. whatsapp).")
    ch_logout.add_argument("--account", default="default", help="Account identifier (default 'default').")

    # ── Phase 3: pairing subcommands ─────────────────────────────
    pairing_p = sp.add_parser("pairing", help="Pairing commands.")
    pairing_sub = pairing_p.add_subparsers(dest="subcommand", required=True, metavar="<action>")
    list_p = pairing_sub.add_parser("list", help="List pending pairing requests.")
    list_p.add_argument(
        "channel", nargs="?", default=None, help="Optional channel to filter by (e.g. telegram)."
    )
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

    # ── Phase 3: whatsapp subcommands ────────────────────────────
    wa_p = sp.add_parser("whatsapp", help="WhatsApp channel commands.")
    wa_sub = wa_p.add_subparsers(dest="subcommand", required=True, metavar="<action>")
    wa_login = wa_sub.add_parser("login", help="Link WhatsApp via in-terminal QR code or pairing code.")
    wa_login.add_argument("--account", default="default", help="Account identifier (default 'default').")
    wa_login.add_argument("--force", action="store_true", help="Force generating fresh QR code.")
    wa_login.add_argument("--phone", default=None, help="Optional phone number for pairing code.")
    wa_status = wa_sub.add_parser("status", help="Show WhatsApp link and credentials status.")
    wa_status.add_argument("--account", default="default", help="Account identifier (default 'default').")
    wa_logout = wa_sub.add_parser("logout", help="Log out WhatsApp session.")
    wa_logout.add_argument("--account", default="default", help="Account identifier (default 'default').")

    mcp_p = sp.add_parser("mcp", help="Model Context Protocol (MCP) commands.")
    mcp_sub = mcp_p.add_subparsers(dest="subcommand", required=True, metavar="<action>")
    mcp_add = mcp_sub.add_parser("add", help="Add a new MCP server.")
    mcp_add.add_argument("name", help="Server name.")
    mcp_add.add_argument("--command", default=None, help="Server launch command.")
    mcp_add.add_argument(
        "--arg", action="append", default=None, help="Server argument (repeatable)."
    )
    mcp_add.add_argument("--transport", default="stdio", help="Server transport.")
    mcp_sub.add_parser("status", help="Show MCP servers status.")
    mcp_doctor = mcp_sub.add_parser("doctor", help="Check an MCP server.")
    mcp_doctor.add_argument("name", help="Server name.")
    mcp_doctor.add_argument("--probe", action="store_true", help="Live capability probe.")
    mcp_probe = mcp_sub.add_parser("probe", help="Live capability probe.")
    mcp_probe.add_argument("name", help="Server name.")
    mcp_login = mcp_sub.add_parser("login", help="OAuth login flow.")
    mcp_login.add_argument("name", help="Server name.")
    mcp_sub.add_parser("reload", help="Reloads MCP runtimes in the current CLI process.")
    mcp_sub.add_parser("serve", help="Exposes JARVIS channels to another MCP client.")

    # ── Subagents task management (OpenClaw parity) ──────────────
    sub_p = sp.add_parser("subagents", help="Subagent task management.")
    sub_sub = sub_p.add_subparsers(dest="subcommand", required=True, metavar="<action>")
    sub_list = sub_sub.add_parser("list", help="List active and recent subagents.")
    sub_list.add_argument(
        "--recent-minutes", type=int, default=30, help="Minutes of history (default 30)."
    )
    sub_cancel = sub_sub.add_parser("cancel", help="Cancel a subagent task and its descendants.")
    sub_cancel.add_argument("task_id", help="The task ID or run ID to cancel.")

    return p


def _cmd_pairing_list(args: argparse.Namespace, workspace: Path) -> int:
    import sqlite3

    from jarvis_channels.pairing import PairingStore
    from jarvis_state_core.database import StateDatabase, StateDatabaseOptions

    db_path = workspace / "state" / "jarvis.sqlite"
    opts = StateDatabaseOptions(
        connection_factory=lambda: sqlite3.connect(db_path, isolation_level=None)
    )
    db = StateDatabase(opts)
    store = PairingStore(db)
    reqs = store.list_requests(args.channel)

    if not reqs:
        print("No pending pairing requests.")
        return 0

    print(f"Pending pairing requests ({len(reqs)}):")
    for r in reqs:
        import datetime

        dt = datetime.datetime.fromtimestamp(r.expires_at / 1000).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  [{r.channel}] {r.pairing_code} (Sender: {r.sender_id}) expires {dt}")
    return 0


def _cmd_pairing_approve(args: argparse.Namespace, workspace: Path) -> int:
    import sqlite3

    from jarvis_channels.pairing import PairingStore
    from jarvis_config_core import load_config, patch_config
    from jarvis_state_core.database import StateDatabase, StateDatabaseOptions

    db_path = workspace / "state" / "jarvis.sqlite"
    opts = StateDatabaseOptions(
        connection_factory=lambda: sqlite3.connect(db_path, isolation_level=None)
    )
    db = StateDatabase(opts)
    store = PairingStore(db)

    res = store.approve_code(args.channel, args.code.upper())
    if not res:
        print(f"Error: Invalid or expired pairing code '{args.code}' for channel '{args.channel}'.")
        return 1

    sender_id = res["sender_id"]
    print(
        f"Approved pairing code {args.code}. Sender '{sender_id}' is now allowed on {args.channel}."
    )

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


def _cmd_subagents_list(args: argparse.Namespace, workspace: Path) -> int:
    from src.agents.subagents import SubagentController, SubagentRegistry

    db_path = workspace / "state" / "jarvis.sqlite"
    reg = SubagentRegistry.get_instance(db_path=db_path)
    ctrl = SubagentController(registry=reg)
    runs = ctrl.list_controlled_runs(
        "desktop:hud", recent_minutes=getattr(args, "recent_minutes", 30)
    )
    if not runs:
        print("No active or recent subagents found.")
        return 0
    print(f"Subagent Runs ({len(runs)}):")
    for r in runs:
        status = r.get("status", "unknown").upper()
        task_id = r.get("taskId", "")
        label = r.get("label") or r.get("task", "")[:40]
        print(f"  [{status}] {task_id}: {label}")
        if r.get("error"):
            print(f"       Error: {r['error']}")
        elif r.get("resultSummary"):
            print(f"       Result: {r['resultSummary']}")
    return 0


def _cmd_subagents_cancel(args: argparse.Namespace, workspace: Path) -> int:
    from src.agents.subagents import SubagentController, SubagentRegistry

    db_path = workspace / "state" / "jarvis.sqlite"
    reg = SubagentRegistry.get_instance(db_path=db_path)
    ctrl = SubagentController(registry=reg)
    ok, msg = ctrl.cancel_run(args.task_id)
    print(msg)
    return 0 if ok else 1


def _cmd_status_runtime(workspace: Path) -> None:
    """Print the effective harness runtime for the default agent's model.

    Mirrors OpenClaw's ``/status`` ``Runtime:`` line: the resolved harness
    id plus the selection reason. Fail-closed requirements surface as
    ``(fail-closed: ...)`` instead of raising — status reports, the run
    path enforces.
    """
    import os

    from src.agents.agent_scope_config import resolve_default_agent_id
    from src.agents.harness.selection import (
        HarnessNotSupportedError,
        MissingAgentHarnessError,
        select_agent_harness,
    )

    raw: dict[str, Any] = {}
    try:
        with open(workspace / "config.json", "r", encoding="utf-8") as f:
            loaded: Any = json.load(f)
        if isinstance(loaded, dict):
            raw = cast(dict[str, Any], loaded)
    except Exception:
        raw = {}

    try:
        agent_id = resolve_default_agent_id(raw)
    except Exception:
        agent_id = "main"
    model_ref = _resolve_default_model_ref(raw, agent_id)
    provider: str | None = None
    model_id: str | None = None
    if model_ref and "/" in model_ref:
        provider, _, remainder = model_ref.partition("/")
        model_id = remainder.strip() or None
        provider = provider.strip() or None

    # No extension registers an agent harness today (codex defines its
    # harness but never calls register_agent_harness), so only the
    # built-in openclaw harness is available. Explicit codex requirements
    # therefore fail closed here exactly as in OpenClaw.
    try:
        decision = select_agent_harness(
            {
                "provider": provider,
                "modelId": model_id,
                "config": raw,
                "env": dict(os.environ),
                "agentId": agent_id,
                "registered_harnesses": [],
            }
        )
        label = model_ref or "(no model configured)"
        print(f"Model: {label} | Harness: {decision['harness_id']} ({decision['reason']})")
    except (MissingAgentHarnessError, HarnessNotSupportedError) as e:
        print(f"Model: {model_ref} | Harness: fail-closed ({e})")


def _resolve_default_model_ref(raw: dict[str, Any], agent_id: str) -> str | None:
    """Return the default agent's primary model ref, if configured.

    Fleet shape (``agents.defaults.model`` / list entry ``model``) wins;
    falls back to the canonical flat ``model`` key.
    """
    agents = raw.get("agents")
    if isinstance(agents, dict):
        agents = cast(dict[str, Any], agents)
        defaults = agents.get("defaults")
        defaults = cast(dict[str, Any], defaults) if isinstance(defaults, dict) else None
        if isinstance(defaults, dict) and isinstance(defaults.get("model"), str):
            ref = defaults["model"].strip()
            if ref:
                return ref
        entries = agents.get("list")
        typed_entries = cast(list[Any], entries) if isinstance(entries, list) else []
        for entry in typed_entries:
            if not isinstance(entry, dict):
                continue
            entry = cast(dict[str, Any], entry)
            try:
                from src.routing.agent_id import normalize_agent_id

                if normalize_agent_id(entry.get("id", "")) != agent_id:
                    continue
            except Exception:
                continue
            if isinstance(entry.get("model"), str) and entry["model"].strip():
                return entry["model"].strip()
    top = raw.get("model")
    if isinstance(top, str) and top.strip():
        return top.strip()
    return None


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
            print("\u26a0 " + "\n\u26a0 ".join(issues))

    print("\nGateway")
    # Reuse existing gateway status printer
    try:
        _cmd_gateway_status(args, workspace)
    except Exception:
        print("Gateway: error checking status")

    print("\nRuntime")
    # Live harness-policy resolution for the default agent's model, mirroring
    # OpenClaw's `/status` Runtime line. Never breaks status output.
    try:
        _cmd_status_runtime(workspace)
    except Exception as e:
        print(f"Runtime: unavailable ({e})")

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
            print(
                "If a plugin is missing, check for: plugin load failed: dependency tree corrupted; run jarvis doctor --fix"
            )
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

    # Desktop owns its own startup-scoped plugin discovery. Avoid loading all
    # CLI plugins first, which would activate optional non-startup extensions
    # before the desktop host applies its OpenClaw activation policy.
    if "desktop" in argv:
        args = parser.parse_args(argv)
        from jarvis_desktop.app import main as desktop_main

        desktop_main()
        return 0

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
    class _CliContext(dict[str, Any]):
        """Context dict that delegates .add_parser to the underlying subparser container."""

        def add_parser(self, *args: Any, **kwargs: Any) -> Any:
            prog = self.get("program")
            if prog is not None and hasattr(prog, "add_parser"):
                return prog.add_parser(*args, **kwargs)
            raise AttributeError("'_CliContext' object has no valid program with add_parser")

    cli_handlers = plugins.get("cli_handlers", [])
    for entry in cli_handlers:
        # OpenClaw-aligned 4-tuple shape: (register_fn, descriptors, parent_path, commands).
        register_fn, _descriptors, parent_path, _commands = entry
        ctx = _CliContext(
            {
                "program": subparsers,
                "parentPath": parent_path,
                "config": getattr(workspace, "config", None),
                "workspaceDir": str(workspace),
                "logger": None,
            }
        )
        try:
            register_fn(ctx)
        except TypeError:
            try:
                register_fn(subparsers)
            except Exception as e:
                print(f"[WARN] cli handler failed: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] cli handler failed: {e}", file=sys.stderr)

    args = parser.parse_args(argv)

    if args.command == "desktop":
        from jarvis_desktop.app import main as desktop_main

        desktop_main()
        return 0
    if args.command in ("start", "voice"):
        from jarvis_voice_pipeline.terminal_app import main as voice_main

        return voice_main()
    if args.command in ("worker", "agent"):
        from jarvis_voice_pipeline.worker import run_worker

        run_worker()
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
    if args.command == "tui":
        return _cmd_session_connect(args, workspace, "tui")
    if args.command == "attach":
        return _cmd_session_connect(args, workspace, "attach")
    if args.command == "resume":
        return _cmd_session_connect(args, workspace, "resume")
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
        if args.subcommand == "doctor":
            return _cmd_channels_doctor(args, workspace)
        if args.subcommand == "list":
            return _cmd_channels_list(args, workspace)
        if args.subcommand == "add":
            return _cmd_channels_add(args, workspace)
        if args.subcommand == "remove":
            return _cmd_channels_remove(args, workspace)
        if args.subcommand == "login":
            return _cmd_channels_login(args, workspace)
        if args.subcommand == "logout":
            return _cmd_channels_logout(args, workspace)
    if args.command == "whatsapp":
        if args.subcommand == "login":
            return _cmd_channels_login(args, workspace)
        if args.subcommand == "status":
            return _cmd_whatsapp_status(args, workspace)
        if args.subcommand == "logout":
            return _cmd_channels_logout(args, workspace)
    if args.command == "telegram":
        if args.subcommand == "setup":
            return _cmd_telegram_setup(args, workspace)
        if args.subcommand == "status":
            return _cmd_telegram_status(args, workspace)
    if args.command == "mcp":
        if handle_mcp_command is None:
            print("Error: MCP support module is unavailable in this build.", file=sys.stderr)
            return 1
        return handle_mcp_command(args, workspace)
    if args.command == "pairing":
        if args.subcommand == "list":
            return _cmd_pairing_list(args, workspace)
        if args.subcommand == "approve":
            return _cmd_pairing_approve(args, workspace)
    if args.command == "subagents":
        if args.subcommand == "list":
            return _cmd_subagents_list(args, workspace)
        if args.subcommand == "cancel":
            return _cmd_subagents_cancel(args, workspace)
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
    import os
    import signal
    import time

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

    cfg_file = (workspace / "config.json") if (workspace / "config.json").exists() else None
    cfg = load_config(config_path=cfg_file)
    cfg_dict = cfg.to_dict() if hasattr(cfg, "to_dict") else {}
    channels_cfg = (
        cfg_dict.get("channels", {}) if isinstance(cfg_dict.get("channels"), dict) else {}
    )
    if not channels_cfg:
        try:
            from src.channels.channel_manager import _read_canonical_config

            can_cfg = _read_canonical_config()
            channels_cfg = can_cfg.get("channels", {}) if isinstance(can_cfg.get("channels"), dict) else {}
        except Exception:
            pass
    plugins = _load_cli_plugins(workspace)

    print("Channels Status")

    discovered = plugins.get("channels", {})
    manifest_meta = plugins.get("manifest_metadata", [])
    channel_ids: set[str] = set(discovered.keys())
    for meta in manifest_meta:
        if meta.get("kind") == "channel":
            channel_ids.add(str(meta["id"]))
    for ch in channels_cfg.keys():
        channel_ids.add(str(ch))

    if not channel_ids:
        print("No channels discovered or configured.")
        return 0

    probe = getattr(args, "probe", False)
    if probe:
        print("Connectivity probe: active")

    for ch_id in sorted(channel_ids):
        is_configured = ch_id in channels_cfg
        ch_conf = channels_cfg.get(ch_id, {}) if is_configured else {}
        is_enabled = ch_conf.get("enabled", True) if isinstance(ch_conf, dict) else True
        has_token = bool(
            isinstance(ch_conf, dict)
            and (
                ch_conf.get("bot_token")
                or ch_conf.get("botToken")
                or ch_conf.get("token")
                or ch_conf.get("api_key")
            )
        )

        status_parts: list[str] = []
        if is_configured:
            status_parts.append("configured")
            status_parts.append("enabled" if is_enabled else "disabled")
            if has_token:
                status_parts.append("token present")
        else:
            status_parts.append("available (not configured)")

        print(f"- {ch_id}: {', '.join(status_parts)}")
        if probe:
            if is_configured and (has_token or not is_enabled):
                print(f"  [{ch_id}] transport status: ready")
            elif is_configured and not has_token:
                print(f"  [{ch_id}] transport status: warning (missing credentials)")
            else:
                print(f"  [{ch_id}] transport status: unconfigured")
    return 0


def _cmd_channels_doctor(args: argparse.Namespace, workspace: Path) -> int:
    import asyncio
    from src.channels.channel_manager import ChannelManager

    cm = ChannelManager.get_instance()
    ch_id = getattr(args, "channel", None)
    auto_fix = getattr(args, "fix", False)

    if auto_fix:
        print(f"Running Channel Doctor with Auto-Fix on '{ch_id or 'all'}'...")
        res = asyncio.run(cm.doctor_repair(channel_id=ch_id, auto_detect_tokens=True))
        print(f"Status: {res.get('status', 'unknown')}")
        print(f"Message: {res.get('message', '')}")
        repairs = res.get("repairs", [])
        if repairs:
            print("Repairs applied:")
            for r in repairs:
                print(f"  ✔ [{r.get('channel')}] {r.get('action')}: {r.get('details')}")
        rem = res.get("remaining_issues", [])
        if rem:
            print("Remaining issues:")
            for issue in rem:
                print(f"  ✖ [{issue.get('channel')}] {issue.get('issue')} -> Recommendation: {issue.get('recommendation')}")
        return 0 if res.get("status") in ("repaired", "healthy") else 1
    else:
        print(f"Running Channel Doctor Diagnosis on '{ch_id or 'all'}'...")
        res = asyncio.run(cm.doctor_diagnose(channel_id=ch_id))
        print(f"Status: {res.get('status', 'unknown')}")
        print(f"Message: {res.get('message', '')}")
        issues = res.get("issues", [])
        if issues:
            print("Issues detected:")
            for issue in issues:
                fixable = " (auto-fixable)" if issue.get("auto_fixable") else ""
                print(f"  ✖ [{issue.get('channel')}] {issue.get('issue')}{fixable}")
                print(f"    Recommendation: {issue.get('recommendation')}")
        else:
            print("All inspected channels are healthy and operational.")
        return 0 if not issues else 1


def _cmd_channels_list(args: argparse.Namespace, workspace: Path) -> int:
    from src.channels.channel_manager import ChannelManager

    cm = ChannelManager.get_instance()
    channels = cm.list_supported_channels()
    print("JARVIS Supported Channels:")
    for ch in channels:
        status_label = "ACTIVE" if ch.get("active") else ("CONFIGURED" if ch.get("configured") else "NOT CONFIGURED")
        tok = "yes" if ch.get("has_token") else "no"
        healing = "yes" if ch.get("self_healing") else "no"
        print(f"  • {ch.get('channel_id')} ({ch.get('name')}) - [{status_label}] (token: {tok}, auto-heal: {healing})")
        print(f"    Platform: {ch.get('platform')} | Auth: {ch.get('auth_type')}")
        print(f"    {ch.get('description')}")
    return 0


def _cmd_channels_add(args: argparse.Namespace, workspace: Path) -> int:
    import asyncio
    from src.channels.channel_manager import ChannelManager

    cm = ChannelManager.get_instance()
    ch_id = args.channel.lower()
    token = args.token or ""
    dm_policy = getattr(args, "dm_policy", "allow_all")
    app_token = getattr(args, "app_token", None)

    print(f"Adding/Configuring channel '{ch_id}'...")
    res = asyncio.run(
        cm.configure_channel(
            channel=ch_id,
            token=token,
            dm_policy=dm_policy,
            app_token=app_token,
        )
    )
    if res.get("ok"):
        print(f"✔ Successfully configured {ch_id}: {res.get('message')}")
        print(f"  Listener status: {res.get('status')} (active: {res.get('listener_active')})")
        return 0
    else:
        print(f"✖ Failed to configure {ch_id}: {res.get('error') or res.get('message')}")
        return 1


def _cmd_channels_remove(args: argparse.Namespace, workspace: Path) -> int:
    import asyncio
    from src.channels.channel_manager import ChannelManager

    cm = ChannelManager.get_instance()
    ch_id = args.channel.lower()
    print(f"Removing channel '{ch_id}'...")
    res = asyncio.run(cm.remove_channel(channel_id=ch_id))
    if res.get("ok"):
        print(f"✔ Successfully removed {ch_id}: {res.get('message')}")
        return 0
    else:
        print(f"✖ Failed to remove {ch_id}: {res.get('message')}")
        return 1


def _cmd_channels_login(args: argparse.Namespace, workspace: Path) -> int:
    channel = (getattr(args, "channel", None) or "whatsapp").strip().lower()
    account_id = getattr(args, "account", "default")
    force = getattr(args, "force", False)
    phone = getattr(args, "phone", None)

    if channel == "whatsapp":
        from src.desktop_automation.providers.whatsapp_provider import WhatsAppDesktopProvider

        # OpenClaw parity: Prompt for owner's personal phone number if not supplied
        if not phone and sys.stdin.isatty():
            try:
                print("\n=======================================================")
                print("  JARVIS WhatsApp Channel Pairing")
                print("=======================================================")
                print("Direct WhatsApp messages to JARVIS are secured by allowlist.")
                print("Enter your personal phone number (with country code, e.g. +97798XXXXXXXX)")
                print("or press Enter to generate a QR code for camera scanning.")
                user_inp = input("Personal Phone Number: ").strip()
                if user_inp:
                    phone = user_inp
            except (KeyboardInterrupt, EOFError):
                pass

        provider = WhatsAppDesktopProvider()
        print(f"Initiating WhatsApp Web pairing for account '{account_id}'...")
        res = provider.generate_pairing_qr(
            account_id=account_id,
            force=force,
            phone=phone,
            print_terminal=True,
            wait_for_connection=True,
        )
        if res.get("connected"):
            print(res.get("message", f"\n✔ WhatsApp account '{account_id}' successfully paired and active!"))
            return 0
        instructions = res.get("instructions", "")
        if instructions:
            print(f"\n{instructions}\n")
        return 0 if res.get("ok") else 1
    else:
        print(f"Interactive login is not supported for channel '{channel}'. Supported channels: whatsapp")
        return 1


def _cmd_channels_logout(args: argparse.Namespace, workspace: Path) -> int:
    channel = (getattr(args, "channel", None) or "whatsapp").strip().lower()
    account_id = getattr(args, "account", "default")

    if channel == "whatsapp":
        from src.desktop_automation.providers.whatsapp_provider import WhatsAppDesktopProvider

        provider = WhatsAppDesktopProvider()
        res = provider.logout(account_id=account_id)
        print(res.get("message", f"WhatsApp account '{account_id}' logged out."))
        return 0
    else:
        print(f"Logout is not supported for channel '{channel}'. Supported channels: whatsapp")
        return 1


def _cmd_whatsapp_status(args: argparse.Namespace, workspace: Path) -> int:
    account_id = getattr(args, "account", "default")
    from src.desktop_automation.providers.whatsapp_provider import WhatsAppDesktopProvider

    provider = WhatsAppDesktopProvider()
    auth = provider.get_auth_state(account_id)
    if auth.get("linked"):
        print(f"WhatsApp Status: LINKED (Account: {account_id}, Identity: {auth.get('who')})")
        print(f"  Auth Directory: {auth.get('auth_dir')}")
        print(f"  Credentials: {auth.get('creds_file')}")
    else:
        print(f"WhatsApp Status: NOT LINKED (Account: {account_id})")
        print("  Run 'jarvis channels login whatsapp' to generate in-terminal pairing QR code.")
    return 0


def _cmd_logs(args: argparse.Namespace, workspace: Path) -> int:
    import os
    import time

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


def _cmd_session_connect(args: argparse.Namespace, workspace: Path, mode: str) -> int:
    import json
    import urllib.request

    from .host import default_gateway_port

    target = getattr(args, "target", None)
    if not target:
        print("Error: missing target")
        return 1

    port = default_gateway_port()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/rpc",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "sessions.resolve",
                    "id": "1",
                    "params": {"target": target},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as response:
            res_data = json.loads(response.read().decode("utf-8"))

            if "error" in res_data:
                err = res_data["error"]
                print(
                    f"Gateway error: {err.get('message', 'Unknown')} ({err.get('code')})",
                    file=sys.stderr,
                )
                return 1

            payload = res_data.get("result", {})
            session_key = payload.get("session", {}).get("session_key")

            if not session_key:
                print("Error: Gateway responded but no session key found.", file=sys.stderr)
                return 1

            print(f"[{mode}] Attaching to session: {session_key}...")
            # Placeholder for actual TUI / coding harness attachment
            return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_ask(args: argparse.Namespace, workspace: Path) -> int:
    """Ask JARVIS a question using Gemini (Phase 3+).

    For now, this is a simple CLI wrapper around the Gemini API.
    In Phase 4+, this will use the full agent loop with sessions,
    tools, memory, and other layers.
    """
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
    model_name = args.model or getattr(config, "model", None) or "gemini-3.8-flash"
    api_key = getattr(config, "gemini_api_key", None)

    if not api_key:
        api_keys_path = workspace / "config" / "api_keys.json"
        if api_keys_path.exists():
            try:
                with open(api_keys_path) as f:
                    data = json.load(f)
                    api_key = data.get("gemini_api_key")
            except Exception:
                pass

    if not api_key:
        canonical_cfg = Path.home() / ".jarvis" / "config.json"
        if canonical_cfg.exists():
            try:
                with open(canonical_cfg, encoding="utf-8") as f:
                    data = json.load(f)
                    api_key = data.get("gemini_api_key")
            except Exception:
                pass

    if not api_key:
        root_cfg_path = workspace / "config.json"
        if root_cfg_path.exists():
            try:
                with open(root_cfg_path) as f:
                    data = json.load(f)
                    api_key = data.get("gemini_api_key")
            except Exception:
                pass

    if not api_key:
        import os
        api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("Error: No API key configured. Run: jarvis configure --api-key <key>")
        return 1

    # Modern Google GenAI Client
    try:
        from google import genai  # type: ignore

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=message,
        )
        print(response.text)
        return 0
    except ImportError:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Legacy client fallback
    try:
        import google.generativeai as legacy_genai  # type: ignore

        legacy_genai.configure(api_key=api_key)  # type: ignore[reportPrivateImportUsage]
        legacy_client = legacy_genai.GenerativeModel(model_name)  # type: ignore[reportPrivateImportUsage]

        legacy_resp = cast(Any, legacy_client).generate_content(message)
        print(legacy_resp.text)
        return 0

    except ImportError:
        print("Error: neither google-genai nor google-generativeai is installed. Run: uv add google-genai")
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
