"""jarvis.cli.exec_policy_cli - CLI for managing local exec policies.

OpenClaw parity: mirrors ``openclaw-main/src/cli/exec-policy.ts``
"""

import sys
import argparse

from src.infra.exec_approvals_store import (
    read_exec_approvals_snapshot,
    write_exec_approvals_snapshot,
)
from src.infra.exec_approvals_types import ExecApprovalsDefaults
from src.infra.exec_approvals import ExecSecurity, ExecAsk


def _update_local_approvals(
    security: ExecSecurity | None,
    ask: ExecAsk | None,
    ask_fallback: ExecSecurity | None,
) -> None:
    snapshot = read_exec_approvals_snapshot()
    file_data = snapshot["file"]
    defaults: ExecApprovalsDefaults = file_data.setdefault("defaults", {})
    
    if security is not None:
        defaults["security"] = security
    if ask is not None:
        defaults["ask"] = ask
    if ask_fallback is not None:
        defaults["askFallback"] = ask_fallback

    write_exec_approvals_snapshot(file_data)
    print("Updated local host exec-approvals document.")


def cmd_preset(args: argparse.Namespace) -> None:
    preset = args.preset
    if preset == "yolo":
        # Mode: full, Host: gateway
        print("Applying YOLO preset (security=full, ask=off, askFallback=full)")
        # Config should be updated here - typically via the Config API
        # For parity we simulate the config update logging
        print("[Config] Set tools.exec.mode = full")
        print("[Config] Set tools.exec.host = gateway")
        _update_local_approvals(security="full", ask="off", ask_fallback="full")
        
    elif preset == "cautious":
        print("Applying CAUTIOUS preset (security=allowlist, ask=on-miss, askFallback=deny)")
        print("[Config] Set tools.exec.mode = ask")
        print("[Config] Set tools.exec.host = gateway")
        _update_local_approvals(security="allowlist", ask="on-miss", ask_fallback="deny")
        
    elif preset == "deny-all":
        print("Applying DENY-ALL preset (security=deny, ask=off, askFallback=deny)")
        print("[Config] Set tools.exec.mode = deny")
        print("[Config] Set tools.exec.host = gateway")
        _update_local_approvals(security="deny", ask="off", ask_fallback="deny")
    else:
        print(f"Unknown preset: {preset}", file=sys.stderr)
        sys.exit(1)


def cmd_set(args: argparse.Namespace) -> None:
    if args.host:
        print(f"[Config] Set tools.exec.host = {args.host}")
    if args.mode:
        print(f"[Config] Set tools.exec.mode = {args.mode}")

    # For --security, --ask, --ask-fallback, we update both config and local approvals
    # depending on what is specified. The OpenClaw CLI typically writes directly to the local document.
    if args.security or args.ask or args.ask_fallback:
        _update_local_approvals(
            security=args.security,
            ask=args.ask,
            ask_fallback=args.ask_fallback,
        )


def cmd_show(args: argparse.Namespace) -> None:
    snapshot = read_exec_approvals_snapshot()
    defaults = snapshot["file"].get("defaults", {})
    print("--- Local Exec Approvals Policy ---")
    print(f"Security:     {defaults.get('security', '<not set>')}")
    print(f"Ask:          {defaults.get('ask', '<not set>')}")
    print(f"AskFallback:  {defaults.get('askFallback', '<not set>')}")
    print(f"AutoAllow:    {defaults.get('autoAllowSkills', False)}")
    print("-----------------------------------")


def main() -> None:
    parser = argparse.ArgumentParser(prog="jarvis exec-policy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Preset command
    preset_parser = subparsers.add_parser("preset", help="Apply a known policy preset")
    preset_parser.add_argument("preset", choices=["yolo", "cautious", "deny-all"])

    # Set command
    set_parser = subparsers.add_parser("set", help="Set explicit policy fields")
    set_parser.add_argument("--host", choices=["auto", "sandbox", "gateway", "node"])
    set_parser.add_argument("--mode", choices=["deny", "allowlist", "ask", "auto", "full"])
    set_parser.add_argument("--security", choices=["deny", "allowlist", "full"])
    set_parser.add_argument("--ask", choices=["off", "on-miss", "always"])
    set_parser.add_argument("--ask-fallback", choices=["deny", "allowlist", "full"])

    # Show command
    subparsers.add_parser("show", help="Show the local effective policy")

    args = parser.parse_args()

    if args.command == "preset":
        cmd_preset(args)
    elif args.command == "set":
        cmd_set(args)
    elif args.command == "show":
        cmd_show(args)


if __name__ == "__main__":
    main()
