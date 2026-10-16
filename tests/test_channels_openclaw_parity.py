"""OpenClaw channel parity test suite.

Tests full parity with OpenClaw's channel architecture and subsystems:
- Status reaction controller (state machine, debouncing, tool emojis, stall detection)
- Typing indicator lifecycle (keepalive loop, start guard concurrency, circuit breaker, safety TTL)
- Mention gating (explicit mentions, implicit mentions: reply_to_bot, quoted_bot, thread_participant, command bypass)
- Command gating & access groups (control command parsing, authorizers, dual identity)
- Direct DM security policy (open, allowlist, pairing, disabled)
- Canonical conversation resolution (prefix stripping, thread qualifiers, session key derivation)
- Progress draft compositor (plan checklists, diffstat, tool status lines, compact receipts)
- 5-stage turn pipeline (ingest -> classify -> preflight -> assemble -> dispatch -> finalize)
"""

from __future__ import annotations

import asyncio
import pytest

from jarvis_channels import (
    AllowlistPolicy,
    AssembledChannelTurn,
    ChannelProgressDraftCompositor,
    ChannelProgressReceiptTracker,
    ChannelTurnDeliveryAdapter,
    ChannelTurnResult,
    ChannelTurnRunner,
    DefaultChannelDeliveryAdapter,
    InboundMentionFacts,
    InboundMentionPolicy,
    OutboundMessage,
    StatusReactionEmojis,
    StatusReactionTiming,
    TypingStartGuard,
    create_status_reaction_controller,
    create_typing_callbacks,
    derive_canonical_session_key,
    extract_thread_qualifier,
    format_diffstat,
    format_plan_step,
    format_progress_line,
    parse_control_command,
    resolve_canonical_conversation,
    resolve_control_command_gate,
    resolve_dual_text_control_command_gate,
    resolve_inbound_direct_dm_access,
    resolve_inbound_mention_decision,
    resolve_tool_emoji,
    strip_target_prefix,
)


# ── Status Reactions Tests ────────────────────────────────────────────


class MockStatusReactionAdapter:
    def __init__(self) -> None:
        self.reactions: list[str] = []
        self.cleared = False

    async def set_reaction(self, emoji: str) -> None:
        self.reactions.append(emoji)

    async def clear_reaction(self) -> None:
        self.cleared = True

    async def remove_reaction(self, emoji: str) -> None:
        if emoji in self.reactions:
            self.reactions.remove(emoji)


class TestStatusReactions:
    def test_tool_emoji_mapping(self) -> None:
        emojis = StatusReactionEmojis()
        assert resolve_tool_emoji("exec", emojis) == "💻"
        assert resolve_tool_emoji("bash", emojis) == "💻"
        assert resolve_tool_emoji("read_file", emojis) == "💻"
        assert resolve_tool_emoji("web_search", emojis) == "🌐"
        assert resolve_tool_emoji("browser", emojis) == "🌐"
        assert resolve_tool_emoji("fastlane_deploy", emojis) == "🛫"
        assert resolve_tool_emoji("cmake_build", emojis) == "🏗️"
        assert resolve_tool_emoji("playwright_click", emojis) == "💁"
        assert resolve_tool_emoji("unknown_tool", emojis) == "🛠️"
        assert resolve_tool_emoji(None, emojis) == "🛠️"

    @pytest.mark.asyncio
    async def test_status_reaction_lifecycle(self) -> None:
        adapter = MockStatusReactionAdapter()
        timing = StatusReactionTiming(debounce_ms=10.0, stall_soft_ms=100.0)
        controller = create_status_reaction_controller(adapter=adapter, timing=timing)

        await controller.set_queued()
        assert controller.current_emoji == "👀"
        assert adapter.reactions == ["👀"]

        await controller.set_thinking()
        await asyncio.sleep(0.02)
        assert controller.current_emoji == "🧠"

        await controller.set_tool("web_search")
        await asyncio.sleep(0.02)
        assert controller.current_emoji == "🌐"

        await controller.set_done()
        assert controller.current_emoji == "✅"
        assert controller.is_finished

        # Terminal state protection: further updates ignored
        await controller.set_thinking()
        await asyncio.sleep(0.02)
        assert controller.current_emoji == "✅"

    @pytest.mark.asyncio
    async def test_status_reaction_debouncing(self) -> None:
        adapter = MockStatusReactionAdapter()
        timing = StatusReactionTiming(debounce_ms=50.0)
        controller = create_status_reaction_controller(adapter=adapter, timing=timing)

        await controller.set_queued()
        # Rapid intermediate updates
        await controller.set_thinking()
        await controller.set_tool("read")
        await controller.set_tool("web_search")

        # Before debounce completes, emoji is still initial
        assert controller.current_emoji == "👀"

        await asyncio.sleep(0.07)
        # Only latest tool emoji applied
        assert controller.current_emoji == "🌐"


