from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from jarvis_sdk.contract import ChannelPlugin
from jarvis_normalization_core.result import Result, Ok, Err

from .actions import build_approval_keyboard, parse_callback_query
from .client import TelegramClient
from .config import TelegramConfig
from .formatting import format_for_telegram
from .polling import PollingWorker
from .targets import parse_telegram_target

from jarvis_channels.types import NormalizedLocation

from jarvis_state_core.database import StateDatabase
from jarvis_channels.pairing import PairingStore
from jarvis_channels.allowlist import enforce_dm_policy

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
        opts = StateDatabaseOptions(connection_factory=lambda: sqlite3.connect(db_path, isolation_level=None))
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
                interval=self.config.pollingIntervalSec
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

    async def send(self, target: str, message: Any) -> Result[None]:
        """Send a message to a Telegram target."""
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

        location = getattr(message, "location", None) or (message.get("location") if isinstance(message, dict) else None)

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
                    reply_markup=reply_markup
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
                    reply_markup=reply_markup
                )
        else:
            res = await self.client.send_message(
                chat_id=parsed_target.chat_id,
                text=formatted_text,
                reply_to_message_id=reply_to,
                message_thread_id=parsed_target.message_thread_id,
                reply_markup=reply_markup
            )

        if res.get("ok"):
            return Ok(None)
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

            # We'll construct a canonical target string for the inbound message.
            target_str = f"telegram:{chat_id}"
            if thread_id:
                target_str += f":topic:{thread_id}"

            # Enforce DM policy (Pairing / Allowlist)
            is_allowed, pairing_msg = enforce_dm_policy(
                sender_id=from_id,
                sender_username=msg.get("from", {}).get("username"),
                policy_str=self.config.dmPolicy,
                allowlist=self.config.allowFrom,
                channel_id="telegram",
                account_id="main",
                pairing_store=self._pairing_store
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
                            message_thread_id=thread_id
                        )
                    )
                _log.info(f"Dropped message from {from_id} due to DM policy (pairing/allowlist)")
                return

            # Determine peer kind and id
            peer_kind = "user"
            peer_id = from_id
            if chat_id != from_id:
                peer_kind = "channel" if str(chat_id).startswith("-100") else "group"
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
                    is_live=False
                )
            elif location_dict:
                is_live = "live_period" in location_dict
                normalized_location = NormalizedLocation(
                    latitude=location_dict.get("latitude", 0.0),
                    longitude=location_dict.get("longitude", 0.0),
                    accuracy_m=location_dict.get("horizontal_accuracy"),
                    source="live" if is_live else "pin",
                    is_live=is_live
                )

            inbound = {
                "kind": "message",
                "chat_id": chat_id,
                "thread_id": thread_id,
                "from_id": from_id,
                "text": text,
                "message_id": message_id,
                "target": target_str,
                "peer_kind": peer_kind,
                "peer_id": peer_id,
                "location": normalized_location,
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
                    "callback_query_id": cb_id
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
