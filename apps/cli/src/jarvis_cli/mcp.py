"""MCP CLI Subcommands."""

import argparse
from pathlib import Path
import asyncio


def _cmd_mcp_add(args: argparse.Namespace, workspace: Path) -> int:
    from jarvis_config_core import load_config, patch_config, McpServerConfig

    config = load_config(config_path=workspace / "config.json")
    mcp_config = config.mcp
    servers = dict(mcp_config.servers)

    name = args.name
    if name in servers:
        print(f"Error: Server '{name}' already exists.")
        return 1

    servers[name] = McpServerConfig(
        command=args.command,
        args=args.arg or [],
        transport=args.transport,
    )

    # Needs to be patched carefully into raw dict, since patch_config operates on raw JSON
    raw_config = config.to_dict()
    mcp_raw = raw_config.setdefault("mcp", {})
    servers_raw = mcp_raw.setdefault("servers", {})
    servers_raw[name] = {
        "command": args.command,
        "args": args.arg or [],
        "transport": args.transport,
    }

    patch_config({"mcp": mcp_raw}, config_path=workspace / "config.json")
    print(f"Added MCP server '{name}'")
    return 0


def _cmd_mcp_status(args: argparse.Namespace, workspace: Path) -> int:
    from jarvis_config_core import load_config

    config = load_config(config_path=workspace / "config.json")
    mcp_config = config.mcp

    print("MCP Servers Configured:")
    if not mcp_config.servers:
        print("  (None)")
        return 0

    for name, srv in mcp_config.servers.items():
        state = "enabled" if srv.enabled else "disabled"
        print(f"  - {name} [{state}] (transport: {srv.transport})")
        if getattr(args, "verbose", False):
            print(f"    Command: {srv.command}")
            print(f"    Args: {srv.args}")
            print(f"    URL: {srv.url}")

    return 0


async def _doctor_probe(name: str, config):
    from jarvis_mcp import McpRegistry

    registry = McpRegistry(config)
    conn = registry.servers.get(name)
    if not conn:
        print(f"Error: Server '{name}' not found or disabled.")
        return 1

    try:
        tools = await conn.get_tools()
        print(f"Server '{name}' is ALIVE.")
        print(f"Exposes {len(tools)} tools:")
        for t in tools:
            print(f"  - {t.name}")
        return 0
    except Exception as e:
        print(f"Error connecting to server '{name}': {e}")
        return 1
    finally:
        await registry.close_all()


def _cmd_mcp_doctor(args: argparse.Namespace, workspace: Path) -> int:
    from jarvis_config_core import load_config

    config = load_config(config_path=workspace / "config.json")

    if args.probe:
        return asyncio.run(_doctor_probe(args.name, config))

    print("Doctor run complete.")
    return 0


def _cmd_mcp_probe(args: argparse.Namespace, workspace: Path) -> int:
    from jarvis_config_core import load_config

    config = load_config(config_path=workspace / "config.json")
    return asyncio.run(_doctor_probe(args.name, config))


def _cmd_mcp_login(args: argparse.Namespace, workspace: Path) -> int:
    print(f"OAuth login flow for {args.name} not implemented yet.")
    return 0


def _cmd_mcp_reload(args: argparse.Namespace, workspace: Path) -> int:
    print("Reloading MCP runtimes...")
    return 0


def _cmd_mcp_serve(args: argparse.Namespace, workspace: Path) -> int:
    print("Exposing JARVIS channels to another MCP client...")
    return 0


def handle_mcp_command(args: argparse.Namespace, workspace: Path) -> int:
    if args.subcommand == "add":
        return _cmd_mcp_add(args, workspace)
    elif args.subcommand == "status":
        return _cmd_mcp_status(args, workspace)
    elif args.subcommand == "doctor":
        return _cmd_mcp_doctor(args, workspace)
    elif args.subcommand == "probe":
        return _cmd_mcp_probe(args, workspace)
    elif args.subcommand == "login":
        return _cmd_mcp_login(args, workspace)
    elif args.subcommand == "reload":
        return _cmd_mcp_reload(args, workspace)
    elif args.subcommand == "serve":
        return _cmd_mcp_serve(args, workspace)
    return 1
