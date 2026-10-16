"""Tests elevated permission resolution from allowlists and message context.

OpenClaw parity: mirrors
``openclaw-main/src/auto-reply/reply/reply-elevated.test.ts``.
"""

from typing import Any

from jarvis.auto_reply.reply.reply_elevated import resolve_elevated_permissions
from jarvis.channels.inbound_context import MsgContext


class DummyConfig:
    def __init__(self, allow_from: list[str]):
        self.tools = type("ToolsConfig", (), {
            "elevated": type("ElevatedConfig", (), {
                "allowFrom": {"whatsapp": allow_from},
                "enabled": True,
            })
        })()


def build_config(allow_from: list[str]) -> Any:
    return DummyConfig(allow_from)


def build_context(overrides: dict[str, Any] | None = None) -> MsgContext:
    ctx: MsgContext = {
        "Provider": "whatsapp",
        "ChatType": "direct",
        "SenderId": "+15550001111",
        "From": "whatsapp:+15550001111",
        "SenderE164": "+15550001111",
    }
    if overrides:
        ctx.update(overrides)  # type: ignore
    return ctx


def expect_allow_from_decision(
    monkeypatch: Any,
    allow_from: list[str],
    allowed: bool,
    ctx_overrides: dict[str, Any] | None = None,
) -> None:
    # Mock resolve_agent_config to return a dummy agent config
    def mock_resolve_agent_config(*args: Any, **kwargs: Any) -> Any:
        return type("AgentConfig", (), {
            "tools": type("AgentToolsConfig", (), {
                "elevated": type("AgentElevatedConfig", (), {
                    "enabled": True,
                    "allowFrom": None,
                })()
            })()
        })()

    monkeypatch.setattr("jarvis.auto_reply.reply.reply_elevated.resolve_agent_config", mock_resolve_agent_config)

    result = resolve_elevated_permissions(
        cfg=build_config(allow_from),
        agent_id="main",
        provider="whatsapp",
        ctx=build_context(ctx_overrides),
    )

    assert result.enabled is True
    assert result.allowed is allowed
    if allowed:
        assert len(result.failures) == 0
    else:
        assert len(result.failures) == 1
        assert result.failures[0]["gate"] == "allowFrom"
        assert result.failures[0]["key"] == "tools.elevated.allowFrom.whatsapp"


def test_authorizes_when_sender_matches_allowFrom(monkeypatch: Any) -> None:
    expect_allow_from_decision(
        monkeypatch,
        allow_from=["+15550001111"],
        allowed=True,
    )


def test_does_not_authorize_when_only_recipient_matches_allowFrom(monkeypatch: Any) -> None:
    expect_allow_from_decision(
        monkeypatch,
        allow_from=["+15559990000"],
        allowed=False,
    )


def test_does_not_authorize_group_conversation_id_as_sender_identity(monkeypatch: Any) -> None:
    expect_allow_from_decision(
        monkeypatch,
        allow_from=["120363411111111111@g.us", "from:120363411111111111@g.us"],
        allowed=False,
        ctx_overrides={
            "ChatType": "group",
            "From": "120363411111111111@g.us",
            "SenderId": "+15550002222",
            "SenderE164": "+15550002222",
        },
    )


def test_keeps_direct_chat_from_fallback_authorization(monkeypatch: Any) -> None:
    expect_allow_from_decision(
        monkeypatch,
        allow_from=["from:whatsapp:+15550001111"],
        allowed=True,
        ctx_overrides={
            "ChatType": "direct",
            "From": "whatsapp:+15550001111",
            "SenderId": None,
            "SenderE164": None,
        },
    )


def test_does_not_authorize_untyped_mutable_sender_fields(monkeypatch: Any) -> None:
    expect_allow_from_decision(
        monkeypatch,
        allow_from=["owner-display-name"],
        allowed=False,
        ctx_overrides={
            "SenderName": "owner-display-name",
            "SenderUsername": "owner-display-name",
            "SenderTag": "owner-display-name",
        },
    )


def test_authorizes_mutable_sender_fields_only_with_explicit_prefix(monkeypatch: Any) -> None:
    expect_allow_from_decision(
        monkeypatch,
        allow_from=["username:owner_username"],
        allowed=True,
        ctx_overrides={
            "SenderUsername": "owner_username",
        },
    )
