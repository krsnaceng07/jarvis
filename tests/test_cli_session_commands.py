"""Tests that session CLI surfaces stay wired (anti-regression).

The ``tui`` / ``attach`` / ``resume`` / ``mcp`` commands were once lost
to an uncommitted-work revert; these parser-level tests lock their
wiring (subcommand names, target plumbing, dispatch attributes) so any
future loss fails loudly here instead of silently dropping commands.
"""

from __future__ import annotations

from apps.cli.src.jarvis_cli.main import _build_parser_v2


def _parse(argv: list[str]):
    return _build_parser_v2().parse_args(argv)


def test_session_commands_parse():
    for command in ("tui", "attach", "resume"):
        args = _parse([command, "agent:main:main"])
        assert args.command == command
        assert args.target == "agent:main:main"
        missing = _parse([command])
        assert missing.target is None


def test_mcp_actions_parse():
    args = _parse(["mcp", "status"])
    assert args.command == "mcp"
    assert args.subcommand == "status"
    add = _parse(["mcp", "add", "srv", "--command", "node", "--arg", "x.js"])
    assert add.name == "srv"
    assert add.command == "node"
    assert add.arg == ["x.js"]
