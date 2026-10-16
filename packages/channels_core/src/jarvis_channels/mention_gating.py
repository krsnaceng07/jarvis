"""Channel mention gating — explicit mentions, implicit mentions, command bypass.

Mirrors OpenClaw's ``src/channels/mention-gating.ts``.

Features:
- Distinguishes explicit @bot mentions from implicit mention kinds:
  - ``reply_to_bot``: sender replied directly to a bot message.
  - ``quoted_bot``: sender quoted text from the bot.
  - ``bot_thread_participant``: bot is already an active participant in this thread.
  - ``native``: platform-native mention entity or mention tag.
- Text control command bypass: allows authorized /command messages in group chats
  even without an explicit bot mention.
- Produces a clear ``InboundMentionDecision`` with ``should_skip`` and matched kinds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

InboundImplicitMentionKind = Literal[
    "reply_to_bot",
    "quoted_bot",
    "bot_thread_participant",
    "native",
]


@dataclass(frozen=True, slots=True)
class InboundMentionFacts:
    """Facts extracted from the incoming message regarding mentions."""

    can_detect_mention: bool = True
    was_mentioned: bool = False
    has_any_mention: bool = False
    implicit_mention_kinds: tuple[InboundImplicitMentionKind, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class InboundMentionPolicy:
    """Channel and group policy configuration for mention gating."""

    is_group: bool = False
    require_mention: bool = False
    implicit_mentions: dict[str, bool] | None = None
    allowed_implicit_mention_kinds: tuple[InboundImplicitMentionKind, ...] | None = None
    allow_text_commands: bool = True
    has_control_command: bool = False
    command_authorized: bool = False


@dataclass(frozen=True, slots=True)
class InboundMentionDecision:
    """Decision output determining whether a message turn runs or skips."""

    effective_was_mentioned: bool
    should_skip: bool
    implicit_mention: bool
    matched_implicit_mention_kinds: tuple[InboundImplicitMentionKind, ...]
    should_bypass_mention: bool


def allowed_implicit_mention_kinds_from_config(
    config: dict[str, bool] | None,
) -> tuple[InboundImplicitMentionKind, ...]:
    """Derive allowed implicit mention kinds from channel configuration."""
    cfg = config or {}
    kinds: list[InboundImplicitMentionKind] = []

    if cfg.get("reply_to_bot", True) is not False:
        kinds.append("reply_to_bot")
    if cfg.get("quoted_bot", True) is not False:
        kinds.append("quoted_bot")
    if (
        cfg.get("thread_participation", True) is not False
        and cfg.get("bot_thread_participant", True) is not False
    ):
        kinds.append("bot_thread_participant")
    kinds.append("native")

    return tuple(kinds)


def resolve_inbound_mention_decision(
    facts: InboundMentionFacts,
    policy: InboundMentionPolicy,
) -> InboundMentionDecision:
    """Resolve whether an inbound message passes mention gating requirements."""
    allowed_kinds = policy.allowed_implicit_mention_kinds
    if allowed_kinds is None:
        allowed_kinds = allowed_implicit_mention_kinds_from_config(policy.implicit_mentions)

    allowed_set = set(allowed_kinds)
    matched_kinds: tuple[InboundImplicitMentionKind, ...] = tuple(
        k for k in facts.implicit_mention_kinds if k in allowed_set
    )
    implicit_mention = len(matched_kinds) > 0

    # Authorized control commands in groups can bypass mention requirements
    # if no other entity was mentioned
    should_bypass_mention = bool(
        policy.is_group
        and policy.require_mention
        and not facts.was_mentioned
        and not facts.has_any_mention
        and policy.allow_text_commands
        and policy.command_authorized
        and policy.has_control_command
    )

    effective_was_mentioned = bool(facts.was_mentioned or implicit_mention or should_bypass_mention)

    should_skip = bool(
        policy.require_mention and facts.can_detect_mention and not effective_was_mentioned
    )

    return InboundMentionDecision(
        effective_was_mentioned=effective_was_mentioned,
        should_skip=should_skip,
        implicit_mention=implicit_mention,
        matched_implicit_mention_kinds=matched_kinds,
        should_bypass_mention=should_bypass_mention,
    )


__all__ = [
    "InboundImplicitMentionKind",
    "InboundMentionDecision",
    "InboundMentionFacts",
    "InboundMentionPolicy",
    "allowed_implicit_mention_kinds_from_config",
    "resolve_inbound_mention_decision",
]
