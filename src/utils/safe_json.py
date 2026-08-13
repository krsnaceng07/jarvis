"""jarvis.utils.safe_json — defensive JSON stringify for diagnostics.

OpenClaw parity: mirrors ``openclaw-main/src/utils/safe-json.ts``.

Public surface:

- :func:`safe_json_stringify`
"""
from __future__ import annotations

import base64
import json
from typing import Any, Optional


def _safe_replacer(key: str, value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_replacer(str(i), v) for i, v in enumerate(value)]
    if isinstance(value, dict):
        return {str(k): _safe_replacer(str(k), v) for k, v in value.items()}
    if callable(value) and not isinstance(value, type):
        return "[Function]"
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            encoded = base64.b64encode(bytes(value)).decode("ascii")
            return {"type": "bytes", "data": encoded}
        except Exception:
            return "[Unserializable]"
    if isinstance(value, BaseException):
        return {"name": value.__class__.__name__, "message": str(value)}
    return str(value)


def safe_json_stringify(value: Any) -> Optional[str]:
    """Safely stringify diagnostic values, preserving bigint/errors/functions.

    Mirrors :func:`safeJsonStringify` (``utils/safe-json.ts``).
    """
    try:
        return json.dumps(
            _safe_replacer("", value),
            default=lambda obj: _safe_replacer("", obj),
        )
    except Exception:
        return None


__all__ = ["safe_json_stringify"]

