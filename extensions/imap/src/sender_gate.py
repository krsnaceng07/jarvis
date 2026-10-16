"""Sender evaluation and authentication gating for incoming IMAP messages."""

from __future__ import annotations

import hmac
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from .config import IdentifierAuthentication, ImapAccountConfig

AUTH_FRESHNESS_SECONDS = 48 * 60 * 60  # 48 hours

STRENGTH_RANKS: dict[IdentifierAuthentication, int] = {
    "mutable": 0,
    "unverified": 1,
    "asserted": 2,
    "verified": 3,
}


def meets_identifier_authentication(
    actual: IdentifierAuthentication,
    required: IdentifierAuthentication,
) -> bool:
    return STRENGTH_RANKS.get(actual, 0) >= STRENGTH_RANKS.get(required, 0)


@dataclass(slots=True)
class SenderGateVerdict:
    accepted: bool
    sender: str | None = None
    reason: str = ""
    strength: IdentifierAuthentication = "unverified"
    transient: bool = False


def matches_imap_sender(sender: str, entries: list[str]) -> bool:
    if "@" not in sender:
        return False
    local, domain = sender.rsplit("@", 1)
    domain = domain.lower()
    for entry in entries:
        if entry.startswith("@"):
            if entry[1:].lower() == domain:
                return True
        elif "@" in entry:
            e_local, e_domain = entry.rsplit("@", 1)
            if e_local == local and e_domain.lower() == domain:
                return True
    return False


def _constant_token_match(address: str, expected: str) -> bool:
    if "@" not in address:
        return False
    local = address.rsplit("@", 1)[0]
    if "+" not in local:
        return False
    token = local.rsplit("+", 1)[1]
    return hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))


def _recipient_addresses(mail: Any) -> list[str]:
    addresses: list[str] = []
    if isinstance(mail, dict):
        to_field = mail.get("to")
        if isinstance(to_field, list):
            addresses.extend([addr for addr in to_field if isinstance(addr, str)])
        elif isinstance(to_field, str):
            addresses.append(to_field)
        deliv = mail.get("delivered-to") or mail.get("delivered_to")
        if isinstance(deliv, str):
            addresses.append(deliv)
        elif isinstance(deliv, list):
            addresses.extend([d for d in deliv if isinstance(d, str)])
    else:
        to_val = getattr(mail, "to", None)
        if isinstance(to_val, list):
            for t in to_val:
                if isinstance(t, str):
                    addresses.append(t)
                elif hasattr(t, "address") and t.address:
                    addresses.append(t.address)
                elif hasattr(t, "value") and isinstance(t.value, list):
                    for v in t.value:
                        if hasattr(v, "address") and v.address:
                            addresses.append(v.address)
        elif isinstance(to_val, str):
            addresses.append(to_val)

        headers = getattr(mail, "headers", {})
        if hasattr(headers, "get"):
            deliv = headers.get("delivered-to")
            if isinstance(deliv, str):
                addresses.append(deliv)
            elif isinstance(deliv, list):
                addresses.extend([d for d in deliv if isinstance(d, str)])

    return addresses


def _matching_sender_token(mail: Any, sender: str, account: ImapAccountConfig) -> bool:
    recipients = _recipient_addresses(mail)
    for token_entry in account.address_tokens:
        if matches_imap_sender(sender, token_entry.senders):
            for addr in recipients:
                if _constant_token_match(addr, token_entry.token):
                    return True
    return False


def _parse_imap_auth_results(value: str) -> dict[str, str] | None:
    unfolded = re.sub(r"\r?\n[\t ]+", " ", value)
    if ";" not in unfolded:
        return None
    authserv_id, methods = unfolded.split(";", 1)
    authserv_id = re.sub(r"\s+\d+$", "", authserv_id.strip())
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9.-]*$", authserv_id):
        return None

    result: dict[str, str] = {"authserv_id": authserv_id}
    dmarc_match = re.search(r"(?:^|;)\s*dmarc\s*=\s*([a-zA-Z]+)", methods)
    if dmarc_match:
        result["dmarc"] = dmarc_match.group(1).lower()

    spf_match = re.search(r"(?:^|;)\s*spf\s*=\s*([a-zA-Z]+)", methods)
    if spf_match:
        result["spf"] = spf_match.group(1).lower()

    return result


