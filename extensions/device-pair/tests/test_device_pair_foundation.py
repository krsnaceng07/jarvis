"""Tests for the foundational device-pair port.

Covers the ported modules:
- src/pairing_qr_channel_data.py
- src/pair_command_auth.py
- src/pair_command_approve.py
- src/notify_state.py

Mirrors a subset of OpenClaw's
``extensions/device-pair/pair-command-auth.test.ts`` and
``extensions/device-pair/notify-state.ts`` tests.
"""

from __future__ import annotations

import asyncio
import os
import sys

# The device-pair directory uses a hyphen (``device-pair``)
# which is not a valid Python identifier; the import path
# therefore has to reach the package via a sys.path entry
# that points at the extension root. This is the same
# pattern the OpenClaw source uses for hyphened extension
# names.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EXT_ROOT = os.path.dirname(_THIS_DIR)
if _EXT_ROOT not in sys.path:
    sys.path.insert(0, _EXT_ROOT)

import pytest  # noqa: E402

from lib.notify_state import (  # noqa: E402
    DEVICE_PAIR_NOTIFY_LEGACY_STATE_FILE,
    DEVICE_PAIR_NOTIFY_MAX_SEEN_AGE_MS,
    DEVICE_PAIR_NOTIFY_SUBSCRIBER_MAX_ENTRIES,
    normalize_legacy_notify_state,
    notify_request_store_key,
    notify_subscriber_key,
    notify_subscriber_store_key,
)
from lib.pair_command_approve import (  # noqa: E402
    approve_pending_pairing_request,
    select_pending_approval_request,
)
from lib.pair_command_auth import (  # noqa: E402
    ADMIN_SCOPE,
    PAIRING_SCOPE,
    TALK_SECRETS_SCOPE,
    build_missing_pairing_scope_reply,
    build_missing_setup_handoff_scope_reply,
    resolve_pairing_command_auth_state,
)
from lib.pairing_qr_channel_data import (  # noqa: E402
    DEVICE_PAIR_PAIRING_QR_CHANNEL_DATA_KEY,
    build_device_pair_pairing_qr_channel_data,
)


# ── Pairing QR channel data ───────────────────────────────


class TestPairingQrChannelData:
    def test_wraps_setup_code_and_expiry(self) -> None:
        envelope = build_device_pair_pairing_qr_channel_data(
            {"setupCode": "ABCD-1234", "expiresAtMs": 1_700_000_000_000}
        )
        assert DEVICE_PAIR_PAIRING_QR_CHANNEL_DATA_KEY in envelope
        inner = envelope[DEVICE_PAIR_PAIRING_QR_CHANNEL_DATA_KEY]
        assert inner == {
            "setupCode": "ABCD-1234",
            "expiresAtMs": 1_700_000_000_000,
        }


# ── Pair command auth ─────────────────────────────────────


class TestPairCommandAuth:
    def test_internal_gateway_caller_with_pairing_scope(self) -> None:
        state = resolve_pairing_command_auth_state(
            {
                "channel": "webchat",
                "gatewayClientScopes": [PAIRING_SCOPE],
            }
        )
        assert state["isInternalGatewayCaller"] is True
        assert state["isMissingPairingPrivilege"] is False
        assert state["isMissingSetupHandoffPrivilege"] is True
        assert state["canIssueFullAccessSetup"] is False
        assert state["approvalCallerScopes"] == [PAIRING_SCOPE]

    def test_internal_gateway_caller_with_admin_scope(self) -> None:
        state = resolve_pairing_command_auth_state(
            {
                "gatewayClientScopes": [ADMIN_SCOPE],
            }
        )
        assert state["isInternalGatewayCaller"] is True
        assert state["isMissingPairingPrivilege"] is False
        assert state["isMissingSetupHandoffPrivilege"] is False
        assert state["canIssueFullAccessSetup"] is True

    def test_internal_gateway_caller_with_no_scopes(self) -> None:
        state = resolve_pairing_command_auth_state({"channel": "webchat"})
        assert state["isInternalGatewayCaller"] is True
        assert state["isMissingPairingPrivilege"] is True
        assert state["canIssueFullAccessSetup"] is False

    def test_owner_caller_full_access(self) -> None:
        state = resolve_pairing_command_auth_state({"channel": "discord", "senderIsOwner": True})
        assert state["isInternalGatewayCaller"] is False
        assert state["isMissingPairingPrivilege"] is False
        assert state["isMissingSetupHandoffPrivilege"] is False
        assert state["canIssueFullAccessSetup"] is True
        assert state["approvalCallerScopes"] == ["operator.pairing"]

    def test_external_non_owner_lacks_pairing_privilege(self) -> None:
        state = resolve_pairing_command_auth_state({"channel": "discord", "senderIsOwner": False})
        assert state["isInternalGatewayCaller"] is False
        assert state["isMissingPairingPrivilege"] is True
        assert state["isMissingSetupHandoffPrivilege"] is True
        assert state["canIssueFullAccessSetup"] is False

    def test_talk_secrets_scope_covers_setup_handoff(self) -> None:
        state = resolve_pairing_command_auth_state(
            {
                "channel": "webchat",
                "gatewayClientScopes": [TALK_SECRETS_SCOPE],
            }
        )
        # Talk secrets covers setup-handoff but not pairing
        # approval itself.
        assert state["isMissingPairingPrivilege"] is True
        assert state["isMissingSetupHandoffPrivilege"] is False

    def test_missing_pairing_scope_reply(self) -> None:
        assert build_missing_pairing_scope_reply() == {
            "text": "⚠️ This command requires operator.pairing."
        }

    def test_missing_setup_handoff_scope_reply(self) -> None:
        assert build_missing_setup_handoff_scope_reply() == {
            "text": (
                "⚠️ Setup code handoff includes Talk secrets and requires operator.talk.secrets."
            )
        }


