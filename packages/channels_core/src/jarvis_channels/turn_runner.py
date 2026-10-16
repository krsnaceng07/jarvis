"""Channel Turn Runner — 5-stage OpenClaw turn execution pipeline.

Mirrors OpenClaw's:
- ``src/channels/turn/run-channel-turn.ts``
- ``src/channels/turn/lifecycle.ts``
- ``src/channels/turn/types.ts``

Pipeline stages:
  1. Ingest:    Normalize raw platform payload into InboundMessage.
  2. Classify:  Determine event class (message vs typing vs reaction vs action).
  3. Preflight: Evaluate dedupe, allowlist, direct DM policy, mention gating,
                and control command gating. Record dropped history on drops.
  4. Assemble:  Resolve canonical sessionKey, conversation, and active bindings.
  5. Dispatch:  Execute agent turn orchestrated with StatusReactionController,
                TypingCallbacks keepalive loop, and ProgressDraftCompositor.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from .allowlist import AllowlistPolicy
from .bindings import BindingRegistry
from .command_gating import (
    CommandAuthorizer,
    CommandGateResult,
    parse_control_command,
    resolve_control_command_gate,
)
from .conversation_resolution import (
    ConversationResolution,
    resolve_canonical_conversation,
)
from .direct_dm import (
    DirectDmAccessDecision,
    DirectDmPolicyKind,
    resolve_inbound_direct_dm_access,
)
from .mention_gating import (
    InboundImplicitMentionKind,
    InboundMentionDecision,
    InboundMentionFacts,
    InboundMentionPolicy,
    resolve_inbound_mention_decision,
)
from .status_reactions import (
    create_status_reaction_controller,
)
from .typing import create_typing_callbacks
from .types import ChannelSession, InboundMessage, OutboundMessage

_log = logging.getLogger("jarvis_channels.turn_runner")


def _raw_message_id(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    direct = raw.get("message_id")
    if direct:
        return str(direct)
    nested = raw.get("raw")
    if isinstance(nested, dict) and nested.get("message_id"):
        return str(nested["message_id"])
    return ""


# ── Turn Stages & Shapes ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ChannelEventClass:
    """Classification of an inbound channel event."""

    kind: str = "message"  # message, reaction, typing, action, delivery_ack
    can_start_agent_turn: bool = True


@dataclass(frozen=True, slots=True)
class ChannelTurnAdmission:
    """Admission decision from turn preflight / classification."""

    kind: str  # dispatch, observeOnly, handled, drop
    reason: str | None = None
    record_history: bool = False


@dataclass(frozen=True, slots=True)
class PreflightFacts:
    """Context gathered during Stage 3 preflight checks."""

    admission: ChannelTurnAdmission
    dm_access: DirectDmAccessDecision | None = None
    mention_decision: InboundMentionDecision | None = None
    command_gate: CommandGateResult | None = None
    is_duplicate: bool = False


@dataclass(frozen=True, slots=True)
class AssembledChannelTurn:
    """Context assembled for dispatch into the agent turn loop."""

    turn_id: str
    message: InboundMessage
    session: ChannelSession
    target_agent_id: str
    conversation: ConversationResolution | None = None
    command_gate: CommandGateResult | None = None
    is_subagent_binding: bool = False
    binding_id: str | None = None
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class ChannelTurnResult:
    """Result of a completed or dropped channel turn."""

    turn_id: str
    admission: ChannelTurnAdmission
    dispatched: bool
    response_text: str | None = None
    delivered: bool = False
    delivery_receipt: Any | None = None
    duration_ms: float = 0.0
    error: str | None = None
    session_key: str | None = None


# ── Delivery Adapter Protocol ─────────────────────────────────────────


@runtime_checkable
class ChannelTurnDeliveryAdapter(Protocol):
    """Adapter protocol through which the turn runner sends outbound responses."""

    async def deliver_text(
        self,
        conversation_id: str,
        text: str,
        reply_to_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any: ...

    async def deliver_typing(
        self,
        conversation_id: str,
        duration_s: float = 2.0,
    ) -> None: ...

    async def deliver_reaction(
        self,
        conversation_id: str,
        message_id: str,
        emoji: str,
    ) -> None: ...

    async def deliver_draft_preview(
        self,
        conversation_id: str,
        draft_text: str,
        draft_id: str | None = None,
    ) -> str | None: ...

    async def finalize_draft_preview(
        self,
        conversation_id: str,
        final_text: str,
        draft_id: str | None = None,
    ) -> Any: ...


# ── Default Delivery Adapter ──────────────────────────────────────────


class DefaultChannelDeliveryAdapter:
    """Default delivery adapter delegating to outbound send callbacks."""

    def __init__(
        self,
        channel_id: str,
        send_fn: Callable[[OutboundMessage], Awaitable[Any]],
        typing_fn: Callable[[str], Awaitable[None]] | None = None,
        reaction_fn: Callable[[str, str, str], Awaitable[None]] | None = None,
        draft_preview_fn: Callable[[str, str, str | None], Awaitable[str | None]] | None = None,
        finalize_draft_fn: Callable[[str, str, str | None], Awaitable[Any]] | None = None,
    ) -> None:
        self.channel_id = channel_id
        self._send_fn = send_fn
        self._typing_fn = typing_fn
        self._reaction_fn = reaction_fn
        self._draft_preview_fn = draft_preview_fn
        self._finalize_draft_fn = finalize_draft_fn

    async def deliver_text(
        self,
        conversation_id: str,
        text: str,
        reply_to_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        msg = OutboundMessage(
            channel_id=self.channel_id,
            conversation_id=conversation_id,
            text=text,
            reply_to_id=reply_to_id,
            metadata=metadata or {},
        )
        return await self._send_fn(msg)

    async def deliver_typing(self, conversation_id: str, duration_s: float = 2.0) -> None:
        if self._typing_fn is not None:
            await self._typing_fn(conversation_id)

    async def deliver_reaction(
        self,
        conversation_id: str,
        message_id: str,
        emoji: str,
    ) -> None:
        if self._reaction_fn is not None:
            await self._reaction_fn(conversation_id, message_id, emoji)

    async def deliver_draft_preview(
        self,
        conversation_id: str,
        draft_text: str,
        draft_id: str | None = None,
    ) -> str | None:
        if self._draft_preview_fn is not None:
            return await self._draft_preview_fn(conversation_id, draft_text, draft_id)
        return draft_id

    async def finalize_draft_preview(
        self,
        conversation_id: str,
        final_text: str,
        draft_id: str | None = None,
    ) -> Any:
        if self._finalize_draft_fn is not None:
            return await self._finalize_draft_fn(conversation_id, final_text, draft_id)
        return await self.deliver_text(conversation_id, final_text)


# ── Channel Turn Runner ───────────────────────────────────────────────


class ChannelTurnRunner:
    """Executes the full 5-stage OpenClaw turn pipeline for an incoming message."""

    def __init__(
        self,
        channel_id: str = "default",
        allowlist_policy: AllowlistPolicy | list[str] | set[str] | str | None = None,
        binding_registry: BindingRegistry | None = None,
        require_mention: bool = False,
        bot_names: set[str] | None = None,
        dm_policy: DirectDmPolicyKind = "open",
        paired_senders: set[str] | None = None,
        use_access_groups: bool = False,
        allow_text_commands: bool = True,
        implicit_mentions: dict[str, bool] | None = None,
        enable_status_reactions: bool = True,
        enable_typing_keepalive: bool = True,
    ) -> None:
        self.channel_id = channel_id
        if allowlist_policy is None:
            self.allowlist_policy = AllowlistPolicy()
        elif isinstance(allowlist_policy, AllowlistPolicy):
            self.allowlist_policy = allowlist_policy
        elif isinstance(allowlist_policy, set):
            self.allowlist_policy = AllowlistPolicy(allowed_senders=allowlist_policy)
        else:
            self.allowlist_policy = AllowlistPolicy(allowlist_policy)

        self.binding_registry = binding_registry or BindingRegistry()
        self.require_mention = require_mention
        self.bot_names = bot_names or {"jarvis", "openclaw"}
        self.dm_policy: DirectDmPolicyKind = dm_policy
        self.paired_senders = paired_senders or set()
        self.use_access_groups = use_access_groups
        self.allow_text_commands = allow_text_commands
        self.implicit_mentions = implicit_mentions
        self.enable_status_reactions = enable_status_reactions
        self.enable_typing_keepalive = enable_typing_keepalive
        self._seen_message_ids: set[str] = set()

    # Stage 1: Ingest
    def ingest(self, raw: Any) -> InboundMessage | None:
        """Normalize raw channel payload into InboundMessage."""
        if isinstance(raw, InboundMessage):
            return raw
        if isinstance(raw, dict):
            return InboundMessage(
                channel_id=raw.get("channel_id", self.channel_id),
                conversation_id=str(raw.get("conversation_id", "")),
                sender_id=str(raw.get("sender_id", "")),
                text=str(raw.get("text", "")),
                kind=raw.get("kind", "text"),
                raw=raw,
                is_owner=bool(raw.get("is_owner", False)),
                peer_kind=raw.get("peer_kind", "user"),
                peer_id=str(raw.get("peer_id", "")),
                account_id=raw.get("account_id"),
                thread_id=raw.get("thread_id"),
            )
        _log.warning("[%s] ingest: unsupported payload type %s", self.channel_id, type(raw))
        return None

    # Stage 2: Classify
    def classify(self, message: InboundMessage) -> ChannelEventClass:
        """Classify inbound event and determine if an agent turn should run."""
        if message.kind in ("typing", "delivery_ack"):
            return ChannelEventClass(kind=message.kind, can_start_agent_turn=False)
        # Empty text on non-media messages
        if not message.text.strip() and not message.attachments and not message.location:
            return ChannelEventClass(kind="empty_message", can_start_agent_turn=False)
        return ChannelEventClass(kind="message", can_start_agent_turn=True)

    # Stage 3: Preflight
    def preflight_facts(
        self,
        message: InboundMessage,
        event_class: ChannelEventClass,
    ) -> PreflightFacts:
        """Evaluate deduplication, allowlist, DM policy, mention and command gating."""
        # 1. Deduplication
        raw_msg_id = _raw_message_id(message.raw)
        dedupe_key = f"{message.channel_id}:{message.conversation_id}:{raw_msg_id or message.text}"
        if dedupe_key in self._seen_message_ids:
            return PreflightFacts(
                admission=ChannelTurnAdmission(kind="drop", reason="duplicate-message"),
                is_duplicate=True,
            )
        self._seen_message_ids.add(dedupe_key)
        if len(self._seen_message_ids) > 10_000:
            self._seen_message_ids.clear()

        # 2. Extract Sender Info
        sender_username = None
        if isinstance(message.raw, dict):
            sender_username = message.raw.get("username")

        is_group = message.peer_kind in ("group", "channel")

        # 3. Direct DM Security Policy Check (if direct chat)
        dm_access: DirectDmAccessDecision | None = None
        if not is_group:
            dm_access = resolve_inbound_direct_dm_access(
                sender_id=message.sender_id,
                sender_username=sender_username,
                dm_policy=self.dm_policy,
                allow_from=self.allowlist_policy,
                paired_senders=self.paired_senders,
            )
            if dm_access.decision == "block":
                return PreflightFacts(
                    admission=ChannelTurnAdmission(kind="drop", reason=dm_access.reason_code),
                    dm_access=dm_access,
                )
            if dm_access.decision == "pairing":
                return PreflightFacts(
                    admission=ChannelTurnAdmission(kind="handled", reason=dm_access.reason_code),
                    dm_access=dm_access,
                )

        # 4. Standard Allowlist check (if not already verified by DM policy)
        if not self.allowlist_policy.is_allowed(message.sender_id, sender_username):
            return PreflightFacts(
                admission=ChannelTurnAdmission(kind="drop", reason="sender-not-allowed")
            )

        # 5. Command Gating
        is_cmd, cmd_name, cmd_args = parse_control_command(message.text)
        command_gate = resolve_control_command_gate(
            use_access_groups=self.use_access_groups,
            authorizers=[
                CommandAuthorizer(
                    configured=bool(self.allowlist_policy),
                    allowed=self.allowlist_policy.is_allowed(message.sender_id, sender_username),
                )
            ],
            allow_text_commands=self.allow_text_commands,
            has_control_command=is_cmd,
            command_name=cmd_name,
            command_args=cmd_args,
        )
        if command_gate.should_block:
            return PreflightFacts(
                admission=ChannelTurnAdmission(kind="handled", reason="command-unauthorized"),
                command_gate=command_gate,
            )

        # 6. Mention Gating (Group chats)
        mention_decision: InboundMentionDecision | None = None
        if is_group:
            lower = message.text.lower()
            explicitly_mentioned = any(name in lower for name in self.bot_names)

            implicit_kinds: list[InboundImplicitMentionKind] = []
            if isinstance(message.raw, dict):
                if message.raw.get("reply_to_bot"):
                    implicit_kinds.append("reply_to_bot")
                if message.raw.get("quoted_bot"):
                    implicit_kinds.append("quoted_bot")
                if message.raw.get("bot_thread_participant"):
                    implicit_kinds.append("bot_thread_participant")

            facts = InboundMentionFacts(
                can_detect_mention=True,
                was_mentioned=explicitly_mentioned,
                has_any_mention=bool(explicitly_mentioned or "@" in message.text),
                implicit_mention_kinds=tuple(implicit_kinds),
            )
            policy = InboundMentionPolicy(
                is_group=True,
                require_mention=self.require_mention,
                implicit_mentions=self.implicit_mentions,
                allow_text_commands=self.allow_text_commands,
                has_control_command=is_cmd,
                command_authorized=command_gate.command_authorized,
            )
            mention_decision = resolve_inbound_mention_decision(facts, policy)
            if mention_decision.should_skip:
                return PreflightFacts(
                    admission=ChannelTurnAdmission(kind="handled", reason="mention-required"),
                    mention_decision=mention_decision,
                    command_gate=command_gate,
                )

        return PreflightFacts(
            admission=ChannelTurnAdmission(kind="dispatch"),
            dm_access=dm_access,
            mention_decision=mention_decision,
            command_gate=command_gate,
        )

    # Legacy preflight signature compatibility
    def preflight(
        self,
        message: InboundMessage,
        event_class: ChannelEventClass,
    ) -> ChannelTurnAdmission:
        return self.preflight_facts(message, event_class).admission

    # Stage 4: Assemble
    def assemble(
        self,
        message: InboundMessage,
        preflight: PreflightFacts | None = None,
    ) -> AssembledChannelTurn:
        """Assemble routing session key and conversation bindings."""
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"

        # Canonical conversation resolution
        conversation = resolve_canonical_conversation(
            channel_id=message.channel_id,
            conversation_id=message.conversation_id,
            peer_kind=message.peer_kind,
            peer_id=message.peer_id or message.sender_id,
            thread_id=message.thread_id,
            account_id=message.account_id,
        )

        session = self.binding_registry.get_or_create(message)
        session_key = conversation.session_key

        # Check active session bindings
        bound = self.binding_registry.get_active(session_key)
        if bound is None:
            bound = self.binding_registry.get_active(
                f"{message.channel_id}:{message.conversation_id}"
            )

        target_agent_id = "default"
        is_subagent = False
        binding_id = None

        if bound is not None:
            target_agent_id = bound.target_session_key
            is_subagent = bound.target_kind == "subagent"
            binding_id = bound.binding_id

        if target_agent_id != "default" or session.session_key != session_key:
            session = ChannelSession(
                channel_id=session.channel_id,
                session_key=session_key,
                conversation_id=conversation.conversation_id,
                agent_id=target_agent_id,
                is_owner=session.is_owner,
            )

        return AssembledChannelTurn(
            turn_id=turn_id,
            message=message,
            session=session,
            target_agent_id=target_agent_id,
            conversation=conversation,
            command_gate=preflight.command_gate if preflight else None,
            is_subagent_binding=is_subagent,
            binding_id=binding_id,
        )

    # Stage 5: Dispatch
    async def run_turn(
        self,
        raw_payload: Any,
        agent_dispatch_fn: (
            Callable[
                [AssembledChannelTurn, ChannelTurnDeliveryAdapter],
                Awaitable[str | None],
            ]
            | None
        ) = None,
        delivery_adapter: ChannelTurnDeliveryAdapter | None = None,
        on_finalize: Callable[[ChannelTurnResult], Awaitable[None]] | None = None,
    ) -> ChannelTurnResult:
        """Execute full 5-stage turn pipeline."""
        started_at = time.time()
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"

        # 1. Ingest
        message = self.ingest(raw_payload)
        if message is None:
            admission = ChannelTurnAdmission(kind="drop", reason="ingest-null")
            res = ChannelTurnResult(
                turn_id=turn_id,
                admission=admission,
                dispatched=False,
                duration_ms=(time.time() - started_at) * 1000.0,
            )
            if on_finalize:
                await on_finalize(res)
            return res

        # 2. Classify
        event_class = self.classify(message)
        if not event_class.can_start_agent_turn:
            admission = ChannelTurnAdmission(kind="handled", reason=f"event:{event_class.kind}")
            res = ChannelTurnResult(
                turn_id=turn_id,
                admission=admission,
                dispatched=False,
                duration_ms=(time.time() - started_at) * 1000.0,
            )
            if on_finalize:
                await on_finalize(res)
            return res

        # 3. Preflight
        facts = self.preflight_facts(message, event_class)
        admission = facts.admission
        if admission.kind != "dispatch":
            res = ChannelTurnResult(
                turn_id=turn_id,
                admission=admission,
                dispatched=False,
                duration_ms=(time.time() - started_at) * 1000.0,
            )
            if on_finalize:
                await on_finalize(res)
            return res

        # 4. Assemble
        assembled = self.assemble(message, facts)
        turn_id = assembled.turn_id

        # 5. Dispatch Setup
        if delivery_adapter is None:

            async def _noop_send(msg: OutboundMessage) -> Any:
                return None

            delivery_adapter = DefaultChannelDeliveryAdapter(
                channel_id=self.channel_id,
                send_fn=_noop_send,
            )

        if agent_dispatch_fn is None:

            async def _noop_dispatch(
                _assembled: AssembledChannelTurn,
                _adapter: ChannelTurnDeliveryAdapter,
            ) -> str | None:
                return None

            agent_dispatch_fn = _noop_dispatch

        # Setup Status Reaction Adapter
        class _StatusReactionAdapterImpl:
            def __init__(self, da: ChannelTurnDeliveryAdapter, conv_id: str, msg_id: str) -> None:
                self.da = da
                self.conv_id = conv_id
                self.msg_id = msg_id

            async def set_reaction(self, emoji: str) -> None:
                if self.msg_id:
                    await self.da.deliver_reaction(self.conv_id, self.msg_id, emoji)

            async def clear_reaction(self) -> None:
                pass

            async def remove_reaction(self, emoji: str) -> None:
                pass

        reply_msg_id = _raw_message_id(message.raw)

        reaction_controller = create_status_reaction_controller(
            adapter=_StatusReactionAdapterImpl(
                delivery_adapter, message.conversation_id, reply_msg_id
            ),
            enabled=self.enable_status_reactions and bool(reply_msg_id),
        )

        typing_callbacks = create_typing_callbacks(
            start=lambda: delivery_adapter.deliver_typing(message.conversation_id),
        )

        try:
            # Start status reactions (queued) and typing keepalive loop
            await reaction_controller.set_queued()
            if self.enable_typing_keepalive:
                await typing_callbacks.on_reply_start()
            else:
                await delivery_adapter.deliver_typing(message.conversation_id)

            await reaction_controller.set_thinking()

            # Execute agent turn
            response_text = await agent_dispatch_fn(assembled, delivery_adapter)
            delivered = False
            receipt = None

            if response_text is not None and response_text.strip():
                receipt = await delivery_adapter.deliver_text(
                    conversation_id=message.conversation_id,
                    text=response_text,
                    reply_to_id=reply_msg_id if reply_msg_id else None,
                )
                delivered = True

            # Mark status reactions finished
            await reaction_controller.set_done()

            result = ChannelTurnResult(
                turn_id=turn_id,
                admission=admission,
                dispatched=True,
                response_text=response_text,
                delivered=delivered,
                delivery_receipt=receipt,
                duration_ms=(time.time() - started_at) * 1000.0,
                session_key=assembled.session.session_key,
            )
        except Exception as err:
            _log.exception("[%s] turn %s dispatch failed: %s", self.channel_id, turn_id, err)
            await reaction_controller.set_error()
            result = ChannelTurnResult(
                turn_id=turn_id,
                admission=admission,
                dispatched=True,
                error=str(err),
                duration_ms=(time.time() - started_at) * 1000.0,
                session_key=assembled.session.session_key,
            )
        finally:
            if typing_callbacks.on_cleanup:
                typing_callbacks.on_cleanup()

        if on_finalize:
            try:
                await on_finalize(result)
            except Exception as e:
                _log.debug("on_finalize error: %s", e)

        return result


__all__ = [
    "AssembledChannelTurn",
    "ChannelEventClass",
    "ChannelTurnAdmission",
    "ChannelTurnDeliveryAdapter",
    "ChannelTurnResult",
    "ChannelTurnRunner",
    "DefaultChannelDeliveryAdapter",
    "PreflightFacts",
]
