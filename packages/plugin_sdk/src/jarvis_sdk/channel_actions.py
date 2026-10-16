"""Typed channel presentation actions — no raw-string command inference.

Mirrors OpenClaw's closed message-action vocabulary
(``src/channels/plugins/message-action-names.ts``) and the
transport-only channel rule: channels render portable
presentation actions declared by core/owner plugins; they never
guess that a ``value`` starting with ``/`` means a command.

Core/owner plugins declare one of the frozen action dataclasses
below; channel adapters map each kind to native widgets when
supported and fall back to plain text otherwise. Approval,
command, URL and select actions stay distinguishable before
channel encoding so transports never special-case product
strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union

#: Closed, core-owned message-action vocabulary. Plugins add names
#: through a core change; runtime registration is unsupported.
CHANNEL_MESSAGE_ACTION_NAMES: tuple[str, ...] = (
    "send",
    "broadcast",
    "poll",
    "poll-vote",
    "react",
    "reactions",
    "read",
    "edit",
    "unsend",
    "reply",
    "sendWithEffect",
    "renameGroup",
    "setGroupIcon",
    "addParticipant",
    "removeParticipant",
    "leaveGroup",
    "sendAttachment",
    "delete",
    "pin",
    "unpin",
    "list-pins",
    "permissions",
    "thread-create",
    "thread-list",
    "thread-reply",
    "search",
    "sticker",
    "sticker-search",
    "member-info",
    "role-info",
    "emoji-list",
    "emoji-upload",
    "sticker-upload",
    "role-add",
    "role-remove",
    "channel-info",
    "channel-list",
    "channel-create",
    "conversation-open",
    "channel-edit",
    "channel-delete",
    "channel-move",
    "category-create",
    "category-edit",
    "category-delete",
    "topic-create",
    "topic-edit",
    "voice-status",
    "event-list",
    "event-create",
    "timeout",
    "kick",
    "ban",
    "set-profile",
    "set-presence",
    "download-file",
    "upload-file",
)

_KNOWN_MESSAGE_ACTIONS: frozenset[str] = frozenset(CHANNEL_MESSAGE_ACTION_NAMES)


def is_known_message_action(name: str) -> bool:
    """Return True when ``name`` is in the closed core vocabulary."""
    return name in _KNOWN_MESSAGE_ACTIONS


#: Presentation-action kinds. Distinct kinds stay distinguishable
#: through channel encoding (never inferred from string prefixes).
ChannelActionKind = Literal["text", "command", "approval", "url", "select"]


@dataclass(frozen=True, slots=True)
class TextAction:
    """Plain portable text (fallback rendering for every transport)."""

    kind: Literal["text"] = "text"
    text: str = ""


@dataclass(frozen=True, slots=True)
class CommandAction:
    """A product command declared by core/owner plugins (leading ``/`` kept verbatim)."""

    kind: Literal["command"] = "command"
    command: str = ""
    label: str = ""


@dataclass(frozen=True, slots=True)
class ApprovalAction:
    """An explicit approve/deny prompt with an opaque approval id."""

    kind: Literal["approval"] = "approval"
    approval_id: str = ""
    label: str = ""
    approve_label: str = "Approve"
    deny_label: str = "Deny"


@dataclass(frozen=True, slots=True)
class UrlAction:
    """A link or web-app open action."""

    kind: Literal["url"] = "url"
    url: str = ""
    label: str = ""


@dataclass(frozen=True, slots=True)
class SelectAction:
    """A bounded option picker (non-empty options enforced below)."""

    kind: Literal["select"] = "select"
    options: tuple[str, ...] = field(default_factory=tuple)
    label: str = ""


#: Union of every portable presentation action a channel can render.
ChannelAction = Union[TextAction, CommandAction, ApprovalAction, UrlAction, SelectAction]


def action_kind(action: ChannelAction) -> ChannelActionKind:
    """Return the declared kind of ``action`` (no string sniffing)."""
    return action.kind


def validate_action(action: ChannelAction) -> ChannelAction:
    """Validate payload invariants; returns ``action`` unchanged.

    Raises
    ------
    ValueError
        When a ``SelectAction`` carries no options or a ``UrlAction``/
        ``CommandAction`` carries an empty payload.
    """
    if isinstance(action, SelectAction) and not action.options:
        raise ValueError("SelectAction requires at least one option")
    if isinstance(action, UrlAction) and not action.url:
        raise ValueError("UrlAction requires a non-empty url")
    if isinstance(action, CommandAction) and not action.command:
        raise ValueError("CommandAction requires a non-empty command")
    if isinstance(action, ApprovalAction) and not action.approval_id:
        raise ValueError("ApprovalAction requires a non-empty approval_id")
    return action


__all__ = [
    "ApprovalAction",
    "CHANNEL_MESSAGE_ACTION_NAMES",
    "ChannelAction",
    "ChannelActionKind",
    "CommandAction",
    "SelectAction",
    "TextAction",
    "UrlAction",
    "action_kind",
    "is_known_message_action",
    "validate_action",
]
