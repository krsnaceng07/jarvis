"""jarvis_sdk.memory_host_query — public query facade.

OpenClaw parity: mirrors the query facade re-export in
``packages/memory-host-sdk/src/query.ts`` (2 LOC). Re-exports the
keyword extraction helpers from ``memory_host_query_expansion``.
"""

from __future__ import annotations

from .memory_host_query_expansion import (
    ExtractKeywordsOptions,
    extract_keywords,
    is_query_stop_word_token,
)

__all__ = [
    "ExtractKeywordsOptions",
    "extract_keywords",
    "is_query_stop_word_token",
]