# ── Pair command approve ────────────────────────────────


def _make_pending(request_id: str, ts: int = 0) -> dict:
    return {"requestId": request_id, "ts": ts}


class TestSelectPendingApprovalRequest:
    def test_no_pending_returns_reply(self) -> None:
        result = select_pending_approval_request({"pending": []})
        assert "pending" not in result
        assert result["reply"]["text"] == "No pending device pairing requests."

    def test_single_pending_no_requested(self) -> None:
        result = select_pending_approval_request({"pending": [_make_pending("r1")]})
        assert result["pending"]["requestId"] == "r1"

    def test_multiple_pending_no_requested_returns_multiple_reply(self) -> None:
        result = select_pending_approval_request(
            {
                "pending": [
                    _make_pending("r1", ts=10),
                    _make_pending("r2", ts=20),
                ]
            }
        )
        assert "pending" not in result
        assert "Multiple pending requests found" in result["reply"]["text"]

    def test_latest_returns_highest_ts(self) -> None:
        result = select_pending_approval_request(
            {
                "pending": [
                    _make_pending("r1", ts=10),
                    _make_pending("r2", ts=30),
                    _make_pending("r3", ts=20),
                ],
                "requested": "latest",
            }
        )
        assert result["pending"]["requestId"] == "r2"

    def test_latest_case_insensitive(self) -> None:
        result = select_pending_approval_request(
            {
                "pending": [
                    _make_pending("r1", ts=10),
                    _make_pending("r2", ts=20),
                ],
                "requested": "LATEST",
            }
        )
        assert result["pending"]["requestId"] == "r2"

    def test_specific_request_id(self) -> None:
        result = select_pending_approval_request(
            {
                "pending": [
                    _make_pending("r1", ts=10),
                    _make_pending("r2", ts=20),
                ],
                "requested": "r1",
            }
        )
        assert result["pending"]["requestId"] == "r1"

    def test_unknown_request_id_returns_no_pending(self) -> None:
        result = select_pending_approval_request(
            {
                "pending": [_make_pending("r1", ts=10)],
                "requested": "missing",
            }
        )
        assert "pending" not in result


class TestApprovePendingPairingRequest:
    def test_approve_returns_paired_reply(self) -> None:
        async def approve(req_id, opts):
            return {
                "status": "ok",
                "device": {"displayName": "My Mac", "deviceId": "mac-1"},
            }

        reply = asyncio.run(
            approve_pending_pairing_request({"requestId": "r1"}, approve_device_pairing=approve)
        )
        assert reply == {"text": "✅ Paired My Mac."}

    def test_approve_uses_device_id_when_no_display_name(self) -> None:
        async def approve(req_id, opts):
            return {
                "status": "ok",
                "device": {"deviceId": "mac-1"},
            }

        reply = asyncio.run(
            approve_pending_pairing_request({"requestId": "r1"}, approve_device_pairing=approve)
        )
        assert reply == {"text": "✅ Paired mac-1."}

    def test_approve_forbidden_returns_scope_reply(self) -> None:
        async def approve(req_id, opts):
            return {"status": "forbidden", "scope": "operator.admin"}

        reply = asyncio.run(
            approve_pending_pairing_request({"requestId": "r1"}, approve_device_pairing=approve)
        )
        assert "operator.admin" in reply["text"]
        assert "requires" in reply["text"]

    def test_approve_missing_returns_not_found_reply(self) -> None:
        async def approve(req_id, opts):
            return None

        reply = asyncio.run(
            approve_pending_pairing_request(
                {"requestId": "missing"}, approve_device_pairing=approve
            )
        )
        assert reply == {"text": "Pairing request not found."}

    def test_approve_passes_caller_scopes(self) -> None:
        seen_opts: list = []

        async def approve(req_id, opts):
            seen_opts.append(opts)
            return {"status": "ok", "device": {"deviceId": "d1"}}

        asyncio.run(
            approve_pending_pairing_request(
                {"requestId": "r1", "callerScopes": [ADMIN_SCOPE]},
                approve_device_pairing=approve,
            )
        )
        assert seen_opts == [{"callerScopes": [ADMIN_SCOPE]}]


