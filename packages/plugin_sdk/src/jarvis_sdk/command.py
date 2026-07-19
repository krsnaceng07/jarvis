"""Plugin command context + result types.

Mirrors OpenClaw's ``PluginCommandContext`` and ``PluginCommandResult``
from ``src/plugins/plugin-command.types.ts``. The host invokes
``command.handler(ctx)`` and uses the returned ``PluginCommandResult``
to drive the agent loop.

For Phase 1C, the JARVIS host is a single live session (no multi-channel
or multi-session yet), so the context has fewer fields than OpenClaw's.
The shape is still compatible — the missing fields default to ``None``
and the host can populate them as JARVIS grows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PluginCommandContext:
    """Context passed to a plugin command's ``handler``.

    Mirrors OpenClaw's ``PluginCommandContext``. The host populates the
    fields it knows; the rest default to ``None`` for fields that aren't
    applicable to JARVIS's single-live-session runtime.

    Attributes
    ----------
    sender_id : str | None
        The sender's identifier (e.g. the operator's user id, or
        ``"operator"`` for the local live session).
    channel : str
        The surface the command was issued on (``"live"`` for the JARVIS
        live mode, ``"telegram"`` / ``"discord"`` once those channels
        land in Phase 2/3).
    is_authorized_sender : bool
        Whether the sender is on the host's allowlist. For Phase 1C
        this is always ``True`` (single-user).
    sender_is_owner : bool
        Whether the sender is the operator. Required for owner-only
        commands (e.g. ``/reminders cancel-all``).
    args : str | None
        Raw arguments after the command name (e.g. for ``/reminders list``
        this is ``"list"``).
    command_body : str
        The full normalized command body (e.g. ``"/reminders list"``).
    config : dict
        Read-only view of the host's plugin config. For Phase 1C this
        is an empty dict; populated as Phase 2 wires real config.
    """

    sender_id: str | None = None
    channel: str = "live"
    is_authorized_sender: bool = True
    sender_is_owner: bool = True
    args: str | None = None
    command_body: str = ""
    config: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PluginCommandResult:
    """Result returned by a plugin command's ``handler``.

    Mirrors OpenClaw's ``PluginCommandResult = ReplyPayload & { ... }``.
    For Phase 1C the JARVIS host only consumes ``reply_text`` and
    ``suppress_reply``; ``continue_agent`` is reserved for Phase 2+ when
    JARVIS gains a real agent loop.

    Attributes
    ----------
    reply_text : str
        The text the command wants the host to deliver to the user.
    continue_agent : bool
        If ``True``, the host's agent loop continues after the command
        returns. (Reserved for Phase 2+; ignored in 1C.)
    suppress_reply : bool
        If ``True``, the host suppresses the channel fallback reply
        (e.g. when the handler already delivered its own response).
    """

    reply_text: str = ""
    continue_agent: bool = False
    suppress_reply: bool = False


#: Async handler signature: ``async (ctx) -> PluginCommandResult``.
PluginCommandHandler = Any  # Callable[[PluginCommandContext], Awaitable[PluginCommandResult]]


__all__ = [
    "PluginCommandContext",
    "PluginCommandHandler",
    "PluginCommandResult",
]
