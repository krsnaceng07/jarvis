"""Shared CLI output formatting and print utilities for Zoom Meetings."""

from __future__ import annotations

import json
import sys
from typing import Any


def print_cli_result(data: Any, is_json: bool = False) -> None:
    """Print structured CLI result to stdout as JSON or human-readable format."""
    if is_json or isinstance(data, (dict, list)):
        sys.stdout.write(f"{json.dumps(data, indent=2, default=str)}\n")
    else:
        sys.stdout.write(f"{data}\n")
    sys.stdout.flush()


def add_json_flag(parser: Any) -> None:
    """Add standard --json flag to a command subparser."""
    parser.add_argument("--json", action="store_true", help="Format command output as JSON")
