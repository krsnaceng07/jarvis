"""Tests for Channel Docking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jarvis_channels import BindingRegistry
from jarvis_channels.types import InboundMessage
from jarvis_config_core import JarvisConfig, SessionConfig
from src.channels.catalog import ChannelCatalog
from src.channels.binding_router import BindingRouter
from src.sessions.session_store import InMemorySessionStore


@dataclass
class _DummyPlugin:
    id: str
    supports_webhook: bool = False
    supports_polling: bool = False
    raw: dict[str, Any] = None  # type: ignore

    def __post_init__(self):
        if self.raw is None:
            self.raw = {}

    def send(self, conv_id: str, text: str) -> None:
        self.raw.setdefault("sent", []).append((conv_id, text))


def _msg(text: str, sender: str = "alice_telegram", conv: str = "conv1", channel: str = "telegram", peer_kind: str = "user") -> InboundMessage:
    return InboundMessage(
        channel_id=channel,
        conversation_id=conv,
        sender_id=sender,
        text=text,
        kind="text",
        raw={},
        peer_kind=peer_kind,
        peer_id=sender,
    )


class TestChannelDocking:
    def _make(self, identity_links: dict | None = None) -> tuple[BindingRouter, InMemorySessionStore, _DummyPlugin, _DummyPlugin]:
        cat = ChannelCatalog()
        tel = _DummyPlugin("telegram")
        discord = _DummyPlugin("discord")
        cat.register(tel)
        cat.register(discord)

        reg = BindingRegistry()
        session_store = InMemorySessionStore()

        def _agent(session_key: str, text: str) -> str | None:
            return "agent reply"

        config = JarvisConfig(
            session=SessionConfig(
                dm_scope="per-peer",
                identityLinks=identity_links or {}
            )
        )
        router = BindingRouter(cat, reg, _agent, config=config, session_store=session_store)
        return router, session_store, tel, discord

    def test_dock_unknown_channel(self) -> None:
        router, store, _, _ = self._make()
        result = router.handle(_msg("/dock_slack", sender="123"))
        assert "Unknown channel plugin slack" in result

    def test_dock_missing_identity(self) -> None:
        router, store, _, _ = self._make(identity_links={"alice": ["telegram:123"]})
        result = router.handle(_msg("/dock_discord", sender="123"))
        assert "No linked identity found for discord" in result

    def test_dock_success(self) -> None:
        router, store, tel, discord = self._make(identity_links={"alice": ["telegram:123", "discord:456"]})
        msg = _msg("/dock_discord", sender="123", channel="telegram")
        
        # Pre-create session so append_entry succeeds
        store.get_or_create(session_key="agent:main:peer:123", agent_id="main", kind="chat")
        
        result = router.handle(msg)
        assert "Docked." in result

        # Check session store has the new route appended
        sessions = store.list_sessions()
        assert len(sessions) == 1
        record = sessions[0]
        assert len(record.entries) == 1
        entry = record.entries[-1]
        assert entry["lastChannel"] == "discord"
        assert entry["lastTo"] == "456"

    def test_dock_from_group_fails(self) -> None:
        router, store, _, _ = self._make(identity_links={"alice": ["telegram:123", "discord:456"]})
        result = router.handle(_msg("/dock_discord", sender="123", peer_kind="group"))
        assert "Docking only works from a direct chat" in result
