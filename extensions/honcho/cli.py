import argparse
from typing import Any


def _cmd_setup(args: argparse.Namespace) -> int:
    print("honcho setup: Mock writing config to plugins.entries['openclaw-honcho'].config")
    print("honcho setup: Migration of workspace memory files not implemented in mock.")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    print("honcho status: Connected (mock)")
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    question = " ".join(args.question)
    print(f"honcho ask: Mock answer to '{question}'")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    query = " ".join(args.query)
    print(f"honcho search: Mock results for '{query}'")
    return 0


def register_honcho_cli(subparsers: Any, host: Any) -> None:
    """Register 'jarvis honcho' commands."""
    parser = subparsers.add_parser("honcho", help="Manage Honcho memory integration")
    subcmds = parser.add_subparsers(dest="honcho_cmd", required=True)

    cmd_setup = subcmds.add_parser("setup", help="Configure API key and migrate files")
    cmd_setup.set_defaults(func=_cmd_setup)

    cmd_status = subcmds.add_parser("status", help="Check connection status")
    cmd_status.set_defaults(func=_cmd_status)

    cmd_ask = subcmds.add_parser("ask", help="Query Honcho about the user")
    cmd_ask.add_argument("question", nargs="+", help="Question to ask")
    cmd_ask.set_defaults(func=_cmd_ask)

    cmd_search = subcmds.add_parser("search", help="Semantic search over memory")
    cmd_search.add_argument("query", nargs="+", help="Search query")
    cmd_search.add_argument("-k", type=int, help="Limit")
    cmd_search.add_argument("-d", type=str, help="Domain")
    cmd_search.set_defaults(func=_cmd_search)
