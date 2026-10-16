"""Phase 7.2c-1 tests — delivery_evidence."""
from __future__ import annotations


from src.agents.embedded_agent_runner.delivery_evidence import (
    collect_ambiguous_automatic_media_urls,
    collect_automatic_delivered_media_urls,
    collect_delivered_media_urls,
    get_gateway_agent_result,
    has_committed_messaging_tool_delivery_evidence,
    has_committed_source_reply_delivery_evidence,
    has_complete_automatic_media_delivery_outcome_evidence,
    has_completed_source_reply_delivery_evidence,
    has_completed_terminal_delivery_evidence,
    has_messaging_tool_delivery_evidence,
    has_unaccounted_messaging_tool_aggregate_evidence,
    has_visible_agent_payload,
    has_visible_committed_messaging_tool_delivery_evidence,
    has_visible_outbound_delivery_evidence,
    resolve_explicit_final_source_reply_delivery_evidence,
)


# ============================================================================
# resolveExplicitFinalSourceReplyDeliveryEvidence
# ============================================================================


class TestResolveExplicitFinal:
    def test_progress_only(self) -> None:
        result = resolve_explicit_final_source_reply_delivery_evidence(
            {"messagingToolSentTargets": [{"sourceReplyFinal": False}]},
        )
        assert result is False

    def test_progress_then_final(self) -> None:
        result = resolve_explicit_final_source_reply_delivery_evidence(
            {
                "messagingToolSentTargets": [
                    {"sourceReplyFinal": False},
                    {"sourceReplyFinal": True},
                ],
            },
        )
        assert result is True

    def test_source_reply_payloads(self) -> None:
        result = resolve_explicit_final_source_reply_delivery_evidence(
            {
                "messagingToolSourceReplyPayloads": [
                    {"sourceReplyFinal": True},
                ],
            },
        )
        assert result is True

    def test_legacy_telemetry(self) -> None:
        result = resolve_explicit_final_source_reply_delivery_evidence(
            {"messagingToolSourceReplyPayloads": [{"text": "legacy"}]},
        )
        assert result is None

    def test_empty(self) -> None:
        assert resolve_explicit_final_source_reply_delivery_evidence({}) is None

    def test_skips_non_dict_entries(self) -> None:
        result = resolve_explicit_final_source_reply_delivery_evidence(
            {"messagingToolSentTargets": [None, "str", 42]},
        )
        assert result is None


# ============================================================================
# hasCompletedSourceReplyDeliveryEvidence
# ============================================================================


class TestHasCompletedSourceReply:
    def test_explicit_final_overrides_legacy(self) -> None:
        assert (
            has_completed_source_reply_delivery_evidence(
                {
                    "messagingToolSentTargets": [{"sourceReplyFinal": False}],
                    "didDeliverSourceReplyViaMessageTool": True,
                },
            )
            is False
        )

    def test_legacy_path(self) -> None:
        assert (
            has_completed_source_reply_delivery_evidence(
                {"didDeliverSourceReplyViaMessageTool": True},
            )
            is True
        )

    def test_no_evidence(self) -> None:
        assert has_completed_source_reply_delivery_evidence({}) is False


# ============================================================================
# hasCompletedTerminalDeliveryEvidence
# ============================================================================


class TestHasCompletedTerminal:
    def test_legacy_completion(self) -> None:
        assert (
            has_completed_terminal_delivery_evidence(
                {"didDeliverSourceReplyViaMessageTool": True},
            )
            is True
        )

    def test_approval_prompt(self) -> None:
        assert (
            has_completed_terminal_delivery_evidence(
                {"didSendDeterministicApprovalPrompt": True},
            )
            is True
        )

    def test_visible_outbound_with_no_markers(self) -> None:
        # No explicit markers + no legacy completion -> use visible outbound.
        assert (
            has_completed_terminal_delivery_evidence(
                {"didSendViaMessagingTool": True},
            )
            is True
        )

    def test_no_evidence(self) -> None:
        assert has_completed_terminal_delivery_evidence({}) is False


# ============================================================================
# hasVisibleAgentPayload
# ============================================================================


