"""jarvis_learning.datasets.canonicalization — deterministic serialization.

Provides RFC 8785 style canonical JSON byte encoding:
- UTF-8 representation
- Alphabetically sorted keys
- Normalized NFC Unicode
- Explicit integer nanosecond timestamps (no float ambiguity)
- Strict types (no NaN, Inf, or non-finite numbers)
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any


def _normalize_obj(obj: Any) -> Any:
    """Recursively normalize objects for canonical serialization."""
    if obj is None or isinstance(obj, (bool, int)):
        return obj
    if isinstance(obj, float):
        if not (float("-inf") < obj < float("inf")):
            raise ValueError(f"Non-finite float not permitted in canonical serialization: {obj}")
        # Normalize -0.0 to 0.0
        return 0.0 if obj == 0.0 else round(obj, 8)
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, dict):
        return {
            unicodedata.normalize("NFC", str(k)): _normalize_obj(v)
            for k, v in sorted(
                obj.items(), key=lambda item: unicodedata.normalize("NFC", str(item[0]))
            )
        }
    if isinstance(obj, (list, tuple)):
        return [_normalize_obj(item) for item in obj]
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return _normalize_obj(obj.to_dict())
    if hasattr(obj, "__dict__"):
        return _normalize_obj(vars(obj))
    return unicodedata.normalize("NFC", str(obj))


def canonical_json_bytes(data: Any) -> bytes:
    """Return deterministic canonical UTF-8 bytes for data."""
    normalized = _normalize_obj(data)
    encoded_str = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return encoded_str.encode("utf-8")


def canonical_hash(data: Any) -> str:
    """Compute SHA-256 hex digest of canonical JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()