def _authentication_headers(mail: Any) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    if isinstance(mail, dict):
        raw_headers = mail.get("headers", {})
        auth_header = raw_headers.get("authentication-results") or raw_headers.get(
            "Authentication-Results"
        )
        if isinstance(auth_header, str):
            parsed = _parse_imap_auth_results(auth_header)
            if parsed:
                results.append(parsed)
        elif isinstance(auth_header, list):
            for entry in auth_header:
                if isinstance(entry, str):
                    parsed = _parse_imap_auth_results(entry)
                    if parsed:
                        results.append(parsed)
    else:
        header_lines = getattr(mail, "header_lines", []) or getattr(mail, "headerLines", [])
        for item in header_lines:
            key = (
                getattr(item, "key", "")
                if hasattr(item, "key")
                else item.get("key", "")
                if isinstance(item, dict)
                else ""
            )
            line = (
                getattr(item, "line", "")
                if hasattr(item, "line")
                else item.get("line", "")
                if isinstance(item, dict)
                else ""
            )
            if key.lower() == "authentication-results":
                colon_idx = line.find(":")
                if colon_idx >= 0:
                    parsed = _parse_imap_auth_results(line[colon_idx + 1 :])
                    if parsed:
                        results.append(parsed)
    return results


def _map_imap_auth_strength(
    auth_result: Any,
    headers: list[dict[str, str]],
    account: ImapAccountConfig,
) -> tuple[IdentifierAuthentication, str, bool]:
    # Check trusted Authentication-Results header
    for header in headers:
        if (
            header.get("dmarc") == "pass"
            and header.get("authserv_id") in account.sender_auth.trusted_authserv_ids
            and account.sender_auth.accept_trusted_authserv_id
        ):
            return "asserted", "trusted-authserv-dmarc-pass", False

    # Check external authenticator result if provided
    if auth_result and hasattr(auth_result, "dmarc"):
        dmarc_val = getattr(auth_result.dmarc, "result", None) or getattr(
            auth_result, "dmarc_result", None
        )
        if dmarc_val == "pass":
            return "verified", "dmarc-pass", False
        if dmarc_val == "temperror":
            return "unverified", "authentication-temperror", True

    # Fallback to general header check
    for header in headers:
        if header.get("dmarc") == "pass" or header.get("spf") == "pass":
            return "unverified", "unverified-authentication", False

    return "unverified", "dmarc-none", False


async def evaluate_imap_sender(
    mail: Any,
    raw: bytes,
    internal_date: float | None,
    account: ImapAccountConfig,
    authenticator: Callable[[bytes], Any] | None = None,
) -> SenderGateVerdict:
    # Resolve From address
    sender: str | None = None
    if isinstance(mail, dict):
        sender = mail.get("from") or mail.get("from_address")
    else:
        from_val = getattr(mail, "from_", None) or getattr(mail, "from", None)
        if isinstance(from_val, str):
            sender = from_val
        elif hasattr(from_val, "text"):
            sender = from_val.text
        elif hasattr(from_val, "value") and isinstance(from_val.value, list) and from_val.value:
            sender = getattr(from_val.value[0], "address", None)

    if not sender or "@" not in sender:
        return SenderGateVerdict(accepted=False, reason="invalid-from", transient=False)

    if not matches_imap_sender(sender, account.allowed_senders):
        return SenderGateVerdict(
            accepted=False, sender=sender, reason="sender-not-allowed", transient=False
        )

    if _matching_sender_token(mail, sender, account):
        return SenderGateVerdict(accepted=True, sender=sender, reason="token")

    if internal_date and (time.time() - internal_date) > AUTH_FRESHNESS_SECONDS:
        return SenderGateVerdict(
            accepted=False, sender=sender, reason="message-too-old", transient=False
        )

    auth_res = None
    if authenticator:
        try:
            auth_res = (
                await authenticator(raw)
                if hasattr(authenticator(raw), "__await__")
                else authenticator(raw)
            )
        except Exception:
            return SenderGateVerdict(
                accepted=False,
                sender=sender,
                strength="unverified",
                reason="authentication-temperror",
                transient=True,
            )

    headers = _authentication_headers(mail)
    strength, reason, transient = _map_imap_auth_strength(auth_res, headers, account)

    if not meets_identifier_authentication(strength, account.sender_auth.min):
        return SenderGateVerdict(
            accepted=False,
            sender=sender,
            strength=strength,
            reason=reason,
            transient=transient,
        )

    return SenderGateVerdict(
        accepted=True,
        sender=sender,
        strength=strength,
        reason=reason,
    )
