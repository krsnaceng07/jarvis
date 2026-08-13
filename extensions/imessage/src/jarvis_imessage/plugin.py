import asyncio
import logging
from typing import Any, Callable

from jarvis_normalization_core.result import Result, Ok, Err
from jarvis_sdk.contract import ChannelPlugin

from .config import resolve_imessage_account, ResolvedIMessageAccount
from .imsg_client import IMsgClient
from .targets import infer_imessage_target_chat_type

logger = logging.getLogger(__name__)

class IMessagePlugin(ChannelPlugin):
    id = "imessage"
    kind = "channel"
    version = "0.1.0"
    description = "iMessage channel plugin using imsg on a signed-in Mac"

    def __init__(self):
        self._ctx = None
        self._account: ResolvedIMessageAccount = None
        self._client: IMsgClient = None
        self._listen_callback: Callable[[Any], None] = None

    def init(self, ctx: Any) -> None:
        self._ctx = ctx
        self._account = resolve_imessage_account(ctx.config)
        
        if not self._account.enabled:
            logger.info("iMessage plugin is disabled in config")
            return
            
        cli_path = self._account.config.cliPath
        if not cli_path:
            logger.warning("iMessage plugin enabled but cliPath is missing")
            return
            
        self._client = IMsgClient(cli_path=cli_path, db_path=self._account.config.dbPath)
        
    def register(self, api: Any) -> None:
        api.register_channel(self)

    async def _handle_imsg_event(self, event: dict):
        if not self._listen_callback:
            return
            
        method = event.get("method")
        params = event.get("params", {})
        
        if method == "message":
            # Map basic imsg event to generic JARVIS inbound message shape
            # In a full port, this would invoke the complex catchup/dedupe bridge
            message_text = params.get("text", "")
            target = params.get("chat_id") or params.get("handle")
            sender = params.get("handle", "unknown")
            is_from_me = params.get("is_from_me", False)
            
            if is_from_me:
                return # Ignore echos for the basic port
                
            inbound = {
                "channel_id": "imessage",
                "target": f"chat_id:{target}" if "chat_id" in params else sender,
                "sender": sender,
                "text": message_text,
                "raw_event": event
            }
            try:
                if asyncio.iscoroutinefunction(self._listen_callback):
                    await self._listen_callback(inbound)
                else:
                    self._listen_callback(inbound)
            except Exception as e:
                logger.error(f"Error in iMessage listen callback: {e}")

    async def send(self, target: str, message: Any) -> Result[None]:
        if not self._client or not self._client._running:
            return Err("imsg client is not running")
            
        chat_type = infer_imessage_target_chat_type(target)
        if not chat_type:
            return Err(f"Invalid target format: {target}")
            
        try:
            # We assume message is either a string or a dict with text/media
            text = ""
            media = None
            if isinstance(message, str):
                text = message
            elif isinstance(message, dict):
                text = message.get("text", "")
                media = message.get("mediaUrl") or message.get("mediaLocalRoots")
                if isinstance(media, list) and len(media) > 0:
                    media = media[0]
            
            if media:
                guid = await self._client.send_media(target, media, text)
            else:
                guid = await self._client.send_message(target, text)
                
            logger.debug(f"Sent iMessage to {target}, guid: {guid}")
            return Ok(None)
        except Exception as e:
            logger.error(f"Failed to send iMessage: {e}")
            return Err(str(e))

    async def listen(self, callback: Callable[[Any], None]) -> None:
        if not self._client:
            logger.error("Cannot listen, client not initialized")
            return
            
        self._listen_callback = callback
        self._client.on_message(lambda evt: asyncio.create_task(self._handle_imsg_event(evt)))
        await self._client.start()
        
        # Block until cancelled to simulate long-running listen loop
        try:
            while self._client._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def shutdown(self) -> None:
        if self._client:
            await self._client.stop()

plugin = IMessagePlugin()
