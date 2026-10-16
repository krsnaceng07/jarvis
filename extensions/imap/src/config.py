"""Configuration definitions and validation for IMAP email triggers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

IdentifierAuthentication = Literal["mutable", "unverified", "asserted", "verified"]
SENDER_STRENGTHS: tuple[IdentifierAuthentication, ...] = (
    "mutable",
    "unverified",
    "asserted",
    "verified",
)

ThinkingLevel = Literal[
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "adaptive",
    "max",
    "ultra",
]

THINKING_LEVELS: set[str] = {
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "adaptive",
    "max",
    "ultra",
}


@dataclass(frozen=True, slots=True)
class ImapSenderAuth:
    min: IdentifierAuthentication = "verified"
    trusted_authserv_ids: list[str] = field(default_factory=list)
    accept_trusted_authserv_id: bool = False


@dataclass(frozen=True, slots=True)
class ImapWatchConfig:
    mode: Literal["auto", "idle", "interval"] = "auto"
    poll_seconds: int = 60


@dataclass(frozen=True, slots=True)
class ImapAddressToken:
    token: str
    senders: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ImapAccountConfig:
    host: str
    user: str
    password: str
    agent_id: str
    port: int = 993
    secure: bool = True
    mailbox: str = "INBOX"
    watch: ImapWatchConfig = field(default_factory=ImapWatchConfig)
    allowed_senders: list[str] = field(default_factory=list)
    sender_auth: ImapSenderAuth = field(default_factory=ImapSenderAuth)
    address_tokens: list[ImapAddressToken] = field(default_factory=list)
    deliver: bool = False
    include_body: bool = True
    max_bytes: int = 20_000
    model: str | None = None
    thinking: ThinkingLevel | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ImapPluginConfig:
    accounts: dict[str, ImapAccountConfig] = field(default_factory=dict)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def resolve_imap_config(
    value: Any,
    on_unavailable_account: Callable[[str], None] | None = None,
) -> ImapPluginConfig:
    """Validate and normalize raw plugin configuration for IMAP triggers."""
    if not isinstance(value, dict):
        return ImapPluginConfig()

    configured_accounts = value.get("accounts")
    if not isinstance(configured_accounts, dict):
        return ImapPluginConfig()

    accounts: dict[str, ImapAccountConfig] = {}
    id_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

    for account_id, input_val in configured_accounts.items():
        if not isinstance(account_id, str) or not id_pattern.match(account_id):
            raise ValueError(f"IMAP account id {account_id!r} is not session-safe")

        if not isinstance(input_val, dict):
            raise ValueError(f"IMAP account {account_id} must be an object")

        host = input_val.get("host")
        user = input_val.get("user")
        password = input_val.get("password")
        agent_id = input_val.get("agentId") or input_val.get("agent_id")

        if not isinstance(host, str) or not isinstance(user, str) or not isinstance(agent_id, str):
            raise ValueError(
                f"IMAP account {account_id} requires host, user, resolved password, and agentId"
            )

        if not isinstance(password, str):
            if isinstance(password, dict):
                if on_unavailable_account:
                    on_unavailable_account(account_id)
                continue
            raise ValueError(f"IMAP account {account_id} requires a resolved password")

        watch_dict = input_val.get("watch") if isinstance(input_val.get("watch"), dict) else {}
        mode_val = watch_dict.get("mode")
        mode: Literal["auto", "idle", "interval"] = (
            mode_val if mode_val in ("idle", "interval") else "auto"
        )
        raw_poll = watch_dict.get("pollSeconds") or watch_dict.get("poll_seconds")
        poll_seconds = max(15, int(raw_poll)) if isinstance(raw_poll, (int, float)) else 60

        sender_auth_dict = (
            input_val.get("senderAuth")
            if isinstance(input_val.get("senderAuth"), dict)
            else input_val.get("sender_auth")
            if isinstance(input_val.get("sender_auth"), dict)
            else {}
        )
        min_strength = sender_auth_dict.get("min")
        resolved_min: IdentifierAuthentication = (
            min_strength if min_strength in SENDER_STRENGTHS else "verified"
        )
        trusted_ids = _string_list(
            sender_auth_dict.get("trustedAuthservIds")
            or sender_auth_dict.get("trusted_authserv_ids")
        )
        accept_trusted = bool(
            sender_auth_dict.get("acceptTrustedAuthservId")
            or sender_auth_dict.get("accept_trusted_authserv_id")
        )

        address_tokens_raw = (
            input_val.get("addressTokens")
            if isinstance(input_val.get("addressTokens"), list)
            else input_val.get("address_tokens")
            if isinstance(input_val.get("address_tokens"), list)
            else []
        )
        address_tokens: list[ImapAddressToken] = []
        for entry in address_tokens_raw:
            if isinstance(entry, dict) and isinstance(entry.get("token"), str):
                address_tokens.append(
                    ImapAddressToken(
                        token=entry["token"],
                        senders=_string_list(entry.get("senders")),
                    )
                )

        raw_thinking = input_val.get("thinking")
        thinking_val: ThinkingLevel | None = (
            raw_thinking if raw_thinking in THINKING_LEVELS else None
        )

        accounts[account_id] = ImapAccountConfig(
            host=host,
            user=user,
            password=password,
            agent_id=agent_id,
            port=int(input_val.get("port", 993)),
            secure=input_val.get("secure", True) is not False,
            mailbox=str(input_val.get("mailbox", "INBOX")),
            watch=ImapWatchConfig(mode=mode, poll_seconds=poll_seconds),
            allowed_senders=_string_list(
                input_val.get("allowedSenders") or input_val.get("allowed_senders")
            ),
            sender_auth=ImapSenderAuth(
                min=resolved_min,
                trusted_authserv_ids=trusted_ids,
                accept_trusted_authserv_id=accept_trusted,
            ),
            address_tokens=address_tokens,
            deliver=bool(input_val.get("deliver", False)),
            include_body=input_val.get("includeBody", input_val.get("include_body", True))
            is not False,
            max_bytes=int(input_val.get("maxBytes", input_val.get("max_bytes", 20_000))),
            model=input_val.get("model") if isinstance(input_val.get("model"), str) else None,
            thinking=thinking_val,
            timeout_seconds=float(input_val["timeoutSeconds"])
            if "timeoutSeconds" in input_val
            and isinstance(input_val["timeoutSeconds"], (int, float))
            else float(input_val["timeout_seconds"])
            if "timeout_seconds" in input_val
            and isinstance(input_val["timeout_seconds"], (int, float))
            else None,
        )

    return ImapPluginConfig(accounts=accounts)
