"""jarvis.config.redact_snapshot_raw — low-level raw-text redaction transforms.

OpenClaw parity: mirrors ``openclaw-main/src/config/redact-snapshot.raw.ts``.
"""
from __future__ import annotations

from typing import Callable, List, Optional


def _unique_strings(values) -> list:
    seen = set()
    out: list = []
    for v in values:
        if not isinstance(v, str):
            continue
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def replace_sensitive_values_in_raw(params: dict) -> str:
    """Replace known sensitive values in raw config text while preserving structure.

    Mirrors :func:`replaceSensitiveValuesInRaw`
    (``shared/config/redact-snapshot.raw.ts`).
    """
    raw: str = params.get("raw") or ""
    sensitive_values: List[str] = params.get("sensitiveValues") or []
    sentinel: str = params.get("redactedSentinel") or "***"
    # Empty string is not a valid replacement token; replaceAll("", x) would
    # match every character boundary and corrupt the whole raw snapshot.
    values = sorted(
        {v for v in sensitive_values if v},
        key=lambda v: -len(v),
    )
    result = raw
    for value in values:
        result = result.replace(value, sentinel)
    return result


def should_fallback_to_structured_raw_redaction(params: dict) -> bool:
    """Return whether raw-string redaction changed semantics and structured redaction is needed.

    Mirrors :func:`shouldFallbackToStructuredRawRedaction`
    (``shared/config/redact-snapshot.raw.ts`).
    """
    redacted_raw: str = params.get("redactedRaw") or ""
    original_config = params.get("originalConfig")
    restore_parsed: Optional[Callable] = params.get("restoreParsed")
    parse_json5: Optional[Callable] = params.get("parseJson5")
    if not callable(restore_parsed) or not callable(parse_json5):
        return True
    try:
        parsed = parse_json5(redacted_raw)
    except Exception:
        return True
    try:
        restored = restore_parsed(parsed)
    except Exception:
        return True
    if not restored or not restored.get("ok"):
        return True
    result = restored.get("result")
    # Best-effort deep-equality check without external dependency.
    return result != original_config


__all__ = [
    "replace_sensitive_values_in_raw",
    "should_fallback_to_structured_raw_redaction",
]
