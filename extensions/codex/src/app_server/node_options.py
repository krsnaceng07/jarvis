"""NODE_OPTIONS attestation for Codex app-server child processes.

OpenClaw parity: mirrors the ``assertSafeNodeOptions`` /
``attestNodeOptions`` / ``parseNodeOptions`` section of
``openclaw-main/extensions/codex/src/app-server/runtime-artifact.ts``.

Inherited ``NODE_OPTIONS`` may contain bounded resource, warning, DNS
result order, network-family autoselection, environment-proxy, and
CA-source options because those cannot preload code or change module
resolution. Malformed or unknown options and code-loading options such
as ``--require`` or ``--import`` fail closed. Live consumer: the Codex
doctor version check spawns the managed binary with inherited env, so it
attests first (see ``extensions/codex/src/doctor.py``).
"""

from __future__ import annotations

import re
from typing import Any

#: Boolean flags that cannot preload code. Mirrors
#: ``SAFE_NODE_OPTIONS_BOOLEAN_FLAGS``.
SAFE_NODE_OPTIONS_BOOLEAN_FLAGS: frozenset[str] = frozenset(
    {
        "--enable-network-family-autoselection",
        "--network-family-autoselection",
        "--no-deprecation",
        "--no-network-family-autoselection",
        "--no-warnings",
        "--pending-deprecation",
        "--throw-deprecation",
        "--trace-deprecation",
        "--trace-warnings",
        "--use-bundled-ca",
        "--use-env-proxy",
        "--use-openssl-ca",
        "--use-system-ca",
    }
)

#: Numeric flags with bounded values. Mirrors
#: ``SAFE_NODE_OPTIONS_NUMERIC_FLAGS``.
SAFE_NODE_OPTIONS_NUMERIC_FLAGS: frozenset[str] = frozenset(
    {
        "--max-old-space-size",
        "--max-semi-space-size",
        "--network-family-autoselection-attempt-timeout",
        "--stack-trace-limit",
    }
)

#: Allowed DNS result orders. Mirrors
#: ``SAFE_NODE_OPTIONS_DNS_RESULT_ORDERS``.
SAFE_NODE_OPTIONS_DNS_RESULT_ORDERS: frozenset[str] = frozenset(
    {"ipv4first", "ipv6first", "verbatim"}
)

_NAME_RE: re.Pattern[str] = re.compile(r"^--[a-z][a-z0-9-]{0,63}$")
_NUMERIC_RE: re.Pattern[str] = re.compile(r"^\d+$")
_WARNING_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")


def parse_node_options(value: str) -> list[str] | None:
    """Split a NODE_OPTIONS value like Node's lexer. Mirrors
    ``parseNodeOptions``: only literal spaces delimit, double quotes
    group, backslashes escape only inside quotes. Returns ``None`` for
    unterminated quotes."""
    # Mechanical port: only literal spaces delimit; double quotes group;
    # backslashes escape only inside quotes; single quotes are literal.
    tokens: list[str] = []
    in_quotes = False
    starts_new_token = True
    index = 0
    while index < len(value):
        character = value[index]
        if character == "\\" and in_quotes:
            index += 1
            if index >= len(value):
                return None
            character = value[index]
        elif character == " " and not in_quotes:
            starts_new_token = True
            index += 1
            continue
        elif character == '"':
            in_quotes = not in_quotes
            index += 1
            continue
        if starts_new_token:
            tokens.append(character)
            starts_new_token = False
        else:
            tokens[-1] += character
        index += 1
    return None if in_quotes else tokens


def _normalized_option_name(token: str) -> str | None:
    """Mirror ``normalizedNodeOptionName`` (underscores read as dashes)."""
    equals = token.find("=")
    raw_name = token if equals == -1 else token[:equals]
    name = raw_name.replace("_", "-")
    return name if _NAME_RE.match(name) else None


def attest_node_options(value: str) -> dict[str, Any]:
    """Attest one NODE_OPTIONS value. Mirrors ``attestNodeOptions``.

    Returns ``{"ok": True}`` or ``{"ok": False, "option"?: str}`` —
    ``option`` names the offending flag when one is identified.
    """
    tokens = parse_node_options(value)
    if not tokens:
        return {"ok": False}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        equals = token.find("=")
        flag = _normalized_option_name(token)
        if not flag:
            return {"ok": False}
        inline_value = None if equals == -1 else token[equals + 1 :]
        if flag in SAFE_NODE_OPTIONS_BOOLEAN_FLAGS:
            if inline_value is None:
                index += 1
                continue
            return {"ok": False, "option": flag}
        if flag == "--disable-warning" and inline_value and _WARNING_NAME_RE.match(inline_value):
            index += 1
            continue
        if flag == "--dns-result-order":
            order = inline_value
            if order is None:
                index += 1
                if index < len(tokens):
                    order = tokens[index]
                else:
                    return {"ok": False, "option": flag}
            if order and order in SAFE_NODE_OPTIONS_DNS_RESULT_ORDERS:
                index += 1
                continue
            return {"ok": False, "option": flag}
        if flag not in SAFE_NODE_OPTIONS_NUMERIC_FLAGS:
            return {"ok": False, "option": flag}
        numeric_value = inline_value
        if numeric_value is None:
            index += 1
            numeric_value = tokens[index] if index < len(tokens) else None
        if not numeric_value or not _NUMERIC_RE.match(numeric_value):
            return {"ok": False, "option": flag}
        index += 1
    return {"ok": True}


def assert_safe_node_options_env(env: Any) -> None:
    """Fail closed on unsafe inherited NODE_OPTIONS. Mirrors
    ``assertSafeNodeOptions`` (key match is case-insensitive; blank
    values are ignored). Raises ``ValueError`` naming the option when
    identified, else a generic parse failure."""
    if not isinstance(env, dict):
        return
    for raw_key, value in env.items():
        if not isinstance(raw_key, str) or raw_key.upper() != "NODE_OPTIONS":
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        result = attest_node_options(value)
        if result.get("ok") is True:
            continue
        option = result.get("option")
        if isinstance(option, str) and option:
            raise ValueError(f"Codex runtime artifact cannot attest NODE_OPTIONS option {option}")
        raise ValueError("Codex runtime artifact cannot safely parse NODE_OPTIONS")


__all__ = [
    "SAFE_NODE_OPTIONS_BOOLEAN_FLAGS",
    "SAFE_NODE_OPTIONS_DNS_RESULT_ORDERS",
    "SAFE_NODE_OPTIONS_NUMERIC_FLAGS",
    "assert_safe_node_options_env",
    "attest_node_options",
    "parse_node_options",
]
