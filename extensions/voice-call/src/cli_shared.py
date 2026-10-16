"""Shared CLI argument helpers and output formatters for Voice Call."""

from __future__ import annotations

import argparse
import json
from typing import Any


def add_json_flag(parser: argparse.ArgumentParser) -> None:
    """Add --json flag for machine-readable JSON output."""
    parser.add_argument("--json", action="store_true", help="Format output as JSON")


def print_cli_result(result: Any, is_json: bool = False) -> None:
    """Print command result in either formatted JSON or human-readable format."""
    if is_json:
        print(json.dumps(result, indent=2))
    else:
        if isinstance(result, dict):
            for k, v in result.items():
                print(f"{k}: {v}")
        else:
            print(result)
