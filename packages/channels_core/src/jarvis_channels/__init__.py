"""jarvis_channels — JARVIS channel transport contracts.

Mirrors OpenClaw's ``src/channels/`` subsystem. Provides typed shapes
for inbound/outbound messages, channel sessions, allowlist policies,
direct DM security & pairing, mention gating with implicit kinds,
text command gating & access groups, canonical conversation resolution,
status reactions controller, typing lifecycle with keepalives,
progress draft compositor, session bindings, and the canonical 5-stage
turn execution pipeline.
"""

from __future__ import annotations

from .allowlist import (
    ALLOW_ALL,
    AllowlistPolicy,
    is_allowed,
    normalize_allowlist,
)
from .bindings import (
    BindingRegistry,
    derive_session_key,
    derive_webhook_path,
    session_from_message,
)
from .command_gating import (
    CommandAuthorizer,
    CommandGateResult,
    CommandGatingModeWhenAccessGroupsOff,
    parse_control_command,
    resolve_command_authorized_from_authorizers,
    resolve_control_command_gate,
    resolve_dual_text_control_command_gate,
)
from .conversation_resolution import (
    CANONICAL_TARGET_PREFIXES,
    ConversationResolution,
    derive_canonical_session_key,
    extract_thread_qualifier,
    resolve_canonical_conversation,
    strip_target_prefix,
)
from .direct_dm import (
    DM_POLICY_ALLOWLISTED,
    DM_POLICY_DISABLED,
    DM_POLICY_NOT_ALLOWLISTED,
    DM_POLICY_OPEN,
    DM_POLICY_PAIRING_REQUIRED,
    DirectDmAccessDecision,
    DirectDmDecisionKind,
    DirectDmPolicyKind,
    resolve_inbound_direct_dm_access,
)
from .mention_gating import (
    InboundImplicitMentionKind,
    InboundMentionDecision,
    InboundMentionFacts,
    InboundMentionPolicy,
    allowed_implicit_mention_kinds_from_config,
    resolve_inbound_mention_decision,
)
from .presence import PresenceEmitter, ReactionEmitter
from .progress_draft_compositor import (
    DEFAULT_PROGRESS_DRAFT_LABELS,
    DEFAULT_TOOL_ICON,
    TOOL_DISPLAY_ICONS,
    ChannelProgressDraftCompositor,
    ChannelProgressReceiptTracker,
    format_diffstat,
    format_plan_step,
    format_progress_line,
    get_tool_icon,
    select_progress_label,
)
from .reply import (
    channel_limit,
    format_reply,
    sender_label,
    split_reply,
    strip_markdown,
)
from .routing import ChannelRouter, ChannelTarget
from .status_reactions import (
    BUILD_TOOL_TOKENS,
    CODING_TOOL_TOKENS,
    CONCIERGE_TOOL_TOKENS,
    DEFAULT_EMOJIS,
    DEFAULT_TIMING,
    DEPLOY_TOOL_TOKENS,
    StatusReactionAdapter,
    StatusReactionController,
    StatusReactionEmojis,
    StatusReactionTiming,
    WEB_TOOL_TOKENS,
    create_status_reaction_controller,
    resolve_tool_emoji,
)
from .turn_runner import (
    AssembledChannelTurn,
    ChannelEventClass,
    ChannelTurnAdmission,
    ChannelTurnDeliveryAdapter,
    ChannelTurnResult,
    ChannelTurnRunner,
    DefaultChannelDeliveryAdapter,
    PreflightFacts,
)
from .typing import (
    DEFAULT_KEEPALIVE_INTERVAL_S,
    DEFAULT_MAX_CONSECUTIVE_FAILURES,
    DEFAULT_SAFETY_TTL_S,
    TypingCallbacks,
    TypingIndicator,
    TypingKeepaliveLoop,
    TypingStartGuard,
    create_typing_callbacks,
)
from .types import ChannelSession, InboundMessage, OutboundMessage

__all__ = [
    # Types
    "InboundMessage",
    "OutboundMessage",
    "ChannelSession",
    # Routing & Resolution
    "ChannelTarget",
    "ChannelRouter",
    "CANONICAL_TARGET_PREFIXES",
    "ConversationResolution",
    "strip_target_prefix",
    "extract_thread_qualifier",
    "derive_canonical_session_key",
    "resolve_canonical_conversation",
    # Turn Runner (5-stage OpenClaw pipeline)
    "ChannelTurnRunner",
    "ChannelTurnResult",
    "ChannelTurnAdmission",
    "ChannelEventClass",
    "PreflightFacts",
    "AssembledChannelTurn",
    "ChannelTurnDeliveryAdapter",
    "DefaultChannelDeliveryAdapter",
    # Status Reactions
    "StatusReactionAdapter",
    "StatusReactionController",
    "StatusReactionEmojis",
    "StatusReactionTiming",
    "DEFAULT_EMOJIS",
    "DEFAULT_TIMING",
    "CODING_TOOL_TOKENS",
    "WEB_TOOL_TOKENS",
    "DEPLOY_TOOL_TOKENS",
    "BUILD_TOOL_TOKENS",
    "CONCIERGE_TOOL_TOKENS",
    "resolve_tool_emoji",
    "create_status_reaction_controller",
    # Typing Lifecycle
    "TypingStartGuard",
    "TypingKeepaliveLoop",
    "TypingCallbacks",
    "TypingIndicator",
    "create_typing_callbacks",
    "DEFAULT_KEEPALIVE_INTERVAL_S",
    "DEFAULT_MAX_CONSECUTIVE_FAILURES",
    "DEFAULT_SAFETY_TTL_S",
    # Mention Gating
    "InboundImplicitMentionKind",
    "InboundMentionFacts",
    "InboundMentionPolicy",
    "InboundMentionDecision",
    "allowed_implicit_mention_kinds_from_config",
    "resolve_inbound_mention_decision",
    # Command Gating
    "CommandAuthorizer",
    "CommandGateResult",
    "CommandGatingModeWhenAccessGroupsOff",
    "parse_control_command",
    "resolve_command_authorized_from_authorizers",
    "resolve_control_command_gate",
    "resolve_dual_text_control_command_gate",
    # Direct DM Security & Pairing
    "DirectDmPolicyKind",
    "DirectDmDecisionKind",
    "DirectDmAccessDecision",
    "DM_POLICY_OPEN",
    "DM_POLICY_DISABLED",
    "DM_POLICY_ALLOWLISTED",
    "DM_POLICY_PAIRING_REQUIRED",
    "DM_POLICY_NOT_ALLOWLISTED",
    "resolve_inbound_direct_dm_access",
    # Progress Draft Compositor
    "ChannelProgressDraftCompositor",
    "ChannelProgressReceiptTracker",
    "DEFAULT_PROGRESS_DRAFT_LABELS",
    "DEFAULT_TOOL_ICON",
    "TOOL_DISPLAY_ICONS",
    "get_tool_icon",
    "select_progress_label",
    "format_progress_line",
    "format_diffstat",
    "format_plan_step",
    # Allowlist
    "ALLOW_ALL",
    "AllowlistPolicy",
    "is_allowed",
    "normalize_allowlist",
    # Bindings
    "BindingRegistry",
    "derive_session_key",
    "derive_webhook_path",
    "session_from_message",
    # Presence
    "PresenceEmitter",
    "ReactionEmitter",
    # Reply
    "channel_limit",
    "format_reply",
    "split_reply",
    "sender_label",
    "strip_markdown",
]
