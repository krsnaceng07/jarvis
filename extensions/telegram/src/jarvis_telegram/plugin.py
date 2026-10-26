from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from jarvis_channels.allowlist import enforce_dm_policy
from jarvis_channels.pairing import PairingStore
from jarvis_channels.types import NormalizedLocation
from jarvis_normalization_core.result import Err, Ok, Result
from jarvis_sdk.contract import ChannelPlugin
from jarvis_state_core.database import StateDatabase

from .actions import build_approval_keyboard, parse_callback_query
from .client import TelegramClient
from .config import TelegramConfig
from .formatting import format_for_telegram
from .polling import PollingWorker
from .targets import parse_telegram_target

if TYPE_CHECKING:
    from collections.abc import Callable

_log = logging.getLogger("jarvis.telegram")


class TelegramChannelPlugin(ChannelPlugin):
    """Telegram channel implementation for JARVIS."""

    id = "telegram"
    kind = "channel"
    version = "0.1.0"
    description = "Telegram channel plugin"

    def __init__(self) -> None:
        self.ctx: Any | None = None
        self.config: TelegramConfig | None = None
        self.client: TelegramClient | None = None
        self.worker: PollingWorker | None = None
        self._callback: Callable[[Any], None] | None = None
        self._pairing_store: PairingStore | None = None

    def init(self, ctx: Any) -> None:
        """Initialize the plugin."""
        self.ctx = ctx

        # Init pairing store
        import sqlite3

        from jarvis_state_core.database import StateDatabaseOptions

        db_path = ctx.workspace / "state" / "jarvis.sqlite"
        opts = StateDatabaseOptions(
            connection_factory=lambda: sqlite3.connect(db_path, isolation_level=None)
        )
        self._pairing_store = PairingStore(StateDatabase(opts))

        # Validate config
        raw_config = ctx.config.get("channels.telegram", {})
        try:
            self.config = TelegramConfig(**raw_config)
        except Exception as e:
            _log.error("Invalid Telegram config: %s", e)
            return

        if not self.config.is_valid:
            _log.warning("Telegram botToken not set. Channel will remain inactive.")
            return

        self.client = TelegramClient(token=self.config.botToken)

        if self.config.transport == "polling":
            self.worker = PollingWorker(
                client=self.client,
                callback=self._handle_update,
                interval=self.config.pollingIntervalSec,
            )
            # Worker is started when `listen` is called

    def register(self, api: Any) -> None:
        api.register_channel(self)

    async def shutdown(self) -> None:
        """Shutdown the plugin."""
        if self.worker:
            await self.worker.stop()
        if self.client:
            await self.client.close()

    def reconfigure(
        self,
        config: TelegramConfig | dict[str, Any],
        callback: Callable[[Any], None] | None = None,
        auto_listen: bool = True,
    ) -> None:
        """Dynamically reconfigure the channel with new credentials or options."""
        if isinstance(config, dict):
            self.config = TelegramConfig(**config)
        else:
            self.config = config

        if callback is not None:
            self._callback = callback

        if not self.config.is_valid:
            _log.warning("Telegram botToken not set. Channel remains inactive.")
            return

        old_worker = self.worker
        if old_worker and old_worker.is_running:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(old_worker.stop())
                else:
                    loop.run_until_complete(old_worker.stop())
            except Exception:
                pass

        self.client = TelegramClient(token=self.config.botToken)
        if self.config.transport == "polling":
            self.worker = PollingWorker(
                client=self.client,
                callback=self._handle_update,
                interval=self.config.pollingIntervalSec,
            )
            if auto_listen and self._callback is not None:
                self.worker.start()

    def _ensure_client(self) -> None:
        """Attempt to initialize client from environment or canonical config if not yet set."""
        if self.client:
            return
        import os

        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            try:
                import json
                from pathlib import Path

                cfg_path = Path.home() / ".jarvis" / "config.json"
                if cfg_path.is_file():
                    data = json.loads(cfg_path.read_text(encoding="utf-8"))
                    channels = data.get("channels", {})
                    tg = channels.get("telegram", {}) if isinstance(channels, dict) else {}
                    token = tg.get("botToken") or data.get("telegram_bot_token")
            except Exception:
                pass
        if token:
            self.client = TelegramClient(token=token)

    async def probe(self) -> dict[str, Any]:
        """Probe the Telegram bot token and retrieve bot metadata."""
        if not self.client:
            self._ensure_client()
        if not self.client:
            return {"ok": False, "error": "Telegram client not initialized (missing botToken)"}
        return await self.client.get_me()

    async def send(self, target: str, message: Any) -> Result[Any]:
        """Send a message to a Telegram target."""
        if not self.client:
            self._ensure_client()
        if not self.client:
            return Err("Telegram client not initialized")

        parsed_target = parse_telegram_target(target)
        if not parsed_target.chat_id:
            return Err("Invalid target format")

        # In a fully typed system, `message` is an OutboundMessage object.
        # For compatibility with legacy and Phase 4 core, we handle dicts or objects.
        text = ""
        reply_to = None
        approval_id = None

        if hasattr(message, "text"):
            text = message.text
        elif isinstance(message, dict):
            text = message.get("text", "")
            reply_to = message.get("reply_to")
            # If it's an exec approval prompt
            if message.get("kind") == "approval_pending":
                approval_id = message.get("approval_id")
        else:
            text = str(message)

        if not text:
            return Err("Cannot send empty message")

        formatted_text = format_for_telegram(text)

        reply_markup = None
        if approval_id:
            reply_markup = build_approval_keyboard(approval_id)

        location = getattr(message, "location", None) or (
            message.get("location") if isinstance(message, dict) else None
        )

        # Check for voice_bytes in message or metadata
        voice_bytes = None
        if isinstance(message, dict):
            voice_bytes = message.get("voice_bytes")
            if not voice_bytes and isinstance(message.get("metadata"), dict):
                voice_bytes = message["metadata"].get("voice_bytes")
        elif hasattr(message, "voice_bytes"):
            voice_bytes = getattr(message, "voice_bytes", None)

        # Voice note synthesis is deferred until after the text is delivered
        # (below); synthesizing first delayed every Telegram reply by seconds.

        if location:
            if location.source == "place" and location.name and location.address:
                res = await self.client.send_venue(
                    chat_id=parsed_target.chat_id,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    title=location.name,
                    address=location.address,
                    reply_to_message_id=reply_to,
                    message_thread_id=parsed_target.message_thread_id,
                    reply_markup=reply_markup,
                )
            else:
                res = await self.client.send_location(
                    chat_id=parsed_target.chat_id,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    horizontal_accuracy=location.accuracy_m,
                    live_period=86400 if location.is_live else None,
                    reply_to_message_id=reply_to,
                    message_thread_id=parsed_target.message_thread_id,
                    reply_markup=reply_markup,
                )
        else:
            res = await self.client.send_message(
                chat_id=parsed_target.chat_id,
                text=formatted_text,
                reply_to_message_id=reply_to,
                message_thread_id=parsed_target.message_thread_id,
                reply_markup=reply_markup,
            )

        # Dual modality: also deliver the interactive voice note to Telegram.
        # Synthesize only after the text landed so a slow TTS never delays the
        # reply the user is waiting for.
        if (
            voice_bytes is None
            and not location
            and res.get("ok")
            and getattr(self.config, "voiceReplies", True)
            and text
        ):
            try:
                from src.talk.speech_synthesizer import synthesize_speech_wav_async

                voice_bytes = await synthesize_speech_wav_async(text)
            except Exception as e:
                _log.debug("Telegram voice note synthesis skipped: %s", e)

        if voice_bytes and not location:
            try:
                await self.client.send_voice(
                    chat_id=parsed_target.chat_id,
                    voice_bytes=voice_bytes,
                    filename="jarvis_reply.wav",
                    reply_to_message_id=reply_to,
                    message_thread_id=parsed_target.message_thread_id,
                )
            except Exception as e:
                _log.warning("Telegram voice note delivery error: %s", e)

        if res.get("ok"):
            sent = res.get("result") or {}
            return Ok(
                {
                    "channel": "telegram",
                    "account_id": getattr(self.config, "accountId", None) or "default",
                    "peer_id": parsed_target.chat_id,
                    "delivery_status": "sent",
                    "message_id": str(sent.get("message_id", "")),
                    "verified": True,
                }
            )
        return Err(res.get("error", "Unknown error"))

    async def listen(self, callback: Callable[[Any], None]) -> None:
        """Start listening for incoming events."""
        if not self.client or not self.config:
            _log.warning("Telegram channel inactive (missing config). Not listening.")
            return

        self._callback = callback

        if self.worker:
            self.worker.start()
        elif self.config.transport == "webhook":
            _log.error("Webhook transport not yet fully implemented. Please use polling.")

    def _handle_update(self, update: dict[str, Any]) -> None:
        """Handle raw updates from the PollingWorker."""
        if not self._callback:
            return

        # Handle messages
        if "message" in update:
            msg = update["message"]
            chat_id = str(msg.get("chat", {}).get("id", ""))
            thread_id = msg.get("message_thread_id")
            from_id = str(msg.get("from", {}).get("id", ""))
            text = msg.get("text", "")
            message_id = msg.get("message_id")

            assert self.config is not None
            assert self.client is not None
            account_id = getattr(self.config, "accountId", None) or "default"

            # We'll construct a canonical target string for the inbound message.
            target_str = f"telegram:{chat_id}"
            if thread_id:
                target_str += f":topic:{thread_id}"

            # Enforce DM policy (Open / Pairing / Allowlist)
            if self.config.dmPolicy == "open":
                is_allowed = True
                pairing_msg = None
            else:
                is_allowed, pairing_msg = enforce_dm_policy(
                    sender_id=from_id,
                    sender_username=msg.get("from", {}).get("username"),
                    policy_str=self.config.dmPolicy,
                    allowlist=self.config.allowFrom,
                    channel_id="telegram",
                    account_id=account_id,
                    pairing_store=self._pairing_store,
                )

            if not is_allowed:
                if pairing_msg:
                    # Send pairing message synchronously in the background task
                    import asyncio

                    asyncio.create_task(
                        self.client.send_message(
                            chat_id=chat_id,
                            text=format_for_telegram(pairing_msg),
                            reply_to_message_id=message_id,
                            message_thread_id=thread_id,
                        )
                    )
                _log.info(f"Dropped message from {from_id} due to DM policy (pairing/allowlist)")
                return

            # Determine peer kind and id
            peer_kind = "user"
            peer_id = from_id
            if chat_id != from_id:
                peer_kind = "group"
                peer_id = chat_id

            # Parse location
            location_dict = msg.get("location")
            venue_dict = msg.get("venue")
            normalized_location = None

            if venue_dict:
                loc = venue_dict.get("location", {})
                normalized_location = NormalizedLocation(
                    latitude=loc.get("latitude", 0.0),
                    longitude=loc.get("longitude", 0.0),
                    accuracy_m=loc.get("horizontal_accuracy"),
                    source="place",
                    name=venue_dict.get("title"),
                    address=venue_dict.get("address"),
                    is_live=False,
                )
            elif location_dict:
                is_live = "live_period" in location_dict
                normalized_location = NormalizedLocation(
                    latitude=location_dict.get("latitude", 0.0),
                    longitude=location_dict.get("longitude", 0.0),
                    accuracy_m=location_dict.get("horizontal_accuracy"),
                    source="live" if is_live else "pin",
                    is_live=is_live,
                )

            inbound = {
                "kind": "message",
                "chat_id": chat_id,
                "thread_id": thread_id,
                "from_id": from_id,
                "text": text,
                "message_id": message_id,
                "reply_to_message_id": message_id,
                "target": target_str,
                "peer_kind": peer_kind,
                "peer_id": peer_id,
                "account_id": account_id,
                "location": normalized_location,
                "origin_surface": "telegram",
                "reply_route": {
                    "channel": "telegram",
                    "account_id": account_id,
                    "target": target_str,
                    "thread_id": str(thread_id) if thread_id is not None else None,
                },
            }
            self._callback(inbound)

        # Handle callbacks (e.g. inline keyboard presses)
        elif "callback_query" in update:
            cb = update["callback_query"]
            data = cb.get("data", "")
            cb_id = cb.get("id")

            parsed = parse_callback_query(data)
            if parsed:
                # We yield a special inbound event for actions
                inbound_action = {
                    "kind": "action",
                    "action": parsed["action"],
                    "approval_id": parsed["approval_id"],
                    "from_id": str(cb.get("from", {}).get("id", "")),
                    "callback_query_id": cb_id,
                }
                self._callback(inbound_action)

                # We can answer the callback query immediately to stop the loading spinner
                # or rely on the core to send an ack. We'll do a quick ack here.
                if self.client and self.ctx:
                    # Best effort ack in background
                    import asyncio

                    asyncio.create_task(self.client.answer_callback_query(cb_id))


# The entrypoint defined in openclaw.plugin.json
plugin = TelegramChannelPlugin()
