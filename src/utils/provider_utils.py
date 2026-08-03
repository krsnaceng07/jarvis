"""jarvis.utils.provider_utils — shared provider behavior helpers.

OpenClaw parity: mirrors ``openclaw-main/src/utils/provider-utils.ts``.

Public surface:

- :func:`is_reasoning_tag_provider`
"""
from __future__ import annotations

from typing import Any, Optional


# Installable hooks ---------------------------------------------------------

_is_reasoning_tag_provider_hook = None
_resolve_reasoning_output_mode_hook = None


def set_is_reasoning_tag_provider_hook(fn) -> None:
    global _is_reasoning_tag_provider_hook
    _is_reasoning_tag_provider_hook = fn


def set_resolve_reasoning_output_mode_hook(fn) -> None:
    global _resolve_reasoning_output_mode_hook
    _resolve_reasoning_output_mode_hook = fn


def _normalize_optional_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def resolve_reasoning_output_mode(params: dict) -> str:
    """Resolve native vs tagged reasoning output mode for a provider.

    Mirrors :func:`resolveReasoningOutputMode` (``utils/provider-utils.ts``).
    """
    if _resolve_reasoning_output_mode_hook is not None:
        v = _resolve_reasoning_output_mode_hook(params)
        return v if v in ("native", "tagged") else "native"
    provider = _normalize_optional_string(params.get("provider"))
    if not provider:
        return "native"
    return "native"


def is_reasoning_tag_provider(
    provider: Any = None,
    options: Optional[dict] = None,
) -> bool:
    """Return true if the provider wraps reasoning in tags instead of native fields.

    Mirrors :func:`isReasoningTagProvider` (``utils/provider-utils.ts``).
    """
    if _is_reasoning_tag_provider_hook is not None:
        return bool(_is_reasoning_tag_provider_hook({"provider": provider, "options": options}))
    return resolve_reasoning_output_mode({"provider": provider, **(options or {})}) == "tagged"


__all__ = [
    "is_reasoning_tag_provider",
    "set_is_reasoning_tag_provider_hook",
    "set_resolve_reasoning_output_mode_hook",
]