class TestHasVisibleAgentPayload:
    def test_text_payload(self) -> None:
        assert has_visible_agent_payload({"payloads": [{"text": "hello"}]}) is True

    def test_no_text(self) -> None:
        assert has_visible_agent_payload({"payloads": [{}]}) is False

    def test_error_payload_excluded(self) -> None:
        assert (
            has_visible_agent_payload(
                {"payloads": [{"text": "err", "isError": True}]},
            )
            is False
        )

    def test_error_payload_included(self) -> None:
        assert (
            has_visible_agent_payload(
                {"payloads": [{"text": "err", "isError": True}]},
                include_error_payloads=True,
            )
            is True
        )

    def test_reasoning_excluded_by_default(self) -> None:
        assert (
            has_visible_agent_payload(
                {"payloads": [{"text": "thinking", "isReasoning": True}]},
            )
            is False
        )

    def test_media_url(self) -> None:
        assert (
            has_visible_agent_payload(
                {"payloads": [{"mediaUrl": "https://x.test/a.png"}]},
            )
            is True
        )

    def test_media_urls_array(self) -> None:
        assert (
            has_visible_agent_payload(
                {"payloads": [{"mediaUrls": ["https://x.test/a.png"]}]},
            )
            is True
        )

    def test_attachments(self) -> None:
        assert (
            has_visible_agent_payload(
                {
                    "payloads": [
                        {
                            "attachments": [
                                {"mediaUrl": "https://x.test/a.png"},
                            ],
                        },
                    ],
                },
            )
            is True
        )

    def test_visible_flag(self) -> None:
        assert has_visible_agent_payload({"payloads": [{"visible": True}]}) is True

    def test_presentation(self) -> None:
        assert (
            has_visible_agent_payload(
                {"payloads": [{"presentation": {"kind": "card"}}]},
            )
            is True
        )

    def test_interactive(self) -> None:
        assert (
            has_visible_agent_payload(
                {"payloads": [{"interactive": {"buttons": []}}]},
            )
            is True
        )

    def test_channel_data(self) -> None:
        assert (
            has_visible_agent_payload(
                {"payloads": [{"channelData": {"id": "x"}}]},
            )
            is True
        )

    def test_no_payloads(self) -> None:
        assert has_visible_agent_payload({}) is False

    def test_non_dict_payload(self) -> None:
        assert has_visible_agent_payload({"payloads": ["str", None]}) is False


# ============================================================================
# collectDeliveredMediaUrls
# ============================================================================


class TestCollectDeliveredMediaUrls:
    def test_payloads_and_messaging_tool(self) -> None:
        urls = collect_delivered_media_urls(
            {
                "payloads": [{"mediaUrl": "https://x.test/a.png"}],
                "messagingToolSentMediaUrls": ["https://x.test/b.png"],
            },
        )
        assert set(urls) == {
            "https://x.test/a.png",
            "https://x.test/b.png",
        }

    def test_payload_attachments(self) -> None:
        urls = collect_delivered_media_urls(
            {
                "payloads": [
                    {
                        "attachments": [
                            {"mediaUrl": "https://x.test/c.png"},
                        ],
                    },
                ],
            },
        )
        assert "https://x.test/c.png" in urls

    def test_dedup(self) -> None:
        urls = collect_delivered_media_urls(
            {
                "payloads": [{"mediaUrl": "https://x.test/a.png"}],
                "messagingToolSentMediaUrls": ["https://x.test/a.png"],
            },
        )
        assert urls.count("https://x.test/a.png") == 1

    def test_no_payloads(self) -> None:
        assert collect_delivered_media_urls({}) == []


# ============================================================================
# collectAutomaticDeliveredMediaUrls
# ============================================================================


class TestCollectAutomaticDeliveredMediaUrls:
    def test_per_payload_status(self) -> None:
        urls = collect_automatic_delivered_media_urls(
            {
                "deliveryStatus": {
                    "payloadOutcomes": [
                        {"index": 0, "status": "sent"},
                    ],
                },
                "payloads": [{"mediaUrl": "https://x.test/a.png"}],
            },
        )
        assert urls == ["https://x.test/a.png"]

    def test_aggregate_status(self) -> None:
        urls = collect_automatic_delivered_media_urls(
            {
                "deliveryStatus": {"status": "sent"},
                "payloads": [{"mediaUrl": "https://x.test/a.png"}],
            },
        )
        assert urls == ["https://x.test/a.png"]

    def test_no_status(self) -> None:
        assert (
            collect_automatic_delivered_media_urls(
                {"payloads": [{"mediaUrl": "https://x.test/a.png"}]},
            )
            == []
        )

    def test_aggregate_suppressed(self) -> None:
        urls = collect_automatic_delivered_media_urls(
            {
                "deliveryStatus": {"status": "suppressed"},
                "payloads": [{"mediaUrl": "https://x.test/a.png"}],
            },
        )
        assert urls == ["https://x.test/a.png"]


