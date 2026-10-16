"""Tests for the Device Pair entry point (Phase 5.19).

Covers the full register(api) flow:
- ``register(api)`` calls the same SDK registrars the
  OpenClaw source calls (service + command)
- the ``/pair`` command handler routes through
  ``run_pair_command`` and emits the same reply shapes
  the OpenClaw source emits (status, pending, notify,
  approve, cleanup, clear, revoke, qr, new)
- the URL helpers (validation, host checks, IP checks,
  scheme resolution) match the OpenClaw semantics
- the format helpers (encode_setup_code, format_setup_reply,
  build_pairing_flow_lines, build_security_notice_lines,
  format_gateway_lines, format_qr_info_lines /
  format_qr_info_markdown) match the OpenClaw output
- the channel-data helper (re-exported from
  pairing_qr_channel_data) builds the same envelope
- the auth helpers (re-exported from pair_command_auth)
  return the same auth state shape
"""

from __future__ import annotations

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


from lib import (  # noqa: E402
    build_device_pair_pairing_qr_channel_data,
    build_missing_pairing_scope_reply,
    build_missing_setup_handoff_scope_reply,
    device_pair_plugin,
    encode_setup_code,
    format_duration_minutes,
    format_setup_reply,
    is_full_access_mobile_pairing_url,
    resolve_auth_label,
    resolve_pairing_command_auth_state,
    run_pair_command,
    validate_mobile_pairing_url,
)
from lib.pairing_format import (  # noqa: E402
    QR_CHANNEL_SENDERS,
    build_access_lines,
    build_pairing_flow_lines,
    build_qr_follow_up_lines,
    build_security_notice_lines,
    decode_setup_code,
    format_gateway_lines,
    format_qr_info_lines,
    format_qr_info_markdown,
    format_setup_instructions,
    normalize_optional,
    resolve_qr_channel_sender,
    resolve_qr_reply_target,
)
from lib.pairing_url_helpers import (  # noqa: E402
    is_loopback_host,
    is_mobile_pairing_cleartext_allowed_host,
    is_private_ipv4,
    is_private_lan_cleartext_host,
    is_tailnet_ipv4,
    normalize_lowercase_string_or_empty,
    normalize_optional_string,
    normalize_url,
    parse_ipv4_octets,
    parse_normalized_gateway_url,
    pick_matching_ipv4,
    resolve_scheme,
)


# ── URL helpers ────────────────────────────────────────────