# ── Typing Lifecycle Tests ────────────────────────────────────────────


class TestTypingLifecycle:
    @pytest.mark.asyncio
    async def test_typing_keepalive_loop(self) -> None:
        ticks = 0

        async def _tick() -> None:
            nonlocal ticks
            ticks += 1

        callbacks = create_typing_callbacks(
            start=_tick,
            keepalive_interval_s=0.03,
        )

        await callbacks.on_reply_start()
        assert ticks == 1  # Initial tick

        await asyncio.sleep(0.08)
        assert ticks >= 2  # Keepalive ticked

        if callbacks.on_idle:
            callbacks.on_idle()

        stopped_ticks = ticks
        await asyncio.sleep(0.05)
        assert ticks == stopped_ticks

    @pytest.mark.asyncio
    async def test_typing_circuit_breaker(self) -> None:
        call_count = 0

        async def _failing_start() -> None:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Platform API rate limit")

        guard = TypingStartGuard(max_consecutive_failures=2)
        assert not guard.is_tripped()

        await guard.run(_failing_start)
        assert not guard.is_tripped()

        await guard.run(_failing_start)
        assert guard.is_tripped()

        # Tripped guard blocks further runs
        await guard.run(_failing_start)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_typing_safety_ttl(self) -> None:
        ticks = 0
        stopped = False

        async def _start() -> None:
            nonlocal ticks
            ticks += 1

        async def _stop() -> None:
            nonlocal stopped
            stopped = True

        callbacks = create_typing_callbacks(
            start=_start,
            stop=_stop,
            keepalive_interval_s=0.05,
            safety_ttl_s=0.08,
        )

        await callbacks.on_reply_start()
        assert ticks == 1

        await asyncio.sleep(0.12)
        # Safety TTL auto-stopped the typing loop
        assert stopped


# ── Mention Gating Tests ──────────────────────────────────────────────


class TestMentionGating:
    def test_explicit_mention_passes(self) -> None:
        facts = InboundMentionFacts(
            can_detect_mention=True,
            was_mentioned=True,
        )
        policy = InboundMentionPolicy(
            is_group=True,
            require_mention=True,
        )
        dec = resolve_inbound_mention_decision(facts, policy)
        assert not dec.should_skip
        assert dec.effective_was_mentioned

    def test_unmentioned_in_group_skipped(self) -> None:
        facts = InboundMentionFacts(
            can_detect_mention=True,
            was_mentioned=False,
        )
        policy = InboundMentionPolicy(
            is_group=True,
            require_mention=True,
        )
        dec = resolve_inbound_mention_decision(facts, policy)
        assert dec.should_skip
        assert not dec.effective_was_mentioned

    def test_implicit_mention_reply_to_bot(self) -> None:
        facts = InboundMentionFacts(
            can_detect_mention=True,
            was_mentioned=False,
            implicit_mention_kinds=("reply_to_bot",),
        )
        policy = InboundMentionPolicy(
            is_group=True,
            require_mention=True,
        )
        dec = resolve_inbound_mention_decision(facts, policy)
        assert not dec.should_skip
        assert dec.implicit_mention
        assert "reply_to_bot" in dec.matched_implicit_mention_kinds

    def test_authorized_control_command_bypass(self) -> None:
        facts = InboundMentionFacts(
            can_detect_mention=True,
            was_mentioned=False,
            has_any_mention=False,
        )
        policy = InboundMentionPolicy(
            is_group=True,
            require_mention=True,
            allow_text_commands=True,
            has_control_command=True,
            command_authorized=True,
        )
        dec = resolve_inbound_mention_decision(facts, policy)
        assert not dec.should_skip
        assert dec.should_bypass_mention


