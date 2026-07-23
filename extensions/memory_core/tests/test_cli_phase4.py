"""Tests for memory_core.cli — Phase 4.4l.

Verifies the OpenClaw-shaped ``register_memory_cli`` produces the
correct argparse subcommand tree and dispatches the right handlers.
"""
from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from extensions.memory_core import cli as cli_module


# ── Test helpers ──────────────────────────────────────────────────────


def _build_program() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    """Build a root parser + subparsers container (mimics JARVIS CLI)."""
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command")
    return root, sub


def _parse_memory(argv: list[str]) -> argparse.Namespace:
    """Parse a ``memory <subcommand> [args]`` command tree."""
    root, sub = _build_program()
    cli_module.register_memory_cli(sub)
    return root.parse_args(argv)


# ── Subcommand registration ────────────────────────────────────────


def test_register_memory_cli_adds_memory_command() -> None:
    """``memory`` parent command is registered."""
    root, sub = _build_program()
    cli_module.register_memory_cli(sub)
    # Parse ``memory status`` to verify the tree
    args = root.parse_args(["memory", "status"])
    assert args.command == "memory"
    assert args.memory_command == "status"


def test_register_memory_cli_has_all_seven_subcommands() -> None:
    """All 7 OpenClaw subcommands are present."""
    root, sub = _build_program()
    cli_module.register_memory_cli(sub)
    for sub_name in (
        "status",
        "index",
        "search",
        "promote",
        "promote-explain",
        "rem-harness",
        "rem-backfill",
    ):
        # Each subcommand must parse without error
        argv = ["memory", sub_name]
        if sub_name in ("search", "promote-explain"):
            argv.append("dummy")
        args = root.parse_args(argv)
        assert args.memory_command == sub_name, sub_name


# ── search / promote-explain argument shapes ──────────────────────


def test_memory_search_takes_query_and_limit() -> None:
    """``memory search <query> [--limit N]`` parses both args."""
    root, sub = _build_program()
    cli_module.register_memory_cli(sub)
    args = root.parse_args(["memory", "search", "hello", "--limit", "5"])
    assert args.memory_command == "search"
    assert args.query == "hello"
    assert args.limit == 5


def test_memory_promote_explain_takes_key() -> None:
    """``memory promote-explain <key>`` parses the key."""
    root, sub = _build_program()
    cli_module.register_memory_cli(sub)
    args = root.parse_args(["memory", "promote-explain", "my-key"])
    assert args.memory_command == "promote-explain"
    assert args.key == "my-key"


def test_memory_promote_takes_dry_run_flag() -> None:
    """``memory promote [--dry-run]`` parses the flag."""
    root, sub = _build_program()
    cli_module.register_memory_cli(sub)
    args = root.parse_args(["memory", "promote", "--dry-run"])
    assert args.memory_command == "promote"
    assert args.dry_run is True


def test_memory_rem_backfill_takes_days() -> None:
    """``memory rem-backfill [--days N]`` parses the days arg."""
    root, sub = _build_program()
    cli_module.register_memory_cli(sub)
    args = root.parse_args(["memory", "rem-backfill", "--days", "7"])
    assert args.memory_command == "rem-backfill"
    assert args.days == 7


def test_memory_rem_harness_takes_limit() -> None:
    """``memory rem-harness [--limit N]`` parses the limit arg."""
    root, sub = _build_program()
    cli_module.register_memory_cli(sub)
    args = root.parse_args(["memory", "rem-harness", "--limit", "3"])
    assert args.memory_command == "rem-harness"
    assert args.limit == 3


# ── Handler dispatch ──────────────────────────────────────────────


def test_handlers_attached_to_subcommands() -> None:
    """Each subcommand has a ``_handler`` callable attached."""
    root, sub = _build_program()
    cli_module.register_memory_cli(sub)
    for sub_name in (
        "status",
        "index",
        "search",
        "promote",
        "promote-explain",
        "rem-harness",
        "rem-backfill",
    ):
        argv = ["memory", sub_name]
        if sub_name in ("search", "promote-explain"):
            argv.append("dummy")
        args = root.parse_args(argv)
        assert callable(getattr(args, "_handler", None)), sub_name


def test_handler_unavailable_emit_returns_zero() -> None:
    """``_emit_unavailable`` returns 0 (not an error)."""
    assert cli_module._emit_unavailable("promote-explain") == 0


# ── Workspace resolution ─────────────────────────────────────────


def test_resolve_workspace_explicit_arg() -> None:
    """``args.workspace`` is used when present."""
    args = argparse.Namespace(workspace="/tmp/explicit")
    assert cli_module._resolve_workspace(args) == "/tmp/explicit"


def test_resolve_workspace_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """``JARVIS_WORKSPACE`` env var is used as fallback."""
    monkeypatch.setenv("JARVIS_WORKSPACE", "/tmp/from-env")
    args = argparse.Namespace(workspace=None)
    assert cli_module._resolve_workspace(args) == "/tmp/from-env"


def test_resolve_workspace_falls_back_to_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    """No workspace / env → cwd."""
    monkeypatch.delenv("JARVIS_WORKSPACE", raising=False)
    args = argparse.Namespace(workspace=None)
    result = cli_module._resolve_workspace(args)
    assert result  # non-empty string


# ── Handler invocation (smoke) ────────────────────────────────────


def test_cmd_memory_promote_explain_calls_emit_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    """``memory promote-explain`` emits a "not yet available" message."""
    args = argparse.Namespace(key="x")
    rc = cli_module._cmd_memory_promote_explain(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "not yet available" in out


def test_cmd_memory_rem_harness_calls_emit_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    """``memory rem-harness`` emits a "not yet available" message."""
    args = argparse.Namespace(limit=5)
    rc = cli_module._cmd_memory_rem_harness(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "not yet available" in out


def test_cmd_memory_index_prints_status(capsys: pytest.CaptureFixture[str]) -> None:
    """``memory index`` prints a status line."""
    args = argparse.Namespace(workspace="/tmp/test-ws")
    rc = cli_module._cmd_memory_index(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "memory index" in out
    assert "/tmp/test-ws" in out


# ── Full handler integration via parse ───────────────────────────


def test_full_parse_and_dispatch_promote_explain(capsys: pytest.CaptureFixture[str]) -> None:
    """End-to-end: ``jarvis memory promote-explain foo`` prints the unavailable message."""
    root, sub = _build_program()
    cli_module.register_memory_cli(sub)
    args = root.parse_args(["memory", "promote-explain", "foo"])
    rc = args._handler(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "not yet available" in out


def test_full_parse_and_dispatch_index(capsys: pytest.CaptureFixture[str]) -> None:
    """End-to-end: ``jarvis memory index`` prints the status line."""
    root, sub = _build_program()
    cli_module.register_memory_cli(sub)
    args = root.parse_args(["memory", "index"])
    rc = args._handler(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "memory index" in out