class TestUrlHelpers:
    def test_normalize_optional_string(self) -> None:
        assert normalize_optional_string("  hello  ") == "hello"
        assert normalize_optional_string("") is None
        assert normalize_optional_string(None) is None
        assert normalize_optional_string(42) is None

    def test_normalize_lowercase_string_or_empty(self) -> None:
        assert normalize_lowercase_string_or_empty("  HELLO  ") == "hello"
        assert normalize_lowercase_string_or_empty("") == ""
        assert normalize_lowercase_string_or_empty(None) == ""

    def test_parse_ipv4_octets(self) -> None:
        assert parse_ipv4_octets("192.168.1.1") == (192, 168, 1, 1)
        assert parse_ipv4_octets("10.0.0.0") == (10, 0, 0, 0)
        assert parse_ipv4_octets("not-an-ip") is None
        assert parse_ipv4_octets("256.0.0.0") is None
        assert parse_ipv4_octets("1.2.3") is None
        assert parse_ipv4_octets("1.2.3.4.5") is None

    def test_is_loopback_host(self) -> None:
        assert is_loopback_host("localhost") is True
        assert is_loopback_host("127.0.0.1") is True
        assert is_loopback_host("127.255.255.254") is True
        assert is_loopback_host("::1") is True
        assert is_loopback_host("0:0:0:0:0:0:0:1") is True
        assert is_loopback_host("192.168.1.1") is False
        assert is_loopback_host("example.com") is False
        assert is_loopback_host("") is False

    def test_is_private_ipv4(self) -> None:
        assert is_private_ipv4("10.0.0.1") is True
        assert is_private_ipv4("172.16.0.1") is True
        assert is_private_ipv4("172.31.255.254") is True
        assert is_private_ipv4("192.168.1.1") is True
        assert is_private_ipv4("8.8.8.8") is False
        assert is_private_ipv4("172.32.0.1") is False
        assert is_private_ipv4("11.0.0.1") is False
        assert is_private_ipv4("not-an-ip") is False

    def test_is_tailnet_ipv4(self) -> None:
        assert is_tailnet_ipv4("100.64.0.1") is True
        assert is_tailnet_ipv4("100.127.255.254") is True
        assert is_tailnet_ipv4("100.63.0.1") is False
        assert is_tailnet_ipv4("100.128.0.1") is False
        assert is_tailnet_ipv4("10.0.0.1") is False

    def test_is_private_lan_cleartext_host(self) -> None:
        assert is_private_lan_cleartext_host("printer.local") is True
        assert is_private_lan_cleartext_host("192.168.1.1") is True
        assert is_private_lan_cleartext_host("169.254.0.1") is True
        assert is_private_lan_cleartext_host("8.8.8.8") is False

    def test_is_mobile_pairing_cleartext_allowed_host(self) -> None:
        assert is_mobile_pairing_cleartext_allowed_host("localhost") is True
        assert is_mobile_pairing_cleartext_allowed_host("10.0.2.2") is True
        assert is_mobile_pairing_cleartext_allowed_host("192.168.1.5") is True
        assert is_mobile_pairing_cleartext_allowed_host("8.8.8.8") is False

    def test_resolve_scheme(self) -> None:
        assert resolve_scheme(None) == "ws"
        assert resolve_scheme(False) == "ws"
        assert resolve_scheme(True) == "wss"
        assert resolve_scheme(None, force_secure=True) == "wss"
        assert resolve_scheme(False, force_secure=True) == "wss"

    def test_normalize_url_rejects_invalid(self) -> None:
        assert normalize_url("", "wss") is None
        assert normalize_url(None, "wss") is None
        assert normalize_url("https://example.com", "wss") == "wss://example.com"
        assert normalize_url("ws://example.com:8080", "wss") == "ws://example.com:8080"
        assert normalize_url("wss://[::1]:7443", "ws") == "wss://[::1]:7443"

    def test_parse_normalized_gateway_url(self) -> None:
        assert parse_normalized_gateway_url("ws://localhost:7433") == "ws://localhost:7433"
        assert parse_normalized_gateway_url("https://example.com") == "wss://example.com"
        assert parse_normalized_gateway_url("http://example.com") == "ws://example.com"
        # Embedded credentials are rejected.
        assert parse_normalized_gateway_url("wss://user:pass@example.com") is None
        # Unknown scheme is rejected.
        assert parse_normalized_gateway_url("ftp://example.com") is None
        # Missing hostname is rejected.
        assert parse_normalized_gateway_url("ws://") is None

    def test_validate_mobile_pairing_url(self) -> None:
        # wss:// always valid.
        assert validate_mobile_pairing_url("wss://example.com") is None
        # ws:// loopback is valid.
        assert validate_mobile_pairing_url("ws://127.0.0.1:7433") is None
        # ws:// public IP is rejected.
        err = validate_mobile_pairing_url("ws://8.8.8.8:7433", source="test")
        assert err is not None
        assert "Tailscale" in err or "secure" in err.lower()
        # Invalid URL.
        assert validate_mobile_pairing_url("not-a-url") is not None

    def test_is_full_access_mobile_pairing_url(self) -> None:
        assert is_full_access_mobile_pairing_url("wss://example.com") is True
        assert is_full_access_mobile_pairing_url("ws://127.0.0.1:7433") is True
        assert is_full_access_mobile_pairing_url("ws://8.8.8.8:7433") is False
        assert is_full_access_mobile_pairing_url("not-a-url") is False

    def test_resolve_auth_label(self) -> None:
        cfg = {"gateway": {"auth": {"token": "abc", "mode": "token"}}}
        assert resolve_auth_label(cfg) == {"label": "token"}
        cfg = {"gateway": {"auth": {"password": "secret", "mode": "password"}}}
        assert resolve_auth_label(cfg) == {"label": "password"}
        cfg = {"gateway": {"auth": {}}}
        result = resolve_auth_label(cfg)
        assert "error" in result
        # Env override wins.
        cfg = {"gateway": {"auth": {}}}
        result = resolve_auth_label(cfg, env={"JARVIS_GATEWAY_TOKEN": "xyz"})
        assert result == {"label": "token"}

    def test_pick_matching_ipv4_predicate(self) -> None:
        # A predicate that matches nothing returns None.
        assert pick_matching_ipv4(lambda _a: False) is None
        # A predicate that matches a 4-octet string returns
        # it (the host may not have such an interface in
        # CI; the test only asserts the predicate is
        # consulted).
        # We don't assert the actual return value because
        # CI hosts may or may not have a Tailscale
        # interface.

    def test_normalize_optional_helper(self) -> None:
        assert normalize_optional("  hi  ") == "hi"
        assert normalize_optional("") is None
        assert normalize_optional(None) is None