# ── Notify state ──────────────────────────────────────────


class TestNotifyStateConstants:
    def test_constants_match_openclaw_source(self) -> None:
        assert DEVICE_PAIR_NOTIFY_LEGACY_STATE_FILE == "device-pair-notify.json"
        assert DEVICE_PAIR_NOTIFY_SUBSCRIBER_MAX_ENTRIES == 1024
        assert DEVICE_PAIR_NOTIFY_MAX_SEEN_AGE_MS == 24 * 60 * 60 * 1000


class TestNormalizeLegacyNotifyState:
    def test_normalizes_minimal_valid_state(self) -> None:
        raw = {
            "subscribers": [{"to": "alice", "mode": "persistent", "addedAtMs": 1_000}],
            "notifiedRequestIds": {"r1": 2_000},
        }
        result = normalize_legacy_notify_state(raw)
        assert len(result["subscribers"]) == 1
        assert result["subscribers"][0]["to"] == "alice"
        assert result["subscribers"][0]["mode"] == "persistent"
        assert result["notifiedRequestIds"] == {"r1": 2_000}

    def test_drops_subscribers_without_to(self) -> None:
        raw = {
            "subscribers": [
                {"mode": "persistent", "addedAtMs": 1_000},
                {"to": "bob", "mode": "persistent", "addedAtMs": 1_000},
            ]
        }
        result = normalize_legacy_notify_state(raw)
        assert len(result["subscribers"]) == 1
        assert result["subscribers"][0]["to"] == "bob"

    def test_defaults_mode_to_persistent(self) -> None:
        raw = {"subscribers": [{"to": "alice", "addedAtMs": 1_000}]}
        result = normalize_legacy_notify_state(raw)
        assert result["subscribers"][0]["mode"] == "persistent"

    def test_accepts_once_mode(self) -> None:
        raw = {"subscribers": [{"to": "alice", "mode": "once", "addedAtMs": 1_000}]}
        result = normalize_legacy_notify_state(raw)
        assert result["subscribers"][0]["mode"] == "once"

    def test_normalizes_string_message_thread_id(self) -> None:
        raw = {
            "subscribers": [
                {
                    "to": "alice",
                    "mode": "persistent",
                    "messageThreadId": "42",
                    "addedAtMs": 1_000,
                }
            ]
        }
        result = normalize_legacy_notify_state(raw)
        assert result["subscribers"][0]["messageThreadId"] == "42"

    def test_normalizes_numeric_message_thread_id(self) -> None:
        raw = {
            "subscribers": [
                {
                    "to": "alice",
                    "mode": "persistent",
                    "messageThreadId": 42,
                    "addedAtMs": 1_000,
                }
            ]
        }
        result = normalize_legacy_notify_state(raw)
        assert result["subscribers"][0]["messageThreadId"] == 42

    def test_drops_invalid_notified_request_ids(self) -> None:
        raw = {
            "notifiedRequestIds": {
                "valid": 1_000,
                "missing_value": None,
                "negative": -1,
                "empty_key": "  ",
            }
        }
        result = normalize_legacy_notify_state(raw)
        assert result["notifiedRequestIds"] == {"valid": 1_000}

    def test_non_dict_input_returns_empty(self) -> None:
        assert normalize_legacy_notify_state(None) == {
            "subscribers": [],
            "notifiedRequestIds": {},
        }
        assert normalize_legacy_notify_state("garbage") == {
            "subscribers": [],
            "notifiedRequestIds": {},
        }
        assert normalize_legacy_notify_state([]) == {
            "subscribers": [],
            "notifiedRequestIds": {},
        }


class TestNotifySubscriberKeys:
    def test_subscriber_key_differentiates_account_id(self) -> None:
        a = {"to": "alice"}
        b = {"to": "alice", "accountId": "acct-1"}
        assert notify_subscriber_key(a) != notify_subscriber_key(b)

    def test_subscriber_key_differentiates_message_thread_id(self) -> None:
        a = {"to": "alice"}
        b = {"to": "alice", "messageThreadId": "thread-1"}
        assert notify_subscriber_key(a) != notify_subscriber_key(b)

    def test_subscriber_store_key_is_sha256_hex(self) -> None:
        key = notify_subscriber_store_key({"to": "alice"})
        # 64-char hex string.
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_subscriber_store_key_is_stable(self) -> None:
        a = notify_subscriber_store_key({"to": "alice"})
        b = notify_subscriber_store_key({"to": "alice"})
        assert a == b

    def test_request_store_key_is_sha256_hex(self) -> None:
        key = notify_request_store_key("r1")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
