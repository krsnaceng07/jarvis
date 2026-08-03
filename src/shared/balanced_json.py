"""jarvis.shared.balanced_json — balanced JSON fragment scanner.

OpenClaw parity: mirrors ``openclaw-main/src/shared/balanced-json.ts``.

Public surface:

- :func:`extract_balanced_json_prefix`
- :func:`extract_balanced_json_fragments`
- :data:`BalancedJsonFragment`
"""
from __future__ import annotations

from typing import Iterable, List, Optional


class BalancedJsonFragment:
    """One balanced JSON object/array fragment found inside arbitrary text."""

    def __init__(self, json: str, start_index: int, end_index: int) -> None:
        self.json = json
        self.start_index = start_index
        self.end_index = end_index

    def to_dict(self) -> dict:
        return {
            "json": self.json,
            "startIndex": self.start_index,
            "endIndex": self.end_index,
        }


_CLOSING_DELIMITER = {"{": "}", "[": "]"}


def _is_opener(char: Optional[str], openers: Iterable[str]) -> bool:
    return char in openers and char in ("{", "[")


def extract_balanced_json_prefix(
    raw: str,
    openers: Optional[Iterable[str]] = None,
) -> Optional[BalancedJsonFragment]:
    """Extract the first balanced JSON object/array prefix in ``raw``.

    Mirrors :func:`extractBalancedJsonPrefix` (``shared/balanced-json.ts``).
    """
    if not isinstance(raw, str):
        return None
    opener_set = list(openers) if openers is not None else ["{", "["]
    start = 0
    while start < len(raw) and not _is_opener(raw[start], opener_set):
        start += 1
    if start >= len(raw):
        return None
    stack: List[str] = []
    in_string = False
    escaped = False
    for i in range(start, len(raw)):
        char = raw[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if _is_opener(char, opener_set):
            stack.append(char)
            continue
        top = stack[-1] if stack else None
        if top and char == _CLOSING_DELIMITER.get(top):
            stack.pop()
            if not stack:
                return BalancedJsonFragment(
                    json=raw[start : i + 1],
                    start_index=start,
                    end_index=i,
                )
    return None


def extract_balanced_json_fragments(
    raw: str,
    openers: Optional[Iterable[str]] = None,
) -> List[BalancedJsonFragment]:
    """Extract every balanced JSON object/array fragment from ``raw``.

    Mirrors :func:`extractBalancedJsonFragments` (``shared/balanced-json.ts``).
    """
    if not isinstance(raw, str):
        return []
    fragments: List[BalancedJsonFragment] = []
    offset = 0
    while offset < len(raw):
        fragment = extract_balanced_json_prefix(raw[offset:], openers)
        if fragment is None:
            break
        fragments.append(
            BalancedJsonFragment(
                json=fragment.json,
                start_index=offset + fragment.start_index,
                end_index=offset + fragment.end_index,
            )
        )
        offset += fragment.end_index + 1
    return fragments


__all__ = [
    "BalancedJsonFragment",
    "extract_balanced_json_prefix",
    "extract_balanced_json_fragments",
]
