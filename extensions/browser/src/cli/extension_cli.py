"""Extension CLI subcommands for browser native bootstrap."""

import json
import sys
from typing import Any

from ..extension_manager import ExtensionManager
from ..pairing_store import PairingStore


def _print_json(data: dict) -> None:
    print(json.dumps(data, indent=2))


def extension_install(args: Any) -> None:
    """Install the native messaging host."""
    mgr = ExtensionManager()
    is_json = getattr(args, "json", False)

    try:
        result = mgr.install_host()
        if is_json:
            _print_json({"success": True, "details": result})
        else:
            print(f"Extension installed successfully: {result}")
    except Exception as e:
        if is_json:
            _print_json({"success": False, "error": str(e)})
        else:
            print(f"Failed to install extension: {e}", file=sys.stderr)


def extension_status(args: Any) -> None:
    """Check the status of the native messaging host."""
    mgr = ExtensionManager()
    is_json = getattr(args, "json", False)

    status = mgr.get_status()
    if is_json:
        _print_json(status)
    else:
        for k, v in status.items():
            print(f"{k}: {v}")


def extension_uninstall_host(args: Any) -> None:
    """Uninstall the native messaging host."""
    mgr = ExtensionManager()
    is_json = getattr(args, "json", False)

    try:
        mgr.uninstall_host()
        if is_json:
            _print_json({"success": True})
        else:
            print("Host uninstalled successfully.")
    except Exception as e:
        if is_json:
            _print_json({"success": False, "error": str(e)})
        else:
            print(f"Failed to uninstall host: {e}", file=sys.stderr)


def extension_path(args: Any) -> None:
    """Print the extension source path."""
    mgr = ExtensionManager()
    path = mgr.get_extension_path()
    print(path)


def extension_pair(args: Any) -> None:
    """Generate a manual pairing string."""
    store = PairingStore()
    token = store.generate_and_save()
    gateway_url = getattr(args, "gateway_url", None)

    # We output a simple JSON-like connection string or just the token
    # to emulate OpenClaw's pairing format.
    pairing_info = {
        "token": token,
        "gatewayUrl": gateway_url or "ws://127.0.0.1:7433/browser/extension",
    }

    # Base64 encode the string to mimic a connection string
    import base64

    pairing_str = base64.b64encode(json.dumps(pairing_info).encode("utf-8")).decode("utf-8")

    print(f"Pairing string generated:\n{pairing_str}")


def extension_cdp(args: Any) -> None:
    """Print CDP relay metadata."""
    is_json = getattr(args, "json", False)
    metadata = {
        "endpoint": "ws://127.0.0.1:7433/browser/extension",
        "protocol": "Browser Relay Authentication v2",
    }
    if is_json:
        _print_json(metadata)
    else:
        for k, v in metadata.items():
            print(f"{k}: {v}")


def register_extension_cli(subparsers: Any) -> None:
    """Register 'extension' subcommand and its actions."""
    ext_parser = subparsers.add_parser(
        "extension", help="Manage the browser extension integration."
    )
    ext_subparsers = ext_parser.add_subparsers(dest="extension_command", required=True)

    install_cmd = ext_subparsers.add_parser(
        "install", help="Pre-register the native host before adding the extension."
    )
    install_cmd.add_argument("--json", action="store_true", help="Output JSON")
    install_cmd.add_argument("--wait-ms", type=int, default=0, help="Wait timeout")
    install_cmd.set_defaults(func=extension_install)

    status_cmd = ext_subparsers.add_parser("status", help="Inspect installation status.")
    status_cmd.add_argument("--json", action="store_true", help="Output JSON")
    status_cmd.set_defaults(func=extension_status)

    uninstall_cmd = ext_subparsers.add_parser(
        "uninstall-host", help="Remove OpenClaw-owned native-host manifests."
    )
    uninstall_cmd.add_argument("--json", action="store_true", help="Output JSON")
    uninstall_cmd.set_defaults(func=extension_uninstall_host)

    path_cmd = ext_subparsers.add_parser(
        "path", help="Print the stable installed copy or bundled source directory."
    )
    path_cmd.set_defaults(func=extension_path)

    pair_cmd = ext_subparsers.add_parser(
        "pair", help="Generate a host-local manual pairing string."
    )
    pair_cmd.add_argument("--gateway-url", help="Optional remote Gateway URL for manual pairing")
    pair_cmd.set_defaults(func=extension_pair)

    cdp_cmd = ext_subparsers.add_parser("cdp", help="Print external CDP client metadata.")
    cdp_cmd.add_argument("--json", action="store_true", help="Output JSON")
    cdp_cmd.add_argument(
        "--legacy-bearer", action="store_true", help="Include legacy bearer credential"
    )
    cdp_cmd.set_defaults(func=extension_cdp)
