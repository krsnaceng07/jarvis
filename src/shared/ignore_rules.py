"""jarvis.shared.ignore_rules — focused minimal ignore-file rule loader.

OpenClaw parity: mirrors ``openclaw-main/src/shared/ignore-rules.ts``.

The OpenClaw source uses the ``node-ignore`` library and patches its
prototype at module load. This focused minimal port exposes a parser that
materializes ignore patterns from a single ignore file's content, plus
the path-normalization helpers OpenClaw callers rely on.

For full node-ignore-compatible behavior, callers should provide a matcher
via the optional ``matcher`` parameter to :func:`add_ignore_rules`.
"""
from __future__ import annotations

import os
import posixpath
import re
from typing import Callable, List, Optional, Set

#: Recognized ignore file names.
IGNORE_FILE_NAMES = (".gitignore", ".ignore", ".fdignore")

#: Upper bound for ignore file size.
IGNORE_FILE_MAX_BYTES = 4 * 1024 * 1024

#: Upper bound for total pattern count.
IGNORE_MATCHER_MAX_PATTERNS = 20_000

#: Upper bound for single pattern length.
IGNORE_PATTERN_MAX_CHARS = 16 * 1024

#: Upper bound for total pattern characters.
IGNORE_MATCHER_MAX_PATTERN_CHARS = IGNORE_FILE_MAX_BYTES

#: Sentinel for "ignore file too large to safely parse".
OVERSIZED_IGNORE_FILE = "OVERSIZED_IGNORE_FILE"

#: Sentinel for "ignore file too complex (too many patterns)".
COMPLEX_IGNORE_FILE = "COMPLEX_IGNORE_FILE"


def to_posix_path(path_value: str) -> str:
    """Normalize path separators to POSIX forward slashes.

    Mirrors ``toPosixPath`` (``shared/ignore-rules.ts``).
    """
    if path_value is None:
        return path_value
    return path_value.replace("\\", "/")


def _normalize_literal_subtree_path(pathname: str) -> str:
    posix = to_posix_path(pathname)
    return posix[:-1] if posix.endswith("/") else posix


def _set_contains_literal_subtree(pathname: str, subtrees: Set[str]) -> bool:
    for subtree in subtrees:
        if not subtree:
            continue
        if pathname == subtree or pathname.startswith(f"{subtree}/"):
            return True
    return False


def _is_in_literal_subtree(pathname: str, *, excluded: Set[str], case_folded: Set[str]) -> bool:
    normalized = _normalize_literal_subtree_path(pathname)
    return (
        _set_contains_literal_subtree(normalized, excluded)
        or _set_contains_literal_subtree(normalized.lower(), case_folded)
    )


def _prefix_ignore_pattern(line: str, prefix: str) -> str:
    trimmed = line.strip()
    if not trimmed or (trimmed.startswith("#") and not trimmed.startswith("\\#")):
        return ""
    negated = line.startswith("!")
    pattern = line[1:] if negated else line
    anchored = pattern.startswith("/")
    normalized = pattern[1:] if anchored else pattern
    match_pattern = re.sub(r" +$", "", normalized)
    if (
        prefix
        and not anchored
        and "/" not in match_pattern[:-1]
    ):
        depth_glob = "**/"
    else:
        depth_glob = ""
    prefixed = f"{prefix}{depth_glob}{normalized}"
    return f"!{prefixed}" if negated else prefixed


def parse_ignore_patterns(
    content: str,
    prefix: str = "",
    *,
    max_patterns: int = IGNORE_MATCHER_MAX_PATTERNS,
    max_chars: int = IGNORE_MATCHER_MAX_PATTERN_CHARS,
):
    """Parse ignore-file content into a list of prefixed patterns.

    Returns :data:`COMPLEX_IGNORE_FILE` when the budget is exceeded so
    callers can fail closed.

    Mirrors the internal ``parseIgnorePatterns`` helper
    (``shared/ignore-rules.ts``).
    """
    patterns: List[str] = []
    pattern_chars = 0
    line_start = 0
    while line_start <= len(content):
        newline = content.find("\n", line_start)
        line_end = len(content) if newline == -1 else newline
        content_end = line_end - 1 if (
            line_end > line_start and content[line_end - 1] == "\r"
        ) else line_end
        pattern = _prefix_ignore_pattern(content[line_start:content_end], prefix)
        if pattern:
            if len(pattern) > IGNORE_PATTERN_MAX_CHARS or len(patterns) >= max_patterns:
                return COMPLEX_IGNORE_FILE
            pattern_chars += len(pattern)
            if pattern_chars > max_chars:
                return COMPLEX_IGNORE_FILE
            patterns.append(pattern)
        if newline == -1:
            break
        line_start = newline + 1
    return {"patterns": patterns, "chars": pattern_chars}


