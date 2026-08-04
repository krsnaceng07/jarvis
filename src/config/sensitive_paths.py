"""jarvis.config.sensitive_paths — config-path redaction classification.

OpenClaw parity: mirrors ``openclaw-main/src/config/sensitive-paths.ts``.
"""
from __future__ import annotations

import re
from typing import List

#: Whitelist suffixes (case-insensitive) that look like secrets but are not.
SENSITIVE_KEY_WHITELIST_SUFFIXES: List[str] = [
    "maxtokens",
    "maxoutputtokens",
    "maxinputtokens",
    "maxcompletiontokens",
    "contexttokens",
    "totaltokens",
    "tokencount",
    "tokenlimit",
    "tokenbudget",
    "passwordFile",
]

#: Pre-normalized whitelist suffixes (lowercase, trimmed).
_NORMALIZED_SENSITIVE_KEY_WHITELIST_SUFFIXES = [s.lower().strip() for s in SENSITIVE_KEY_WHITELIST_SUFFIXES]

#: Patterns that mark a path as sensitive.
SENSITIVE_PATTERNS = [
    re.compile(r"token$", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"api.?key", re.IGNORECASE),
    re.compile(r"encrypt.?key", re.IGNORECASE),
    re.compile(r"private.?key", re.IGNORECASE),
    re.compile(r"serviceaccount(?:ref)?$", re.IGNORECASE),
]


def _is_whitelisted_sensitive_path(path: str) -> bool:
    if not isinstance(path, str):
        return False
    lower = path.strip().lower()
    return any(lower.endswith(suffix) for suffix in _NORMALIZED_SENSITIVE_KEY_WHITELIST_SUFFIXES)


def _matches_sensitive_pattern(path: str) -> bool:
    if not isinstance(path, str):
        return False
    return any(p.search(path) for p in SENSITIVE_PATTERNS)


def _is_local_service_env_value_path(path: str) -> bool:
    if not isinstance(path, str):
        return False
    return "localservice.env." in path.strip().lower()


def is_sensitive_config_path(path: str) -> bool:
    """Return whether a config path's value should be redacted from output.

    Mirrors :func:`isSensitiveConfigPath`
    (``shared/config/sensitive-paths.ts`).
    """
    return (
        _is_local_service_env_value_path(path)
        or (not _is_whitelisted_sensitive_path(path) and _matches_sensitive_pattern(path))
    )


__all__ = [
    "SENSITIVE_KEY_WHITELIST_SUFFIXES",
    "SENSITIVE_PATTERNS",
    "is_sensitive_config_path",
]
