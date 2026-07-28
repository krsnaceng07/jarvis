"""Session chat-type derivation entry point.

Mirrors OpenClaw's ``extensions/sessions/session-chat-type.ts``:
the top-level ``derive_session_chat_type`` that first uses
the generic key parser (in ``session-chat-type-shared``),
then falls back to per-channel ``derive_legacy_session_chat_type``
hooks (in OpenClaw these come from the bootstrap channel
plugin registry).

The Python port keeps the same contract but the
"bootstrap registry" is replaced with an opt-in
``LEGACY_CHAT_TYPE_DERIVERS`` dict keyed on channel id.
Plugins can register their own derivers via
``register_legacy_chat_type_deriver``.
"""
from __future__ import annotations

from typing import Callable, Optional

from .session_chat_type_shared import (
    SessionKeyChatType,
    derive_session_chat_type_from_key,
)

# ── Per-channel legacy chat-type deriver registry ──────────────────


LegacyChatTypeDeriver = Callable[[str], Optional[SessionKeyChatType]]


_LEGACY_CHAT_TYPE_DERIVERS: dict[str, LegacyChatTypeDeriver] = {}


def register_legacy_chat_type_deriver(
    channel: str, deriver: LegacyChatTypeDeriver
) -> Callable[[], None]:
    """Register a legacy chat-type deriver for a channel.

    Returns an unregister callable. Mirrors the OpenClaw
    bootstrap-plugin ``messaging.deriveLegacySessionChatType``
    hook surface.
    """
    normalized = channel.strip().lower()
    _LEGACY_CHAT_TYPE_DERIVERS[normalized] = deriver

    def unregister() -> None:
        _LEGACY_CHAT_TYPE_DERIVERS.pop(normalized, None)

    return unregister


def _collect_legacy_chat_type_derivers(
    scoped_session_key: str,
) -> list[LegacyChatTypeDeriver]:
    """Collect the legacy derivers relevant to ``scoped_session_key``.

    Mirrors the OpenClaw ``collectLegacyChatTypeCandidatePluginIds``
    heuristic:
    - The first colon-delimited token of the scoped key
    - ``"whatsapp"`` when ``@g.us`` is in the key (legacy
      bare JID format)
    """
    candidates: set[str] = set()
    first_token = next((t for t in scoped_session_key.split(":") if t), "")
    if first_token:
        candidates.add(first_token.strip().lower())
    if "@g.us" in scoped_session_key:
        candidates.add("whatsapp")
    return [_LEGACY_CHAT_TYPE_DERIVERS[c] for c in candidates if c in _LEGACY_CHAT_TYPE_DERIVERS]


# ── Top-level derivation ──────────────────────────────────────────


def derive_session_chat_type(session_key: object) -> SessionKeyChatType:
    """Best-effort chat-type derivation from a session key.

    Mirrors OpenClaw's ``deriveSessionChatType``:
    1. Try the generic key parser (canonical + built-in legacy)
    2. If that returns ``"unknown"``, try per-channel legacy
       derivers registered via ``register_legacy_chat_type_deriver``

    Note: the OpenClaw source uses a bootstrap plugin
    registry for step 2; the Python port exposes an
    opt-in ``register_legacy_chat_type_deriver`` API with
    the same effect for plugins to call.
    """
    if not isinstance(session_key, str):
        return "unknown"
    # First try the generic derivation (canonical + built-in legacy).
    built_in = derive_session_chat_type_from_key(session_key, [])
    if built_in != "unknown":
        return built_in
    # Compute the scoped key the same way the generic
    # derivation does so plugin derivers see the same input.
    from .session_key_utils import parse_agent_session_key

    raw = session_key.strip().lower()
    parsed = parse_agent_session_key(raw)
    scoped = parsed.rest if parsed is not None else raw
    for deriver in _collect_legacy_chat_type_derivers(scoped):
        try:
            derived = deriver(scoped)
        except Exception:  # noqa: BLE001 — best-effort fan-out
            continue
        if derived is not None:
            return derived
    return "unknown"


__all__ = [
    "LegacyChatTypeDeriver",
    "derive_session_chat_type",
    "register_legacy_chat_type_deriver",
]
