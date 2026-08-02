"""jarvis.agents.embedded_agent_runner.model_compat — model compat merging + reasoning resolution.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/model.compat.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`merge_model_media_input` — shallow-merge two
  ``ModelMediaInputConfig`` dicts (deep-merging the ``image``
  sub-config).
- :func:`merge_model_compat` — shallow-merge two ``ModelCompatConfig``
  dicts.
- :func:`resolve_configured_model_reasoning` — return the
  configured reasoning flag, with the vLLM/Qwen thinking
  compatibility fallback.
- :func:`resolve_configured_fallback_reasoning` — boolean variant
  that defaults to ``False`` when no source applies.
- :func:`resolve_merged_configured_model_reasoning` — merged
  variant combining configured and resolved compat layers.

Phase 7.3a — focused minimal port.

The OpenClaw source uses :func:`normalizeProviderId` from
``model-selection.js``. The Python port delegates provider id
normalization to an installable normalizer so the host can plug
in the real provider-catalog implementation when the catalog
lands.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


#: Provider id normalizer. The Python port defaults to a
#: focused minimal trim+lowercase.
_PROVIDER_ID_NORMALIZER: Callable[[str], str] = lambda value: (value or "").strip().lower()


def set_provider_id_normalizer(
    normalizer: Callable[[str], str],
) -> None:
    """Install a custom provider id normalizer."""
    global _PROVIDER_ID_NORMALIZER
    _PROVIDER_ID_NORMALIZER = normalizer


def _normalize_provider_id(value: str) -> str:
    return _PROVIDER_ID_NORMALIZER(value or "")


def _read_compat_thinking_format(compat: Any) -> Optional[str]:
    """Read the ``thinkingFormat`` field from a compat object.

    Mirrors :func:`readCompatThinkingFormat``
    (``model.compat.ts:76-82``).
    """
    if not compat or not isinstance(compat, dict) or isinstance(compat, list):
        return None
    thinking_format = compat.get("thinkingFormat")
    return thinking_format if isinstance(thinking_format, str) else None


def _is_vllm_qwen_thinking_compat(
    *,
    provider: str,
    compat: Any,
) -> bool:
    """Return True when the provider/compat signals vLLM-Qwen thinking.

    Mirrors :func:`isVllmQwenThinkingCompat``
    (``model.compat.ts:68-74``).
    """
    thinking_format = _read_compat_thinking_format(compat)
    return (
        _normalize_provider_id(provider) == "vllm"
        and thinking_format in ("qwen", "qwen-chat-template")
    )


def merge_model_media_input(
    base: Optional[Dict[str, Any]],
    override: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Shallow-merge two media-input configs (deep-merging ``image``).

    Mirrors :func:`mergeModelMediaInput``
    (``model.compat.ts:4-25``).
    """
    if not base:
        return override
    if not override:
        return base
    image_merged: Optional[Dict[str, Any]]
    if base.get("image") or override.get("image"):
        image_merged = {**(base.get("image") or {}), **(override.get("image") or {})}
    else:
        image_merged = None
    out: Dict[str, Any] = {**base, **override}
    if image_merged is not None:
        out["image"] = image_merged
    else:
        out.pop("image", None)
    return out


def merge_model_compat(
    base: Optional[Dict[str, Any]],
    override: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Shallow-merge two compat configs.

    Mirrors :func:`mergeModelCompat``
    (``model.compat.ts:84-95``).
    """
    if not base:
        return override
    if not override:
        return base
    return {**base, **override}


def resolve_configured_model_reasoning(
    *,
    provider: str,
    compat: Any = None,
    reasoning: Optional[bool] = None,
) -> Optional[bool]:
    """Resolve the configured reasoning flag with vLLM/Qwen fallback.

    Mirrors :func:`resolveConfiguredModelReasoning``
    (``model.compat.ts:35-44``).
    """
    if reasoning is not None:
        return reasoning
    if _is_vllm_qwen_thinking_compat(provider=provider, compat=compat):
        return True
    return None


def resolve_configured_fallback_reasoning(
    *,
    provider: str,
    compat: Any = None,
    reasoning: Optional[bool] = None,
) -> bool:
    """Boolean variant of :func:`resolve_configured_model_reasoning`.

    Mirrors :func:`resolveConfiguredFallbackReasoning``
    (``model.compat.ts:27-33``).
    """
    return resolve_configured_model_reasoning(
        provider=provider, compat=compat, reasoning=reasoning
    ) or False


def resolve_merged_configured_model_reasoning(
    *,
    provider: str,
    configured_compat: Any = None,
    resolved_compat: Any = None,
    configured_reasoning: Optional[bool] = None,
    discovered_reasoning: Optional[bool] = None,
) -> bool:
    """Resolve the merged reasoning flag across two compat layers.

    Mirrors :func:`resolveMergedConfiguredModelReasoning``
    (``model.compat.ts:46-66``).
    """
    if configured_reasoning is not None:
        return configured_reasoning
    if _is_vllm_qwen_thinking_compat(
        provider=provider, compat=configured_compat
    ):
        return True
    return (
        resolve_configured_model_reasoning(
            provider=provider,
            compat=resolved_compat,
            reasoning=discovered_reasoning,
        )
        or False
    )


__all__ = [
    "merge_model_compat",
    "merge_model_media_input",
    "resolve_configured_fallback_reasoning",
    "resolve_configured_model_reasoning",
    "resolve_merged_configured_model_reasoning",
    "set_provider_id_normalizer",
]
