"""jarvis.plugins.voice_call — Voice Call plugin configuration & RPC method definitions.

OpenClaw parity: mirrors
``openclaw-main/extensions/voice-call/src/config.ts`` and
``openclaw-main/extensions/voice-call/index.ts``.

Features:
- `VoiceCallProvider`: `"mock"` | `"plivo"` | `"telnyx"` | `"twilio"`
- `VoiceCallInboundPolicy`: `"disabled"` | `"allowlist"` | `"pairing"` | `"open"`
- `VoiceCallSessionScope`: `"per-phone"` | `"per-call"`
- `VOICE_CALL_RPC_METHODS`: List of 9 registered Gateway RPC methods.
- `VOICE_CALL_AGENT_TOOL_ACTIONS`: List of 6 supported agent tool actions.
- `VoiceCallConfig`: Plugin configuration dataclass.
- `resolve_voice_call_config()`: Resolves and defaults Voice Call plugin options.
- `is_valid_e164_phone_number()`: Validates E.164 phone numbers (`+15550001234`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

VoiceCallProvider = Literal["mock", "plivo", "telnyx", "twilio"]
VoiceCallInboundPolicy = Literal["disabled", "allowlist", "pairing", "open"]
VoiceCallSessionScope = Literal["per-phone", "per-call"]

VOICE_CALL_RPC_METHODS: list[str] = [
    "voicecall.initiate",
    "voicecall.start",
    "voicecall.continue",
    "voicecall.continue.start",
    "voicecall.continue.result",
    "voicecall.speak",
    "voicecall.dtmf",
    "voicecall.end",
    "voicecall.status",
]

VOICE_CALL_AGENT_TOOL_ACTIONS: list[str] = [
    "initiate_call",
    "continue_call",
    "speak_to_user",
    "send_dtmf",
    "end_call",
    "get_status",
]

_E164_REGEX = re.compile(r"^\+[1-9]\d{1,14}$")


@dataclass
class VoiceCallConfig:
    enabled: bool = False
    provider: VoiceCallProvider = "twilio"
    fromNumber: str | None = None
    toNumber: str | None = None
    inboundPolicy: VoiceCallInboundPolicy = "disabled"
    allowFrom: list[str] = field(default_factory=list)
    sessionScope: VoiceCallSessionScope = "per-phone"
    maxDurationSeconds: int = 300
    staleCallReaperSeconds: int = 120
    agentId: str = "main"


def is_valid_e164_phone_number(num: str) -> bool:
    """Validate if a string is a valid E.164 phone number."""
    if not num or not isinstance(num, str):
        return False
    return bool(_E164_REGEX.match(num.strip()))


def resolve_voice_call_config(plugin_cfg: dict[str, Any] | None) -> VoiceCallConfig:
    """Resolve Voice Call plugin options from configuration dictionary."""
    val = plugin_cfg if isinstance(plugin_cfg, dict) else {}

    raw_prov = str(val.get("provider") or "twilio").lower()
    prov: VoiceCallProvider = (
        raw_prov if raw_prov in ("mock", "plivo", "telnyx", "twilio") else "twilio"  # type: ignore[assignment]
    )

    raw_inbound = str(val.get("inboundPolicy") or "disabled").lower()
    inbound: VoiceCallInboundPolicy = (
        raw_inbound if raw_inbound in ("disabled", "allowlist", "pairing", "open") else "disabled"  # type: ignore[assignment]
    )

    raw_scope = str(val.get("sessionScope") or "per-phone").lower()
    scope: VoiceCallSessionScope = (
        raw_scope if raw_scope in ("per-phone", "per-call") else "per-phone"  # type: ignore[assignment]
    )

    allow_from = val.get("allowFrom")
    clean_allow = (
        [str(x).strip() for x in allow_from if isinstance(x, str) and is_valid_e164_phone_number(x)]
        if isinstance(allow_from, list)
        else []
    )

    return VoiceCallConfig(
        enabled=bool(val.get("enabled", False)),
        provider=prov,
        fromNumber=val.get("fromNumber"),
        toNumber=val.get("toNumber"),
        inboundPolicy=inbound,
        allowFrom=clean_allow,
        sessionScope=scope,
        maxDurationSeconds=int(val.get("maxDurationSeconds", 300)),
        staleCallReaperSeconds=int(val.get("staleCallReaperSeconds", 120)),
        agentId=str(val.get("agentId") or "main").strip(),
    )


__all__ = [
    "VOICE_CALL_AGENT_TOOL_ACTIONS",
    "VOICE_CALL_RPC_METHODS",
    "VoiceCallConfig",
    "VoiceCallInboundPolicy",
    "VoiceCallProvider",
    "VoiceCallSessionScope",
    "is_valid_e164_phone_number",
    "resolve_voice_call_config",
]
