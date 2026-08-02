"""jarvis.agents.embedded_agent_runner.history — limit embedded-agent history length.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/history.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`limit_history_turns` — limit conversation history to the
  last N user turns (preserving leading non-conversation
  messages like compactionSummary/branchSummary).
- :func:`get_history_limit_from_session_key` — extract
  provider + user id from a session key and look up
  ``dmHistoryLimit`` / ``historyLimit``.

Phase 7.5a — focused minimal port.

The OpenClaw source uses
:func:`normalizeProviderId` from
``@openclaw/model-catalog-core/provider-id`` and
:func:`normalizeOptionalLowercaseString` from
``@openclaw/normalization-core/string-coerce``. The Python port
delegates provider-id normalization to an installable hook so
the host can plug in the real provider-catalog layer when it
lands.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


#: Regex matching the ``:thread:N`` / ``:topic:N`` suffix. Mirrors
#: :data:`THREAD_SUFFIX_REGEX`` (``history.ts:9``).
THREAD_SUFFIX_REGEX = re.compile(r"^(.*)(?::(?:thread|topic):\d+)$", re.IGNORECASE)


def _strip_thread_suffix(value: str) -> str:
    """Strip the ``:thread:N`` / ``:topic:N`` suffix from ``value``.

    Mirrors :func:`stripThreadSuffix`` (``history.ts:11-14``).
    """
    match = THREAD_SUFFIX_REGEX.match(value)
    return match.group(1) if match else value


#: Provider id normalizer. The OpenClaw source uses
#: ``normalizeProviderId`` from
#: ``@openclaw/model-catalog-core/provider-id``. The Python port
#: defaults to a focused minimal trim+lowercase.
_PROVIDER_ID_NORMALIZER: Any = lambda value: (value or "").strip().lower()


def set_provider_id_normalizer(
    normalizer: Any,
) -> None:
    """Install a custom provider id normalizer."""
    global _PROVIDER_ID_NORMALIZER
    _PROVIDER_ID_NORMALIZER = normalizer


def _normalize_provider_id(value: str) -> str:
    return _PROVIDER_ID_NORMALIZER(value or "")


def _normalize_optional_lowercase_string(value: Any) -> Optional[str]:
    """Coerce ``value`` to a lowercased string, or ``None`` for empty input.

    Mirrors :func:`normalizeOptionalLowercaseString``.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed.lower()


def limit_history_turns(
    messages: List[Dict[str, Any]],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    """Limit conversation history to the last N user turns.

    Mirrors :func:`limitHistoryTurns`` (``history.ts:24-61``).
    """
    if not limit or limit <= 0 or not messages:
        return messages
    # Preserve leading non-conversation messages.
    conversation_start = 0
    while conversation_start < len(messages):
        role = messages[conversation_start].get("role") if isinstance(
            messages[conversation_start], dict
        ) else None
        if role == "user" or role == "assistant":
            break
        conversation_start += 1
    tail = messages[conversation_start:]
    if not tail:
        return messages
    user_count = 0
    last_user_index = len(tail)
    for i in range(len(tail) - 1, -1, -1):
        if not isinstance(tail[i], dict):
            continue
        if tail[i].get("role") == "user":
            user_count += 1
            if user_count > limit:
                return [*messages[:conversation_start], *tail[last_user_index:]]
            last_user_index = i
    return messages


def _resolve_provider_config(
    config: Optional[Dict[str, Any]],
    provider_id: str,
) -> Optional[Dict[str, Any]]:
    """Return the channel config for ``provider_id`` from ``config``.

    Mirrors the inline resolver in
    :func:`getHistoryLimitFromSessionKey``
    (``history.ts:88-118``).
    """
    if not config or not isinstance(config, dict):
        return None
    channels = config.get("channels")
    if not channels or not isinstance(channels, dict):
        return None
    for configured_provider_id, value in channels.items():
        if _normalize_provider_id(configured_provider_id) != provider_id:
            continue
        if not value or not isinstance(value, dict) or isinstance(value, list):
            return None
        return value
    return None


def get_history_limit_from_session_key(
    session_key: Optional[str],
    config: Optional[Dict[str, Any]],
) -> Optional[int]:
    """Extract provider + user id from ``session_key`` and look up the limit.

    Mirrors :func:`getHistoryLimitFromSessionKey``
    (``history.ts:68-140``).
    """
    if not session_key or not config:
        return None
    parts = [p for p in session_key.split(":") if p]
    if len(parts) >= 3 and parts[0] == "agent":
        provider_parts = parts[2:]
    else:
        provider_parts = parts
    provider = _normalize_provider_id(provider_parts[0] if provider_parts else "")
    if not provider:
        return None
    kind = _normalize_optional_lowercase_string(
        provider_parts[1] if len(provider_parts) > 1 else None
    )
    user_id_raw = ":".join(provider_parts[2:])
    user_id = _strip_thread_suffix(user_id_raw)
    provider_config = _resolve_provider_config(config, provider)
    if not provider_config:
        return None
    if kind == "dm" or kind == "direct":
        if (
            user_id
            and isinstance(provider_config.get("dms"), dict)
            and user_id in provider_config["dms"]
        ):
            history_limit = provider_config["dms"][user_id].get("historyLimit")
            if isinstance(history_limit, (int, float)) and not isinstance(history_limit, bool):
                return int(history_limit)
        history_limit = provider_config.get("dmHistoryLimit")
        if isinstance(history_limit, (int, float)) and not isinstance(history_limit, bool):
            return int(history_limit)
        return None
    if kind == "channel" or kind == "group":
        history_limit = provider_config.get("historyLimit")
        if isinstance(history_limit, (int, float)) and not isinstance(history_limit, bool):
            return int(history_limit)
        return None
    return None


__all__ = [
    "get_history_limit_from_session_key",
    "limit_history_turns",
    "set_provider_id_normalizer",
]
