"""src.infra.exec_approvals_allowlist - Allowlist pattern matching.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-allowlist-pattern.ts``
"""

import os
import re
import sys


GLOB_REGEX_CACHE_LIMIT = 512
_glob_regex_cache: dict[str, re.Pattern[str]] = {}


def _normalize_lowercase_string_or_empty(value: str) -> str:
    return value.strip().lower()


def expand_home_prefix(value: str) -> str:
    if value.startswith("~"):
        return os.path.expanduser(value)
    return value


def _normalize_match_target(value: str) -> str:
    if sys.platform == "win32":
        stripped = re.sub(r"^\\\\\[\?\.]\\\\", "", value)
        return _normalize_lowercase_string_or_empty(stripped.replace("\\", "/"))
    normalized = value.replace("\\", "/")
    if sys.platform == "darwin":
        if normalized == "/private/var":
            return "/var"
        if normalized.startswith("/private/var/"):
            return normalized[len("/private") :]
    return normalized


def _try_realpath(value: str) -> str | None:
    try:
        return os.path.realpath(value)
    except Exception:
        return None


def _has_dot_path_segment(value: str) -> bool:
    segments = value.replace("\\", "/").split("/")
    return any(segment in (".", "..") for segment in segments)


def _normalize_dot_path_segments(value: str) -> str:
    normalized = os.path.normpath(value)
    return _normalize_match_target(normalized)


def _compile_glob_regex(pattern: str) -> re.Pattern[str]:
    cache_key = f"{sys.platform}:{pattern}"
    if cache_key in _glob_regex_cache:
        return _glob_regex_cache[cache_key]

    regex = "^"
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                regex += ".*"
                i += 2
                continue
            regex += "[^/]*"
            i += 1
            continue
        if ch == "?":
            regex += "[^/]"
            i += 1
            continue
        regex += re.escape(ch)
        i += 1
    regex += "$"

    flags = re.IGNORECASE if sys.platform == "win32" else 0
    compiled = re.compile(regex, flags)

    if len(_glob_regex_cache) >= GLOB_REGEX_CACHE_LIMIT:
        _glob_regex_cache.clear()
    _glob_regex_cache[cache_key] = compiled
    return compiled


def matches_exec_allowlist_pattern(pattern: str, target: str) -> bool:
    trimmed = pattern.strip()
    if not trimmed:
        return False

    expanded = expand_home_prefix(trimmed) if trimmed.startswith("~") else trimmed
    has_wildcard = bool(re.search(r"[*?]", expanded))

    normalized_pattern = expanded
    normalized_target = target

    if sys.platform == "win32" and not has_wildcard:
        normalized_pattern = _try_realpath(expanded) or expanded
        normalized_target = _try_realpath(target) or target

    normalized_pattern = _normalize_match_target(normalized_pattern)
    normalized_target = _normalize_match_target(normalized_target)

    # Normalize only the target. Glob patterns are operator-authored strings, and
    # normalizing them can change wildcard structure such as `*/..`.
    if has_wildcard and _has_dot_path_segment(normalized_target):
        normalized_target = _normalize_dot_path_segments(normalized_target)

    compiled_regex = _compile_glob_regex(normalized_pattern)
    return bool(compiled_regex.search(normalized_target))
