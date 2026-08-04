"""jarvis.config.types_messages — message queue + delivery config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.messages.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Mention patterns mode.
MentionPatternsMode = Literal["allow", "deny"]

#: Group-chat visible-replies mode.
VisibleRepliesMode = Literal["automatic", "message_tool"]

#: Group-chat unmentioned-inbound mode.
UnmentionedInboundMode = Literal["user_request", "room_event"]

#: Native commands setting (bool or "auto").
NativeCommandsSetting = bool | str  # bool | "auto"

#: Owner display mode.
CommandOwnerDisplay = Literal["raw", "hash"]

#: Broadcast strategy.
BroadcastStrategy = Literal["parallel", "sequential"]


class MentionPatternsPolicyConfig(TypedDict, total=False):
    mode: str
    allowIn: list
    denyIn: list


class GroupChatConfig(TypedDict, total=False):
    mentionPatterns: list
    historyLimit: int
    unmentionedInbound: str
    visibleReplies: str


class DmConfig(TypedDict, total=False):
    historyLimit: int


class QueueConfig(TypedDict, total=False):
    mode: str
    byChannel: dict
    debounceMs: int
    debounceMsByChannel: dict
    cap: int
    drop: str


#: Per-channel debounce overrides (ms).
InboundDebounceByProvider = dict


class InboundDebounceConfig(TypedDict, total=False):
    debounceMs: int
    byChannel: InboundDebounceByProvider


class StatusReactionsEmojiConfig(TypedDict, total=False):
    queued: str
    thinking: str
    tool: str
    coding: str
    web: str
    deploy: str
    build: str
    concierge: str
    done: str
    error: str
    stallSoft: str
    stallHard: str
    compacting: str


class StatusReactionsTimingConfig(TypedDict, total=False):
    debounceMs: int
    stallSoftMs: int
    stallHardMs: int
    doneHoldMs: int
    errorHoldMs: int


class StatusReactionsConfig(TypedDict, total=False):
    enabled: bool
    emojis: StatusReactionsEmojiConfig
    timing: StatusReactionsTimingConfig


class MessagesConfig(TypedDict, total=False):
    messagePrefix: str
    visibleReplies: str
    responsePrefix: str
    usageTemplate: object
    responseUsage: object
    groupChat: GroupChatConfig
    queue: QueueConfig
    inbound: InboundDebounceConfig
    ackReaction: str
    ackReactionScope: str
    removeAckAfterReply: bool
    statusReactions: StatusReactionsConfig
    suppressToolErrors: bool
    tts: dict


#: Per-provider allowlist for command authorization.
CommandAllowFrom = dict


class CommandsConfig(TypedDict, total=False):
    native: object
    nativeSkills: object
    text: bool
    bash: bool
    bashForegroundMs: int
    config: bool
    mcp: bool
    plugins: bool
    debug: bool
    restart: bool
    useAccessGroups: bool
    ownerAllowFrom: list
    ownerDisplay: str
    ownerDisplaySecret: str
    allowFrom: CommandAllowFrom


class ProviderCommandsConfig(TypedDict, total=False):
    native: object
    nativeSkills: object


__all__ = [
    "MentionPatternsMode",
    "VisibleRepliesMode",
    "UnmentionedInboundMode",
    "NativeCommandsSetting",
    "CommandOwnerDisplay",
    "BroadcastStrategy",
    "MentionPatternsPolicyConfig",
    "GroupChatConfig",
    "DmConfig",
    "QueueConfig",
    "InboundDebounceByProvider",
    "InboundDebounceConfig",
    "StatusReactionsEmojiConfig",
    "StatusReactionsTimingConfig",
    "StatusReactionsConfig",
    "MessagesConfig",
    "CommandAllowFrom",
    "CommandsConfig",
    "ProviderCommandsConfig",
]
