"""IMAP account watcher service for dispatching email events to agents."""

from __future__ import annotations

import asyncio
import email
from email import policy
import logging
import time
from typing import Any, Callable

from .config import ImapAccountConfig
from .prompt import render_imap_prompt
from .sender_gate import evaluate_imap_sender
from .state import (
    advance_imap_cursor,
    count_imap_skip,
    initialize_imap_cursor,
    record_imap_attempt,
    remember_imap_message,
    ImapWatcherState,
)

logger = logging.getLogger("jarvis.extensions.imap")

MAX_SOURCE_BYTES = 1_048_576
MAX_ATTEMPTS = 3
MAX_RECONNECT_DELAY_SECONDS = 60.0


def _sender_domain(sender: str | None) -> str:
    if not sender or "@" not in sender:
        return "unknown"
    return sender.rsplit("@", 1)[-1].lower()


def _parse_raw_email(raw_bytes: bytes) -> dict[str, Any]:
    """Parse raw RFC822/MIME bytes using Python's standard email module."""
    try:
        msg = email.message_from_bytes(raw_bytes, policy=policy.default)
        from_header = str(msg.get("From", ""))
        subject_header = str(msg.get("Subject", "(no subject)"))
        to_header = [str(addr) for addr in msg.get_all("To", [])]
        delivered_to = [str(addr) for addr in msg.get_all("Delivered-To", [])]
        auth_results = [str(r) for r in msg.get_all("Authentication-Results", [])]
        message_id = str(msg.get("Message-ID", "")).strip()

        # Extract plain text body and attachments
        body = ""
        attachments: list[str] = []
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disp = str(part.get("Content-Disposition", ""))
                if "attachment" in content_disp:
                    filename = part.get_filename()
                    if filename:
                        attachments.append(filename)
                elif content_type == "text/plain" and not body:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        body = payload.decode(
                            part.get_content_charset() or "utf-8", errors="replace"
                        )
        else:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            elif isinstance(payload, str):
                body = payload

        return {
            "from": from_header,
            "subject": subject_header,
            "to": to_header,
            "delivered_to": delivered_to,
            "headers": {"authentication-results": auth_results},
            "message_id": message_id,
            "text": body,
            "attachments": attachments,
        }
    except Exception as err:
        logger.debug(f"Failed to parse email message: {err}")
        return {
            "from": "unknown",
            "subject": "(no subject)",
            "text": "",
            "attachments": [],
            "headers": {},
        }


