"""Channel Manager — OpenClaw-parity channel configuration and runtime listener management.

Manages external messaging channels (Telegram, Discord, etc.):
1. Token validation against official APIs (e.g. Telegram /getMe).
2. Canonical configuration persistence into ~/.jarvis/config.json.
3. Dynamic hot-reloading and start of channel listeners without process restart.
4. Inbound message routing to the live JARVIS agent session.
5. Auto-start of enabled channels upon desktop host startup.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable

import httpx
from jarvis_channels import (
    ChannelTurnRunner,
    DefaultChannelDeliveryAdapter,
    InboundMessage,
    OutboundMessage,
)

_log = logging.getLogger("jarvis.channels.manager")

_NO_MODEL_SELECTED = "No model selected"
_CHANNEL_TEXT_MODEL_ENV = "JARVIS_CHANNEL_TEXT_MODEL"
_DEFAULT_CHANNEL_TEXT_MODEL = "gemini-2.5-flash"


def _get_config_path() -> Path:
    """Return canonical path to ~/.jarvis/config.json."""
    data_dir = Path(os.environ.get("JARVIS_DATA_DIR") or (Path.home() / ".jarvis"))
    return data_dir / "config.json"


def _read_canonical_config() -> dict[str, Any]:
    """Read ~/.jarvis/config.json safely."""
    path = _get_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        _log.warning("Failed to parse %s: %s", path, e)
        return {}


def _get_workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_gemini_api_key() -> str:
    for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "JARVIS_GEMINI_API_KEY"):
        value = os.environ.get(env_name)
        if value:
            return value
    api_path = _get_workspace_root() / "config" / "api_keys.json"
    try:
        data = json.loads(api_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    value = data.get("gemini_api_key")
    return value if isinstance(value, str) else ""


def _load_channel_system_prompt() -> str:
    prompt_path = _get_workspace_root() / "core" / "prompt.txt"
    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS. Reply directly and concisely to the user's channel message. "
            "Do not claim actions were completed unless a tool actually verified them."
        )


def _write_canonical_config(cfg: dict[str, Any]) -> None:
    """Atomically write ~/.jarvis/config.json."""
    path = _get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    temp_path.replace(path)


class ChannelManager:
    """Central manager for external messaging channels in JARVIS."""

    _instance: ChannelManager | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._channels: dict[str, Any] = {}
        self._live_host: Any | None = None
        self._channel_plugins: dict[str, Any] = {}
        self._active_listeners: dict[str, bool] = {}
        self._bot_info: dict[str, dict[str, Any]] = {}
        self._reply_tasks: set[asyncio.Task[None]] = set()
        self._active_channel_tasks: set[asyncio.Task[Any]] = set()
        self._turn_runners: dict[str, ChannelTurnRunner] = {}
        self._worker_loop: asyncio.AbstractEventLoop | None = None
        self._worker_thread: threading.Thread | None = None

    @classmethod
    def get_instance(cls) -> "ChannelManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _ensure_event_loop(self) -> asyncio.AbstractEventLoop:
        """Ensure a running event loop is available for channel turn execution."""
        if self._live_host is not None:
            loop = getattr(self._live_host, "_loop", None)
            if isinstance(loop, asyncio.AbstractEventLoop) and loop.is_running():
                return loop
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                return loop
        except RuntimeError:
            pass
        with self._lock:
            if self._worker_loop is None or not self._worker_loop.is_running():
                self._worker_loop = asyncio.new_event_loop()
                ready = threading.Event()

                def _run() -> None:
                    assert self._worker_loop is not None
                    asyncio.set_event_loop(self._worker_loop)
                    ready.set()
                    self._worker_loop.run_forever()

                self._worker_thread = threading.Thread(
                    target=_run, name="jarvis-channel-worker", daemon=True
                )
                self._worker_thread.start()
                ready.wait(timeout=2.0)
            return self._worker_loop

    def set_live_host(self, live_host: Any) -> None:
        """Register the running JarvisLive or desktop host instance."""
        self._live_host = live_host

    def register_plugin(self, channel_id: str, plugin: Any) -> None:
        """Register a channel plugin instance."""
        self._channel_plugins[channel_id] = plugin

    def get_plugin(self, channel_id: str) -> Any | None:
        """Retrieve registered plugin instance for channel."""
        if channel_id in self._channel_plugins:
            return self._channel_plugins[channel_id]
        # Lazy fallback: attempt import from extensions
        if channel_id == "telegram":
            try:
                from extensions.telegram.src.jarvis_telegram.plugin import plugin as tg_plugin

                self._channel_plugins["telegram"] = tg_plugin
                return tg_plugin
            except Exception as e:
                _log.warning("Could not lazily import telegram plugin: %s", e)
        else:
            try:
                import importlib

                mod = importlib.import_module(f"extensions.{channel_id}.plugin")
                plugin = (
                    getattr(mod, f"{channel_id}_plugin", None)
                    or getattr(mod, "plugin", None)
                    or getattr(mod, "entry", None)
                )
                if plugin is not None:
                    self._channel_plugins[channel_id] = plugin
                    return plugin
            except Exception:
                pass
        return None

    # ── Telegram Configuration & Verification (OpenClaw Parity) ───────

    async def verify_telegram_token(
        self, bot_token: str, timeout_sec: float = 10.0
    ) -> dict[str, Any]:
        """Validate Telegram bot token against https://api.telegram.org/bot<token>/getMe.

        Returns:
            {"ok": True, "result": {...}} on success, or
            {"ok": False, "error": "..."} on failure.
        """
        token = bot_token.strip()
        if not token:
            return {"ok": False, "error": "Bot token cannot be empty."}

        url = f"https://api.telegram.org/bot{token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                r = await client.get(url)
                if r.status_code == 401:
                    return {
                        "ok": False,
                        "error": "Unauthorized: Telegram Bot API rejected the provided token.",
                    }
                r.raise_for_status()
                data = r.json()
                if data.get("ok"):
                    return {"ok": True, "result": data.get("result", {})}
                return {
                    "ok": False,
                    "error": data.get("description", "Unknown Telegram API error."),
                }
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": f"Telegram API HTTP error {e.response.status_code}: {e}"}
        except httpx.RequestError as e:
            return {"ok": False, "error": f"Failed to connect to Telegram API: {e}"}
        except Exception as e:
            return {"ok": False, "error": f"Unexpected error validating Telegram token: {e}"}

    async def configure_telegram(
        self,
        bot_token: str,
        dm_policy: str = "open",
        allow_from: list[str] | None = None,
        polling_interval_sec: int = 1,
        auto_start: bool = True,
        live_host: Any | None = None,
    ) -> dict[str, Any]:
        """Configure Telegram channel with validation, state persistence, and live start."""
        if live_host is not None:
            self._live_host = live_host

        clean_token = bot_token.strip()

        # Step 1: Validate credentials with official Telegram API
        probe_res = await self.verify_telegram_token(clean_token)
        if not probe_res.get("ok"):
            error_msg = probe_res.get("error", "Invalid bot token.")
            _log.error("Telegram verification failed: %s", error_msg)
            return {
                "ok": False,
                "channel": "telegram",
                "error": f"Telegram verification failed: {error_msg}",
            }

        bot_info = probe_res.get("result", {})
        bot_id = bot_info.get("id")
        bot_username = bot_info.get("username", "")
        bot_name = bot_info.get("first_name", "")
        self._bot_info["telegram"] = bot_info

        # Step 2: Persist canonical configuration to ~/.jarvis/config.json
        cfg = _read_canonical_config()
        channels = cfg.setdefault("channels", {})
        channels["telegram"] = {
            "enabled": True,
            "botToken": clean_token,
            "dmPolicy": dm_policy,
            "allowFrom": allow_from if allow_from is not None else ["*"],
            "pollingIntervalSec": max(1, int(polling_interval_sec)),
            "botId": bot_id,
            "botUsername": bot_username,
            "botName": bot_name,
        }
        _write_canonical_config(cfg)

        # Step 3: Sync to TelegramState for legacy CLI compatibility
        try:
            from extensions.telegram.runtime import TelegramState

            tg_state = TelegramState.default()
            tg_state.set_bot_token(clean_token)
            tg_state.set_polling_interval(max(1, int(polling_interval_sec)))
        except Exception as e:
            _log.debug("TelegramState sync skipped: %s", e)

        # Step 4: Hot-reload / start channel listener
        listener_started = False
        if auto_start:
            listener_res = await self.start_channel_listener("telegram")
            listener_started = listener_res.get("ok", False)

        formatted_username = f"@{bot_username}" if bot_username else f"ID:{bot_id}"
        return {
            "ok": True,
            "channel": "telegram",
            "bot_id": bot_id,
            "bot_username": formatted_username,
            "bot_name": bot_name,
            "status": "connected_and_listening" if listener_started else "configured",
            "listener_active": listener_started,
            "message": (
                f"Successfully configured and verified Telegram bot {formatted_username} "
                f"('{bot_name}', ID: {bot_id}). Live listener is "
                f"{'active and polling' if listener_started else 'ready'}."
            ),
        }

    # ── Channel Inbound Dispatcher ─────────────────────────────────────

    def _create_inbound_handler(self, channel_id: str) -> Callable[[dict[str, Any]], None]:
        """Create an inbound event handler for channel updates."""

        def _handler(inbound: dict[str, Any]) -> None:
            kind = inbound.get("kind", "message")
            if kind == "message":
                text = inbound.get("text", "")
                chat_id = inbound.get("chat_id", "")
                from_id = inbound.get("from_id", "")
                sender_name = inbound.get("peer_id") or from_id

                print(f"[JARVIS: {channel_id}] 📥 Inbound from {chat_id} ({sender_name}): {text}")

                if not text:
                    return

                # Strict channel reply isolation (OpenClaw parity):
                # Inbound channel turns must NEVER leak into desktop speakers or HUD.
                # Every channel turn is dispatched directly to ChannelTurnRunner and delivered
                # strictly back to the origin channel route via the channel plugin.
                loop = self._ensure_event_loop()

                def dispatch() -> None:
                    task = loop.create_task(self._run_channel_turn(channel_id, inbound))
                    self._reply_tasks.add(task)
                    task.add_done_callback(self._reply_tasks.discard)

                loop.call_soon_threadsafe(dispatch)

        return _handler

    def _get_turn_runner(self, channel_id: str) -> ChannelTurnRunner:
        runner = self._turn_runners.get(channel_id)
        if runner is not None:
            return runner
        cfg = _read_canonical_config()
        ch_cfg = cfg.get("channels", {}).get(channel_id, {})
        allow_from = ch_cfg.get("allowFrom") or ["*"]
        runner = ChannelTurnRunner(
            channel_id=channel_id,
            allowlist_policy=allow_from,
            dm_policy="open" if str(ch_cfg.get("dmPolicy") or "open").lower() == "open" else "allowlist",
            require_mention=bool(ch_cfg.get("requireMention", False)),
        )
        self._turn_runners[channel_id] = runner
        return runner

    def _normalize_inbound_message(self, channel_id: str, inbound: dict[str, Any]) -> InboundMessage:
        target = str(inbound.get("target") or "")
        if not target:
            chat_id = str(inbound.get("chat_id") or inbound.get("conversation_id") or "")
            target = f"{channel_id}:{chat_id}" if chat_id else ""
        conversation_id = target or str(inbound.get("conversation_id") or "")
        message_id = inbound.get("message_id")
        thread_id = inbound.get("thread_id") or inbound.get("topic_id")
        account_id = inbound.get("account_id") or inbound.get("accountId") or "default"
        peer_kind = str(inbound.get("peer_kind") or inbound.get("peer_type") or "user")
        raw = dict(inbound)
        raw.setdefault("message_id", message_id)
        raw.setdefault("origin_surface", channel_id)
        raw.setdefault("reply_route", {
            "channel": channel_id,
            "account_id": account_id,
            "target": conversation_id,
            "thread_id": str(thread_id) if thread_id is not None else None,
        })
        return InboundMessage(
            channel_id=channel_id,
            conversation_id=conversation_id,
            sender_id=str(inbound.get("from_id") or inbound.get("sender_id") or ""),
            text=str(inbound.get("text") or ""),
            kind=inbound.get("kind", "text"),
            raw=raw,
            is_owner=bool(inbound.get("is_owner", False)),
            attachments=list(inbound.get("attachments") or []),
            location=inbound.get("location"),
            peer_kind=peer_kind,
            peer_id=str(inbound.get("peer_id") or inbound.get("chat_id") or ""),
            account_id=str(account_id),
            thread_id=str(thread_id) if thread_id is not None else None,
        )

    async def _run_channel_turn(self, channel_id: str, inbound: dict[str, Any]) -> None:
        """Run the existing OpenClaw channel turn pipeline for one inbound event."""
        plugin = self.get_plugin(channel_id)
        message = self._normalize_inbound_message(channel_id, inbound)
        if plugin is None or not message.conversation_id:
            _log.error("Missing reply route for %s", channel_id)
            return

        async def send_fn(outbound: OutboundMessage) -> dict[str, Any]:
            delivery_payload = {
                "text": outbound.text,
                "reply_to": outbound.reply_to_id,
                "metadata": dict(outbound.metadata or {}),
                "origin_route": message.raw.get("reply_route"),
            }
            # OpenClaw dual-modality: if channel is telegram (or requested voice),
            # synthesize speech audio alongside text without touching desktop speakers.
            if channel_id == "telegram" and outbound.text:
                try:
                    from src.talk.speech_synthesizer import synthesize_speech_wav_async

                    voice_bytes = await synthesize_speech_wav_async(outbound.text)
                    if voice_bytes:
                        delivery_payload["voice_bytes"] = voice_bytes
                except Exception as e:
                    _log.warning("Voice synthesis skipped: %s", e)

            send_result = await plugin.send(outbound.conversation_id, delivery_payload)
            failed = bool(getattr(send_result, "is_err", False)) or (
                isinstance(send_result, dict) and send_result.get("ok") is False
            )
            return {
                "channel": channel_id,
                "account_id": message.account_id,
                "peer_id": message.peer_id or message.conversation_id,
                "delivery_status": "failed" if failed else "sent",
                "verified": not failed,
            }

        delivery = DefaultChannelDeliveryAdapter(channel_id=channel_id, send_fn=send_fn)
        runner = self._get_turn_runner(channel_id)
        result = await runner.run_turn(
            message,
            agent_dispatch_fn=self._dispatch_channel_agent_turn,
            delivery_adapter=delivery,
        )
        status = "delivered" if result.delivered and not result.error else "failed"
        _log.info(
            "[CHANNEL] turn_id=%s channel=%s account=%s peer=%s session=%s delivery=%s",
            result.turn_id,
            channel_id,
            message.account_id,
            message.peer_id or message.conversation_id,
            result.session_key,
            status,
        )

    async def _dispatch_channel_agent_turn(self, assembled: Any, _delivery: Any) -> str | None:
        """Generate reply content for a channel turn without owning delivery."""
        try:
            live_host = self._live_host
            if live_host is not None and hasattr(live_host, "_runtime_state"):
                live_host._runtime_state.begin_user_turn(
                    assembled.turn_id,
                    assembled.message.text,
                    origin=assembled.message.channel_id,
                    session_id=assembled.session.session_key,
                )

            # OpenClaw parity: ChannelAgentPipeline executes host tools,
            # handles multi-turn loops, records session transcripts, and routes slash commands.
            from src.channels.channel_agent_pipeline import ChannelAgentPipeline

            pipeline = ChannelAgentPipeline.get_instance()
            reply = await pipeline.dispatch_turn(assembled, live_host=live_host)
            if reply:
                return reply

            # Fallback to direct text model if pipeline returned no reply
            fallback_reply = await self._dispatch_channel_text_model_fallback(assembled)
            if fallback_reply:
                return fallback_reply

            return (
                "I received your message, but could not generate a reply. "
                "Please check the channel agent's model configuration and connection."
            )
        except Exception as err:
            _log.exception("Channel agent turn failed for %s: %s", assembled.message.channel_id, err)
            fallback_reply = await self._dispatch_channel_text_model_fallback(assembled)
            if fallback_reply:
                return fallback_reply
            return (
                "I received your message, but could not generate a reply. "
                "Please check the channel agent's model configuration and connection."
            )

    async def _dispatch_channel_text_model_fallback(self, assembled: Any) -> str | None:
        """Generate a channel reply through Gemini text path with temporal & memory context."""
        api_key = _read_gemini_api_key()
        if not api_key:
            return None
        model = os.environ.get(_CHANNEL_TEXT_MODEL_ENV)
        if not model:
            cfg = _read_canonical_config()
            model = (
                cfg.get("channels", {}).get(assembled.message.channel_id, {}).get("model")
                or cfg.get("model")
                or _DEFAULT_CHANNEL_TEXT_MODEL
            )

        # OpenClaw memory context parity (inject long-term memory facts)
        memory_ctx = ""
        try:
            from apps.desktop.src.jarvis_desktop.memory_bridge import (
                format_memory_for_prompt,
                load_memory,
            )

            memory = load_memory()
            memory_ctx = format_memory_for_prompt(memory, _get_workspace_root())
        except Exception:
            pass

        # OpenClaw temporal context parity (LiveClock)
        temporal_ctx = ""
        try:
            from src.system.live_clock import LiveClock

            temporal_ctx = LiveClock.build_temporal_context_prompt()
        except Exception:
            pass

        prompt_blocks = [_load_channel_system_prompt()]
        if temporal_ctx:
            prompt_blocks.append(temporal_ctx)
        if memory_ctx:
            prompt_blocks.append(memory_ctx)

        prompt_blocks.append(
            "[Channel message]\n"
            f"Channel: {assembled.message.channel_id}\n"
            f"Sender: {assembled.message.sender_id}\n"
            f"Message: {assembled.message.text}\n\n"
            "Reply directly and concisely to this channel message."
        )
        prompt = "\n\n".join(prompt_blocks)

        def _generate() -> str:
            from google import genai

            client = genai.Client(api_key=api_key)
            candidates = [
                model,
                "gemini-2.5-flash",
                "gemini-flash-latest",
                "gemini-flash-lite-latest",
                "gemini-2.5-pro",
                "gemini-3-flash-preview",
                "gemini-3.1-flash-lite-preview",
            ]
            unique_candidates: list[str] = []
            for c in candidates:
                if c and c not in unique_candidates:
                    unique_candidates.append(c)

            last_err = None
            for cand in unique_candidates:
                try:
                    response = client.models.generate_content(model=cand, contents=prompt)
                    text = getattr(response, "text", None)
                    if isinstance(text, str) and text.strip():
                        return text.strip()
                except Exception as err:
                    last_err = err
                    _log.warning("Channel fallback candidate model %s failed: %s", cand, err)

            if last_err:
                raise last_err
            return ""

        try:
            reply = await asyncio.to_thread(_generate)
        except Exception:
            _log.exception(
                "Channel Gemini text fallback failed for %s",
                assembled.message.channel_id,
            )
            return None
        return reply or None

    async def _reply_in_channel(self, channel_id: str, target: str, text: str) -> None:
        """Compatibility wrapper for tests and legacy callers."""
        await self._run_channel_turn(
            channel_id,
            {"kind": "message", "target": target, "chat_id": target, "text": text},
        )

    # ── Listener Lifecycle ─────────────────────────────────────────────

    async def start_channel_listener(self, channel_id: str) -> dict[str, Any]:
        """Start or restart the long-polling listener for a channel."""
        cfg = _read_canonical_config()
        ch_cfg = cfg.get("channels", {}).get(channel_id, {})
        if not ch_cfg.get("enabled", False):
            return {"ok": False, "error": f"Channel '{channel_id}' is not enabled in config."}

        plugin = self.get_plugin(channel_id)
        if not plugin:
            return {"ok": False, "error": f"Channel plugin '{channel_id}' not found."}

        handler = self._create_inbound_handler(channel_id)

        try:
            if hasattr(plugin, "reconfigure"):
                plugin.reconfigure(config=ch_cfg, callback=handler, auto_listen=True)
            elif hasattr(plugin, "listen"):
                await plugin.listen(handler)
            else:
                return {
                    "ok": False,
                    "error": f"Channel '{channel_id}' has no listener implementation.",
                }
            self._active_listeners[channel_id] = True
            print(f"[INFO] channel: live listener ACTIVE for '{channel_id}'")
            return {"ok": True, "status": "listening"}
        except Exception as e:
            _log.error("Failed to start listener for %s: %s", channel_id, e)
            return {"ok": False, "error": str(e)}

    async def stop_channel_listener(self, channel_id: str) -> dict[str, Any]:
        """Stop the active listener for a channel."""
        plugin = self.get_plugin(channel_id)
        if plugin and hasattr(plugin, "shutdown"):
            try:
                await plugin.shutdown()
                self._active_listeners[channel_id] = False
                return {"ok": True, "status": "stopped"}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": False, "error": f"Channel '{channel_id}' has no active shutdown."}

    # ── General Dispatcher & Status ────────────────────────────────────

    async def configure_channel(self, channel: str, **kwargs: Any) -> dict[str, Any]:
        """Generic dispatcher for channel configuration."""
        ch = channel.strip().lower()
        if ch == "telegram":
            token = kwargs.get("token") or kwargs.get("bot_token") or kwargs.get("botToken") or ""
            policy = kwargs.get("dm_policy") or kwargs.get("dmPolicy") or "open"
            allow = kwargs.get("allow_from") or kwargs.get("allowFrom")
            return await self.configure_telegram(
                bot_token=token,
                dm_policy=policy,
                allow_from=allow,
                live_host=self._live_host,
            )

        token = kwargs.get("token") or kwargs.get("bot_token") or kwargs.get("botToken") or ""
        policy = kwargs.get("dm_policy") or kwargs.get("dmPolicy") or "open"
        allow = kwargs.get("allow_from") or kwargs.get("allowFrom") or ["*"]
        auto_start = bool(kwargs.get("auto_start", True))

        cfg = _read_canonical_config()
        channels = cfg.setdefault("channels", {})
        cleaned_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k
            not in (
                "token",
                "bot_token",
                "botToken",
                "dm_policy",
                "dmPolicy",
                "allow_from",
                "allowFrom",
                "auto_start",
            )
        }
        channels[ch] = {
            "enabled": True,
            "botToken": token,
            "dmPolicy": policy,
            "allowFrom": allow,
            **cleaned_kwargs,
        }
        _write_canonical_config(cfg)

        listener_started = False
        if auto_start:
            listener_res = await self.start_channel_listener(ch)
            listener_started = bool(listener_res.get("ok", False))

        return {
            "ok": True,
            "channel": ch,
            "status": "connected_and_listening" if listener_started else "configured",
            "listener_active": listener_started,
            "message": f"Successfully configured channel '{ch}'.",
        }

    def get_channel_status(self, channel: str | None = None) -> dict[str, Any]:
        """Return status for all or a specific configured channel."""
        cfg = _read_canonical_config()
        channels = cfg.get("channels", {})
        if channel:
            ch_name = channel.strip().lower()
            ch_data = channels.get(ch_name, {})
            is_active = self._active_listeners.get(ch_name, False)
            return {
                "channel": ch_name,
                "configured": bool(
                    ch_data.get("botToken") or ch_data.get("token") or ch_data.get("enabled")
                ),
                "enabled": ch_data.get("enabled", False),
                "listening": is_active,
                "bot_username": ch_data.get("botUsername") or "",
                "bot_name": ch_data.get("botName") or "",
                "dm_policy": ch_data.get("dmPolicy") or "open",
            }

        summary: dict[str, Any] = {}
        for cname, cdata in channels.items():
            summary[cname] = {
                "configured": bool(
                    cdata.get("botToken") or cdata.get("token") or cdata.get("enabled")
                ),
                "enabled": cdata.get("enabled", False),
                "listening": self._active_listeners.get(cname, False),
                "bot_username": cdata.get("botUsername") or "",
            }
        return summary

    def auto_start_enabled_channels(self, live_host: Any | None = None) -> None:
        """Inspect ~/.jarvis/config.json and launch listeners for enabled channels."""
        if live_host is not None:
            self._live_host = live_host

        cfg = _read_canonical_config()
        channels = cfg.get("channels", {})
        for ch_id, ch_cfg in channels.items():
            if isinstance(ch_cfg, dict) and ch_cfg.get("enabled") and (
                ch_cfg.get("botToken") or ch_cfg.get("token")
            ):
                print(
                    f"[INFO] channel '{ch_id}': found configured credentials; auto-starting listener..."
                )
                try:
                    loop = self._ensure_event_loop()
                    if loop.is_running():
                        def _spawn_listener(cid: str = ch_id) -> None:
                            task = asyncio.create_task(self.start_channel_listener(cid))
                            self._active_channel_tasks.add(task)
                            task.add_done_callback(self._active_channel_tasks.discard)

                        loop.call_soon_threadsafe(_spawn_listener)
                    else:
                        loop.run_until_complete(self.start_channel_listener(ch_id))
                except Exception as e:
                    _log.warning("Could not auto-start %s: %s", ch_id, e)

    def format_channel_status_for_prompt(self) -> str:
        """Format configured channels for injection into the live system instruction.

        Informs the model about active channel listeners across restarts so that
        the assistant knows external channels are already configured and connected.
        """
        summary = self.get_channel_status()
        if not summary:
            return ""
        lines: list[str] = [
            "[CONFIGURED EXTERNAL MESSAGING CHANNELS]",
            "The following messaging channels are already configured and connected on this host:",
        ]
        has_configured = False
        for cname, cinfo in summary.items():
            if cinfo.get("configured") and cinfo.get("enabled"):
                has_configured = True
                u = cinfo.get("bot_username")
                u_str = f" (@{u})" if u else ""
                status_str = "ACTIVE & LISTENING" if cinfo.get("listening") else "ENABLED & READY"
                lines.append(
                    f"- Channel '{cname}': {status_str}{u_str}. "
                    "Inbound messages are received and replied to automatically."
                )
        if not has_configured:
            return ""
        lines.append(
            "CRITICAL: Do NOT ask the user for bot tokens or to reconfigure channels that are already enabled above. "
            "They are already active and persistent across restarts."
        )
        return "\n".join(lines) + "\n"


__all__ = ["ChannelManager"]
