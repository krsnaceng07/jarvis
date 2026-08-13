"""jarvis.auto_reply.thinking_shared — shared thinking normalization.

OpenClaw parity: mirrors
``openclaw-main/src/auto-reply/thinking.shared.ts``.

Shared normalization for thinking, verbosity, tracing, reasoning, and
usage directives.

Adaptations
-----------
- TS union types (``ThinkLevel``, ``VerboseLevel``, ...) become
  module-level tuples of the accepted string values plus type aliases
  (``str``).
- ``ThinkingCatalogEntry`` is a dict shape: ``{"provider", "id",
  "api"?, "reasoning"?, "params"?, "compat"?}``.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from jarvis_normalization_core.string_coerce import (
    normalize_fast_mode,
    normalize_lowercase_string_or_empty,
    normalize_optional_lowercase_string,
)

__all__ = [
    "ALL_THINKING_LEVELS",
    "BASE_THINKING_LEVELS",
    "THINKING_LEVELS_HELP",
    "THINKING_LEVEL_RANKS",
    "is_session_default_directive_value",
    "normalize_elevated_level",
    "normalize_fast_mode",
    "normalize_reasoning_level",
    "normalize_think_level",
    "normalize_trace_level",
    "normalize_usage_display",
    "normalize_verbose_level",
    "resolve_effective_response_usage",
    "resolve_response_usage_mode",
    "resolve_thinking_default_for_model",
]

#: Complete canonical level set accepted by user-facing thinking
#: controls. Mirrors ``ALL_THINKING_LEVELS``
#: (``thinking.shared.ts:42-52``).
ALL_THINKING_LEVELS: tuple[str, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "adaptive",
    "max",
    "ultra",
)

#: Mirrors ``THINKING_LEVELS_HELP`` (``thinking.shared.ts:53``).
THINKING_LEVELS_HELP: str = "|".join(ALL_THINKING_LEVELS)

#: Mirrors ``BASE_THINKING_LEVELS`` (``thinking.shared.ts:54``).
BASE_THINKING_LEVELS: list[str] = ["off", "minimal", "low", "medium", "high"]

#: Mirrors ``THINKING_LEVEL_RANKS`` (``thinking.shared.ts:55-65``).
THINKING_LEVEL_RANKS: dict[str, int] = {
    "off": 0,
    "minimal": 10,
    "low": 20,
    "medium": 30,
    "high": 40,
    "adaptive": 30,
    "xhigh": 60,
    "max": 70,
    "ultra": 80,
}

_COLLAPSE = re.compile(r"[\s_-]+")


def normalize_think_level(raw: Optional[str] = None) -> Optional[str]:
    """Normalizes user-provided thinking level strings to the canonical
    enum. Mirrors ``normalizeThinkLevel``
    (``thinking.shared.ts:68-108``)."""
    key = normalize_optional_lowercase_string(raw)
    if not key:
        return None
    collapsed = _COLLAPSE.sub("", key)
    if collapsed in ("adaptive", "auto"):
        return "adaptive"
    if collapsed == "max":
        return "max"
    if collapsed == "ultra":
        return "ultra"
    if collapsed in ("xhigh", "extrahigh"):
        return "xhigh"
    if key in ("off",):
        return "off"
    if key in ("on", "enable", "enabled"):
        return "low"
    if key in ("min", "minimal"):
        return "minimal"
    if key in ("low", "thinkhard", "think-hard", "think_hard"):
        return "low"
    if key in ("mid", "med", "medium", "thinkharder", "think-harder", "harder"):
        return "medium"
    if key in ("high", "ultrathink", "think-hard", "thinkhardest", "highest"):
        return "high"
    if key in ("think",):
        return "minimal"
    return None


def is_session_default_directive_value(raw: Optional[str] = None) -> bool:
    """Returns True for command values that clear an inherited session
    override. Mirrors ``isSessionDefaultDirectiveValue``
    (``thinking.shared.ts:111-117``)."""
    key = normalize_optional_lowercase_string(raw)
    if not key:
        return False
    return key in ("default", "inherit", "inherited", "clear", "reset", "unpin")


def resolve_thinking_default_for_model(params: dict) -> str:
    """Chooses the default thinking level for one provider/model
    catalog entry. Mirrors ``resolveThinkingDefaultForModel``
    (``thinking.shared.ts:120-132``) — the *fallback* resolver (the
    profile-aware resolver lives in :mod:`src.auto_reply.thinking`)."""
    catalog = params.get("catalog") or []
    candidate = next(
        (
            entry
            for entry in catalog
            if entry.get("provider") == params.get("provider")
            and entry.get("id") == params.get("model")
        ),
        None,
    )
    if candidate and candidate.get("reasoning"):
        return "low"
    return "off"


def _normalize_on_off_full_level(raw: Optional[str] = None) -> Optional[str]:
    """Mirrors ``normalizeOnOffFullLevel``
    (``thinking.shared.ts:136-151``)."""
    key = normalize_optional_lowercase_string(raw)
    if not key:
        return None
    if key in ("off", "false", "no", "0"):
        return "off"
    if key in ("full", "all", "everything"):
        return "full"
    if key in ("on", "minimal", "true", "yes", "1"):
        return "on"
    return None


def normalize_verbose_level(raw: Optional[str] = None) -> Optional[str]:
    """Normalizes /verbose values. Mirrors ``normalizeVerboseLevel``
    (``thinking.shared.ts:154-156``)."""
    return _normalize_on_off_full_level(raw)


def normalize_trace_level(raw: Optional[str] = None) -> Optional[str]:
    """Normalizes /trace values. Mirrors ``normalizeTraceLevel``
    (``thinking.shared.ts:159-174``)."""
    key = normalize_optional_lowercase_string(raw)
    if not key:
        return None
    if key in ("off", "false", "no", "0"):
        return "off"
    if key in ("on", "true", "yes", "1"):
        return "on"
    if key in ("raw", "unfiltered"):
        return "raw"
    return None


def normalize_usage_display(raw: Optional[str] = None) -> Optional[str]:
    """Normalizes response usage display values. Mirrors
    ``normalizeUsageDisplay`` (``thinking.shared.ts:177-195``)."""
    if not raw:
        return None
    key = normalize_lowercase_string_or_empty(raw)
    if key in ("off", "false", "no", "0", "disable", "disabled"):
        return "off"
    if key in ("on", "true", "yes", "1", "enable", "enabled"):
        return "tokens"
    if key in ("tokens", "token", "tok", "minimal", "min"):
        return "tokens"
    if key in ("full", "session"):
        return "full"
    return None


def resolve_response_usage_mode(raw: Optional[str] = None) -> str:
    """Resolves response usage display mode with the persisted default.
    Mirrors ``resolveResponseUsageMode``
    (``thinking.shared.ts:198-200``)."""
    normalized = normalize_usage_display(raw)
    return normalized if normalized is not None else "off"


def _resolve_messages_response_usage_default(
    configured: Any,
    channel: Optional[str] = None,
) -> Optional[str]:
    """Mirrors ``resolveMessagesResponseUsageDefault``
    (``thinking.shared.ts:207-218``)."""
    if isinstance(configured, str):
        return configured
    if isinstance(configured, dict):
        channel_value = configured.get(channel) if channel else None
        return (
            channel_value
            if channel_value is not None
            else configured.get("default")
        )
    return None


def resolve_effective_response_usage(
    session_raw: Optional[str],
    configured: Any,
    channel: Optional[str] = None,
) -> str:
    """Mirrors ``resolveEffectiveResponseUsage``
    (``thinking.shared.ts:220-231``)."""
    session_normalized = normalize_usage_display(session_raw)
    if session_normalized is not None:
        return session_normalized
    config_default = _resolve_messages_response_usage_default(
        configured, channel
    )
    return resolve_response_usage_mode(config_default)


def normalize_elevated_level(raw: Optional[str] = None) -> Optional[str]:
    """Normalizes elevated execution policy values. Mirrors
    ``normalizeElevatedLevel`` (``thinking.shared.ts:234-252``)."""
    if not raw:
        return None
    key = normalize_lowercase_string_or_empty(raw)
    if key in ("off", "false", "no", "0"):
        return "off"
    if key in ("full", "auto", "auto-approve", "autoapprove"):
        return "full"
    if key in ("ask", "prompt", "approval", "approve"):
        return "ask"
    if key in ("on", "true", "yes", "1"):
        return "on"
    return None


def normalize_reasoning_level(raw: Optional[str] = None) -> Optional[str]:
    """Normalizes reasoning visibility values. Mirrors
    ``normalizeReasoningLevel`` (``thinking.shared.ts:255-270``)."""
    if not raw:
        return None
    key = normalize_lowercase_string_or_empty(raw)
    if key in (
        "off", "false", "no", "0", "hide", "hidden", "disable", "disabled",
    ):
        return "off"
    if key in (
        "on", "true", "yes", "1", "show", "visible", "enable", "enabled",
    ):
        return "on"
    if key in ("stream", "streaming", "draft", "live"):
        return "stream"
    return None
