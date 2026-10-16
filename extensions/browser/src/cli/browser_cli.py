"""CLI integration for the Browser extension."""

from typing import Any

from .extension_cli import register_extension_cli
from .cli_lifecycle import register_lifecycle_cli
from .cli_profiles import register_profiles_cli
from .cli_tabs import register_tabs_cli
from .cli_inspection import register_inspection_cli
from .cli_actions import register_actions_cli
from .cli_state import register_state_cli
from .cli_batch import register_batch_cli


# Removed duplicate lifecycle commands since they are moved to cli_lifecycle.py


def register_cli(ctx: Any) -> None:
    """Register CLI handlers with argparse."""
    subparsers_parent = ctx["program"] if isinstance(ctx, dict) else ctx.program
    browser_parser = subparsers_parent.add_parser(
        "browser", help="Manage the OpenClaw browser automation runtime."
    )
    browser_parser.add_argument(
        "--browser-profile",
        dest="browser_profile",
        default="openclaw",
        help="Browser profile to use",
    )
    subparsers = browser_parser.add_subparsers(dest="browser_command")

    # Register modular subcommands
    register_lifecycle_cli(subparsers)
    register_profiles_cli(subparsers)
    register_tabs_cli(subparsers)
    register_inspection_cli(subparsers)
    register_actions_cli(subparsers)
    register_state_cli(subparsers)
    register_batch_cli(subparsers)
    register_extension_cli(subparsers)
