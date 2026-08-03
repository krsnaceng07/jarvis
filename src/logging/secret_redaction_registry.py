"""jarvis.logging.secret_redaction_registry — register resolved secrets for redaction.

OpenClaw parity: mirrors
``openclaw-main/src/logging/secret-redaction-registry.ts``.

Public surface:

- :func:`register_secret_value_for_redaction`
- :func:`is_secret_value_registered_for_redaction`
- :func:`has_registered_secret_values_for_redaction`
- :func:`redact_registered_secret_values`
- :func:`reset_secret_redaction_registry_for_test`
"""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from typing import Callable, Optional


MIN_SECRET_VALUE_LENGTH = 6
MAX_SECRET_VALUES = 512

#: Process-local bounded registry of exact secret values.
_registered_values: "OrderedDict[str, bool]" = OrderedDict()
_compiled_matcher: Optional[re.Pattern] = None
_first_chars: set = set()


def _escape_regex(value: str) -> str:
    return re.sub(r"[.*+?^${}()|[\]\\]", lambda m: "\\" + m.group(0), value)


def _rebuild_probe() -> None:
    global _first_chars, _compiled_matcher
    _first_chars = {value[0] for value in _registered_values.keys() if value}
    _compiled_matcher = None


def _register_one_secret_value(value: str) -> None:
    if value in _registered_values:
        # Move to end so bounded eviction prefers newer secrets.
        _registered_values.pop(value, None)
        _registered_values[value] = True
        return
    _registered_values[value] = True
    if len(_registered_values) > MAX_SECRET_VALUES:
        _registered_values.pop(next(iter(_registered_values)), None)
    _rebuild_probe()


def register_secret_value_for_redaction(value: str) -> None:
    """Register ``value`` so logs redact occurrences of it.

    Mirrors :func:`registerSecretValueForRedaction`
    (``logging/secret-redaction-registry.ts``).
    """
    if not isinstance(value, str) or len(value) < MIN_SECRET_VALUE_LENGTH:
        return
    # Mirror OpenClaw's URL/JSON-escape pre-registration.
    encoded = None
    try:
        encoded = (
            __import__("urllib.parse").quote(value, safe="")
        )
    except Exception:
        encoded = None
    if encoded and encoded != value:
        _register_one_secret_value(encoded)
    try:
        json_escaped = json.dumps(value)[1:-1]
    except (TypeError, ValueError):
        json_escaped = None
    if json_escaped and json_escaped != value:
        _register_one_secret_value(json_escaped)
    _register_one_secret_value(value)


def is_secret_value_registered_for_redaction(value: str) -> bool:
    """Return whether ``value`` is in the registry.

    Mirrors :func:`isSecretValueRegisteredForRedaction`
    (``logging/secret-redaction-registry.ts``).
    """
    return isinstance(value, str) and value in _registered_values


def has_registered_secret_values_for_redaction() -> bool:
    """Return whether the registry has any registered values.

    Mirrors :func:`hasRegisteredSecretValuesForRedaction`
    (``logging/secret-redaction-registry.ts``).
    """
    return len(_registered_values) > 0


def redact_registered_secret_values(
    text: str,
    mask: Callable[[str], str],
) -> str:
    """Replace registered values in ``text`` using ``mask``.

    Mirrors :func:`redactRegisteredSecretValues`
    (``logging/secret-redaction-registry.ts``).
    """
    global _compiled_matcher
    if not text or not _registered_values:
        return text
    if not any(ch in text for ch in _first_chars):
        return text
    if _compiled_matcher is None:
        keys = sorted(_registered_values.keys(), key=lambda s: -len(s))
        pattern = "|".join(_escape_regex(k) for k in keys)
        if pattern:
            _compiled_matcher = re.compile(pattern)
    if _compiled_matcher is None:
        return text
    return _compiled_matcher.sub(lambda m: mask(m.group(0)), text)


def reset_secret_redaction_registry_for_test() -> None:
    """Clear the registry (test helper)."""
    global _compiled_matcher, _first_chars
    _registered_values.clear()
    _first_chars = set()
    _compiled_matcher = None


__all__ = [
    "register_secret_value_for_redaction",
    "is_secret_value_registered_for_redaction",
    "has_registered_secret_values_for_redaction",
    "redact_registered_secret_values",
    "reset_secret_redaction_registry_for_test",
]
