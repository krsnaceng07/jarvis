"""CLI commands for browser batch execution."""

from typing import Any


def browser_batch(args: Any) -> None:
    print("Batch execution")


def register_batch_cli(subparsers: Any) -> None:
    batch = subparsers.add_parser("batch", help="Execute batch of actions")
    batch.add_argument("--actions")
    batch.add_argument("--actions-file")
    batch.add_argument("--continue", action="store_true", dest="continue_on_error")
    batch.add_argument("--target-id")
    batch.set_defaults(func=browser_batch)