def read_ignore_file_content(file_path: str) -> Optional[str]:
    """Read an ignore file as utf-8, returning None on errors.

    Mirrors ``readIgnoreFileContent`` (``shared/ignore-rules.ts``).
    """
    try:
        size = os.path.getsize(file_path)
    except OSError:
        return None
    if size > IGNORE_FILE_MAX_BYTES:
        return OVERSIZED_IGNORE_FILE
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


# Minimal matcher interface: a callable that returns True when a path is ignored.
IgnoreMatcher = Callable[[str], bool]


def _build_subtree_matcher(
    subtrees: Set[str], case_folded: Set[str]
) -> IgnoreMatcher:
    def _matcher(pathname: str) -> bool:
        return _is_in_literal_subtree(pathname, excluded=subtrees, case_folded=case_folded)
    return _matcher


def add_ignore_rules(
    dir_path: str,
    root_dir: str,
    matcher: Optional[IgnoreMatcher] = None,
    *,
    ignore_case: bool = True,
) -> IgnoreMatcher:
    """Add nested ignore-file rules to a matcher using paths relative to ``root_dir``.

    Returns the matcher (or a new one) including all rules from
    ``.gitignore``/``.ignore``/``.fdignore`` files in ``dir_path``.

    Focused minimal port of :func:`addIgnoreRules`
    (``shared/ignore-rules.ts``).
    """
    excluded: Set[str] = set()
    case_folded: Set[str] = set()
    if not dir_path or not root_dir:
        if matcher is not None:
            return matcher
        return _build_subtree_matcher(excluded, case_folded)

    relative_dir = posixpath.relpath(to_posix_path(dir_path), to_posix_path(root_dir))
    prefix = f"{relative_dir}/" if relative_dir and relative_dir != "." else ""

    for filename in IGNORE_FILE_NAMES:
        ignore_path = os.path.join(dir_path, filename)
        if not os.path.isfile(ignore_path):
            continue
        content = read_ignore_file_content(ignore_path)
        if content == OVERSIZED_IGNORE_FILE:
            if ignore_case:
                case_folded.add(_normalize_literal_subtree_path(prefix).lower())
            else:
                excluded.add(_normalize_literal_subtree_path(prefix))
            break
        if content is None:
            continue
        parsed = parse_ignore_patterns(content, prefix)
        if parsed == COMPLEX_IGNORE_FILE:
            if ignore_case:
                case_folded.add(_normalize_literal_subtree_path(prefix).lower())
            else:
                excluded.add(_normalize_literal_subtree_path(prefix))
            break
        if parsed["patterns"]:
            for p in parsed["patterns"]:
                if matcher is not None and matcher(p):
                    continue
                if ignore_case:
                    case_folded.add(_normalize_literal_subtree_path(p).lower())
                else:
                    excluded.add(_normalize_literal_subtree_path(p))

    def _combined(pathname: str) -> bool:
        if _is_in_literal_subtree(pathname, excluded=excluded, case_folded=case_folded):
            return True
        if matcher is not None:
            return matcher(pathname)
        return False

    return _combined


__all__ = [
    "IGNORE_FILE_NAMES",
    "IGNORE_FILE_MAX_BYTES",
    "IGNORE_MATCHER_MAX_PATTERNS",
    "IGNORE_PATTERN_MAX_CHARS",
    "IGNORE_MATCHER_MAX_PATTERN_CHARS",
    "OVERSIZED_IGNORE_FILE",
    "COMPLEX_IGNORE_FILE",
    "IgnoreMatcher",
    "to_posix_path",
    "parse_ignore_patterns",
    "read_ignore_file_content",
    "add_ignore_rules",
]
