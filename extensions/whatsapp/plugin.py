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

from jarvis_sdk import ChannelPlugin, Err, Ok

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
        # Bounded waits; tests shrink these, production keeps the bridge honest.
        self._ready_timeout_sec = 25.0
        self._send_ack_timeout_sec = 25.0
        self._active_logins: dict[str, dict[str, Any]] = {}

    def init(self, ctx: Any) -> None:
        """Channel init hook (auth + connection)."""
        return None

    def _resolve_auth_dir(self, account_id: str | None = None) -> pathlib.Path:
        acc = account_id or self.metadata.get("accountId") or "default"
        auth_dir = pathlib.Path.home() / ".jarvis" / "credentials" / "whatsapp" / acc
        auth_dir.mkdir(parents=True, exist_ok=True)
        return auth_dir

    def _config_linked_flag(self) -> bool | None:
        """Read the persisted link flag, or None when config never recorded it."""
        cfg_path = pathlib.Path.home() / ".jarvis" / "config.json"
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        wa_cfg = (cfg.get("channels") or {}).get("whatsapp") or {}
        flag = wa_cfg.get("linked")
        return flag if isinstance(flag, bool) else None

    def _is_linked(self, account_id: str | None = None) -> bool:
        """Check whether local WhatsApp credentials exist and are registered."""
        if self._config_linked_flag() is False:
            # Server-side logout leaves stale creds.json behind; trust the flag.
            return False
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

    def auth_state(self, account_id: str | None = None) -> dict[str, Any]:
        """Describe the local link state (used by CLI status and agent tools)."""
        auth_dir = self._resolve_auth_dir(account_id)
        who = self._linked_identity(account_id)
        linked = bool(who) and self._is_linked(account_id)
        return {
            "linked": linked,
            "who": who if linked else "",
            "auth_dir": str(auth_dir),
            "creds_file": str(auth_dir / "creds.json"),
        }

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
                error_text = str(evt.get("error") or "")
                _log.warning("WhatsApp live listener closed: %s", error_text)
                if "logged out" in error_text.lower():
                    # The phone unlinked this device; stale creds would otherwise
                    # keep reporting LINKED and fail every send.
                    self.metadata["linked_as"] = ""
                    self._persist_link(False, "", self.metadata.get("accountId", "default"))

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
        self._recent_sent_texts = {
            k: v for k, v in self._recent_sent_texts.items() if now - v < 60.0
        }
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

    def _linked_identity(self, account_id: str | None = None) -> str:
        """Return the linked WhatsApp JID, or '' when not linked."""
        creds_file = self._resolve_auth_dir(account_id) / "creds.json"
        try:
            data = json.loads(creds_file.read_text(encoding="utf-8"))
        except Exception:
            return ""
        me_id = str((data.get("me") or {}).get("id") or "")
        return me_id.split(":")[0] if me_id else ""

    def _persist_link(self, linked: bool, who: str, account_id: str) -> None:
        """Record link state in canonical config so doctor/CLI report the truth."""
        cfg_path = pathlib.Path.home() / ".jarvis" / "config.json"
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        except Exception:
            cfg = {}
        channels = cfg.setdefault("channels", {})
        wa_cfg = channels.setdefault("whatsapp", {})
        if linked:
            wa_cfg["enabled"] = True
        wa_cfg["linked"] = linked
        wa_cfg["who"] = who
        wa_cfg["accountId"] = account_id
        wa_cfg["authDir"] = str(self._resolve_auth_dir(account_id))
        tmp = cfg_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        tmp.replace(cfg_path)

    def _run_login_bridge(
        self,
        auth_dir: pathlib.Path,
        phone: str | None,
        force: bool,
        show_terminal: bool,
        timeout_sec: float = 180.0,
    ) -> dict[str, Any]:
        """Run ``bridge.js login`` and block until paired, cancelled, or timeout."""
        bridge_script = pathlib.Path(__file__).resolve().parent / "bridge" / "bridge.js"
        if not bridge_script.exists():
            return {"ok": False, "error": f"WhatsApp bridge script not found at {bridge_script}"}

        cmd = ["node", str(bridge_script), "login", "--auth-dir", str(auth_dir)]
        digits = "".join(ch for ch in (phone or "") if ch.isdigit())
        if digits:
            cmd += ["--phone", digits]
        if force:
            cmd += ["--force"]
        if not show_terminal:
            cmd += ["--no-terminal"]

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=None,  # inherit: the terminal QR renders straight to the user
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except Exception as exc:
            return {"ok": False, "error": f"Failed to start WhatsApp login bridge: {exc}"}

        deadline = time.monotonic() + timeout_sec
        linked_who = ""
        failure = ""
        try:
            if proc.stdout is None:
                return {"ok": False, "error": "WhatsApp login bridge produced no stdout."}
            for line in proc.stdout:
                if time.monotonic() > deadline:
                    break
                try:
                    evt = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                evt_type = evt.get("event")
                if evt_type == "pairing_code":
                    print(f"WhatsApp pairing code: {evt.get('code')}")
                elif evt_type == "qr" and not show_terminal:
                    print("WhatsApp QR payload received; re-run login with terminal QR enabled.")
                elif evt_type == "connected":
                    linked_who = str(evt.get("who") or "")
                    break
                elif evt_type == "listener_closed":
                    failure = str(evt.get("error") or "login failed")
                    break
        finally:
            if proc.poll() is None:
                # The login bridge flushes creds.json and exits on its own after a
                # successful pair; terminating it instantly can lose the link.
                try:
                    proc.wait(timeout=6 if linked_who else 3)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
        if linked_who:
            return {"ok": True, "linked": True, "who": linked_who}
        if failure:
            return {"ok": False, "error": failure}
        return {
            "ok": False,
            "error": "Timed out waiting for WhatsApp pairing. Run login again for a fresh QR.",
        }

    @staticmethod
    def _quarantine_broken_creds(auth_dir: pathlib.Path) -> None:
        """Move an unreadable creds.json aside so pairing can start clean."""
        creds_file = auth_dir / "creds.json"
        if not creds_file.exists():
            return
        try:
            raw = creds_file.read_text(encoding="utf-8").strip()
            if not raw:
                raise ValueError("empty WhatsApp creds.json")
            json.loads(raw)
            return
        except (json.JSONDecodeError, OSError, UnicodeDecodeError, ValueError):
            pass
        backup = auth_dir / f"creds.broken.{int(time.time())}.json"
        try:
            creds_file.replace(backup)
            _log.warning("WhatsApp creds.json was unreadable; moved it to %s", backup.name)
        except OSError as exc:
            _log.warning("WhatsApp could not quarantine creds.json: %s", exc)

    @staticmethod
    def _render_qr_data_url(qr_payload: str) -> str:
        """Render raw QR payload string into base64 PNG data URL."""
        import base64
        import io
        import qrcode

        img = qrcode.make(qr_payload)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    @staticmethod
    def _render_ascii_qr(qr_payload: str) -> str:
        """Render raw QR payload into terminal ASCII art."""
        import io
        import qrcode

        qr = qrcode.QRCode()
        qr.add_data(qr_payload)
        buf = io.StringIO()
        qr.print_ascii(out=buf, invert=True)
        return buf.getvalue()

    def start_login_qr(
        self,
        account_id: str = "default",
        force: bool = False,
        phone: str | None = None,
        timeout_sec: float = 25.0,
    ) -> dict[str, Any]:
        """Start WhatsApp pairing bridge process and return QR data URL / instructions."""
        who = self._linked_identity(account_id)
        if who and not force:
            return {
                "ok": True,
                "already_linked": True,
                "connected": True,
                "who": who,
                "message": f"WhatsApp is already linked as {who}.",
            }

        # Check existing active login for this account
        with self._lock:
            existing = self._active_logins.get(account_id)
            if existing and not force and existing.get("qr_data_url") and time.time() - existing.get("started_at", 0) < 60.0:
                return {
                    "ok": True,
                    "status": "qr_ready",
                    "qr": existing.get("qr"),
                    "qr_data_url": existing.get("qr_data_url"),
                    "qr_file": existing.get("qr_file"),
                    "ascii_qr": existing.get("ascii_qr"),
                    "message": existing.get("message"),
                }
            if existing and existing.get("proc"):
                try:
                    existing["proc"].terminate()
                except Exception:
                    pass
                self._active_logins.pop(account_id, None)

        auth_dir = self._resolve_auth_dir(account_id)
        if force:
            for entry in auth_dir.iterdir():
                try:
                    if entry.is_dir():
                        import shutil
                        shutil.rmtree(entry)
                    else:
                        entry.unlink()
                except Exception:
                    pass
            self._persist_link(False, "", account_id)
        else:
            self._quarantine_broken_creds(auth_dir)

        bridge_script = pathlib.Path(__file__).resolve().parent / "bridge" / "bridge.js"
        if not bridge_script.exists():
            return {"ok": False, "error": f"WhatsApp bridge script not found at {bridge_script}"}

        cmd = ["node", str(bridge_script), "login", "--auth-dir", str(auth_dir)]
        digits = "".join(ch for ch in (phone or "") if ch.isdigit())
        if digits:
            cmd += ["--phone", digits]
        if force:
            cmd += ["--force"]

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except Exception as exc:
            return {"ok": False, "error": f"Failed to start WhatsApp login bridge: {exc}"}

        deadline = time.monotonic() + timeout_sec
        qr_payload = ""
        pairing_code = ""
        connected_who = ""
        err_msg = ""

        while time.monotonic() < deadline:
            if proc.poll() is not None:
                err_msg = f"Bridge exited early with code {proc.returncode}"
                break
            line = proc.stdout.readline() if proc.stdout else ""
            if not line:
                time.sleep(0.05)
                continue
            try:
                evt = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            evt_type = evt.get("event")
            if evt_type == "qr":
                qr_payload = str(evt.get("qr") or "")
                break
            elif evt_type == "pairing_code":
                pairing_code = str(evt.get("code") or "")
                break
            elif evt_type == "connected":
                connected_who = str(evt.get("who") or "linked")
                break
            elif evt_type == "listener_closed":
                err_msg = str(evt.get("error") or "closed")
                break

        if connected_who:
            self._persist_link(True, connected_who, account_id)
            self._start_bridge_listener()
            return {
                "ok": True,
                "connected": True,
                "who": connected_who,
                "message": f"WhatsApp linked and active as {connected_who}!",
            }

        if pairing_code:
            instructions = (
                f"WhatsApp 8-Digit Pairing Code: **{pairing_code}**\n\n"
                "Enter this code on your phone: Open WhatsApp -> Linked Devices -> Link with phone number instead."
            )
            login_state = {
                "proc": proc,
                "phone": digits,
                "pairing_code": pairing_code,
                "connected": False,
                "who": "",
                "started_at": time.time(),
                "event": threading.Event(),
            }
            with self._lock:
                self._active_logins[account_id] = login_state
            self._start_login_waiter_thread(account_id, login_state)
            return {
                "ok": True,
                "status": "pairing_code_ready",
                "pairing_code": pairing_code,
                "message": instructions,
            }

        if qr_payload:
            qr_data_url = self._render_qr_data_url(qr_payload)
            ascii_qr = self._render_ascii_qr(qr_payload)
            qr_file = auth_dir / "qr.png"
            try:
                import base64
                png_bytes = base64.b64decode(qr_data_url.split(",")[1])
                qr_file.write_bytes(png_bytes)
            except Exception:
                pass

            try:
                print("\n" + "=" * 48)
                print("   JARVIS WHATSAPP QR CODE (SCAN WITH PHONE)")
                print("=" * 48)
                print(ascii_qr)
                print("=" * 48 + "\n")
            except Exception:
                pass

            msg = (
                "WhatsApp QR code generated successfully.\n\n"
                "To link your WhatsApp channel:\n"
                "1. Open WhatsApp on your mobile phone.\n"
                "2. Tap Settings (or 3 dots) -> Linked Devices -> Link a Device.\n"
                "3. Scan the QR code displayed below:\n\n"
                f"![whatsapp-qr]({qr_data_url})\n\n"
                "Once scanned, WhatsApp will link automatically."
            )

            login_state = {
                "proc": proc,
                "qr": qr_payload,
                "qr_data_url": qr_data_url,
                "qr_file": str(qr_file),
                "ascii_qr": ascii_qr,
                "message": msg,
                "connected": False,
                "who": "",
                "started_at": time.time(),
                "event": threading.Event(),
            }
            with self._lock:
                self._active_logins[account_id] = login_state

            self._start_login_waiter_thread(account_id, login_state)

            return {
                "ok": True,
                "status": "qr_ready",
                "qr": qr_payload,
                "qr_data_url": qr_data_url,
                "qr_file": str(qr_file),
                "ascii_qr": ascii_qr,
                "message": msg,
            }

        if err_msg:
            return {"ok": False, "error": f"WhatsApp QR generation failed: {err_msg}"}

        return {"ok": False, "error": "Timed out waiting for WhatsApp QR generation."}

    def _start_login_waiter_thread(self, account_id: str, login_state: dict[str, Any]) -> None:
        """Run background thread waiting for QR scan completion."""
        def _waiter():
            proc = login_state["proc"]
            who = ""
            try:
                if proc.stdout:
                    for line in proc.stdout:
                        try:
                            evt = json.loads(line.strip())
                        except Exception:
                            continue
                        if evt.get("event") == "connected":
                            who = str(evt.get("who") or "linked")
                            login_state["connected"] = True
                            login_state["who"] = who
                            login_state["event"].set()
                            self._persist_link(True, who, account_id)
                            self._start_bridge_listener()
                            _log.info("WhatsApp successfully paired in background as %s", who)
                            break
                        elif evt.get("event") == "listener_closed":
                            break
            finally:
                login_state["event"].set()
                if proc.poll() is None:
                    try:
                        proc.wait(timeout=4)
                    except Exception:
                        proc.kill()

        t = threading.Thread(target=_waiter, daemon=True, name=f"wa-login-waiter-{account_id}")
        t.start()

    async def wait_for_login(
        self,
        account_id: str = "default",
        timeout_sec: float = 90.0,
    ) -> dict[str, Any]:
        """Wait for an in-flight WhatsApp login scan to finish."""
        who = self._linked_identity(account_id)
        if who:
            return {
                "ok": True,
                "connected": True,
                "who": who,
                "message": f"WhatsApp is linked as {who}.",
            }

        with self._lock:
            login_state = self._active_logins.get(account_id)

        if not login_state:
            if self._is_linked(account_id):
                linked_who = self._linked_identity(account_id)
                return {
                    "ok": True,
                    "connected": True,
                    "who": linked_who,
                    "message": f"WhatsApp is linked as {linked_who}.",
                }
            return {
                "ok": False,
                "connected": False,
                "message": "No active WhatsApp login pairing session found. Start pairing first.",
            }

        evt = login_state["event"]
        await asyncio.get_running_loop().run_in_executor(
            None, evt.wait, timeout_sec
        )
        if login_state.get("connected"):
            linked_who = login_state.get("who") or self._linked_identity(account_id)
            return {
                "ok": True,
                "connected": True,
                "who": linked_who,
                "message": f"WhatsApp successfully linked as {linked_who}! Channel listener is now active.",
            }

        return {
            "ok": False,
            "connected": False,
            "message": "WhatsApp pairing still pending. Please scan the QR code with your mobile phone.",
        }

    async def login(
        self,
        account_id: str = "default",
        force: bool = False,
        print_terminal: bool = True,
        phone: str | None = None,
    ) -> dict[str, Any]:
        """Link WhatsApp via in-terminal QR code or an 8-digit pairing code."""
        who = self._linked_identity(account_id)
        if who and not force:
            return {
                "ok": True,
                "already_linked": True,
                "who": who,
                "message": f"WhatsApp is already linked ({who}). Say 'relink' for a fresh QR.",
            }

        await self.shutdown()
        auth_dir = self._resolve_auth_dir(account_id)
        self._quarantine_broken_creds(auth_dir)
        result = await asyncio.to_thread(
            self._run_login_bridge,
            auth_dir,
            phone,
            force,
            print_terminal,
        )
        if result.get("ok"):
            self._persist_link(True, str(result.get("who") or ""), account_id)
            would_refresh = self._callback is not None
            result["message"] = "WhatsApp linked."
            result["listener_restart_required"] = would_refresh
        return result

    async def logout(self, account_id: str = "default") -> dict[str, Any]:
        """Clear the local WhatsApp session.

        Local credentials are deleted; the phone may still list this device under
        Linked Devices until it is removed there manually.
        """
        await self.shutdown()
        auth_dir = self._resolve_auth_dir(account_id)
        removed = 0
        for entry in auth_dir.iterdir():
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    import shutil

                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                removed += 1
            except Exception as exc:
                _log.warning("WhatsApp logout could not remove %s: %s", entry.name, exc)
        self._persist_link(False, "", account_id)
        return {
            "ok": True,
            "removed_files": removed,
            "message": (
                "Local WhatsApp session cleared. If this device still appears under "
                "Linked Devices on the phone, remove it there."
            ),
        }

    async def send(self, target: str, message: Any):  # type: ignore[override]
        """Send a message to a WhatsApp target via the active Baileys bridge."""
        text = str(
            message.get("text", "")
            if isinstance(message, dict)
            else getattr(message, "text", None) or message
        ).strip()
        if not target:
            return Err("Target recipient is required", code="missing_target")
        if not text:
            return Err("Message text cannot be empty", code="empty_message")

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

        # Suppress loopback if the bridge echoes our own outbound message back.
        self._recent_sent_texts[text] = time.time()

        if self._proc is None or self._proc.poll() is not None:
            if not self._start_bridge_listener():
                return Err(
                    f"WhatsApp bridge could not start: {self._failure_detail()}",
                    code="bridge_unavailable",
                )

        if self._proc is None or self._proc.poll() is not None or not self._proc.stdin:
            return Err(
                f"WhatsApp bridge is not running: {self._failure_detail()}",
                code="bridge_unavailable",
            )

        # A freshly spawned bridge still has to open the WhatsApp socket; writing
        # a send command into a connecting socket fails with "Connection Closed".
        if not self._ready.is_set():
            ready = await asyncio.get_running_loop().run_in_executor(
                None, self._ready.wait, self._ready_timeout_sec
            )
            if not ready:
                return Err(
                    f"WhatsApp bridge did not connect within {self._ready_timeout_sec}s: "
                    f"{self._failure_detail()}",
                    code="bridge_not_ready",
                )

        # Wait for the bridge's real send ack instead of claiming delivery the
        # moment bytes hit stdin; a dead socket must surface as a failure.
        self._request_seq += 1
        request_id = f"{int(time.time() * 1000)}-{self._request_seq}"
        waiter: dict[str, Any] = {"event": threading.Event(), "result": None}
        with self._waiters_lock:
            self._waiters[request_id] = waiter
        try:
            payload = {
                "action": "send",
                "target": jid,
                "text": text,
                "requestId": request_id,
            }
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except Exception as exc:
            with self._waiters_lock:
                self._waiters.pop(request_id, None)
            return Err(str(exc), code="bridge_write_failed")

        acked = await asyncio.get_running_loop().run_in_executor(
            None, waiter["event"].wait, self._send_ack_timeout_sec
        )
        with self._waiters_lock:
            self._waiters.pop(request_id, None)
        result = waiter["result"]
        if not acked:
            return Err(
                f"WhatsApp bridge did not acknowledge the send within {self._send_ack_timeout_sec}s.",
                code="bridge_timeout",
            )
        if not result or not result.get("ok"):
            return Err(
                str((result or {}).get("error") or "WhatsApp bridge rejected the message."),
                code="send_failed",
            )
        return Ok(
            {
                "channel": "whatsapp",
                "account_id": self.metadata.get("accountId", "default"),
                "peer_id": jid,
                "delivery_status": "sent",
                "message_id": str(result.get("messageId") or ""),
                "verified": True,
            }
        )

    def reconfigure(
        self,
        config: dict[str, Any],
        callback: Any = None,
        auto_listen: bool = True,
    ) -> bool:
        """Apply channel config; returns whether the listener process started."""
        self.metadata.update(config)
        if callback is not None:
            self._callback = callback
        if auto_listen and self._callback is not None:
            return self._start_bridge_listener()
        return True

    async def listen(self, callback: Any) -> None:  # type: ignore[override]
        """Start the bridge listener and wait until it is actually connected.

        Raises ``RuntimeError`` when the bridge cannot start or does not report
        readiness, so the channel manager never advertises a dead listener.
        """
        self._callback = callback
        already_running = self.metadata.get("listener_active", False)
        if not self._start_bridge_listener():
            raise RuntimeError(f"WhatsApp listener failed to start: {self._failure_detail()}")
        if already_running:
            return
        ready = await asyncio.get_running_loop().run_in_executor(
            None, self._ready.wait, self._ready_timeout_sec
        )
        if not ready:
            self.metadata["listener_active"] = False
            raise RuntimeError(f"WhatsApp bridge did not become ready: {self._failure_detail()}")

    async def shutdown(self) -> None:
        """Shutdown the WhatsApp channel listener."""
        self.metadata["listener_active"] = False
        self._ready.clear()
        with self._lock:
            proc = self._proc
            self._proc = None
        if proc is None or proc.poll() is not None:
            return
        try:
            if proc.stdin:
                proc.stdin.write(json.dumps({"action": "stop"}) + "\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()


whatsapp_plugin = WhatsAppPlugin()
entry = whatsapp_plugin
