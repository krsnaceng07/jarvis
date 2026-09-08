"""Pure argument parsers for `/codex` subcommands.

OpenClaw parity: mirrors the parser subset of
``openclaw-main/extensions/codex/src/command-handler-args.ts``
(``splitArgs``, ``parseBindArgs``, ``parseResumeArgs``,
``parseCodexCliSessionsArgs``, ``isMenuVerb``).

Invalid input sets ``help=True`` (the caller shows usage) instead of
raising, exactly like the source.
"""

from __future__ import annotations

from typing import Any


def split_args(value: Any) -> list[str]:
    """Split chat text into argv tokens. Mirrors ``splitArgs``: quotes
    group, backslash escapes outside single quotes, trailing lone
    backslash is kept literally, whitespace splits, empty tokens drop."""
    text = value if isinstance(value, str) else ""
    args: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaping = False
    token_started = False
    for char in text:
        if escaping:
            current.append(char)
            escaping = False
            token_started = True
            continue
        if char == "\\" and quote != "'":
            escaping = True
            token_started = True
            continue
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
            token_started = True
            continue
        if char in ("'", '"'):
            quote = char
            token_started = True
            continue
        if char.isspace():
            if token_started:
                args.append("".join(current))
                current = []
                token_started = False
            continue
        current.append(char)
        token_started = True
    if escaping:
        current.append("\\")
    if token_started:
        args.append("".join(current))
    return args


def is_menu_verb(rest: list[str]) -> bool:
    """Mirror ``isMenuVerb`` (single ``menu`` token)."""
    return len(rest) == 1 and rest[0].strip().lower() == "menu"


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _read_required_option_value(args: list[str], index: int) -> str | None:
    """Mirror ``readRequiredOptionValue``: next token unless blank or flag."""
    if index + 1 >= len(args):
        return None
    value = args[index + 1]
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed or trimmed.startswith("-"):
        return None
    return value


def parse_bind_args(args: list[str]) -> dict[str, Any]:
    """Parse ``/codex bind [thread-id] [--cwd] [--model] [--provider]``.
    Mirrors ``parseBindArgs`` (``--provider``/``--model-provider`` aliases)."""
    parsed: dict[str, Any] = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("--help", "-h"):
            parsed["help"] = True
        elif arg == "--cwd":
            value = _read_required_option_value(args, index)
            if not value or parsed.get("cwd") is not None:
                parsed["help"] = True
            else:
                parsed["cwd"] = value
                index += 1
        elif arg == "--model":
            value = _read_required_option_value(args, index)
            if not value or parsed.get("model") is not None:
                parsed["help"] = True
            else:
                parsed["model"] = value
                index += 1
        elif arg in ("--provider", "--model-provider"):
            value = _read_required_option_value(args, index)
            if not value or parsed.get("provider") is not None:
                parsed["help"] = True
            else:
                parsed["provider"] = value
                index += 1
        elif not arg.startswith("-") and parsed.get("thread_id") is None:
            parsed["thread_id"] = arg
        else:
            parsed["help"] = True
        index += 1
    for key in ("thread_id", "cwd", "model", "provider"):
        parsed[key] = _optional_str(parsed.get(key))
    return parsed


def parse_resume_args(args: list[str]) -> dict[str, Any]:
    """Parse ``/codex resume <thread-id> [--host/--node] [--bind here]``.
    Mirrors ``parseResumeArgs``."""
    parsed: dict[str, Any] = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("--help", "-h"):
            parsed["help"] = True
        elif arg in ("--host", "--node"):
            value = _read_required_option_value(args, index)
            if not value or parsed.get("host") is not None:
                parsed["help"] = True
            else:
                parsed["host"] = value
                index += 1
        elif arg == "--bind":
            value = _read_required_option_value(args, index)
            if value != "here" or parsed.get("bind_here") is not None:
                parsed["help"] = True
            else:
                parsed["bind_here"] = True
                index += 1
        elif not arg.startswith("-") and parsed.get("thread_id") is None:
            parsed["thread_id"] = arg
        else:
            parsed["help"] = True
        index += 1
    parsed["thread_id"] = _optional_str(parsed.get("thread_id"))
    parsed["host"] = _optional_str(parsed.get("host"))
    return parsed


def parse_sessions_args(args: list[str]) -> dict[str, Any]:
    """Parse ``/codex sessions [filter] [--host/--node] [--limit]``. Mirrors
    ``parseCodexCliSessionsArgs`` (positive-integer limit)."""
    parsed: dict[str, Any] = {"filter": ""}
    filters: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("--help", "-h"):
            parsed["help"] = True
        elif arg in ("--host", "--node"):
            value = _read_required_option_value(args, index)
            if not value or parsed.get("host") is not None:
                parsed["help"] = True
            else:
                parsed["host"] = value
                index += 1
        elif arg == "--limit":
            value = _read_required_option_value(args, index)
            limit = int(value) if value is not None and value.isdigit() else None
            if limit is None or limit <= 0:
                parsed["help"] = True
            else:
                parsed["limit"] = limit
                index += 1
        elif arg.startswith("-"):
            parsed["help"] = True
        else:
            filters.append(arg)
        index += 1
    parsed["host"] = _optional_str(parsed.get("host"))
    parsed["filter"] = " ".join(filters).strip()
    return parsed


__all__ = [
    "is_menu_verb",
    "parse_bind_args",
    "parse_resume_args",
    "parse_sessions_args",
    "split_args",
]
