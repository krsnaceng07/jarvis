"""jarvis.agents.embedded_agent_runner.delivery_evidence — extract visible delivery evidence.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/delivery-evidence.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`resolve_explicit_final_source_reply_delivery_evidence` —
  return True/False when ``sourceReplyFinal`` markers are present,
  otherwise ``None`` (legacy telemetry).
- :func:`has_completed_source_reply_delivery_evidence` — combined
  explicit + legacy-completion evidence.
- :func:`has_completed_terminal_delivery_evidence` — whether the
  delivery evidence completes the current interactive turn.
- :func:`collect_delivered_media_urls` — collect all media URLs
  proven delivered.
- :func:`collect_messaging_tool_delivered_media_urls` — collect
  media URLs from messaging-tool sends.
- :func:`collect_automatic_delivered_media_urls` — collect media
  URLs from automatic delivery evidence.
- :func:`collect_ambiguous_automatic_media_urls` — collect media
  URLs that may have been sent before a per-payload failure.
- :func:`has_complete_automatic_media_delivery_outcome_evidence` —
  every expected-media payload is classified.
- :func:`get_gateway_agent_result` — extract a gateway result
  payload carrying delivery evidence fields.
- :func:`has_visible_agent_payload` — payload contains visible
  text, media, presentation, or channel data.
- :func:`has_messaging_tool_delivery_evidence` — messaging tool
  attempted or committed an outbound delivery.
- :func:`has_committed_messaging_tool_delivery_evidence` —
  messaging-tool metadata proves committed text/media/target.
- :func:`has_unaccounted_messaging_tool_aggregate_evidence` —
  aggregate sends lack route-checkable target records.
- :func:`has_visible_committed_messaging_tool_delivery_evidence` —
  messaging-tool metadata proves a user-visible committed delivery.
- :func:`has_committed_source_reply_delivery_evidence` — a source
  reply was visibly delivered through the message tool.
- :func:`has_visible_outbound_delivery_evidence` — outbound
  metadata proves a visible message, spawn, or cron side effect.

Phase 7.2c-1 — focused minimal port.

The OpenClaw source uses ``normalizeMediaReferenceForComparison``
to canonicalize media URLs (so the same URL with different trailing
slashes still matches). The Python port keeps the same surface but
uses a small private :func:`_normalize_media_reference` that
applies a focused minimal canonicalization (trim + lowercase). The
host can install a custom normalizer via
:func:`set_media_reference_normalizer` if the real catalog is
needed.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set


#: Media reference normalizer. The OpenClaw source uses
#: ``normalizeMediaReferenceForComparison`` from
#: ``media-reference-comparison.js``. The Python port defaults to
#: a focused minimal trim+lowercase; the host can override.
_MEDIA_REFERENCE_NORMALIZER: Callable[[str], str] = lambda value: (value or "").strip().lower()


def set_media_reference_normalizer(
    normalizer: Callable[[str], str],
) -> None:
    """Install a custom media reference normalizer."""
    global _MEDIA_REFERENCE_NORMALIZER
    _MEDIA_REFERENCE_NORMALIZER = normalizer


def _normalize_media_reference(value: str) -> str:
    return _MEDIA_REFERENCE_NORMALIZER(value or "")


def _has_accepted_session_spawn(value: Any) -> bool:
    """Return True if ``value`` indicates an accepted session spawn.

    Mirrors :func:`hasAcceptedSessionSpawn`` from
    ``accepted-session-spawn.js``. The focused minimal port checks
    the ``accepted`` / ``acceptedSessionSpawns`` shape used by the
    delivery-evidence types.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        if value.get("accepted") is True:
            return True
        if value.get("acceptedSessionSpawns"):
            return True
        return False
    return bool(value)


def _collect_source_reply_final_markers(value: Any) -> List[bool]:
    """Flatten ``sourceReplyFinal`` markers from a list of records.

    Mirrors :func:`collectSourceReplyFinalMarkers``
    (``delivery-evidence.ts:68-79``).
    """
    if not isinstance(value, list):
        return []
    out: List[bool] = []
    for entry in value:
        if not entry or not isinstance(entry, dict) or isinstance(entry, list):
            continue
        marker = entry.get("sourceReplyFinal")
        if isinstance(marker, bool):
            out.append(marker)
    return out


def resolve_explicit_final_source_reply_delivery_evidence(
    result: Dict[str, Any],
) -> Optional[bool]:
    """Return True/False for explicit progress/final markers.

    Mirrors :func:`resolveExplicitFinalSourceReplyDeliveryEvidence``
    (``delivery-evidence.ts:82-90``). Returns ``None`` for legacy
    runtimes that do not emit ``sourceReplyFinal`` markers.
    """
    markers: List[bool] = []
    markers.extend(_collect_source_reply_final_markers(result.get("messagingToolSentTargets")))
    markers.extend(
        _collect_source_reply_final_markers(result.get("messagingToolSourceReplyPayloads"))
    )
    if not markers:
        return None
    return any(markers)


def has_completed_source_reply_delivery_evidence(
    result: Dict[str, Any],
) -> bool:
    """Combined explicit + legacy completion evidence.

    Mirrors :func:`hasCompletedSourceReplyDeliveryEvidence``
    (``delivery-evidence.ts:93-100``).
    """
    explicit = resolve_explicit_final_source_reply_delivery_evidence(result)
    if explicit is not None:
        return explicit
    return has_committed_source_reply_delivery_evidence(result)


def has_completed_terminal_delivery_evidence(result: Dict[str, Any]) -> bool:
    """Return whether the delivery evidence completes the turn.

    Mirrors :func:`hasCompletedTerminalDeliveryEvidence``
    (``delivery-evidence.ts:103-112``).
    """
    explicit = resolve_explicit_final_source_reply_delivery_evidence(result)
    if has_completed_source_reply_delivery_evidence(result):
        return True
    if explicit is None and has_visible_outbound_delivery_evidence(result):
        return True
    return result.get("didSendDeterministicApprovalPrompt") is True


def _has_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _has_non_empty_array(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _has_non_empty_string_array(value: Any) -> bool:
    return isinstance(value, list) and any(_has_non_empty_string(v) for v in value)


def _has_visible_messaging_tool_target(value: Any) -> bool:
    if not value or not isinstance(value, dict) or isinstance(value, list):
        return False
    record = value
    has_known_field = any(
        key in record
        for key in ("text", "mediaUrls", "hasRichContent", "visible")
    )
    if has_known_field:
        return (
            _has_non_empty_string(record.get("text"))
            or _has_non_empty_string_array(record.get("mediaUrls"))
            or record.get("hasRichContent") is True
            or record.get("visible") is True
        )
    return True


def _has_visible_attachment_reference(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    urls: Set[str] = set()
    for attachment in value:
        if attachment and isinstance(attachment, dict) and not isinstance(attachment, list):
            _collect_media_urls_from_record(attachment, urls)
    return len(urls) > 0


def _collect_string_values(value: Any, output: Set[str]) -> None:
    if isinstance(value, str) and value.strip():
        output.add(value.strip())
        return
    if not isinstance(value, list):
        return
    for entry in value:
        if isinstance(entry, str) and entry.strip():
            output.add(entry.strip())


def _collect_media_urls_from_record(
    record: Dict[str, Any],
    output: Set[str],
    seen: Optional[Set[int]] = None,
) -> None:
    if seen is None:
        seen = set()
    if id(record) in seen:
        return
    seen.add(id(record))
    _collect_string_values(record.get("mediaUrl"), output)
    _collect_string_values(record.get("mediaUrls"), output)
    _collect_string_values(record.get("path"), output)
    _collect_string_values(record.get("url"), output)
    _collect_string_values(record.get("filePath"), output)
    attachments = record.get("attachments")
    if isinstance(attachments, list):
        for attachment in attachments:
            if attachment and isinstance(attachment, dict) and not isinstance(attachment, list):
                _collect_media_urls_from_record(attachment, output, seen)


def collect_delivered_media_urls(result: Dict[str, Any]) -> List[str]:
    """Collect all media URLs proven delivered.

    Mirrors :func:`collectDeliveredMediaUrls``
    (``delivery-evidence.ts:209-222``).
    """
    urls: Set[str] = set()
    payloads = result.get("payloads")
    if isinstance(payloads, list):
        for payload in payloads:
            if payload and isinstance(payload, dict) and not isinstance(payload, list):
                _collect_media_urls_from_record(payload, urls)
    for url in collect_messaging_tool_delivered_media_urls(result):
        urls.add(url)
    return list(urls)


def collect_messaging_tool_delivered_media_urls(
    result: Dict[str, Any],
) -> List[str]:
    """Collect media URLs from messaging-tool sends.

    Mirrors :func:`collectMessagingToolDeliveredMediaUrls``
    (``delivery-evidence.ts:225-238``).
    """
    urls: Set[str] = set()
    _collect_string_values(result.get("messagingToolSentMediaUrls"), urls)
    targets = result.get("messagingToolSentTargets")
    if isinstance(targets, list):
        for target in targets:
            if target and isinstance(target, dict) and not isinstance(target, list):
                _collect_media_urls_from_record(target, urls)
    return list(urls)


def _has_deliverable_agent_payload(payload: Any) -> bool:
    if payload and isinstance(payload, dict) and not isinstance(payload, list):
        if payload.get("visible") is False:
            return False
    return has_visible_agent_payload(
        {"payloads": [payload]},
        include_error_payloads=False,
        include_reasoning_payloads=False,
    )


def _has_positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and value > 0


def get_gateway_agent_result(response: Any) -> Optional[Dict[str, Any]]:
    """Extract a gateway result payload with delivery evidence fields.

    Mirrors :func:`getGatewayAgentResult``
    (``delivery-evidence.ts:374-385``).
    """
    if not response or not isinstance(response, dict):
        return None
    candidate = response if _has_agent_delivery_evidence_shape(response) else response.get("result")
    if (
        not candidate
        or not isinstance(candidate, dict)
        or not _has_agent_delivery_evidence_shape(candidate)
    ):
        return None
    return candidate


def _has_agent_delivery_evidence_shape(value: Dict[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "payloads",
            "deliveryStatus",
            "didSendViaMessagingTool",
            "messagingToolSentTexts",
            "messagingToolSentMediaUrls",
            "messagingToolSentTargets",
            "acceptedSessionSpawns",
            "successfulCronAdds",
            "meta",
        )
    )


def has_visible_agent_payload(
    result: Dict[str, Any],
    *,
    include_error_payloads: bool = False,
    include_reasoning_payloads: bool = False,
) -> bool:
    """Return whether any payload contains visible text, media, etc.

    Mirrors :func:`hasVisibleAgentPayload``
    (``delivery-evidence.ts:402-432``).
    """
    payloads = result.get("payloads")
    if not isinstance(payloads, list):
        return False
    for payload in payloads:
        if not payload or not isinstance(payload, dict):
            continue
        if include_error_payloads is False and payload.get("isError") is True:
            continue
        if include_reasoning_payloads is False and payload.get("isReasoning") is True:
            continue
        if (
            _has_non_empty_string(payload.get("text"))
            or _has_non_empty_string(payload.get("mediaUrl"))
            or _has_non_empty_string_array(payload.get("mediaUrls"))
            or _has_visible_attachment_reference(payload.get("attachments"))
            or payload.get("visible") is True
            or payload.get("presentation")
            or payload.get("interactive")
            or payload.get("channelData")
        ):
            return True
    return False


def has_messaging_tool_delivery_evidence(result: Dict[str, Any]) -> bool:
    """Return whether the messaging tool attempted or committed delivery.

    Mirrors :func:`hasMessagingToolDeliveryEvidence``
    (``delivery-evidence.ts:435-439``).
    """
    return result.get("didSendViaMessagingTool") is True or has_committed_messaging_tool_delivery_evidence(
        result
    )


def has_committed_messaging_tool_delivery_evidence(result: Dict[str, Any]) -> bool:
    """Return whether messaging-tool metadata proves committed delivery.

    Mirrors :func:`hasCommittedMessagingToolDeliveryEvidence``
    (``delivery-evidence.ts:442-453``).
    """
    return (
        _has_non_empty_string_array(result.get("messagingToolSentTexts"))
        or _has_non_empty_string_array(result.get("messagingToolSentMediaUrls"))
        or _has_non_empty_array(result.get("messagingToolSentTargets"))
    )


def _collect_non_empty_string_array(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def _has_unaccounted_strings(aggregate: List[str], accounted: List[str]) -> bool:
    remaining: Dict[str, int] = {}
    for value in accounted:
        remaining[value] = remaining.get(value, 0) + 1
    for value in aggregate:
        count = remaining.get(value, 0)
        if count == 0:
            return True
        if count == 1:
            remaining.pop(value, None)
        else:
            remaining[value] = count - 1
    return False


def has_unaccounted_messaging_tool_aggregate_evidence(
    result: Dict[str, Any],
) -> bool:
    """Return whether aggregate sends lack route-checkable target records.

    Mirrors :func:`hasUnaccountedMessagingToolAggregateEvidence``
    (``delivery-evidence.ts:481-519``).
    """
    targets = result.get("messagingToolSentTargets")
    route_checkable_targets: List[Dict[str, Any]] = []
    if isinstance(targets, list):
        for target in targets:
            if not target or not isinstance(target, dict) or isinstance(target, list):
                continue
            to = target.get("to")
            if isinstance(to, str) and to.strip():
                route_checkable_targets.append(target)
    aggregate_texts = _collect_non_empty_string_array(result.get("messagingToolSentTexts"))
    aggregate_media = _collect_non_empty_string_array(
        result.get("messagingToolSentMediaUrls")
    )
    accounted_texts: List[str] = []
    accounted_media: List[str] = []
    for target in route_checkable_targets:
        text = target.get("text")
        if isinstance(text, str) and text.strip():
            accounted_texts.append(text.strip())
        accounted_media.extend(_collect_non_empty_string_array(target.get("mediaUrls")))
    if _has_unaccounted_strings(aggregate_texts, accounted_texts):
        return True
    if _has_unaccounted_strings(aggregate_media, accounted_media):
        return True
    return (
        result.get("didSendViaMessagingTool") is True
        and len(route_checkable_targets) == 0
        and len(aggregate_texts) == 0
        and len(aggregate_media) == 0
    )


def has_visible_committed_messaging_tool_delivery_evidence(
    result: Dict[str, Any],
) -> bool:
    """Return whether messaging-tool metadata proves visible committed delivery.

    Mirrors :func:`hasVisibleCommittedMessagingToolDeliveryEvidence``
    (``delivery-evidence.ts:522-534``).
    """
    return (
        _has_non_empty_string_array(result.get("messagingToolSentTexts"))
        or _has_non_empty_string_array(result.get("messagingToolSentMediaUrls"))
        or (
            isinstance(result.get("messagingToolSentTargets"), list)
            and any(
                _has_visible_messaging_tool_target(t)
                for t in result["messagingToolSentTargets"]
            )
        )
    )


def has_committed_source_reply_delivery_evidence(
    result: Dict[str, Any],
) -> bool:
    """Return whether a source reply was visibly delivered.

    Mirrors :func:`hasCommittedSourceReplyDeliveryEvidence``
    (``delivery-evidence.ts:545-552``).
    """
    return result.get("didDeliverSourceReplyViaMessageTool") is True or has_visible_agent_payload(
        {"payloads": result.get("messagingToolSourceReplyPayloads")}
    )


def has_visible_outbound_delivery_evidence(result: Dict[str, Any]) -> bool:
    """Return whether outbound metadata proves a visible side effect.

    Mirrors :func:`hasVisibleOutboundDeliveryEvidence``
    (``delivery-evidence.ts:555-end``).
    """
    if has_visible_committed_messaging_tool_delivery_evidence(result):
        return True
    if result.get("didSendViaMessagingTool") is True:
        return True
    spawns = result.get("acceptedSessionSpawns")
    if isinstance(spawns, list):
        for spawn in spawns:
            if _has_accepted_session_spawn(spawn):
                return True
    elif _has_accepted_session_spawn(spawns):
        return True
    if result.get("successfulCronAdds"):
        return True
    if has_visible_agent_payload(result):
        return True
    return False


def _collect_deliverable_payload_media_urls(payloads: Any) -> List[str]:
    if not isinstance(payloads, list):
        return []
    urls: Set[str] = set()
    for payload in payloads:
        if not _has_deliverable_agent_payload(payload):
            continue
        for url in collect_delivered_media_urls({"payloads": [payload]}):
            urls.add(url)
    return list(urls)


def _collect_payload_outcome_media_urls(
    result: Dict[str, Any],
    statuses: Callable[[Dict[str, Any]], bool],
) -> List[str]:
    payloads = result.get("payloads") if isinstance(result.get("payloads"), list) else []
    outcomes = (
        result.get("deliveryStatus", {}).get("payloadOutcomes")
        if isinstance(result.get("deliveryStatus"), dict)
        else None
    )
    if not isinstance(outcomes, list):
        outcomes = []
    urls: Set[str] = set()
    for outcome in outcomes:
        if not outcome or not isinstance(outcome, dict) or isinstance(outcome, list):
            continue
        if not statuses(outcome):
            continue
        index = outcome.get("index")
        if not isinstance(index, int):
            continue
        payload = payloads[index] if 0 <= index < len(payloads) else None
        if not _has_deliverable_agent_payload(payload):
            continue
        for url in collect_delivered_media_urls({"payloads": [payload]}):
            urls.add(url)
    return list(urls)


def collect_automatic_delivered_media_urls(result: Dict[str, Any]) -> List[str]:
    """Collect media URLs from automatic-delivery evidence.

    Mirrors :func:`collectAutomaticDeliveredMediaUrls``
    (``delivery-evidence.ts:300-312``).
    """
    delivery_status = result.get("deliveryStatus")
    if not isinstance(delivery_status, dict):
        delivery_status = {}
    outcomes = delivery_status.get("payloadOutcomes")
    if isinstance(outcomes, list):
        return _collect_payload_outcome_media_urls(
            result,
            lambda o: o.get("status") in ("sent", "suppressed"),
        )
    if delivery_status.get("status") in ("sent", "suppressed"):
        return _collect_deliverable_payload_media_urls(result.get("payloads"))
    return []


def collect_ambiguous_automatic_media_urls(result: Dict[str, Any]) -> List[str]:
    """Collect media URLs that may have been sent before a per-payload failure.

    Mirrors :func:`collectAmbiguousAutomaticMediaUrls``
    (``delivery-evidence.ts:315-322``).
    """
    return _collect_payload_outcome_media_urls(
        result,
        lambda o: o.get("status") == "failed" and o.get("sentBeforeError") is True,
    )


def has_complete_automatic_media_delivery_outcome_evidence(
    result: Dict[str, Any],
    expected_media_urls: List[str],
) -> bool:
    """Check that a partial automatic send classifies every expected-media payload.

    Mirrors :func:`hasCompleteAutomaticMediaDeliveryOutcomeEvidence``
    (``delivery-evidence.ts:325-367``).
    """
    if result.get("payloadsTruncated") is True:
        return False
    payloads = result.get("payloads")
    if not isinstance(payloads, list) or not payloads:
        return False
    delivery_status = result.get("deliveryStatus")
    outcomes = (
        delivery_status.get("payloadOutcomes")
        if isinstance(delivery_status, dict)
        else None
    )
    if not isinstance(outcomes, list) or not outcomes:
        return False
    classified_indexes: Set[int] = set()
    for outcome in outcomes:
        if not outcome or not isinstance(outcome, dict) or isinstance(outcome, list):
            continue
        index = outcome.get("index")
        if (
            not isinstance(index, int)
            or index < 0
            or index >= len(payloads)
        ):
            continue
        status = outcome.get("status")
        classified = (
            status in ("sent", "suppressed")
            or (status == "failed" and isinstance(outcome.get("sentBeforeError"), bool))
        )
        if classified:
            classified_indexes.add(index)
    expected = {_normalize_media_reference(url) for url in expected_media_urls}
    for index, payload in enumerate(payloads):
        if not isinstance(payload, dict):
            continue
        contains_expected = any(
            _normalize_media_reference(url) in expected
            for url in collect_delivered_media_urls({"payloads": [payload]})
        )
        if contains_expected and index not in classified_indexes:
            return False
    return True


__all__ = [
    "collect_ambiguous_automatic_media_urls",
    "collect_automatic_delivered_media_urls",
    "collect_delivered_media_urls",
    "collect_messaging_tool_delivered_media_urls",
    "get_gateway_agent_result",
    "has_committed_messaging_tool_delivery_evidence",
    "has_committed_source_reply_delivery_evidence",
    "has_complete_automatic_media_delivery_outcome_evidence",
    "has_completed_source_reply_delivery_evidence",
    "has_completed_terminal_delivery_evidence",
    "has_messaging_tool_delivery_evidence",
    "has_unaccounted_messaging_tool_aggregate_evidence",
    "has_visible_agent_payload",
    "has_visible_committed_messaging_tool_delivery_evidence",
    "has_visible_outbound_delivery_evidence",
    "resolve_explicit_final_source_reply_delivery_evidence",
    "set_media_reference_normalizer",
]