# ── Command Gating Tests ──────────────────────────────────────────────


class TestCommandGating:
    def test_parse_control_command(self) -> None:
        is_cmd, name, args = parse_control_command("/status")
        assert is_cmd and name == "status" and args == ()

        is_cmd, name, args = parse_control_command("/model@JarvisBot claude-3-5-sonnet")
        assert is_cmd and name == "model" and args == ("claude-3-5-sonnet",)

        is_cmd, name, args = parse_control_command("hello world")
        assert not is_cmd and name is None

    def test_command_authorization(self) -> None:
        gate = resolve_control_command_gate(
            use_access_groups=True,
            authorizers=[],
            allow_text_commands=True,
            has_control_command=True,
        )
        assert not gate.command_authorized
        assert gate.should_block

    def test_dual_command_gate(self) -> None:
        # Secondary actor is authorized
        gate = resolve_dual_text_control_command_gate(
            use_access_groups=True,
            primary_configured=False,
            primary_allowed=False,
            secondary_configured=True,
            secondary_allowed=True,
            has_control_command=True,
            command_name="reset",
        )
        assert gate.command_authorized
        assert not gate.should_block
        assert gate.command == "reset"


# ── Direct DM Security Tests ──────────────────────────────────────────


class TestDirectDmSecurity:
    def test_dm_open_policy(self) -> None:
        dec = resolve_inbound_direct_dm_access(
            sender_id="user_123",
            dm_policy="open",
        )
        assert dec.decision == "allow"

    def test_dm_allowlist_policy(self) -> None:
        dec = resolve_inbound_direct_dm_access(
            sender_id="user_123",
            dm_policy="allowlist",
            allow_from=["user_123", "user_456"],
        )
        assert dec.decision == "allow"

        dec_blocked = resolve_inbound_direct_dm_access(
            sender_id="user_999",
            dm_policy="allowlist",
            allow_from=["user_123"],
        )
        assert dec_blocked.decision == "block"

    def test_dm_pairing_policy(self) -> None:
        # Unknown sender requires pairing
        dec_pair = resolve_inbound_direct_dm_access(
            sender_id="user_unknown",
            dm_policy="pairing",
            paired_senders=set(),
        )
        assert dec_pair.decision == "pairing"

        # Already paired sender is allowed
        dec_paired = resolve_inbound_direct_dm_access(
            sender_id="user_unknown",
            dm_policy="pairing",
            paired_senders={"user_unknown"},
        )
        assert dec_paired.decision == "allow"


# ── Conversation Resolution Tests ─────────────────────────────────────


