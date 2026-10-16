"""jarvis.auto_reply.reply.elevated_allowlist_matcher - Matches elevated-command allowlists against normalized sender identities.

OpenClaw parity: mirrors
``openclaw-main/src/auto-reply/reply/elevated-allowlist-matcher.ts``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Literal

from jarvis.utils import _lower

ExplicitElevatedAllowField = Literal["id", "from", "e164", "name", "username", "tag"]
INTERNAL_ALLOWLIST_CHANNEL = "webchat"

EXPLICIT_ELEVATED_ALLOW_FIELDS: set[ExplicitElevatedAllowField] = {
    "id",
    "from",
    "e164",
    "name",
    "username",
    "tag",
}

# In OpenClaw, this dynamically imports CHAT_CHANNEL_ORDER. Here we list the typical prefixes.
SENDER_PREFIXES = [
    "telegram",
    "discord",
    "slack",
    "whatsapp",
    "teams",
    "sms",
    "email",
    "webchat",
    "user",
    "group",
    "channel",
]

SENDER_PREFIX_RE = re.compile(rf"^({'|'.join(SENDER_PREFIXES)}):", flags=re.IGNORECASE)

AllowFromFormatter = Callable[[list[str]], list[str]]


def strip_sender_prefix(value: str | None) -> str:
    """Removes known channel/user prefixes before identity comparisons."""
    if not value:
        return ""
    trimmed = value.strip()
    return SENDER_PREFIX_RE.sub("", trimmed)


def parse_explicit_elevated_allow_entry(entry: str) -> dict[str, str] | None:
    """Parses explicit elevated allowlist entries such as `id:telegram:123`."""
    separator_index = entry.find(":")
    if separator_index <= 0:
        return None

    field_raw = _lower(entry[:separator_index])
    if field_raw not in EXPLICIT_ELEVATED_ALLOW_FIELDS:
        return None

    value = entry[separator_index + 1 :].strip()
    if not value:
        return None

    return {
        "field": field_raw,
        "value": value,
    }


def _slug_allow_token(value: str | None) -> str:
    """Normalize token by replacing @ and # with slug forms."""
    if not value:
        return ""
    # Mirror normalizeAtHashSlug
    val = value.replace("@", "").replace("#", "")
    return _lower(val)


def _add_token_variants(tokens: set[str], value: str | None) -> None:
    if not value:
        return
    tokens.add(value)
    normalized = _lower(value)
    if normalized:
        tokens.add(normalized)


def add_formatted_tokens(
    format_allow_from: AllowFromFormatter,
    values: list[str],
    tokens: set[str],
) -> None:
    """Adds formatted identity token variants into a matcher set."""
    formatted = format_allow_from(values)
    for entry in formatted:
        _add_token_variants(tokens, entry)


def matches_formatted_tokens(
    format_allow_from: AllowFromFormatter,
    value: str,
    tokens: set[str],
    include_stripped: bool = False,
) -> bool:
    """Checks a value against formatted identity tokens."""
    probe_tokens: set[str] = set()
    if include_stripped:
        stripped = strip_sender_prefix(value)
        values = [value, stripped] if stripped else [value]
    else:
        values = [value]

    add_formatted_tokens(
        format_allow_from=format_allow_from,
        values=values,
        tokens=probe_tokens,
    )

    for token in probe_tokens:
        if token in tokens:
            return True
    return False


def build_mutable_tokens(value: str | None) -> set[str]:
    """Builds normalized variants for mutable labels such as names and tags."""
    tokens: set[str] = set()
    trimmed = (value or "").strip()
    if not trimmed:
        return tokens

    _add_token_variants(tokens, trimmed)
    slugged = _slug_allow_token(trimmed)
    if slugged:
        _add_token_variants(tokens, slugged)
    return tokens


def matches_mutable_tokens(value: str | None, tokens: set[str]) -> bool:
    """Checks mutable label text against normalized token variants."""
    if not value or len(tokens) == 0:
        return False

    probes: set[str] = set()
    _add_token_variants(probes, value)
    slugged = _slug_allow_token(value)
    if slugged:
        _add_token_variants(probes, slugged)

    for probe in probes:
        if probe in tokens:
            return True
    return False
