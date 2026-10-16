"""jarvis.cli.approvals_cli - CLI for raw approvals JSON document access.

OpenClaw parity: mirrors ``openclaw-main/src/cli/approvals.ts``
"""

import sys
import json
import argparse

from src.infra.exec_approvals_store import (
    read_exec_approvals_snapshot,
    write_exec_approvals_snapshot,
)
from src.infra.exec_approvals_types import ExecApprovalsFile


def cmd_get(args: argparse.Namespace) -> None:
    snapshot = read_exec_approvals_snapshot()
    if not snapshot["exists"]:
        print("No local approvals document exists.")
        sys.exit(0)
    
    print(json.dumps(snapshot["file"], indent=2))


def cmd_set(args: argparse.Namespace) -> None:
    if not args.stdin:
        print("Error: must use --stdin to provide approvals document.", file=sys.stderr)
        sys.exit(1)

    try:
        input_data = sys.stdin.read()
        file_data: ExecApprovalsFile = json.loads(input_data)
        
        # OpenClaw schema requires version 1
        if file_data.get("version") != 1:
            print("Error: approvals document must have version 1.", file=sys.stderr)
            sys.exit(1)

        write_exec_approvals_snapshot(file_data)
        print("Updated local host exec-approvals document.")
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from stdin: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="jarvis approvals")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Get command
    subparsers.add_parser("get", help="Get the local approvals document JSON")

    # Set command
    set_parser = subparsers.add_parser("set", help="Set the local approvals document JSON")
    set_parser.add_argument("--stdin", action="store_true", help="Read JSON from stdin")

    args = parser.parse_args()

    if args.command == "get":
        cmd_get(args)
    elif args.command == "set":
        cmd_set(args)


if __name__ == "__main__":
    main()