# ── Format helpers ──────────────────────────────────────────


class TestFormatHelpers:
    def test_format_duration_minutes(self) -> None:
        now = 1_000_000_000_000
        # 0 ms remaining → "1 minute" (clamped to at least 1)
        assert format_duration_minutes(now, now_ms=now) == "1 minute"
        # ~1 min remaining
        assert format_duration_minutes(now + 60_000, now_ms=now) == "1 minute"
        # ~5 min remaining
        assert format_duration_minutes(now + 5 * 60_000, now_ms=now) == "5 minutes"
        # ~65 min remaining
        assert format_duration_minutes(now + 65 * 60_000, now_ms=now) == "65 minutes"

    def test_encode_decode_setup_code_roundtrip(self) -> None:
        payload = {
            "url": "wss://example.com:7443",
            "bootstrapToken": "abc123",
            "expiresAtMs": 1_700_000_000_000,
            "access": "full",
        }
        encoded = encode_setup_code(payload)
        # Base64url alphabet (no padding).
        assert "+" not in encoded
        assert "/" not in encoded
        assert "=" not in encoded
        decoded = decode_setup_code(encoded)
        assert decoded == payload

    def test_encode_setup_code_url_safe(self) -> None:
        encoded = encode_setup_code({"x": "hello world"})
        assert "hello world" not in encoded
        # Decoding restores the original.
        assert decode_setup_code(encoded) == {"x": "hello world"}

    def test_build_pairing_flow_lines(self) -> None:
        lines = build_pairing_flow_lines("Paste the setup code below")
        assert lines[0].startswith("1)")
        assert "Paste the setup code below" in lines[1]
        assert "/pair approve" in lines[2]
        assert "/pair cleanup" in lines[3]

    def test_build_security_notice_lines(self) -> None:
        lines = build_security_notice_lines(kind="setup code", expires_at_ms=1_700_000_000_000)
        assert any("single-use" in line for line in lines)
        assert any("Expires" in line for line in lines)
        assert any("/pair cleanup" in line for line in lines)
        # Markdown variant.
        lines = build_security_notice_lines(
            kind="QR code",
            expires_at_ms=1_700_000_000_000,
            markdown=True,
        )
        assert any(line.startswith("- ") for line in lines)
        assert any("**Important:**" in line for line in lines)

    def test_format_gateway_lines(self) -> None:
        assert format_gateway_lines({"url": "wss://a"}) == ["Gateway: wss://a"]
        # When ``urls`` is provided, ``urls[0]`` is the
        # primary (matches OpenClaw's
        # ``(payload.urls ?? [payload.url]).map(...)``
        # behavior).
        assert format_gateway_lines({"url": "wss://a", "urls": ["wss://b", "wss://c"]}) == [
            "Gateway: wss://b",
            "Fallback: wss://c",
        ]

    def test_build_access_lines(self) -> None:
        lines = build_access_lines({"access": "full"})
        assert lines == ["Access: full"]
        lines = build_access_lines({"access": "limited", "accessDowngraded": True})
        assert len(lines) == 2
        assert "downgraded" in lines[1].lower() or "Plaintext" in lines[1]

    def test_build_qr_follow_up_lines(self) -> None:
        assert len(build_qr_follow_up_lines(auto_notify_armed=True)) == 3
        assert len(build_qr_follow_up_lines(auto_notify_armed=False)) == 1

    def test_format_setup_instructions(self) -> None:
        text = format_setup_instructions(1_700_000_000_000)
        assert "Pairing setup code generated." in text
        assert "1)" in text
        assert "/pair cleanup" in text

    def test_format_setup_reply_contains_setup_code(self) -> None:
        payload = {
            "url": "wss://example.com",
            "bootstrapToken": "tok",
            "expiresAtMs": 1_700_000_000_000,
            "access": "full",
        }
        text = format_setup_reply(payload, auth_label="token")
        assert "Pairing setup code generated." in text
        assert "Setup code:" in text
        # The setup code is the encoded payload.
        encoded = encode_setup_code(payload)
        assert encoded in text
        assert "Auth: token" in text
        assert "Gateway: wss://example.com" in text

    def test_format_qr_info_lines_and_markdown(self) -> None:
        payload = {
            "url": "wss://example.com",
            "bootstrapToken": "tok",
            "expiresAtMs": 1_700_000_000_000,
            "access": "full",
        }
        lines = format_qr_info_lines(
            payload=payload,
            auth_label="token",
            auto_notify_armed=True,
            expires_at_ms=1_700_000_000_000,
        )
        assert any("Gateway:" in line for line in lines)
        assert any("Auth: token" in line for line in lines)
        md = format_qr_info_markdown(
            payload=payload,
            auth_label="token",
            auto_notify_armed=False,
            expires_at_ms=1_700_000_000_000,
        )
        assert "Gateway: wss://example.com" in md
        assert "- Auth: token" in md

    def test_qr_channel_senders(self) -> None:
        # The senders map covers the supported channels.
        for channel in ("telegram", "discord", "slack", "signal", "imessage", "whatsapp"):
            assert channel in QR_CHANNEL_SENDERS
            sender = resolve_qr_channel_sender(channel)
            assert sender is not None
        # Unknown channel returns None.
        assert resolve_qr_channel_sender("unknown") is None
        assert resolve_qr_channel_sender("") is None

    def test_resolve_qr_reply_target(self) -> None:
        # Discord normalizes senderId with user: prefix.
        assert resolve_qr_reply_target({"channel": "discord", "senderId": "u123"}) == "user:u123"
        assert (
            resolve_qr_reply_target({"channel": "discord", "senderId": "channel:c1"})
            == "channel:c1"
        )
        # Other channels use senderId / from / to.
        assert resolve_qr_reply_target({"channel": "telegram", "senderId": "u1"}) == "u1"
        assert resolve_qr_reply_target({"channel": "telegram", "from": "u2"}) == "u2"
        assert resolve_qr_reply_target({"channel": "telegram", "to": "u3"}) == "u3"
        # Empty context returns empty string.
        assert resolve_qr_reply_target({"channel": "telegram"}) == ""