class ImapAccountWatcher:
    """Watches an IMAP account and dispatches verified incoming messages to agent turns."""

    def __init__(
        self,
        account_id: str,
        account: ImapAccountConfig,
        runtime: Any,
        state: ImapWatcherState,
        context: Any = None,
        authenticator: Callable[[bytes], Any] | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.account_id = account_id
        self.account = account
        self.runtime = runtime
        self.state = state
        self.context = context
        self.authenticator = authenticator
        self.client_factory = client_factory

        self._stopping = False
        self._failures = 0
        self._auth_failures = 0
        self._poll_task: asyncio.Task[None] | None = None
        self._active_client: Any = None

    def start(self) -> None:
        if not self.account.allowed_senders:
            logger.warning(
                f"imap: account={self.account_id} disabled; configure allowedSenders before watching"
            )
            return
        self._stopping = False
        self._poll_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        if self._active_client:
            try:
                if hasattr(self._active_client, "close"):
                    res = self._active_client.close()
                    if hasattr(res, "__await__"):
                        await res
            except Exception:
                pass
            self._active_client = None

    async def _run_loop(self) -> None:
        while not self._stopping:
            try:
                await self._connect_and_poll()
            except asyncio.CancelledError:
                break
            except Exception as err:
                self._failures += 1
                logger.warning(f"imap: account={self.account_id} connection error={err}")
                delay = min(1.0 * (2**self._failures), MAX_RECONNECT_DELAY_SECONDS)
                await asyncio.sleep(delay)

    async def _connect_and_poll(self) -> None:
        # If a custom client factory is injected (e.g. for testing)
        client = self.client_factory(self.account) if self.client_factory else None
        self._active_client = client

        # Initialize cursor
        uid_validity = getattr(client, "uid_validity", "1") if client else "1"
        uid_next = getattr(client, "uid_next", 1) if client else 1
        init_res = await initialize_imap_cursor(
            self.state, self.account_id, str(uid_validity), uid_next
        )
        cursor = init_res["cursor"]

        while not self._stopping:
            if client and hasattr(client, "fetch_messages"):
                messages = await client.fetch_messages(cursor.last_seen_uid + 1)
                for msg in sorted(messages, key=lambda m: getattr(m, "uid", 0)):
                    uid = getattr(msg, "uid", 0)
                    raw_bytes = getattr(msg, "raw", b"")
                    ok = await self.process_message(uid, raw_bytes, cursor.uid_validity)
                    if not ok:
                        break
                    await advance_imap_cursor(self.state, self.account_id, cursor.uid_validity, uid)
                    cursor.last_seen_uid = uid

            await asyncio.sleep(self.account.watch.poll_seconds)

    async def process_message(
        self,
        uid: int,
        raw_bytes: bytes,
        uid_validity: str,
    ) -> bool:
        key = f"{self.account_id}:{uid_validity}:{uid}"
        if not raw_bytes:
            await self._record_skip(uid, None, "message-source-missing")
            return True

        mail = _parse_raw_email(raw_bytes)
        verdict = await evaluate_imap_sender(
            mail=mail,
            raw=raw_bytes,
            internal_date=time.time(),
            account=self.account,
            authenticator=self.authenticator,
        )

        if not verdict.accepted:
            if (
                verdict.transient
                and (await record_imap_attempt(self.state, key, verdict.reason)) < MAX_ATTEMPTS
            ):
                logger.warning(
                    f"imap: account={self.account_id} uid={uid} domain={_sender_domain(verdict.sender)} gate={verdict.reason} retry=true"
                )
                return False

            await self.state.claims.register_if_absent(
                key,
                {"accountId": self.account_id, "uid": uid, "recordedAt": time.time()},
            )
            await self._record_skip(uid, verdict.sender, verdict.reason)
            return True

        # Check message ring duplicate
        msg_id = mail.get("message_id")
        if msg_id:
            ring = await self.state.message_ids.lookup(self.account_id)
            if ring and msg_id in ring.message_ids:
                await self._record_skip(uid, verdict.sender, "duplicate-message-id")
                return True

        # Register claim
        claimed = await self.state.claims.register_if_absent(
            key,
            {"accountId": self.account_id, "uid": uid, "recordedAt": time.time()},
        )
        if not claimed:
            await self._record_skip(uid, verdict.sender, "duplicate-uid")
            return True

        session_key = f"hook:imap:{key}"
        rendered_prompt = render_imap_prompt(
            mail, self.account, source_truncated=len(raw_bytes) > MAX_SOURCE_BYTES
        )

        dispatch_ok = False
        run_id = "run-default"
        if (
            self.runtime
            and hasattr(self.runtime, "hooks")
            and hasattr(self.runtime.hooks, "dispatch_hook_agent_turn")
        ):
            try:
                res = await self.runtime.hooks.dispatch_hook_agent_turn(
                    name=f"IMAP {self.account_id}",
                    agent_id=self.account.agent_id,
                    session_key=session_key,
                    message=rendered_prompt,
                    external_content_source="email",
                    deliver=self.account.deliver,
                    idempotency_key=session_key,
                    model=self.account.model,
                    thinking=self.account.thinking,
                    timeout_seconds=self.account.timeout_seconds,
                )
                if isinstance(res, dict):
                    dispatch_ok = bool(res.get("ok", False))
                    run_id = str(res.get("runId") or res.get("run_id") or "run-default")
                elif hasattr(res, "ok"):
                    dispatch_ok = bool(res.ok)
                    run_id = getattr(res, "run_id", "run-default")
            except Exception as e:
                logger.warning(f"IMAP turn dispatch exception: {e}")
                dispatch_ok = False
        else:
            dispatch_ok = True

        if dispatch_ok:
            if msg_id:
                await remember_imap_message(self.state, self.account_id, msg_id)
            logger.info(
                f"imap: account={self.account_id} uid={uid} domain={_sender_domain(verdict.sender)} strength={verdict.strength} run={run_id}"
            )
            return True

        await self.state.claims.delete(key)
        if (await record_imap_attempt(self.state, key, "dispatch-rejected")) < MAX_ATTEMPTS:
            logger.warning(f"imap: account={self.account_id} uid={uid} dispatch rejected")
            return False

        await self.state.claims.register_if_absent(
            key,
            {"accountId": self.account_id, "uid": uid, "recordedAt": time.time()},
        )
        await self._record_skip(uid, verdict.sender, "dispatch-rejected")
        return True

    async def _record_skip(self, uid: int, sender: str | None, reason: str) -> None:
        await count_imap_skip(self.state, self.account_id, reason)
        logger.warning(
            f"imap: account={self.account_id} uid={uid} domain={_sender_domain(sender)} gate={reason}"
        )
