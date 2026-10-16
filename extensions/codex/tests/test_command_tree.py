"""Tests for the full `/codex` command tree: parse, authorize, terminal.

OpenClaw parity: ``command-handler-args.ts`` (parsers),
``command-authorization.ts`` (owner/admin gates),
``command-handler-actions.ts`` (early-return matrix), and the
``commands-and-diagnostics`` doc section (full verb list, admin-only
mutations and host inspection).
"""

from __future__ import annotations

import asyncio

import pytest

from extensions.codex.src.command_actions import (
    NATIVE_CONTROL_SUBCOMMANDS,
    NATIVE_EXECUTION_SUBCOMMANDS,
    is_read_only_goal_command,
    returns_before_execution,
)
from extensions.codex.src.command_args import (
    is_menu_verb,
    parse_bind_args,
    parse_resume_args,
    parse_sessions_args,
    split_args,
)
from extensions.codex.src.command_authorization import (
    CODEX_HOST_INSPECTION_AUTH_ERROR,
    CODEX_NATIVE_EXECUTION_AUTH_ERROR,
    can_mutate_host,
    has_admin_scope,
)
from extensions.codex.src.commands import (
    CodexCommandContext,
    build_codex_help,
    handle_codex_command,
)
from extensions.codex.src.conversation_control import (
    format_permissions_mode,
    parse_fast_mode_arg,
    parse_permissions_mode_arg,
)


def _run(ctx, **kwargs):
    return asyncio.run(handle_codex_command(ctx, **kwargs))


def _admin(args, **ctx_kwargs):
    return CodexCommandContext(args=args, is_admin=True, **ctx_kwargs)


def _reader(args, **ctx_kwargs):
    return CodexCommandContext(args=args, is_admin=False, **ctx_kwargs)


def test_arg_parsers():
    assert parse_bind_args(["th_1", "--cwd", "/tmp", "--model", "m", "--provider", "p"]) == {
        "thread_id": "th_1",
        "cwd": "/tmp",
        "model": "m",
        "provider": "p",
    }
    assert parse_bind_args(["--help"])["help"] is True
    assert parse_bind_args(["a", "b"])["help"] is True
    assert parse_bind_args(["--model"])["help"] is True
    assert parse_resume_args(["th_1"])["thread_id"] == "th_1"
    parsed = parse_resume_args(["th_1", "--host", "n1", "--bind", "here"])
    assert (parsed["host"], parsed["bind_here"]) == ("n1", True)
    assert parse_resume_args([]).get("thread_id") is None
    assert parse_resume_args(["--bind", "there"])["help"] is True
    sessions = parse_sessions_args(["--host", "n1", "--limit", "5", "f o o"])
    assert (sessions["host"], sessions["limit"], sessions["filter"]) == ("n1", 5, "f o o")
    assert parse_sessions_args(["--limit", "0"])["help"] is True
    assert split_args('a "b c" d') == ["a", "b c", "d"]
    assert is_menu_verb(["menu"]) is True
    assert is_menu_verb(["menu", "x"]) is False


def test_mode_parsers_and_format():
    assert parse_fast_mode_arg("on") is True
    assert parse_fast_mode_arg("flex") is False
    assert parse_fast_mode_arg("status") is None
    assert parse_fast_mode_arg("bogus") is None
    assert parse_permissions_mode_arg("yolo") == "yolo"
    assert parse_permissions_mode_arg("approve") == "default"
    assert parse_permissions_mode_arg("status") is None
    assert format_permissions_mode("full") == "full access"
    assert format_permissions_mode(None) == "default"


def test_authorization_predicates():
    assert can_mutate_host(_admin("x")) is True
    assert can_mutate_host(_reader("x")) is False
    assert has_admin_scope(_admin("x")) is True
    assert has_admin_scope(_reader("x")) is False


def test_action_sets_and_early_returns():
    assert (
        NATIVE_CONTROL_SUBCOMMANDS
        >= NATIVE_EXECUTION_SUBCOMMANDS
        >= {
            "bind",
            "resume",
            "model",
            "fast",
            "compact",
        }
    )
    assert {"detach", "unbind", "stop"} <= NATIVE_CONTROL_SUBCOMMANDS
    assert is_read_only_goal_command("goal", []) is True
    assert is_read_only_goal_command("goal", ["get"]) is True
    assert is_read_only_goal_command("goal", ["set", "x"]) is False
    assert returns_before_execution("model", []) is True
    assert returns_before_execution("model", ["a", "b"]) is True
    assert returns_before_execution("model", ["a"]) is False
    assert returns_before_execution("steer", []) is True
    assert returns_before_execution("steer", ["x"]) is False
    assert returns_before_execution("fast", ["bogus"]) is True
    assert returns_before_execution("stop", ["x"]) is True
    assert returns_before_execution("stop", []) is False


def test_help_lists_full_tree():
    text = build_codex_help()
    assert "Codex Plugin Commands" in text
    assert "/codex status" in text
    for verb in (
        "threads",
        "resume",
        "bind",
        "detach",
        "stop",
        "steer",
        "compact",
        "review",
        "diagnostics",
        "account",
        "plugins",
        "skills",
        "goal",
    ):
        assert f"/codex {verb}" in text


@pytest.mark.parametrize(
    "args",
    [
        "threads",
        "resume th_1",
        "bind th_1",
        "detach",
        "stop",
        "steer hello",
        "model openai/gpt-5.6-sol",
        "fast on",
        "permissions default",
        "compact",
        "review",
        "diagnostics note",
        "account",
        "mcp",
        "skills",
        "plugins list",
        "goal set ship it",
    ],
)
def test_mutations_and_inspection_require_admin(args):
    res = _run(_reader(args))
    assert res.text in (CODEX_NATIVE_EXECUTION_AUTH_ERROR, CODEX_HOST_INSPECTION_AUTH_ERROR)


def test_reader_inspection_verbs_stay_open():
    for args in ("help", "models", "binding", "goal", "fast status", "permissions status"):
        res = _run(_reader(args))
        assert res.text not in (
            CODEX_NATIVE_EXECUTION_AUTH_ERROR,
            CODEX_HOST_INSPECTION_AUTH_ERROR,
        ), args


def test_terminals_name_the_missing_backend():
    res = _run(_admin("threads"))
    assert "live Codex app-server connection" in res.text
    res = _run(_admin("bind th_1"))
    assert "verified thread binding" in res.text
    # No fake success: never claims the action happened.
    assert "attached" not in res.text.lower() or "not available" in res.text


@pytest.mark.parametrize(
    ("args", "usage"),
    [
        ("bind --model", "/codex bind"),
        ("resume", "/codex resume"),
        ("steer", "/codex steer"),
        ("model a b", "/codex model"),
        ("fast bogus", "/codex fast"),
        ("permissions bogus", "/codex permissions"),
        ("stop now", "/codex stop"),
        ("compact x", "/codex compact"),
        ("goal frobnicate", "/codex goal"),
        ("plugins install no-at-sign", "/codex plugins install"),
        ("plugins enable", "/codex plugins"),
    ],
)
def test_usage_errors(args, usage):
    res = _run(_admin(args))
    assert "Usage:" in res.text
    assert usage in res.text


def test_yolo_names_admin_requirement():
    res = _run(_reader("permissions yolo"))
    assert "operator.admin" in res.text


def test_status_now_requires_admin():
    res = _run(_reader("status"))
    assert res.text == CODEX_HOST_INSPECTION_AUTH_ERROR