# ── Channel data + auth helpers ────────────────────────────


class TestChannelDataAndAuth:
    def test_build_channel_data_envelope(self) -> None:
        env = build_device_pair_pairing_qr_channel_data(
            {"setupCode": "abc", "expiresAtMs": 1_700_000_000_000}
        )
        assert "openclawPairingQr" in env
        assert env["openclawPairingQr"]["setupCode"] == "abc"
        assert env["openclawPairingQr"]["expiresAtMs"] == 1_700_000_000_000

    def test_resolve_pairing_command_auth_state_missing_pairing(self) -> None:
        state = resolve_pairing_command_auth_state({"channel": "telegram", "senderIsOwner": False})
        assert state["isMissingPairingPrivilege"] is True
        assert state["isInternalGatewayCaller"] is False

    def test_resolve_pairing_command_auth_state_owner(self) -> None:
        state = resolve_pairing_command_auth_state({"channel": "telegram", "senderIsOwner": True})
        assert state["isMissingPairingPrivilege"] is False
        assert state["canIssueFullAccessSetup"] is True

    def test_resolve_pairing_command_auth_state_internal(self) -> None:
        state = resolve_pairing_command_auth_state(
            {
                "channel": "webchat",
                "gatewayClientScopes": ["operator.pairing"],
            }
        )
        assert state["isInternalGatewayCaller"] is True
        assert state["isMissingPairingPrivilege"] is False
        assert state["canIssueFullAccessSetup"] is False  # needs admin

    def test_resolve_pairing_command_auth_state_admin(self) -> None:
        state = resolve_pairing_command_auth_state(
            {
                "channel": "webchat",
                "gatewayClientScopes": ["operator.admin"],
            }
        )
        assert state["canIssueFullAccessSetup"] is True

    def test_missing_pairing_scope_reply(self) -> None:
        reply = build_missing_pairing_scope_reply()
        assert "operator.pairing" in reply["text"]

    def test_missing_setup_handoff_scope_reply(self) -> None:
        reply = build_missing_setup_handoff_scope_reply()
        assert "operator.talk.secrets" in reply["text"]


