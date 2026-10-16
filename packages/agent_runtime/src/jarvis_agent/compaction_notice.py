"""Compaction notice payloads for user-facing status messages.

Port of ``src/auto-reply/reply/compaction-notice.ts``.

These helpers produce the brief status notices that appear in the chat when
``agents.defaults.compaction.notifyUser`` is ``true``.  They are channel-
agnostic — channels receive ``ReplyPayload`` dicts and render them however
they like.
"""

from __future__ import annotations

from typing import Any, Callable, Literal

# ---------------------------------------------------------------------------
# Phase type + notice text
# ---------------------------------------------------------------------------

CompactionNoticePhase = Literal[
    "start",
    "end",
    "incomplete",
    "skipped",
    "memory_flush_degraded",
]

#: Display text for each compaction lifecycle phase.
#: Parity: ``COMPACTION_NOTICE_TEXT``.
COMPACTION_NOTICE_TEXT: dict[str, str] = {
    "start": "\U0001f9f9 Compacting context...",
    "end": "\U0001f9f9 Compaction complete",
    "incomplete": "\U0001f9f9 Compaction incomplete",
    "skipped": "\U0001f9f9 Compaction not needed",
    "memory_flush_degraded": (
        "\u26a0\ufe0f Memory maintenance temporarily failed; continuing your reply."
    ),
}


# ---------------------------------------------------------------------------
# Model ref formatting
# ---------------------------------------------------------------------------


def _sanitize_for_log(text: str) -> str:
    """Strip ANSI escape sequences from a string.

    Simplified port of ``sanitizeForLog`` from ``terminal-core``.
    Delegates to the real implementation when available.
    """
    try:
        from jarvis_normalization_core.text_utility import sanitize_ansi  # type: ignore[import]

        return sanitize_ansi(text)
    except Exception:
        import re

        return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def _normalize_optional_string(value: Any) -> str | None:
    """Return a non-empty stripped string, or ``None``.

    Parity: ``normalizeOptionalString``.
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


def format_compaction_model_ref(
    provider: str | None = None,
    model: str | None = None,
) -> str:
    """Format a ``provider/model`` display string for log messages.

    Parity: ``formatCompactionModelRef``.
    """
    normalized_provider = _normalize_optional_string(provider)
    normalized_model = _normalize_optional_string(model)
    if normalized_provider and normalized_model:
        return f"{_sanitize_for_log(normalized_provider)}/{_sanitize_for_log(normalized_model)}"
    if normalized_provider:
        return _sanitize_for_log(normalized_provider)
    if normalized_model:
        return _sanitize_for_log(normalized_model)
    return "unknown model"


# ---------------------------------------------------------------------------
# Config check
# ---------------------------------------------------------------------------


def should_notify_user_about_compaction(cfg: Any = None) -> bool:
    """Return whether the config has ``notifyUser: true``.

    Parity: ``shouldNotifyUserAboutCompaction``.
    """
    if cfg is None:
        return False
    try:
        return bool(
            cfg.agents.defaults.compaction.notify_user
            or cfg.get("agents", {})
            .get("defaults", {})
            .get("compaction", {})
            .get("notifyUser", False)
        )
    except Exception:
        try:
            return bool(
                cfg.get("agents", {})
                .get("defaults", {})
                .get("compaction", {})
                .get("notifyUser", False)
            )
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def create_compaction_notice_payload(
    phase: CompactionNoticePhase,
    current_message_id: str | None = None,
    apply_reply_to_mode: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a ``ReplyPayload`` dict for a compaction lifecycle notice.

    Parity: ``createCompactionNoticePayload``.
    """
    payload: dict[str, Any] = {
        "text": COMPACTION_NOTICE_TEXT.get(phase, phase),
        "replyToCurrent": True,
        "isCompactionNotice": True,
    }
    if current_message_id:
        payload["replyToId"] = current_message_id
    if apply_reply_to_mode is not None:
        payload = apply_reply_to_mode(payload)
    return payload


def read_compaction_hook_messages(value: Any) -> list[str]:
    """Coerce hook output to a clean list of non-empty strings.

    Parity: ``readCompactionHookMessages``.
    """
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        trimmed = entry.strip()
        if trimmed:
            result.append(trimmed)
    return result


def create_compaction_hook_notice_payload(
    messages: list[str],
    current_message_id: str | None = None,
    apply_reply_to_mode: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Build a notice payload from compaction hook messages.

    Returns ``None`` when the message list is empty.
    Parity: ``createCompactionHookNoticePayload``.
    """
    if not messages:
        return None
    payload: dict[str, Any] = {
        "text": "\n\n".join(messages),
        "replyToCurrent": True,
        "isCompactionNotice": True,
    }
    if current_message_id:
        payload["replyToId"] = current_message_id
    if apply_reply_to_mode is not None:
        payload = apply_reply_to_mode(payload)
    return payload


__all__ = [
    "COMPACTION_NOTICE_TEXT",
    "CompactionNoticePhase",
    "create_compaction_hook_notice_payload",
    "create_compaction_notice_payload",
    "format_compaction_model_ref",
    "read_compaction_hook_messages",
    "should_notify_user_about_compaction",
]
