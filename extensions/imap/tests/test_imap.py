"""Unit tests for IMAP extension."""

from __future__ import annotations

import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from extensions.imap.src.config import (
    resolve_imap_config,
    ImapAccountConfig,
    ImapSenderAuth,
    ImapAddressToken,
)
from extensions.imap.src.prompt import render_imap_prompt
from extensions.imap.src.state import (
    create_imap_state,
    initialize_imap_cursor,
    advance_imap_cursor,
    remember_imap_message,
    count_imap_skip,
    record_imap_attempt,
)
from extensions.imap.src.sender_gate import (
    evaluate_imap_sender,
    matches_imap_sender,
    meets_identifier_authentication,
)
from extensions.imap.src.watcher import ImapAccountWatcher


def test_resolve_imap_config() -> None:
    raw = {
        "accounts": {
            "inbox": {
                "host": "imap.example.com",
                "user": "agent@example.com",
                "password": "secret-password",
                "agentId": "agent-1",
                "port": 993,
                "mailbox": "INBOX",
                "allowedSenders": ["admin@example.com", "@partner.org"],
                "senderAuth": {
                    "min": "asserted",
                    "trustedAuthservIds": ["auth.example.com"],
                    "acceptTrustedAuthservId": True,
                },
                "addressTokens": [{"token": "sec123", "senders": ["admin@example.com"]}],
                "deliver": True,
                "includeBody": True,
                "maxBytes": 10000,
            }
        }
    }
    cfg = resolve_imap_config(raw)
    assert "inbox" in cfg.accounts
    acc = cfg.accounts["inbox"]
    assert acc.host == "imap.example.com"
    assert acc.user == "agent@example.com"
    assert acc.password == "secret-password"
    assert acc.agent_id == "agent-1"
    assert acc.sender_auth.min == "asserted"
    assert acc.sender_auth.accept_trusted_authserv_id is True
    assert len(acc.address_tokens) == 1
    assert acc.address_tokens[0].token == "sec123"

    # Test invalid id
    with pytest.raises(ValueError, match="not session-safe"):
        resolve_imap_config(
            {
                "accounts": {
                    "invalid id!": {"host": "h", "user": "u", "password": "p", "agentId": "a"}
                }
            }
        )


def test_render_imap_prompt() -> None:
    account = ImapAccountConfig(
        host="h", user="u", password="p", agent_id="a", include_body=True, max_bytes=500
    )
    mail = {
        "from": "alice@example.com",
        "subject": "Status update",
        "text": "Hello world from the automated test!",
        "attachments": ["report.pdf"],
    }
    rendered = render_imap_prompt(mail, account, source_truncated=False)
    assert "From: alice@example.com" in rendered
    assert "Subject: Status update" in rendered
    assert "Snippet: Hello world" in rendered
    assert "Attachments: report.pdf" in rendered
    assert "Hello world from the automated test!" in rendered

    # Test byte limit truncation
    small_account = ImapAccountConfig(
        host="h", user="u", password="p", agent_id="a", include_body=True, max_bytes=100
    )
    truncated = render_imap_prompt(mail, small_account, source_truncated=False)
    assert "[truncated: email content exceeded the configured byte limit]" in truncated
    assert len(truncated.encode("utf-8")) <= 100


def test_matches_imap_sender() -> None:
    entries = ["user@example.com", "@company.org"]
    assert matches_imap_sender("user@example.com", entries) is True
    assert matches_imap_sender("other@example.com", entries) is False
    assert matches_imap_sender("anyone@company.org", entries) is True
    assert matches_imap_sender("anyone@other.org", entries) is False


def test_meets_identifier_authentication() -> None:
    assert meets_identifier_authentication("verified", "asserted") is True
    assert meets_identifier_authentication("asserted", "verified") is False
    assert meets_identifier_authentication("asserted", "asserted") is True
    assert meets_identifier_authentication("unverified", "mutable") is True


