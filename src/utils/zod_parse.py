"""jarvis.utils.zod_parse — null-returning Zod parse helpers.

OpenClaw parity: mirrors ``openclaw-main/src/utils/zod-parse.ts``.

Public surface:

- :func:`safe_parse_with_schema`
- :func:`safe_parse_json_with_schema`
"""
from __future__ import annotations

import json
from typing import Any, Optional, Protocol


class ZodLike(Protocol):
    def safe_parse(self, value: Any) -> Any: ...


def safe_parse_with_schema(schema: Any, value: Any) -> Optional[Any]:
    """Validate ``value`` with ``schema.safe_parse``; return None on failure.

    Mirrors :func:`safeParseWithSchema` (``utils/zod-parse.ts``).
    """
    if schema is None or not callable(getattr(schema, "safe_parse", None)):
        return None
    parsed = schema.safe_parse(value)
    success = getattr(parsed, "success", None)
    if success is True:
        return getattr(parsed, "data", None)
    if isinstance(parsed, dict):
        return parsed.get("data") if parsed.get("success") else None
    return None


def safe_parse_json_with_schema(schema: Any, raw: str) -> Optional[Any]:
    """Parse ``raw`` as JSON, then validate with ``schema``.

    Mirrors :func:`safeParseJsonWithSchema` (``utils/zod-parse.ts``).
    """
    try:
        value = json.loads(raw)
    except Exception:
        return None
    return safe_parse_with_schema(schema, value)


__all__ = [
    "safe_parse_with_schema",
    "safe_parse_json_with_schema",
]