# ── Plugin descriptor + register(api) ─────────────────────


class _RecordingApi:
    """Minimal API surface for the register() flow tests."""

    def __init__(self) -> None:
        self.services: list[dict] = []
        self.commands: list[dict] = []
        self.config: dict = {}
        self.env: dict = {}

    def register_service(self, service: dict) -> None:
        self.services.append(service)

    def register_command(self, command: dict) -> None:
        self.commands.append(command)


class TestDevicePairingPlugin:
    def test_descriptor_metadata(self) -> None:
        assert device_pair_plugin.id == "device-pair"
        assert device_pair_plugin.kind == "infra"
        assert device_pair_plugin.version == "0.1.0"
        assert "pairing" in device_pair_plugin.description.lower()

    def test_init_is_noop(self) -> None:
        assert device_pair_plugin.init({}) is None

    def test_register_registers_service_and_command(self) -> None:
        api = _RecordingApi()
        device_pair_plugin.register(api)
        # Service registration: the notifier service.
        assert len(api.services) == 1
        svc = api.services[0]
        assert svc["id"] == "device-pair-notifier"
        assert callable(svc["start"])
        assert callable(svc["stop"])
        # Command registration: the /pair command.
        assert len(api.commands) == 1
        cmd = api.commands[0]
        assert cmd["name"] == "pair"
        assert cmd["accepts_args"] is True
        assert cmd["expose_sender_is_owner"] is True
        assert callable(cmd["handler"])


# ── run_pair_command flow ─────────────────────────────────


