"""Conversation-level Codex control parsing.

OpenClaw parity: mirrors the parser subset of
``openclaw-main/extensions/codex/src/conversation-control.ts``
(``parseCodexFastModeArg``, ``parseCodexPermissionsModeArg``,
``formatPermissionsMode``).
"""

from __future__ import annotations

from typing import Any


def parse_fast_mode_arg(arg: Any) -> bool | None:
    """Parse a ``/codex fast`` mode argument. Mirrors
    ``parseCodexFastModeArg``: ``on``/``true``/``fast`` → True,
    ``off``/``false``/``flex`` → False, ``status``/blank/unknown → None."""
    normalized = arg.strip().lower() if isinstance(arg, str) else ""
    if not normalized or normalized == "status":
        return None
    if normalized in ("on", "true", "fast"):
        return True
    if normalized in ("off", "false", "flex"):
        return False
    return None


def parse_permissions_mode_arg(arg: Any) -> str | None:
    """Parse a ``/codex permissions`` mode argument. Mirrors
    ``parseCodexPermissionsModeArg``: yolo-family → ``"yolo"``,
    default-family → ``"default"``, ``status``/blank/unknown → None."""
    normalized = arg.strip().lower() if isinstance(arg, str) else ""
    if not normalized or normalized == "status":
        return None
    if normalized in ("yolo", "full", "full-access"):
        return "yolo"
    if normalized in ("default", "guardian", "guarded", "approve"):
        return "default"
    return None


def format_permissions_mode(mode: Any) -> str:
    """Mirror ``formatPermissionsMode`` (``full`` → ``full access``)."""
    return "full access" if mode == "full" else (mode or "default")


__all__ = [
    "format_permissions_mode",
    "parse_fast_mode_arg",
    "parse_permissions_mode_arg",
]
