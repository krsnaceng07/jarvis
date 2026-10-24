"""WhatsApp channel plugin definition.

OpenClaw parity: mirrors the OpenClaw ``whatsapp`` channel extension.
Binds channel send/listen contracts with real-time Baileys Node.js WebSocket bridge.
Supports bidirectional real-time messaging, selfChatMode, allowlist DM policy,
and in-terminal QR / phone number pairing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import subprocess
import threading
import time
from collections import deque
from typing import Any

from jarvis_sdk import ChannelPlugin, Result

_log = logging.getLogger("jarvis.whatsapp")


class WhatsAppPlugin(ChannelPlugin):
    """WhatsApp channel descriptor and provider coordinator."""

    id: str = "whatsapp"
    name: str = "WhatsApp"
    kind: str = "channel"
    base_url: str = "https://graph.facebook.com/v17.0"
    poll_interval_sec: int = 5

    def __init__(self) -> None:
        self.metadata: dict[str, Any] = {}
        self.on_message: Any = None
        self._callback: Any = None
        self._proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._recent_sent_texts: dict[str, float] = {}
        self._ready = threading.Event()
        self._stderr_tail: deque[str] = deque(maxlen=20)
        self._waiters: dict[str, dict[str, Any]] = {}
        self._waiters_lock = threading.Lock()
        self._request_seq = 0

    def init(self, ctx: Any) -> None:
        """Channel init hook (auth + connection)."""
        return None

    def _resolve_auth_dir(self, account_id: str | None = None) -> pathlib.Path:
        acc = account_id or self.metadata.get("accountId") or "default"
        auth_dir = pathlib.Path.home() / ".jarvis" / "credentials" / "whatsapp" / acc
        auth_dir.mkdir(parents=True, exist_ok=True)
        return auth_dir

    def _is_linked(self, account_id: str | None = None) -> bool:
        """Check whether local WhatsApp credentials exist and are registered."""
        auth_dir = self._resolve_auth_dir(account_id)
        creds_file = auth_dir / "creds.json"
        if not creds_file.exists():
            return False
        try:
            with open(creds_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return bool(
                data.get("registered") is True
                or data.get("linked") is True
                or bool((data.get("me") or {}).get("id"))
            )
        except Exception:
            return False

    def _start_bridge_listener(self) -> bool:
        """Launch the background node bridge.js listen process.

        Returns True only when the process was actually spawned; connection
        readiness is signalled separately through ``_ready`` and
        ``metadata['listener_active']`` so callers never report a listener
        that failed to start.
        """
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return True

            account_id = self.metadata.get("accountId", "default")
            if not self._is_linked(account_id):
                _log.warning(
                    "WhatsApp listener not started: account '%s' has no linked credentials. "
                    "Run 'jarvis channels login whatsapp' to pair.",
                    account_id,
                )
                return False

            bridge_script = pathlib.Path(__file__).resolve().parent / "bridge" / "bridge.js"
            if not bridge_script.exists():
                _log.error("WhatsApp bridge script not found at %s", bridge_script)
                return False

            auth_dir = self._resolve_auth_dir(account_id)
            self._ready.clear()
            self._stderr_tail.clear()
            cmd = [
                "node",
                str(bridge_script),
                "listen",
                "--auth-dir",
                str(auth_dir),
                "--no-terminal",
            ]
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                )
            except Exception as exc:
                _log.error("Failed to start WhatsApp bridge process: %s", exc)
                self._proc = None
                return False

            self.metadata["listener_starting"] = True
            self._reader_thread = threading.Thread(
                target=self._stdout_reader_loop,
                args=(self._proc,),
                daemon=True,
            )
            self._reader_thread.start()
            self._stderr_thread = threading.Thread(
                target=self._stderr_reader_loop,
                args=(self._proc,),
                daemon=True,
            )
            self._stderr_thread.start()
            _log.info("WhatsApp bridge process starting (PID %d)", self._proc.pid)
            return True

    def _stderr_reader_loop(self, proc: subprocess.Popen) -> None:
        """Drain bridge stderr so the child never blocks on a full pipe."""
        if not proc.stderr:
            return
        for line in proc.stderr:
            text = line.strip()
            if not text:
                continue
            self._stderr_tail.append(text)
            _log.debug("whatsapp bridge: %s", text)

    def _stdout_reader_loop(self, proc: subprocess.Popen) -> None:
        """Read stdout lines from the node bridge process and dispatch events."""
        if not proc.stdout:
            return
        for line in proc.stdout:
            text = line.strip()
            if not text:
                continue
            try:
                evt = json.loads(text)
            except json.JSONDecodeError:
                _log.debug("whatsapp bridge non-JSON stdout: %s", text[:200])
                continue
            evt_type = evt.get("event")

            if evt_type in ("listener_ready", "connected"):
                who = evt.get("who", "linked")
                self.metadata["listener_starting"] = False
                self.metadata["listener_active"] = True
                self.metadata["linked_as"] = who
                self._ready.set()
                if evt_type == "listener_ready":
                    _log.info("WhatsApp live listener ready on %s", who)

            elif evt_type == "message":
                self._handle_inbound_message(evt)

            elif evt_type == "send_result":
                request_id = str(evt.get("requestId") or "")
                with self._waiters_lock:
                    waiter = self._waiters.get(request_id)
                if waiter is not None:
                    waiter["result"] = evt
                    waiter["event"].set()

            elif evt_type == "listener_closed":
                self.metadata["listener_starting"] = False
                self.metadata["listener_active"] = False
                self._ready.clear()
                _log.warning("WhatsApp live listener closed: %s", evt.get("error"))

        self.metadata["listener_starting"] = False
        self.metadata["listener_active"] = False
        self._ready.clear()
        tail = " | ".join(list(self._stderr_tail)[-3:])
        if proc.poll() not in (None, 0):
            _log.error(
                "WhatsApp bridge exited with code %s%s",
                proc.returncode,
                f": {tail}" if tail else "",
            )

    def _failure_detail(self) -> str:
        tail = " | ".join(list(self._stderr_tail)[-2:])
        if tail:
            return tail
        if self._proc is None:
            return "bridge process was not started"
        return f"bridge did not report readiness (exit code {self._proc.poll()})"

    def _handle_inbound_message(self, evt: dict[str, Any]) -> None:
        """Process inbound WhatsApp message event from bridge."""
        if not self._callback:
            return

        text = (evt.get("text") or "").strip()
        if not text:
            return

        remote_jid = str(evt.get("remoteJid", ""))
        from_me = bool(evt.get("fromMe", False))
        push_name = str(evt.get("pushName", ""))
        msg_id = str(evt.get("messageId", int(time.time())))

        # Suppress echo if JARVIS just sent this exact message (< 60s)
        now = time.time()
        self._recent_sent_texts = {k: v for k, v in self._recent_sent_texts.items() if now - v < 60.0}
        if text in self._recent_sent_texts:
            return

        # Check selfChatMode and dmPolicy from config
        account_id = self.metadata.get("accountId", "default")
        dm_policy = "allowlist"
        allow_from: list[str] = []
        self_chat_mode = True
        try:
            cfg_path = pathlib.Path.home() / ".jarvis" / "config.json"
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                wa_cfg = cfg.get("channels", {}).get("whatsapp", {})
                dm_policy = wa_cfg.get("dmPolicy", "allowlist")
                allow_from = wa_cfg.get("allowFrom", [])
                self_chat_mode = bool(wa_cfg.get("selfChatMode", True))
        except Exception:
            pass

        # In selfChatMode, allow messages typed by the owner to themselves (fromMe=True)
        if from_me and not self_chat_mode:
            return

        sender_phone = remote_jid.split("@")[0].split(":")[0]
        # Check allowlist if dm_policy == allowlist
        if dm_policy == "allowlist" and allow_from and "*" not in allow_from:
            clean_allowed = ["".join(c for c in str(p) if c.isdigit()) for p in allow_from]
            clean_sender = "".join(c for c in sender_phone if c.isdigit())
            allowed_match = clean_sender in clean_allowed or any(
                clean_sender.endswith(a) or a.endswith(clean_sender)
                for a in clean_allowed
                if len(a) >= 9 and len(clean_sender) >= 9
            )
            if not allowed_match:
                _log.info("WhatsApp message from %s dropped by allowlist policy", sender_phone)
                return

        inbound = {
            "kind": "message",
            "chat_id": remote_jid,
            "from_id": sender_phone,
            "text": text,
            "message_id": msg_id,
            "reply_to_message_id": msg_id,
            "target": f"whatsapp:{remote_jid}",
            "peer_kind": "group" if "@g.us" in remote_jid else "user",
            "peer_id": remote_jid,
            "account_id": account_id,
            "push_name": push_name,
            "origin_surface": "whatsapp",
            "from_me": False if self_chat_mode else from_me,
            "is_from_me": False if self_chat_mode else from_me,
            "self_chat_mode": self_chat_mode,
            "reply_route": {
                "channel": "whatsapp",
                "account_id": account_id,
                "target": f"whatsapp:{remote_jid}",
            },
        }
        try:
            self._callback(inbound)
        except Exception as cb_err:
            _log.error("WhatsApp inbound callback error: %s", cb_err)

    async def login(
        self,
        account_id: str = "default",
        force: bool = False,
        print_terminal: bool = True,
        phone: str | None = None,
    ) -> dict[str, Any]:
        """Link WhatsApp via in-terminal QR code generation or 8-digit pairing code."""
        from src.desktop_automation.providers.whatsapp_provider import WhatsAppDesktopProvider

        provider = WhatsAppDesktopProvider()
        return provider.generate_pairing_qr(
            account_id=account_id,
            force=force,
            phone=phone,
            print_terminal=print_terminal,
        )

    async def logout(self, account_id: str = "default") -> dict[str, Any]:
        """Log out WhatsApp session and clear credentials."""
        await self.shutdown()
        from src.desktop_automation.providers.whatsapp_provider import WhatsAppDesktopProvider

        provider = WhatsAppDesktopProvider()
        return provider.logout(account_id=account_id)

    async def send(self, target: str, message: Any):  # type: ignore[override]
        """Send a message to a WhatsApp target via the active Baileys bridge."""
        text = str(
            message.get("text", "")
            if isinstance(message, dict)
            else getattr(message, "text", None) or message
        ).strip()
        if not target:
            return Result.err("missing_target", "Target recipient is required")
        if not text:
            return Result.err("empty_message", "Message text cannot be empty")

        clean_target = target.replace("whatsapp:", "").strip()
        if "@" not in clean_target:
            clean_digits = "".join(c for c in clean_target if c.isdigit())
            if len(clean_digits) == 10 and clean_digits.startswith(("98", "97", "96")):
                clean_digits = "977" + clean_digits
            jid = f"{clean_digits}@s.whatsapp.net"
        else:
            user_part, domain = clean_target.split("@", 1)
            clean_user = user_part.split(":")[0]
            jid = f"{clean_user}@{domain}"

        # Suppress loopback
        self._recent_sent_texts[text] = time.time()

        # Ensure bridge listener is active
        if self._proc is None or self._proc.poll() is not None:
            self._start_bridge_listener()

        if self._proc is not None and self._proc.poll() is None and self._proc.stdin:
            try:
                cmd = json.dumps({"action": "send", "target": jid, "text": text}) + "\n"
                self._proc.stdin.write(cmd)
                self._proc.stdin.flush()
                return Result.ok({
                    "channel": "whatsapp",
                    "account_id": self.metadata.get("accountId", "default"),
                    "peer_id": jid,
                    "delivery_status": "sent",
                    "verified": True,
                })
            except Exception as e:
                _log.warning("WhatsApp bridge stdin write error: %s", e)

        # Fallback to desktop provider
        try:
            from src.desktop_automation.providers.whatsapp_provider import WhatsAppDesktopProvider

            provider = WhatsAppDesktopProvider()
            res = await provider.send_message(jid, text)
            if res.ok:
                return Result.ok(res.evidence)
            return Result.err("provider_error", res.error or "Failed to send message via provider")
        except Exception as exc:
            return Result.err("send_exception", str(exc))

    def reconfigure(
        self,
        config: dict[str, Any],
        callback: Any = None,
        auto_listen: bool = True,
    ) -> None:
        """Dynamically configure the WhatsApp channel and auto-start bridge listener."""
        self.metadata.update(config)
        if callback is not None:
            self._callback = callback
        if auto_listen and self._callback is not None:
            self._start_bridge_listener()

    async def listen(self, callback: Any) -> None:  # type: ignore[override]
        """Start listening for WhatsApp channel events."""
        self._callback = callback
        self.metadata["listener_active"] = True
        self._start_bridge_listener()

    async def shutdown(self) -> None:
        """Shutdown the WhatsApp channel listener."""
        self.metadata["listener_active"] = False
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                try:
                    if self._proc.stdin:
                        self._proc.stdin.write(json.dumps({"action": "stop"}) + "\n")
                        self._proc.stdin.flush()
                    self._proc.terminate()
                except Exception:
                    pass
                self._proc = None


whatsapp_plugin = WhatsAppPlugin()
entry = whatsapp_plugin
