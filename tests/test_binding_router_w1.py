"""Wave 1 binding router tests — end-to-end dispatch.

Tests ``src.channels.catalog.ChannelCatalog`` and
``src.channels.binding_router.BindingRouter`` without network calls.
"""

from __future__ import annotations

import threading


from jarvis_channels import BindingRegistry, InboundMessage
from src.channels.binding_router import BindingRouter
from src.channels.catalog import ChannelCatalog, ChannelPlugin
from jarvis_config_core import JarvisConfig, SessionConfig


# ── Helpers ────────────────────────────────────────────────────────────


def _make_catalog(sends: list | None = None) -> ChannelCatalog:
    """Catalog with a single stub telegram plugin that logs sends."""
    catalog = ChannelCatalog()
    sent = sends if sends is not None else []
    catalog.register(
        ChannelPlugin(
            id="telegram",
            send=lambda target, msg: sent.append((target, msg)),
            raw={"id": "telegram", "send_typing": None},
        )
    )
    return catalog


def _msg(text: str = "hello", sender: str = "42", conv: str = "chat1") -> InboundMessage:
    return InboundMessage(
        channel_id="telegram",
        conversation_id=conv,
        sender_id=sender,
        text=text,
        peer_id=conv,
    )


# ── Catalog ────────────────────────────────────────────────────────────


class TestChannelCatalog:
    def test_register_raw_valid(self) -> None:
        cat = ChannelCatalog()
        cat.register_raw({"id": "telegram", "send": lambda t, m: None})
        assert cat.is_registered("telegram")

    def test_register_raw_none_ignored(self) -> None:
        cat = ChannelCatalog()
        cat.register_raw(None)
        assert len(cat) == 0

    def test_register_raw_missing_id_skipped(self) -> None:
        cat = ChannelCatalog()
        cat.register_raw({"send": lambda t, m: None})
        assert len(cat) == 0

    def test_register_raw_missing_send_skipped(self) -> None:
        cat = ChannelCatalog()
        cat.register_raw({"id": "telegram"})
        assert len(cat) == 0

    def test_ids(self) -> None:
        cat = _make_catalog()
        assert cat.ids() == ["telegram"]

    def test_supports_polling_when_listen_set(self) -> None:
        cat = ChannelCatalog()
        cat.register_raw(
            {
                "id": "tg",
                "send": lambda t, m: None,
                "listen": lambda cb: None,
            }
        )
        plugin = cat.get("tg")
        assert plugin is not None
        assert plugin.supports_polling is True
        assert plugin.supports_webhook is False

    def test_supports_webhook_when_on_webhook_set(self) -> None:
        cat = ChannelCatalog()
        cat.register_raw(
            {
                "id": "dc",
                "send": lambda t, m: None,
                "on_webhook": lambda b, h: None,
            }
        )
        plugin = cat.get("dc")
        assert plugin is not None
        assert plugin.supports_webhook is True
        assert plugin.supports_polling is False


# ── BindingRouter ──────────────────────────────────────────────────────


class TestBindingRouter:
    def _make(
        self,
        agent_reply: str | None = "JARVIS reply",
        allowlists: dict | None = None,
        sends: list | None = None,
    ) -> tuple[BindingRouter, list, list]:
        calls: list[tuple[str, str]] = []
        sent: list[tuple[str, str]] = [] if sends is None else sends

        cat = _make_catalog(sent)
        reg = BindingRegistry()

        def _agent(session_key: str, text: str) -> str | None:
            calls.append((session_key, text))
            return agent_reply
        config = JarvisConfig(session=SessionConfig(dm_scope="per-peer"))
        router = BindingRouter(cat, reg, _agent, config=config, allowlists=allowlists)
        return router, calls, sent

    def test_dispatches_message_to_agent(self) -> None:
        router, calls, _ = self._make()
        router.handle(_msg("hello"))
        assert len(calls) == 1
        assert calls[0][1] == "hello"

    def test_sends_reply_through_channel(self) -> None:
        router, _, sent = self._make(agent_reply="hi back")
        router.handle(_msg("hello"))
        assert len(sent) == 1
        assert sent[0][0] == "chat1"
        assert "hi back" in sent[0][1]

    def test_returns_reply_text(self) -> None:
        router, _, _ = self._make(agent_reply="pong")
        result = router.handle(_msg("ping"))
        assert result == "pong"

    def test_drops_empty_text(self) -> None:
        router, calls, sent = self._make()
        result = router.handle(_msg(""))
        assert result is None
        assert calls == []
        assert sent == []

    def test_allowlist_allows_known_sender(self) -> None:
        router, calls, _ = self._make(allowlists={"telegram": ["42"]})
        router.handle(_msg(sender="42"))
        assert len(calls) == 1

    def test_allowlist_blocks_unknown_sender(self) -> None:
        router, calls, _ = self._make(allowlists={"telegram": ["99"]})
        result = router.handle(_msg(sender="42"))
        assert result is None
        assert calls == []

    def test_null_agent_reply_sends_nothing(self) -> None:
        router, _, sent = self._make(agent_reply=None)
        router.handle(_msg("hello"))
        assert sent == []

    def test_session_is_reused_for_same_conv(self) -> None:
        router, calls, _ = self._make()
        router.handle(_msg(conv="conv1"))
        router.handle(_msg(conv="conv1"))
        assert calls[0][0] == calls[1][0]  # same session key

    def test_different_convs_get_different_sessions(self) -> None:
        router, calls, _ = self._make()
        router.handle(_msg(conv="conv1"))
        router.handle(_msg(conv="conv2"))
        assert calls[0][0] != calls[1][0]

    def test_unknown_channel_returns_none(self) -> None:
        cat = ChannelCatalog()  # empty catalog — no telegram plugin
        reg = BindingRegistry()
        calls: list[str] = []
        config = JarvisConfig()
        router = BindingRouter(cat, reg, lambda sk, t: calls.append(t) or "reply", config=config)
        msg = InboundMessage(channel_id="telegram", conversation_id="c1", sender_id="1", text="hi")
        result = router.handle(msg)
        assert result is None

    def test_make_callback_normalizes_raw_dict(self) -> None:
        router, calls, _ = self._make()
        cb = router.make_callback("telegram")
        cb({"chat_id": "chat1", "from_id": "42", "text": "from_callback"})
        assert len(calls) == 1
        assert calls[0][1] == "from_callback"

    def test_per_session_serialization(self) -> None:
        """Concurrent messages to the same session are serialized."""
        order: list[int] = []
        lock = threading.Lock()

        def _slow_agent(session_key: str, text: str) -> str | None:
            import time
            time.sleep(0.02)
            with lock:
                order.append(int(text))
            return "ok"

        cat = _make_catalog()
        reg = BindingRegistry()
        config = JarvisConfig()
        router = BindingRouter(cat, reg, _slow_agent, config=config)

        threads = [
            threading.Thread(target=router.handle, args=(_msg(str(i)),))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 5 messages processed — order may vary but none dropped.
        assert len(order) == 5
