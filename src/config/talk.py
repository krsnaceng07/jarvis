"""jarvis.config.talk — talk-mode config normalizer.

OpenClaw parity: mirrors ``openclaw-main/src/config/talk.ts``.

Focused minimal port: applies the talk config normalizer pipeline.
All provider + realtime normalization is delegated to caller-provided
callables until the secrets/string-coerce modules land.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


def _is_record(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes, set))


def _normalize_optional_string(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _normalize_positive_int(value: Any) -> Optional[int]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    n = int(value)
    return n if n > 0 else None


def _normalize_non_negative_int(value: Any) -> Optional[int]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    n = int(value)
    return n if n >= 0 else None


def _normalize_vad_threshold(value: Any) -> Optional[float]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    f = float(value)
    return f if 0 <= f <= 1 else None


def normalize_talk_section(
    value: Any,
    *,
    normalize_optional_string_fn: Optional[Callable[[Any], str]] = None,
    normalize_think_level_fn: Optional[Callable[[str], str]] = None,
    normalize_fast_mode_fn: Optional[Callable[[Any], Any]] = None,
    coerce_secret_ref_fn: Optional[Callable[[Any], Any]] = None,
) -> Optional[dict]:
    """Normalize persisted talk config into the canonical provider/providers shape.

    Mirrors :func:`normalizeTalkSection`
    (``shared/config/talk.ts`).
    """
    if not _is_record(value):
        return None
    norm_str = normalize_optional_string_fn or _normalize_optional_string
    norm_think = normalize_think_level_fn or (lambda s: s if isinstance(s, str) else "")
    norm_fast = normalize_fast_mode_fn or (lambda v: v)
    coerce_ref = coerce_secret_ref_fn or (lambda v: v if _is_record(v) else None)

    def _secret(value):
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed if trimmed else None
        ref = coerce_ref(value)
        return ref if ref is not None else None

    out: dict = {}
    speech_locale = norm_str(value.get("speechLocale"))
    if speech_locale:
        out["speechLocale"] = speech_locale
    if isinstance(value.get("interruptOnSpeech"), bool):
        out["interruptOnSpeech"] = value["interruptOnSpeech"]
    consult_thinking = norm_think(norm_str(value.get("consultThinkingLevel")))
    if consult_thinking:
        out["consultThinkingLevel"] = consult_thinking
    raw_fast = value.get("consultFastMode")
    if isinstance(raw_fast, (bool, str)):
        fast = norm_fast(raw_fast)
        if isinstance(fast, bool):
            out["consultFastMode"] = fast
    silence = _normalize_positive_int(value.get("silenceTimeoutMs"))
    if silence is not None:
        out["silenceTimeoutMs"] = silence
    # providers/realtime/provider kept open-world here; downstream callables
    # in the io/load path apply the strict field allow-list.
    if isinstance(value.get("providers"), dict):
        out["providers"] = value["providers"]
    if isinstance(value.get("realtime"), dict):
        out["realtime"] = value["realtime"]
    provider = norm_str(value.get("provider"))
    if provider:
        out["provider"] = provider
    return out or None


def normalize_talk_config(config: Any) -> Any:
    """Return a config copy with ``talk`` normalized when a valid Talk section is present.

    Mirrors :func:`normalizeTalkConfig`
    (``shared/config/talk.ts`).
    """
    if not _is_record(config) or not isinstance(config.get("talk"), dict):
        return config
    normalized = normalize_talk_section(config["talk"])
    if not normalized:
        return config
    return {**config, "talk": normalized}


def resolve_active_talk_provider_config(
    talk: Any,
    *,
    normalize_talk_section_fn: Optional[Callable] = None,
) -> Optional[dict]:
    """Resolve the single active talk speech provider and its provider-owned config."""
    norm = (normalize_talk_section_fn or normalize_talk_section)(talk)
    if not norm:
        return None
    provider = _normalize_optional_string(norm.get("provider"))
    providers = norm.get("providers")
    if provider:
        if isinstance(providers, dict) and not isinstance(providers.get(provider), dict):
            return None
        return {"provider": provider, "config": (providers or {}).get(provider) or {}}
    if isinstance(providers, dict):
        keys = list(providers.keys())
        if len(keys) == 1:
            return {"provider": keys[0], "config": providers.get(keys[0]) or {}}
    return None


__all__ = [
    "normalize_talk_section",
    "normalize_talk_config",
    "resolve_active_talk_provider_config",
]