@pytest.mark.asyncio
async def test_state_lifecycle() -> None:
    state = create_imap_state()
    # Baseline
    res = await initialize_imap_cursor(state, "acc1", "100", 5)
    assert res["kind"] == "baseline"
    assert res["cursor"].last_seen_uid == 4

    # Resume
    res2 = await initialize_imap_cursor(state, "acc1", "100", 10)
    assert res2["kind"] == "resume"
    assert res2["cursor"].last_seen_uid == 4

    # Reset
    res3 = await initialize_imap_cursor(state, "acc1", "101", 10)
    assert res3["kind"] == "reset"
    assert res3["cursor"].last_seen_uid == 9

    # Advance
    await advance_imap_cursor(state, "acc1", "101", 15)
    cur = await state.cursors.lookup("acc1")
    assert cur.last_seen_uid == 15

    # Message ring
    assert await remember_imap_message(state, "acc1", "msg-1") is True
    assert await remember_imap_message(state, "acc1", "msg-1") is False
    assert await remember_imap_message(state, "acc1", "msg-2") is True

    # Skips and attempts
    await count_imap_skip(state, "acc1", "invalid-from")
    attempts = await record_imap_attempt(state, "acc1:101:1", "temp-err")
    assert attempts == 1
    attempts2 = await record_imap_attempt(state, "acc1:101:1", "temp-err")
    assert attempts2 == 2


@pytest.mark.asyncio
async def test_evaluate_imap_sender() -> None:
    account = ImapAccountConfig(
        host="h",
        user="u",
        password="p",
        agent_id="a",
        allowed_senders=["@example.com"],
        sender_auth=ImapSenderAuth(
            min="asserted",
            trusted_authserv_ids=["mail.trusted.com"],
            accept_trusted_authserv_id=True,
        ),
        address_tokens=[ImapAddressToken(token="mytoken", senders=["@example.com"])],
    )

    # 1. Invalid sender not allowed
    v1 = await evaluate_imap_sender(
        mail={"from": "bad@unknown.com"},
        raw=b"",
        internal_date=time.time(),
        account=account,
    )
    assert v1.accepted is False
    assert v1.reason == "sender-not-allowed"

    # 2. Token match
    v2 = await evaluate_imap_sender(
        mail={"from": "user@example.com", "delivered-to": "bot+mytoken@example.com"},
        raw=b"",
        internal_date=time.time(),
        account=account,
    )
    assert v2.accepted is True
    assert v2.reason == "token"

    # 3. Trusted Authentication-Results Header Pass
    v3 = await evaluate_imap_sender(
        mail={
            "from": "user@example.com",
            "headers": {"authentication-results": "mail.trusted.com; dmarc=pass"},
        },
        raw=b"",
        internal_date=time.time(),
        account=account,
    )
    assert v3.accepted is True
    assert v3.strength == "asserted"


@pytest.mark.asyncio
async def test_watcher_process_message() -> None:
    account = ImapAccountConfig(
        host="h",
        user="u",
        password="p",
        agent_id="agent-test",
        allowed_senders=["@example.com"],
        sender_auth=ImapSenderAuth(
            min="asserted",
            trusted_authserv_ids=["mail.trusted.com"],
            accept_trusted_authserv_id=True,
        ),
    )
    state = create_imap_state()
    runtime = MagicMock()
    runtime.hooks = MagicMock()
    runtime.hooks.dispatch_hook_agent_turn = AsyncMock(
        return_value={"ok": True, "runId": "run-123"}
    )

    watcher = ImapAccountWatcher(
        account_id="test-acc",
        account=account,
        runtime=runtime,
        state=state,
    )

    raw_email = (
        b"From: user@example.com\r\n"
        b"Subject: Test email\r\n"
        b"Authentication-Results: mail.trusted.com; dmarc=pass\r\n"
        b"Message-ID: <msg-unique-123@example.com>\r\n"
        b"\r\n"
        b"This is the body of the test email."
    )

    ok = await watcher.process_message(uid=1, raw_bytes=raw_email, uid_validity="100")
    assert ok is True
    runtime.hooks.dispatch_hook_agent_turn.assert_called_once()
    assert runtime.hooks.dispatch_hook_agent_turn.call_args.kwargs["agent_id"] == "agent-test"

    # Re-processing same message ID is skipped as duplicate
    ok_dup = await watcher.process_message(uid=2, raw_bytes=raw_email, uid_validity="100")
    assert ok_dup is True
    # Dispatch was not called a second time
    assert runtime.hooks.dispatch_hook_agent_turn.call_count == 1
