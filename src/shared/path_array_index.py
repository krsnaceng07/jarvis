"""jarvis.shared.path_array_index — config-path array-index parser.

OpenClaw parity: mirrors ``openclaw-main/src/shared/path-array-index.ts``.
"""
from __future__ import annotations

import re

#: Upper bound for config path array indexes to reject impractical sparse writes.
MAX_CONFIG_PATH_ARRAY_INDEX = 100_000

_CANONICAL_ARRAY_INDEX_SEGMENT = re.compile(r"^(0|[1-9]\d*)$")


def parse_config_path_array_index(segment: str):
    """Parse a canonical non-negative array index segment.

    Mirrors :func:`parseConfigPathArrayIndex``
    (``shared/path-array-index.ts``).
    """
    if not isinstance(segment, str) or not _CANONICAL_ARRAY_INDEX_SEGMENT.match(segment):
        return None
    try:
        index = int(segment)
    except ValueError:
        return None
    if not (0 <= index <= MAX_CONFIG_PATH_ARRAY_INDEX):
        return None
    return index


__all__ = ["parse_config_path_array_index", "MAX_CONFIG_PATH_ARRAY_INDEX"]
