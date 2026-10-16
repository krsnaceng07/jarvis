"""Tests for src/plugins/voice_call.py.

Mirrors tests of extensions/voice-call/src/config.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.voice_call import (
    VOICE_CALL_AGENT_TOOL_ACTIONS,
    VOICE_CALL_RPC_METHODS,
    is_valid_e164_phone_number,
    resolve_voice_call_config,
)


def test_voice_call_rpc_methods():
    assert "voicecall.initiate" in VOICE_CALL_RPC_METHODS
    assert "voicecall.speak" in VOICE_CALL_RPC_METHODS
    assert len(VOICE_CALL_RPC_METHODS) == 9


def test_voice_call_agent_tool_actions():
    assert "initiate_call" in VOICE_CALL_AGENT_TOOL_ACTIONS
    assert "send_dtmf" in VOICE_CALL_AGENT_TOOL_ACTIONS
    assert len(VOICE_CALL_AGENT_TOOL_ACTIONS) == 6


def test_is_valid_e164_phone_number():
    assert is_valid_e164_phone_number("+15550001234") is True
    assert is_valid_e164_phone_number("+442079460912") is True
    assert is_valid_e164_phone_number("5550001234") is False
    assert is_valid_e164_phone_number("+012345") is False


def test_resolve_voice_call_config_defaults():
    cfg = resolve_voice_call_config(None)
    assert cfg.enabled is False
    assert cfg.provider == "twilio"
    assert cfg.inboundPolicy == "disabled"
    assert cfg.sessionScope == "per-phone"
    assert cfg.maxDurationSeconds == 300
    assert cfg.staleCallReaperSeconds == 120
    assert cfg.agentId == "main"


def test_resolve_voice_call_config_custom():
    custom = {
        "enabled": True,
        "provider": "telnyx",
        "inboundPolicy": "allowlist",
        "allowFrom": ["+15550001234", "invalid_num"],
        "sessionScope": "per-call",
        "agentId": "receptionist",
    }
    cfg = resolve_voice_call_config(custom)
    assert cfg.enabled is True
    assert cfg.provider == "telnyx"
    assert cfg.inboundPolicy == "allowlist"
    assert cfg.allowFrom == ["+15550001234"]
    assert cfg.sessionScope == "per-call"
    assert cfg.agentId == "receptionist"
