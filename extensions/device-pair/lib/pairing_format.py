"""Device Pair setup-code encoding + reply formatting.

Mirrors OpenClaw's ``extensions/device-pair/index.ts``
format helpers (``formatDurationMinutes``,
``encodeSetupCode``, ``formatSetupReply``,
``formatSetupInstructions``, ``formatGatewayLines``,
``buildAccessLines``, ``buildSecurityNoticeLines``,
``buildPairingFlowLines``, ``buildQrInfoLines``,
``formatQrInfoMarkdown``, ``buildQrFollowUpLines``,
``QR_CHANNEL_SENDERS``, ``resolveQrChannelSender``,
``resolveQrReplyTarget``).

The Python port keeps the same output shapes so the
entry point's command handler can produce identical
markdown / plain-text replies without re-implementing the
formatting rules.

Public surface (mirrors the TS source):
- ``format_duration_minutes(expires_at_ms, now_ms)`` —
  ``"<N> minute(s)"`` until expiry
- ``encode_setup_code(payload)`` — base64url(JSON)
- ``build_pairing_flow_lines(step_two)`` — the 4-step
  pairing instructions
- ``build_security_notice_lines(params)`` — the
  expiry + cleanup reminder lines
- ``format_gateway_lines(payload)`` — primary +
  fallback gateway lines
- ``build_access_lines(payload, markdown)`` — access
  mode lines
- ``format_setup_instructions(expires_at_ms)`` — plain
  setup-code flow (used when a channel can't receive
  the QR image)
- ``format_setup_reply(payload, auth_label)`` — the
  full pasteable setup code reply
- ``format_qr_info_lines(params)`` — the info lines
  under a QR code
- ``format_qr_info_markdown(params)`` — the markdown
  version
- ``build_qr_follow_up_lines(auto_notify_armed)`` — the
  post-scan follow-up lines
- ``QR_CHANNEL_SENDERS`` — per-channel media-send opts
  factory
- ``resolve_qr_channel_sender(channel)`` — sender lookup
- ``resolve_qr_reply_target(ctx)`` — channel-specific
  reply target

Python adaptations (documented in code):
- TS ``Buffer.from(json, "utf8").toString("base64")`` →
  Python ``base64.urlsafe_b64encode`` (URL-safe
  base64, no padding). The OpenClaw source uses
  base64url without padding; the Python port keeps
  the same shape.
- TS literal-union ``QrChannelSender`` dict → Python
  ``dict[str, dict]`` keyed by channel name.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Optional, TypedDict


# ── Setup code encoding ────────────────────────────────────


def encode_setup_code(payload: dict) -> str:
    """Encode a setup-code payload as base64url(JSON).

    Mirrors ``encodeSetupCode``. The OpenClaw source
    uses Node's ``Buffer.from(json).toString("base64")``
    with ``+`` → ``-`` and ``/`` → ``_`` and trailing
    ``=`` stripped; the Python port uses
    ``base64.urlsafe_b64encode`` which produces the
    same character set with padding already stripped.
    """
    json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(json_bytes).rstrip(b"=").decode("ascii")


def decode_setup_code(setup_code: str) -> Optional[dict]:
    """Decode a setup-code string back to its payload dict.

    The Python port adds a ``decodeSetupCode`` helper
    (no TS counterpart) for tests + introspection; the
    OpenClaw source never needs to decode a setup
    code (the mobile client does).
    """
    if not isinstance(setup_code, str) or not setup_code:
        return None
    try:
        # Restore the padding that ``urlsafe_b64encode``
        # stripped; ``urlsafe_b64decode`` requires
        # length to be a multiple of 4.
        padding = "=" * (-len(setup_code) % 4)
        json_bytes = base64.urlsafe_b64decode(setup_code + padding)
        return json.loads(json_bytes.decode("utf-8"))
    except (ValueError, TypeError):
        return None


# ── Duration formatting ────────────────────────────────────


def format_duration_minutes(
    expires_at_ms: int, now_ms: Optional[int] = None
) -> str:
    """Return the minutes-until-expiry string for a setup code.

    Mirrors ``formatDurationMinutes``. Returns
    ``"<N> minute(s)"`` with at least 1 minute; the
    function clamps negative durations to 0.
    """
    if now_ms is None:
        import time

        now_ms = int(time.time() * 1000)
    ms_remaining = max(0, int(expires_at_ms) - int(now_ms))
    minutes = max(1, (ms_remaining + 59_999) // 60_000)
    return f"{minutes} minute{'' if minutes == 1 else 's'}"


# ── Pairing flow + security notice + access lines ─────────


def build_pairing_flow_lines(step_two: str) -> list[str]:
    """Return the 4-step pairing instructions.

    Mirrors ``buildPairingFlowLines``.
    """
    return [
        "1) Open the iOS app → Settings → Gateway",
        f"2) {step_two}",
        "3) Back here, run /pair approve",
        "4) If this code leaks or you are done, run /pair cleanup",
    ]


def build_security_notice_lines(
    *,
    kind: str,
    expires_at_ms: int,
    markdown: bool = False,
) -> list[str]:
    """Return the security / expiry / cleanup reminder lines.

    Mirrors ``buildSecurityNoticeLines``.
    """
    cleanup = "`/pair cleanup`" if markdown else "/pair cleanup"
    security_prefix = "- " if markdown else ""
    important = (
        f"**Important:** Run {cleanup} after pairing finishes."
        if markdown
        else f"IMPORTANT: After pairing finishes, run {cleanup}."
    )
    return [
        f"{security_prefix}Security: single-use bootstrap token",
        f"{security_prefix}Expires: {format_duration_minutes(expires_at_ms)}",
        "",
        important,
        f"If this {kind} leaks, run {cleanup} immediately.",
    ]


def format_gateway_lines(payload: dict) -> list[str]:
    """Return the primary + fallback gateway URL lines.

    Mirrors ``formatGatewayLines``. The first line is
    ``"Gateway: <url>"``; subsequent lines use
    ``"Fallback: <url>"``.
    """
    urls = payload.get("urls") or [payload.get("url", "")]
    return [
        (f"Gateway: {url}" if index == 0 else f"Fallback: {url}")
        for index, url in enumerate(urls)
    ]


def build_access_lines(payload: dict, markdown: bool = False) -> list[str]:
    """Return the access-mode lines for a setup payload.

    Mirrors ``buildAccessLines``. When the access was
    downgraded (cleartext URL was used), appends an
    explanation line.
    """
    prefix = "- " if markdown else ""
    lines = [f"{prefix}Access: {payload.get('access', 'full')}"]
    if payload.get("accessDowngraded"):
        lines.append(
            f"{prefix}Plaintext ws:// was limited for safety. "
            "Use wss:// or Tailscale Serve, then generate a new code for full access."
        )
    return lines


# ── Setup-code reply formatting ────────────────────────────


def format_setup_instructions(expires_at_ms: int) -> str:
    """Return the plain setup-code flow (no QR).

    Mirrors ``formatSetupInstructions``. Used when a
    channel can't receive the QR image and the
    helper emits a pasteable setup code instead.
    """
    return "\n".join(
        [
            "Pairing setup code generated.",
            "",
            *build_pairing_flow_lines(
                "Paste the setup code from my next message and tap Connect"
            ),
            "",
            *build_security_notice_lines(
                kind="setup code", expires_at_ms=expires_at_ms
            ),
        ]
    )


def format_setup_reply(payload: dict, auth_label: str) -> str:
    """Return the full pasteable setup code reply.

    Mirrors ``formatSetupReply``.
    """
    setup_code = encode_setup_code(payload)
    return "\n".join(
        [
            "Pairing setup code generated.",
            "",
            *build_pairing_flow_lines("Paste the setup code below and tap Connect"),
            "",
            "Setup code:",
            setup_code,
            "",
            *format_gateway_lines(payload),
            f"Auth: {auth_label}",
            *build_access_lines(payload),
            *build_security_notice_lines(
                kind="setup code", expires_at_ms=payload.get("expiresAtMs", 0)
            ),
        ]
    )


# ── QR follow-up lines ────────────────────────────────────


def build_qr_follow_up_lines(auto_notify_armed: bool) -> list[str]:
    """Return the post-scan follow-up lines.

    Mirrors ``buildQrFollowUpLines``.
    """
    if auto_notify_armed:
        return [
            "After scanning, wait here for the pairing request ping.",
            "I'll auto-ping here when the pairing request arrives, then auto-disable.",
            "If the ping does not arrive, run `/pair approve latest` manually.",
        ]
    return ["After scanning, run `/pair approve` to complete pairing."]


def format_qr_info_lines(
    *,
    payload: dict,
    auth_label: str,
    auto_notify_armed: bool,
    expires_at_ms: int,
) -> list[str]:
    """Return the info lines under a QR code (plain text).

    Mirrors ``formatQrInfoLines``.
    """
    return [
        *format_gateway_lines(payload),
        f"Auth: {auth_label}",
        *build_access_lines(payload),
        *build_security_notice_lines(kind="QR code", expires_at_ms=expires_at_ms),
        "",
        *build_qr_follow_up_lines(auto_notify_armed),
        "",
        "If your camera still won't lock on, run `/pair` for a pasteable setup code.",
    ]


def format_qr_info_markdown(
    *,
    payload: dict,
    auth_label: str,
    auto_notify_armed: bool,
    expires_at_ms: int,
) -> str:
    """Return the info lines under a QR code (markdown).

    Mirrors ``formatQrInfoMarkdown``.
    """
    lines: list[str] = []
    for line in format_gateway_lines(payload):
        lines.append(f"- {line}")
    lines.append(f"- Auth: {auth_label}")
    lines.extend(build_access_lines(payload, markdown=True))
    lines.extend(
        build_security_notice_lines(
            kind="QR code", expires_at_ms=expires_at_ms, markdown=True
        )
    )
    lines.append("")
    lines.extend(build_qr_follow_up_lines(auto_notify_armed))
    lines.append("")
    lines.append(
        "If your camera still won't lock on, run `/pair` for a pasteable setup code."
    )
    return "\n".join(lines)


# ── QR channel senders + reply target ─────────────────────


class QrCommandContext(TypedDict, total=False):
    channel: str
    senderId: str
    from_: str  # TS ``from`` (Python keyword)
    to: str
    accountId: str
    messageThreadId: str | int


def _create_telegram_opts(
    ctx: dict, qr_file_path: str, media_local_roots: list[str], account_id: Optional[str]
) -> dict:
    opts: dict = {
        "mediaUrl": qr_file_path,
        "mediaLocalRoots": media_local_roots,
    }
    if "messageThreadId" in ctx and ctx["messageThreadId"] is not None:
        opts["threadId"] = ctx["messageThreadId"]
    if account_id:
        opts["accountId"] = account_id
    return opts


def _create_discord_opts(
    _ctx: dict, qr_file_path: str, media_local_roots: list[str], account_id: Optional[str]
) -> dict:
    opts: dict = {
        "mediaUrl": qr_file_path,
        "mediaLocalRoots": media_local_roots,
    }
    if account_id:
        opts["accountId"] = account_id
    return opts


def _create_slack_opts(
    ctx: dict, qr_file_path: str, media_local_roots: list[str], account_id: Optional[str]
) -> dict:
    opts: dict = {
        "mediaUrl": qr_file_path,
        "mediaLocalRoots": media_local_roots,
    }
    if "messageThreadId" in ctx and ctx["messageThreadId"] is not None:
        opts["threadId"] = str(ctx["messageThreadId"])
    if account_id:
        opts["accountId"] = account_id
    return opts


def _create_imessage_opts(
    _ctx: dict, qr_file_path: str, media_local_roots: list[str], account_id: Optional[str]
) -> dict:
    opts: dict = {
        "mediaUrl": qr_file_path,
        "mediaLocalRoots": media_local_roots,
    }
    if account_id:
        opts["accountId"] = account_id
    return opts


def _create_whatsapp_opts(
    _ctx: dict, qr_file_path: str, media_local_roots: list[str], account_id: Optional[str]
) -> dict:
    opts: dict = {
        "verbose": False,
        "mediaUrl": qr_file_path,
        "mediaLocalRoots": media_local_roots,
    }
    if account_id:
        opts["accountId"] = account_id
    return opts


# Per-channel QR media-send opts factory. Mirrors
# ``QR_CHANNEL_SENDERS`` from the OpenClaw source. The
# Python port keeps the same channel set + the same
# default opts shape so the entry point can route the
# right factory per channel.
QR_CHANNEL_SENDERS: dict[str, Any] = {
    "telegram": _create_telegram_opts,
    "discord": _create_discord_opts,
    "slack": _create_slack_opts,
    "signal": _create_imessage_opts,  # mirror: signal has no special opts
    "imessage": _create_imessage_opts,
    "whatsapp": _create_whatsapp_opts,
}


def resolve_qr_channel_sender(channel: str) -> Optional[Any]:
    """Return the QR media-send opts factory for ``channel``.

    Mirrors ``resolveQrChannelSender``. Returns
    ``None`` when the channel is not supported.
    """
    return QR_CHANNEL_SENDERS.get(channel)


def resolve_qr_reply_target(ctx: dict) -> str:
    """Return the channel-specific reply target.

    Mirrors ``resolveQrReplyTarget``. For Discord,
    the sender id is normalized to ``"user:<id>"`` or
    ``"channel:<id>"``; for other channels, the first
    non-empty ``senderId`` / ``from`` / ``to`` wins.
    """
    channel = ctx.get("channel", "")
    if channel == "discord":
        sender_id = normalize_optional(ctx.get("senderId", "")) or ""
        if sender_id:
            return (
                sender_id
                if sender_id.startswith("user:") or sender_id.startswith("channel:")
                else f"user:{sender_id}"
            )
    return (
        normalize_optional(ctx.get("senderId"))
        or normalize_optional(ctx.get("from"))
        or normalize_optional(ctx.get("to"))
        or ""
    )


def normalize_optional(value: Any) -> Optional[str]:
    """Trim a string; return ``None`` for empty / non-string."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


__all__ = [
    "QR_CHANNEL_SENDERS",
    "build_access_lines",
    "build_pairing_flow_lines",
    "build_qr_follow_up_lines",
    "build_security_notice_lines",
    "decode_setup_code",
    "encode_setup_code",
    "format_duration_minutes",
    "format_gateway_lines",
    "format_qr_info_lines",
    "format_qr_info_markdown",
    "format_setup_instructions",
    "format_setup_reply",
    "normalize_optional",
    "resolve_qr_channel_sender",
    "resolve_qr_reply_target",
]
