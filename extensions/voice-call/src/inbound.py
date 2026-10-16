"""Inbound telephony call policy evaluation and per-number routing."""

from __future__ import annotations

from dataclasses import dataclass

from .audio.tts_engine import TTSEngine
from .config import (
    VoiceCallConfig,
    VoiceCallInboundPolicy,
    VoiceCallNumberRouting,
    VoiceCallRealtimeConfig,
    VoiceCallTTSConfig,
)
from .phone_utils import normalize_e164_phone_number


@dataclass(slots=True)
class InboundEvaluationResult:
    allowed: bool
    reason: str | None = None
    agent_id: str = "main"
    inbound_policy: VoiceCallInboundPolicy = "disabled"
    tts_override: VoiceCallTTSConfig | None = None
    realtime_override: VoiceCallRealtimeConfig | None = None
    greeting: str | None = None
    response_model: str | None = None
    response_system_prompt: str | None = None
    response_timeout_ms: int | None = None
    routing_match: VoiceCallNumberRouting | None = None


def evaluate_inbound_call(
    caller_number: str,
    called_number: str,
    config: VoiceCallConfig,
    active_pairings: set[str] | None = None,
) -> InboundEvaluationResult:
    """Evaluate whether an inbound call is permitted according to global and per-number policies."""
    norm_caller = caller_number
    try:
        norm_caller = normalize_e164_phone_number(caller_number)
    except ValueError:
        pass

    norm_called = called_number
    try:
        norm_called = normalize_e164_phone_number(called_number)
    except ValueError:
        pass

    # Check for per-number routing override
    routing_entry = config.numbers.get(norm_called)
    effective_agent = (
        routing_entry.agent_id if routing_entry and routing_entry.agent_id else config.agent_id
    ) or "main"
    effective_policy = (
        routing_entry.inbound_policy
        if routing_entry and routing_entry.inbound_policy is not None
        else config.inbound_policy
    )
    effective_tts = (
        TTSEngine().resolve_effective_tts_config(routing_entry.tts, config)
        if (routing_entry and routing_entry.tts)
        else config.tts
    )
    effective_realtime = routing_entry.realtime if routing_entry else None
    effective_greeting = (
        routing_entry.effective_greeting
        if routing_entry and routing_entry.effective_greeting
        else "Hello, thanks for calling JARVIS."
    )
    effective_resp_model = (
        routing_entry.response_model
        if routing_entry and routing_entry.response_model
        else config.response_model
    )
    effective_resp_prompt = (
        routing_entry.response_system_prompt
        if routing_entry and routing_entry.response_system_prompt
        else config.response_system_prompt
    )
    effective_resp_timeout = (
        routing_entry.response_timeout_ms
        if routing_entry and routing_entry.response_timeout_ms is not None
        else config.response_timeout_ms
    )

    if effective_policy == "disabled":
        return InboundEvaluationResult(
            allowed=False,
            reason="inbound-policy-disabled",
            agent_id=effective_agent,
            inbound_policy=effective_policy,
            tts_override=effective_tts,
            realtime_override=effective_realtime,
            greeting=effective_greeting,
            response_model=effective_resp_model,
            response_system_prompt=effective_resp_prompt,
            response_timeout_ms=effective_resp_timeout,
            routing_match=routing_entry,
        )

    if effective_policy == "open":
        return InboundEvaluationResult(
            allowed=True,
            reason=None,
            agent_id=effective_agent,
            inbound_policy=effective_policy,
            tts_override=effective_tts,
            realtime_override=effective_realtime,
            greeting=effective_greeting,
            response_model=effective_resp_model,
            response_system_prompt=effective_resp_prompt,
            response_timeout_ms=effective_resp_timeout,
            routing_match=routing_entry,
        )

    if effective_policy == "allowlist":
        # Check global allow_from
        normalized_allows = set()
        for num in config.allow_from:
            try:
                normalized_allows.add(normalize_e164_phone_number(num))
            except ValueError:
                normalized_allows.add(num.strip())

        if norm_caller in normalized_allows:
            return InboundEvaluationResult(
                allowed=True,
                reason=None,
                agent_id=effective_agent,
                inbound_policy=effective_policy,
                tts_override=effective_tts,
                realtime_override=effective_realtime,
                greeting=effective_greeting,
                response_model=effective_resp_model,
                response_system_prompt=effective_resp_prompt,
                response_timeout_ms=effective_resp_timeout,
                routing_match=routing_entry,
            )

        return InboundEvaluationResult(
            allowed=False,
            reason="caller-not-allowlisted",
            agent_id=effective_agent,
            inbound_policy=effective_policy,
            tts_override=effective_tts,
            realtime_override=effective_realtime,
            greeting=effective_greeting,
            response_model=effective_resp_model,
            response_system_prompt=effective_resp_prompt,
            response_timeout_ms=effective_resp_timeout,
            routing_match=routing_entry,
        )

    if effective_policy == "pairing":
        pairings = active_pairings or set()
        if norm_caller in pairings:
            return InboundEvaluationResult(
                allowed=True,
                reason=None,
                agent_id=effective_agent,
                inbound_policy=effective_policy,
                tts_override=effective_tts,
                realtime_override=effective_realtime,
                greeting=effective_greeting,
                response_model=effective_resp_model,
                response_system_prompt=effective_resp_prompt,
                response_timeout_ms=effective_resp_timeout,
                routing_match=routing_entry,
            )
        return InboundEvaluationResult(
            allowed=False,
            reason="pairing-required",
            agent_id=effective_agent,
            inbound_policy=effective_policy,
            tts_override=effective_tts,
            realtime_override=effective_realtime,
            greeting=effective_greeting,
            response_model=effective_resp_model,
            response_system_prompt=effective_resp_prompt,
            response_timeout_ms=effective_resp_timeout,
            routing_match=routing_entry,
        )

    return InboundEvaluationResult(
        allowed=False,
        reason=f"unknown-inbound-policy:{effective_policy}",
        agent_id=effective_agent,
        inbound_policy=effective_policy,
        tts_override=effective_tts,
        response_model=effective_resp_model,
        response_system_prompt=effective_resp_prompt,
        response_timeout_ms=effective_resp_timeout,
    )