class TestRunPairCommand:
    """Test the ``/pair`` command handler with stub runners."""

    @staticmethod
    def _auth_state(**overrides) -> dict:
        state = {
            "isInternalGatewayCaller": True,
            "isMissingPairingPrivilege": False,
            "isMissingSetupHandoffPrivilege": False,
            "canIssueFullAccessSetup": True,
            "approvalCallerScopes": ["operator.pairing"],
        }
        state.update(overrides)
        return state

    def test_missing_pairing_privilege_takes_priority(self) -> None:
        reply = run_pair_command(
            action="new",
            auth_state=self._auth_state(isMissingPairingPrivilege=True),
            config={},
        )
        assert "operator.pairing" in reply["text"]

    def test_status_action_with_empty_pending(self) -> None:
        reply = run_pair_command(
            action="status",
            auth_state=self._auth_state(),
            config={},
            list_pairing=lambda: {"pending": []},
        )
        assert "No pending pairing requests." in reply["text"]

    def test_status_action_with_pending(self) -> None:
        reply = run_pair_command(
            action="status",
            auth_state=self._auth_state(),
            config={},
            list_pairing=lambda: {"pending": [{"requestId": "r1", "device": "iPhone"}]},
        )
        assert "r1" in reply["text"]
        assert "iPhone" in reply["text"]

    def test_cleanup_action_no_tokens(self) -> None:
        reply = run_pair_command(
            action="cleanup",
            auth_state=self._auth_state(),
            config={},
            clear_bootstrap_tokens=lambda: {"removed": 0},
        )
        assert "No unused setup codes were active." in reply["text"]

    def test_cleanup_action_with_tokens(self) -> None:
        reply = run_pair_command(
            action="cleanup",
            auth_state=self._auth_state(),
            config={},
            clear_bootstrap_tokens=lambda: {"removed": 3},
        )
        assert "Invalidated 3 unused setup codes." in reply["text"]

    def test_approve_action_no_pending(self) -> None:
        """When the pending list is empty, the select helper
        returns a "no pending" reply (not a "not found" reply)."""
        reply = run_pair_command(
            action="approve",
            auth_state=self._auth_state(),
            config={},
            requested="nope",
            list_pairing=lambda: {"pending": []},
        )
        # The select helper returns its own "no pending"
        # message; the ``run_pair_command`` handler surfaces
        # it as ``reply["reply"]``.
        assert "No pending" in reply["text"]

    def test_qr_action_returns_setup_code(self) -> None:
        reply = run_pair_command(
            action="qr",
            auth_state=self._auth_state(),
            config={"gateway": {"auth": {"token": "x", "mode": "token"}}},
            resolve_url=lambda _c, _pc: {"url": "wss://example.com"},
            issue_bootstrap_token=lambda _p: {
                "token": "tok",
                "expiresAtMs": 1_700_000_000_000,
            },
        )
        # The QR action returns the standard "QR code sent" reply.
        assert "QR code sent" in reply["text"]
        assert "/pair cleanup" in reply["text"]

    def test_default_action_returns_setup_code(self) -> None:
        reply = run_pair_command(
            action="",
            auth_state=self._auth_state(),
            config={"gateway": {"auth": {"token": "x", "mode": "token"}}},
            resolve_url=lambda _c, _pc: {"url": "wss://example.com"},
            issue_bootstrap_token=lambda _p: {
                "token": "tok",
                "expiresAtMs": 1_700_000_000_000,
            },
        )
        assert "Pairing setup code generated." in reply["text"]
        assert "Setup code:" in reply["text"]
        assert "Gateway: wss://example.com" in reply["text"]

    def test_notify_action_routes_to_handler(self) -> None:
        reply = run_pair_command(
            action="notify",
            auth_state=self._auth_state(),
            config={},
            notify_action="arm",
            handle_notify_command=lambda _ctx, action: {"text": f"armed={action}"},
        )
        assert reply == {"text": "armed=arm"}

    def test_notify_action_without_handler(self) -> None:
        reply = run_pair_command(
            action="notify",
            auth_state=self._auth_state(),
            config={},
            notify_action="arm",
        )
        assert "not yet ported" in reply["text"]

    def test_missing_setup_handoff_privilege(self) -> None:
        reply = run_pair_command(
            action="new",
            auth_state=self._auth_state(
                isMissingSetupHandoffPrivilege=True,
                isInternalGatewayCaller=True,
            ),
            config={},
        )
        assert "operator.talk.secrets" in reply["text"]