# ============================================================================
# collectAmbiguousAutomaticMediaUrls
# ============================================================================


class TestCollectAmbiguousAutomaticMediaUrls:
    def test_failed_with_sent_before_error(self) -> None:
        urls = collect_ambiguous_automatic_media_urls(
            {
                "deliveryStatus": {
                    "payloadOutcomes": [
                        {
                            "index": 0,
                            "status": "failed",
                            "sentBeforeError": True,
                        },
                    ],
                },
                "payloads": [{"mediaUrl": "https://x.test/a.png"}],
            },
        )
        assert urls == ["https://x.test/a.png"]

    def test_failed_without_sent_before_error(self) -> None:
        urls = collect_ambiguous_automatic_media_urls(
            {
                "deliveryStatus": {
                    "payloadOutcomes": [
                        {
                            "index": 0,
                            "status": "failed",
                            "sentBeforeError": False,
                        },
                    ],
                },
                "payloads": [{"mediaUrl": "https://x.test/a.png"}],
            },
        )
        assert urls == []


# ============================================================================
# hasCompleteAutomaticMediaDeliveryOutcomeEvidence
# ============================================================================


class TestHasCompleteAutomaticMediaDeliveryOutcomeEvidence:
    def test_complete(self) -> None:
        assert (
            has_complete_automatic_media_delivery_outcome_evidence(
                {
                    "deliveryStatus": {
                        "payloadOutcomes": [
                            {"index": 0, "status": "sent"},
                        ],
                    },
                    "payloads": [{"mediaUrl": "https://x.test/a.png"}],
                },
                ["https://x.test/a.png"],
            )
            is True
        )

    def test_truncated(self) -> None:
        assert (
            has_complete_automatic_media_delivery_outcome_evidence(
                {
                    "payloadsTruncated": True,
                    "deliveryStatus": {
                        "payloadOutcomes": [
                            {"index": 0, "status": "sent"},
                        ],
                    },
                    "payloads": [{"mediaUrl": "https://x.test/a.png"}],
                },
                ["https://x.test/a.png"],
            )
            is False
        )

    def test_unclassified_payload(self) -> None:
        # Payload contains the expected media but its index is not in the
        # classified set.
        assert (
            has_complete_automatic_media_delivery_outcome_evidence(
                {
                    "deliveryStatus": {
                        "payloadOutcomes": [
                            {"index": 1, "status": "sent"},
                        ],
                    },
                    "payloads": [
                        {"mediaUrl": "https://x.test/a.png"},
                        {"text": "no media"},
                    ],
                },
                ["https://x.test/a.png"],
            )
            is False
        )

    def test_failed_with_sent_before_error_classified(self) -> None:
        assert (
            has_complete_automatic_media_delivery_outcome_evidence(
                {
                    "deliveryStatus": {
                        "payloadOutcomes": [
                            {
                                "index": 0,
                                "status": "failed",
                                "sentBeforeError": True,
                            },
                        ],
                    },
                    "payloads": [{"mediaUrl": "https://x.test/a.png"}],
                },
                ["https://x.test/a.png"],
            )
            is True
        )

    def test_no_outcomes(self) -> None:
        assert (
            has_complete_automatic_media_delivery_outcome_evidence(
                {"payloads": [{"mediaUrl": "https://x.test/a.png"}]},
                ["https://x.test/a.png"],
            )
            is False
        )


# ============================================================================
# Messaging tool evidence
# ============================================================================


class TestMessagingToolDeliveryEvidence:
    def test_did_send_flag(self) -> None:
        assert (
            has_messaging_tool_delivery_evidence({"didSendViaMessagingTool": True})
            is True
        )

    def test_committed_text(self) -> None:
        assert (
            has_messaging_tool_delivery_evidence(
                {"messagingToolSentTexts": ["hi"]},
            )
            is True
        )

    def test_committed_media(self) -> None:
        assert (
            has_messaging_tool_delivery_evidence(
                {"messagingToolSentMediaUrls": ["https://x.test/a.png"]},
            )
            is True
        )

    def test_committed_targets(self) -> None:
        assert (
            has_messaging_tool_delivery_evidence(
                {"messagingToolSentTargets": [{"to": "user-1"}]},
            )
            is True
        )

    def test_no_evidence(self) -> None:
        assert has_messaging_tool_delivery_evidence({}) is False

    def test_committed_evidence_helper(self) -> None:
        assert (
            has_committed_messaging_tool_delivery_evidence(
                {"messagingToolSentTexts": ["hi"]},
            )
            is True
        )

    def test_visible_committed_text(self) -> None:
        assert (
            has_visible_committed_messaging_tool_delivery_evidence(
                {"messagingToolSentTexts": ["hi"]},
            )
            is True
        )

    def test_visible_committed_target(self) -> None:
        assert (
            has_visible_committed_messaging_tool_delivery_evidence(
                {"messagingToolSentTargets": [{"text": "hello"}]},
            )
            is True
        )

    def test_visible_committed_target_with_no_known_field(self) -> None:
        # If target has no known visibility field, treat as visible.
        assert (
            has_visible_committed_messaging_tool_delivery_evidence(
                {"messagingToolSentTargets": [{"to": "user-1"}]},
            )
            is True
        )


