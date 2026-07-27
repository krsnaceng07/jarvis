"""jarvis.routing.channel_ids — chat-channel-id normalization seam.

OpenClaw parity: mirrors ``src/channels/ids.ts``'s ``normalizeChatChannelId``.

OpenClaw resolves against a generated bundled-channel catalog (ids +
aliases). JARVIS has no bundled channel catalog yet; the runtime
catalog is a registration seam. Semantics preserved:

- unknown / empty input → ``None``
- alias → canonical id (when registered)
- known id → id (lowered)
- unknown id → ``None`` (callers like ``normalize_route_binding_channel_id``
  then fall through to the raw lowered id, matching the TS behavior where
  binding channels are NOT collapsed through the alias map — see the
  channel-route-targets "imsg" test).
"""

from __future__ import annotations

from jarvis_normalization_core.string_coerce import normalize_optional_lowercase_string

# Runtime-registered catalog: canonical id -> tuple of aliases.
_RUNTIME_CHANNEL_ENTRIES: dict[str, tuple[str, ...]] = {}


def register_chat_channel_id(channel_id: str, aliases: tuple[str, ...] | list[str] = ()) -> None:
    """Register a canonical channel id (runtime-catalog seam)."""
    normalized = normalize_optional_lowercase_string(channel_id)
    if not normalized:
        return
    _RUNTIME_CHANNEL_ENTRIES[normalized] = tuple(
        alias for alias in (normalize_optional_lowercase_string(a) for a in aliases) if alias
    )


def reset_chat_channel_ids_for_tests() -> None:
    """Clear the runtime channel catalog (test seam)."""
    _RUNTIME_CHANNEL_ENTRIES.clear()


def normalize_chat_channel_id(raw: object) -> str | None:
    """Normalize a raw chat channel id or alias to a known canonical id.

    Mirrors ``normalizeChatChannelId``: ``None`` when the id is not in
    the catalog (bundled or runtime).
    """
    normalized = normalize_optional_lowercase_string(raw)
    if not normalized:
        return None
    if normalized in _RUNTIME_CHANNEL_ENTRIES:
        return normalized
    for channel_id, aliases in _RUNTIME_CHANNEL_ENTRIES.items():
        if normalized in aliases:
            return channel_id
    return None


__all__ = [
    "normalize_chat_channel_id",
    "register_chat_channel_id",
    "reset_chat_channel_ids_for_tests",
]