class TestConversationResolution:
    def test_strip_target_prefix(self) -> None:
        assert strip_target_prefix("user:12345") == "12345"
        assert strip_target_prefix("spaces/room_abc") == "room_abc"
        assert strip_target_prefix("group:987") == "987"
        assert strip_target_prefix("regular_id") == "regular_id"

    def test_extract_thread_qualifier(self) -> None:
        conv, thread = extract_thread_qualifier("chat_123:thread:thread_456")
        assert conv == "chat_123"
        assert thread == "thread_456"

        conv, topic = extract_thread_qualifier("forum_99:topic:77")
        assert conv == "forum_99"
        assert topic == "77"

    def test_canonical_session_key(self) -> None:
        key = derive_canonical_session_key(
            channel_id="telegram",
            peer_id="user:987654321",
            peer_kind="user",
            agent_id="default",
        )
        assert key == "agent:default:telegram:user:987654321"

        threaded_key = derive_canonical_session_key(
            channel_id="discord",
            peer_id="channel:112233",
            peer_kind="group",
            thread_id="thread_4455",
            agent_id="subagent_1",
        )
        assert threaded_key == "agent:subagent_1:discord:group:112233:thread:thread_4455"

    def test_resolve_canonical_conversation(self) -> None:
        res = resolve_canonical_conversation(
            channel_id="discord",
            conversation_id="ch_100:thread:thr_200",
            peer_kind="group",
        )
        assert res.channel_id == "discord"
        assert res.conversation_id == "ch_100"
        assert res.thread_id == "thr_200"
        assert "thread:thr_200" in res.session_key


# ── Progress Draft Compositor Tests ───────────────────────────────────


class TestProgressDraftCompositor:
    def test_format_plan_step(self) -> None:
        assert format_plan_step({"status": "completed", "title": "Index repo"}) == "[x] Index repo"
        assert format_plan_step({"status": "running", "title": "Run tests"}) == "⏳ Run tests"
        assert format_plan_step({"status": "pending", "title": "Deploy app"}) == "[ ] Deploy app"

    def test_format_diffstat(self) -> None:
        assert format_diffstat(3, 24, 8) == "`+24 -8` in 3 files"
        assert format_diffstat(1, 10, 0) == "`+10` in 1 file"

    def test_receipt_tracker(self) -> None:
        tracker = ChannelProgressReceiptTracker()
        tracker.note_reasoning()
        tracker.note_reasoning()
        tracker.note_tool_call("web_search")
        tracker.note_commentary("Looking up docs")

        summary = tracker.build_summary_line()
        assert "🧠 2 thoughts" in summary
        assert "🛠️ 1 tool call" in summary
        assert "💬 1 note" in summary

    def test_compositor_render(self) -> None:
        comp = ChannelProgressDraftCompositor(status_headline="Processing request...")
        comp.set_plan_steps(
            [
                {"status": "completed", "title": "Step 1"},
                {"status": "running", "title": "Step 2"},
            ]
        )
        comp.add_line(format_progress_line("read", "config.json"))
        comp.set_diffstat(2, 15, 3)

        rendered = comp.render()
        assert "Processing request..." in rendered
        assert "[x] Step 1" in rendered
        assert "⏳ Step 2" in rendered
        assert "📖 Read: config.json" in rendered
        assert "Changes: `+15 -3` in 2 files" in rendered


# ── 5-Stage Turn Pipeline End-to-End Tests ─────────────────────────────


class TestTurnRunnerPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_success(self) -> None:
        delivered_texts: list[str] = []
        reactions: list[str] = []
        typings: list[str] = []

        async def _mock_send(msg: OutboundMessage) -> str:
            delivered_texts.append(msg.text)
            return "msg_receipt_123"

        async def _mock_typing(conv_id: str) -> None:
            typings.append(conv_id)

        async def _mock_react(conv_id: str, msg_id: str, emoji: str) -> None:
            reactions.append(emoji)

        delivery_adapter = DefaultChannelDeliveryAdapter(
            channel_id="telegram",
            send_fn=_mock_send,
            typing_fn=_mock_typing,
            reaction_fn=_mock_react,
        )

        runner = ChannelTurnRunner(
            channel_id="telegram",
            allowlist_policy=AllowlistPolicy(["12345"]),
            dm_policy="open",
        )

        raw_inbound = {
            "channel_id": "telegram",
            "conversation_id": "conv_99",
            "sender_id": "12345",
            "text": "Hello JARVIS, run a test!",
            "message_id": "msg_001",
        }

        async def _agent_dispatch(
            turn: AssembledChannelTurn,
            da: ChannelTurnDeliveryAdapter,
        ) -> str:
            assert turn.message.sender_id == "12345"
            assert "agent:default:telegram:user:12345" in turn.session.session_key
            return "Task completed successfully!"

        finalized_results: list[ChannelTurnResult] = []

        async def _on_finalize(res: ChannelTurnResult) -> None:
            finalized_results.append(res)

        result = await runner.run_turn(
            raw_payload=raw_inbound,
            agent_dispatch_fn=_agent_dispatch,
            delivery_adapter=delivery_adapter,
            on_finalize=_on_finalize,
        )

        assert result.dispatched
        assert result.delivered
        assert result.response_text == "Task completed successfully!"
        assert result.delivery_receipt == "msg_receipt_123"
        assert len(delivered_texts) == 1
        assert delivered_texts[0] == "Task completed successfully!"
        assert len(finalized_results) == 1
        assert "👀" in reactions
        assert "✅" in reactions

    @pytest.mark.asyncio
    async def test_duplicate_message_dropped(self) -> None:
        runner = ChannelTurnRunner(channel_id="slack", dm_policy="open")
        raw = {
            "channel_id": "slack",
            "conversation_id": "c1",
            "sender_id": "u1",
            "text": "Repeat message",
            "message_id": "dupe_1",
        }

        res1 = await runner.run_turn(raw_payload=raw)
        assert res1.dispatched

        # Second submission is dropped in Stage 3 preflight
        res2 = await runner.run_turn(raw_payload=raw)
        assert not res2.dispatched
        assert res2.admission.kind == "drop"
        assert res2.admission.reason == "duplicate-message"

    @pytest.mark.asyncio
    async def test_group_mention_required_handled(self) -> None:
        runner = ChannelTurnRunner(
            channel_id="discord",
            require_mention=True,
            bot_names={"jarvis"},
        )
        raw_group_msg = {
            "channel_id": "discord",
            "conversation_id": "group_chan",
            "sender_id": "alice",
            "peer_kind": "group",
            "text": "Anyone know where the coffee machine is?",
        }

        result = await runner.run_turn(raw_payload=raw_group_msg)
        assert not result.dispatched
        assert result.admission.kind == "handled"
        assert result.admission.reason == "mention-required"

    @pytest.mark.asyncio
    async def test_pairing_required_handled(self) -> None:
        runner = ChannelTurnRunner(
            channel_id="whatsapp",
            dm_policy="pairing",
            paired_senders=set(),
        )
        raw_dm = {
            "channel_id": "whatsapp",
            "conversation_id": "wa_123",
            "sender_id": "unknown_phone_num",
            "peer_kind": "user",
            "text": "Hi bot",
        }

        result = await runner.run_turn(raw_payload=raw_dm)
        assert not result.dispatched
        assert result.admission.kind == "handled"
        assert result.admission.reason == "dm_policy_pairing_required"

    @pytest.mark.asyncio
    async def test_dispatch_error_handling(self) -> None:
        reactions: list[str] = []

        async def _mock_react(conv_id: str, msg_id: str, emoji: str) -> None:
            reactions.append(emoji)

        delivery_adapter = DefaultChannelDeliveryAdapter(
            channel_id="telegram",
            send_fn=lambda m: asyncio.sleep(0),
            reaction_fn=_mock_react,
        )

        runner = ChannelTurnRunner(channel_id="telegram", dm_policy="open")

        async def _failing_dispatch(
            turn: AssembledChannelTurn, da: ChannelTurnDeliveryAdapter
        ) -> str:
            raise RuntimeError("Agent crashed during execution")

        raw = {
            "channel_id": "telegram",
            "conversation_id": "c1",
            "sender_id": "u1",
            "text": "Do something",
            "message_id": "m1",
        }

        result = await runner.run_turn(
            raw_payload=raw,
            agent_dispatch_fn=_failing_dispatch,
            delivery_adapter=delivery_adapter,
        )

        assert result.dispatched
        assert result.error is not None
        assert "Agent crashed during execution" in result.error
        assert "❌" in reactions
