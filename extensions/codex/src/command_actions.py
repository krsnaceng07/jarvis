"""`/codex` subcommand classification (pure).

OpenClaw parity: mirrors the pure surface of
``openclaw-main/extensions/codex/src/command-handler-actions.ts``:
``CODEX_NATIVE_EXECUTION_SUBCOMMANDS``,
``CODEX_NATIVE_CONTROL_SUBCOMMANDS``, ``isReadOnlyCodexGoalCommand``,
and ``returnsBeforeNativeCodexExecution``.
"""

from __future__ import annotations

from typing import Any

from extensions.codex.src.command_args import (
    parse_bind_args,
    parse_resume_args,
    split_args,
)
from extensions.codex.src.conversation_control import (
    parse_fast_mode_arg,
    parse_permissions_mode_arg,
)

#: Subcommands that drive native execution. Mirrors
#: ``CODEX_NATIVE_EXECUTION_SUBCOMMANDS``.
NATIVE_EXECUTION_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "bind",
        "resume",
        "steer",
        "model",
        "fast",
        "permissions",
        "compact",
        "review",
        "goal",
    }
)

#: Execution subcommands plus terminal controls. Mirrors
#: ``CODEX_NATIVE_CONTROL_SUBCOMMANDS``.
NATIVE_CONTROL_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        *NATIVE_EXECUTION_SUBCOMMANDS,
        "detach",
        "unbind",
        "stop",
    }
)


def is_read_only_goal_command(subcommand: str, args: list[str]) -> bool:
    """Mirror ``isReadOnlyCodexGoalCommand``: bare ``goal`` or
    ``goal status|get`` never mutates."""
    if subcommand != "goal" or len(args) > 1:
        return False
    action = args[0].lower() if args else "status"
    return action in ("status", "get")


def _returns_before_resume(args: list[str]) -> bool:
    """Mirror ``returnsBeforeNativeCodexResume``."""
    parsed = parse_resume_args(list(args))
    if parsed.get("help"):
        return True
    thread_id = (parsed.get("thread_id") or "").strip()
    if parsed.get("host"):
        return not thread_id or parsed.get("bind_here") is not True
    return not thread_id or len(args) != 1


def returns_before_execution(subcommand: str, args: list[str]) -> bool:
    """Mirror ``returnsBeforeNativeCodexExecution``: arg shapes that
    resolve to usage/help instead of reaching native execution."""
    if subcommand == "bind":
        return parse_bind_args(list(args)).get("help", False) is True
    if subcommand == "resume":
        return _returns_before_resume(args)
    if subcommand == "steer":
        return " ".join(args).strip() == ""
    if subcommand == "model":
        return len(args) == 0 or len(args) > 1
    if subcommand == "fast":
        return len(args) == 0 or len(args) > 1 or parse_fast_mode_arg(args[0]) is None
    if subcommand == "permissions":
        return len(args) == 0 or len(args) > 1 or parse_permissions_mode_arg(args[0]) is None
    if subcommand in ("compact", "review", "detach", "unbind", "stop"):
        return len(args) > 0
    return False


def parse_command_args(args: Any) -> list[str]:
    """Normalize raw subcommand args to a list (mirrors the TS
    ``string[]`` rest convention)."""
    if isinstance(args, str):
        return split_args(args)
    return [str(entry) for entry in args] if isinstance(args, list) else []


__all__ = [
    "NATIVE_CONTROL_SUBCOMMANDS",
    "NATIVE_EXECUTION_SUBCOMMANDS",
    "is_read_only_goal_command",
    "parse_command_args",
    "returns_before_execution",
]