# ============================================================================
# hasUnaccountedMessagingToolAggregateEvidence
# ============================================================================


class TestHasUnaccountedAggregate:
    def test_all_accounted(self) -> None:
        assert (
            has_unaccounted_messaging_tool_aggregate_evidence(
                {
                    "messagingToolSentTexts": ["hi", "bye"],
                    "messagingToolSentTargets": [
                        {"to": "u1", "text": "hi"},
                        {"to": "u1", "text": "bye"},
                    ],
                },
            )
            is False
        )

    def test_extra_aggregate_text(self) -> None:
        assert (
            has_unaccounted_messaging_tool_aggregate_evidence(
                {
                    "messagingToolSentTexts": ["hi", "extra"],
                    "messagingToolSentTargets": [{"to": "u1", "text": "hi"}],
                },
            )
            is True
        )

    def test_did_send_no_evidence(self) -> None:
        assert (
            has_unaccounted_messaging_tool_aggregate_evidence(
                {"didSendViaMessagingTool": True},
            )
            is True
        )

    def test_no_unaccounted(self) -> None:
        assert (
            has_unaccounted_messaging_tool_aggregate_evidence({}) is False
        )


# ============================================================================
# hasCommittedSourceReplyDeliveryEvidence
# ============================================================================


class TestHasCommittedSourceReply:
    def test_legacy(self) -> None:
        assert (
            has_committed_source_reply_delivery_evidence(
                {"didDeliverSourceReplyViaMessageTool": True},
            )
            is True
        )

    def test_payloads(self) -> None:
        assert (
            has_committed_source_reply_delivery_evidence(
                {"messagingToolSourceReplyPayloads": [{"text": "hi"}]},
            )
            is True
        )

    def test_no_evidence(self) -> None:
        assert has_committed_source_reply_delivery_evidence({}) is False


# ============================================================================
# hasVisibleOutboundDeliveryEvidence
# ============================================================================


class TestHasVisibleOutbound:
    def test_texts(self) -> None:
        assert (
            has_visible_outbound_delivery_evidence(
                {"messagingToolSentTexts": ["hi"]},
            )
            is True
        )

    def test_did_send_flag(self) -> None:
        assert (
            has_visible_outbound_delivery_evidence(
                {"didSendViaMessagingTool": True},
            )
            is True
        )

    def test_session_spawn(self) -> None:
        assert (
            has_visible_outbound_delivery_evidence(
                {"acceptedSessionSpawns": [{"accepted": True}]},
            )
            is True
        )

    def test_cron_adds(self) -> None:
        assert (
            has_visible_outbound_delivery_evidence(
                {"successfulCronAdds": [{"id": "c1"}]},
            )
            is True
        )

    def test_visible_payload(self) -> None:
        assert (
            has_visible_outbound_delivery_evidence(
                {"payloads": [{"text": "hello"}]},
            )
            is True
        )

    def test_no_evidence(self) -> None:
        assert has_visible_outbound_delivery_evidence({}) is False


# ============================================================================
# getGatewayAgentResult
# ============================================================================


class TestGetGatewayAgentResult:
    def test_top_level_shape(self) -> None:
        response = {"payloads": [{"text": "hi"}]}
        result = get_gateway_agent_result(response)
        assert result is response

    def test_nested_result(self) -> None:
        response = {"result": {"payloads": [{"text": "hi"}]}}
        result = get_gateway_agent_result(response)
        assert result == {"payloads": [{"text": "hi"}]}

    def test_no_shape(self) -> None:
        assert get_gateway_agent_result({"foo": "bar"}) is None

    def test_none(self) -> None:
        assert get_gateway_agent_result(None) is None

    def test_non_dict(self) -> None:
        assert get_gateway_agent_result("str") is None
