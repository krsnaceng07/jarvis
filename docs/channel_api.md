# JARVIS Channel API Reference

This guide details how to implement a messaging channel extension for JARVIS conforming to OpenClaw parity.

---

## 1. Implementing `create_chat_channel_plugin`

Every channel extension exports a channel plugin object created using `create_chat_channel_plugin`:

```python
from jarvis_sdk.channel_adapters import create_chat_channel_plugin
from jarvis_channels.types import InboundMessage, OutboundMessage

def build_telegram_channel():
    return create_chat_channel_plugin(
        id="telegram",
        name="Telegram",
        description="Telegram bot channel plugin",
        capabilities={
            "draft_preview": True,
            "actions": True,
            "rich_blocks": True,
            "audio_voice": True,
            "pairing": True,
        },
        start_account=start_telegram_account,
        stop_account=stop_telegram_account,
        send_message=send_telegram_message,
    )
```

---

## 2. Inbound Event Lifecycle

When an inbound event occurs:
1. Translate raw payload into `InboundMessage`.
2. Pass to `ChannelTurnRunner.run_turn(raw_message)`.
3. The runner handles classification, allowlist check, session routing, and agent turn dispatch.

---

## 3. Outbound Message Handling

Outbound responses flow back through the channel's delivery adapter:
- `send(outbound_message)`: Delivers plaintext or markdown.
- `send_media(outbound_message)`: Transmits images, audio notes, or documents.
- `send_typing(conversation_id)`: Displays status indicators while model is processing.
- `send_reaction(conversation_id, message_id, emoji)`: Acknowledges messages.
