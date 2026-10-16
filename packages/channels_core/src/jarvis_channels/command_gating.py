"""Channel text command gating and access group authorization.

Mirrors OpenClaw's ``src/channels/command-gating.ts``.

Features:
- Distinguishes control commands (e.g. ``/status``, ``/help``, ``/reset``, ``/model``)
  from normal conversational agent prompt turns.
- Gating based on configured access groups or direct owner authorization.
- Dual-source authorizer checks (sender ID and platform-specific actor ID).
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Literal

CommandGatingModeWhenAccessGroupsOff = Literal["allow", "deny", "configured"]


@dataclass(frozen=True, slots=True)
class CommandAuthorizer:
    """One channel-specific authorization source for text control commands."""

    configured: bool
    allowed: bool


@dataclass(frozen=True, slots=True)
class CommandGateResult:
    """Outcome of command authorization gate check."""

    command_authorized: bool
    should_block: bool
    command: str | None = None
    args: tuple[str, ...] = ()


def parse_control_command(text: str | None) -> tuple[bool, str | None, tuple[str, ...]]:
    """Check if text is a control command (e.g. /status, /reset).

    Returns (is_command, command_name, arguments).
    """
    if not text or not text.strip().startswith("/"):
        return False, None, ()

    stripped = text.strip()
    try:
        parts = shlex.split(stripped)
    except Exception:
        parts = stripped.split()

    if not parts:
        return False, None, ()

    raw_cmd = parts[0]
    # Handle bot handle suffix: e.g. /status@JarvisBot -> /status
    if "@" in raw_cmd:
        raw_cmd = raw_cmd.split("@", 1)[0]

    cmd_name = raw_cmd.lstrip("/").lower()
    return True, cmd_name, tuple(parts[1:])


def resolve_command_authorized_from_authorizers(
    use_access_groups: bool,
    authorizers: list[CommandAuthorizer],
    mode_when_access_groups_off: CommandGatingModeWhenAccessGroupsOff = "allow",
) -> bool:
    """Determine whether any configured authorizer permits a control command."""
    if not use_access_groups:
        if mode_when_access_groups_off == "allow":
            return True
        if mode_when_access_groups_off == "deny":
            return False
        # "configured" preserves open-by-default until at least one authorizer is configured
        any_configured = any(a.configured for a in authorizers)
        if not any_configured:
            return True
        return any(a.configured and a.allowed for a in authorizers)

    return any(a.configured and a.allowed for a in authorizers)


def resolve_control_command_gate(
    use_access_groups: bool,
    authorizers: list[CommandAuthorizer],
    allow_text_commands: bool,
    has_control_command: bool,
    mode_when_access_groups_off: CommandGatingModeWhenAccessGroupsOff = "allow",
    command_name: str | None = None,
    command_args: tuple[str, ...] = (),
) -> CommandGateResult:
    """Resolve command authorization and whether the text command should be blocked."""
    command_authorized = resolve_command_authorized_from_authorizers(
        use_access_groups=use_access_groups,
        authorizers=authorizers,
        mode_when_access_groups_off=mode_when_access_groups_off,
    )
    should_block = bool(allow_text_commands and has_control_command and not command_authorized)
    return CommandGateResult(
        command_authorized=command_authorized,
        should_block=should_block,
        command=command_name,
        args=command_args,
    )


def resolve_dual_text_control_command_gate(
    use_access_groups: bool,
    primary_configured: bool,
    primary_allowed: bool,
    secondary_configured: bool,
    secondary_allowed: bool,
    has_control_command: bool,
    mode_when_access_groups_off: CommandGatingModeWhenAccessGroupsOff = "allow",
    command_name: str | None = None,
    command_args: tuple[str, ...] = (),
) -> CommandGateResult:
    """Dual-identity gate checking both primary (sender) and secondary (actor) identities."""
    return resolve_control_command_gate(
        use_access_groups=use_access_groups,
        authorizers=[
            CommandAuthorizer(configured=primary_configured, allowed=primary_allowed),
            CommandAuthorizer(configured=secondary_configured, allowed=secondary_allowed),
        ],
        allow_text_commands=True,
        has_control_command=has_control_command,
        mode_when_access_groups_off=mode_when_access_groups_off,
        command_name=command_name,
        command_args=command_args,
    )


__all__ = [
    "CommandAuthorizer",
    "CommandGateResult",
    "CommandGatingModeWhenAccessGroupsOff",
    "parse_control_command",
    "resolve_command_authorized_from_authorizers",
    "resolve_control_command_gate",
    "resolve_dual_text_control_command_gate",
]
