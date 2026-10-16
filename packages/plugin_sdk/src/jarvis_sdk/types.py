"""Minimal TypedDicts for common provider/catalog shapes.

These are intentionally small, only including fields used by the
registration surface so static checkers can validate names without
requiring full runtime classes from the host.
"""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict

JSON = Dict[str, Any]


class MediaUnderstandingProvider(TypedDict, total=False):
    id: str
    capabilities: List[str]
    default_models: Dict[str, Any]
    auto_priority: Dict[str, Any]
    transcribe_audio: Any
    metadata: Dict[str, Any]


class SpeechProvider(TypedDict, total=False):
    id: str
    name: str
    aliases: List[str]
    auto_select_order: int
    default_timeout_ms: int
    formats: List[str]
    metadata: Dict[str, Any]


class CompactionProvider(TypedDict, total=False):
    id: str
    compact: Any


class MemoryEmbeddingProvider(TypedDict, total=False):
    id: str
    provider: Any
