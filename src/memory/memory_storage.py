"""jarvis_sdk.memory_storage — memory storage interface.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/types.ts``'s
``MemorySearchManager``, ``MemorySearchResult``, ``MemorySource``.

Used by ``memory-core`` and ``memory-lancedb`` to provide a
uniform search interface over heterogeneous backends
(builtin, qmd, lancedb).

Architecture
============
OpenClaw's storage interface is async-first (Node callbacks).
The Python port keeps the shape but exposes a thin sync
wrapper: ``MemorySearchManager.search(agent_id, query)`` returns
a list of ``MemorySearchResult``. Backends implement the
abstract base class.

Parity
======
- ``MemorySource`` is a ``str`` enum: ``"memory" | "wiki" | "sessions"``.
- ``MemorySearchResult`` is a frozen dataclass: ``id``, ``path``,
  ``start_line``, ``end_line``, ``score``, ``source``, ``text``,
  ``citation``.
- ``MemorySearchManager`` is an abstract base class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

# Source identifiers (mirrors OpenClaw's ``MemorySource``).
SOURCE_MEMORY = "memory"
SOURCE_WIKI = "wiki"
SOURCE_SESSIONS = "sessions"
SOURCE_ALL = "all"

VALID_SOURCES = frozenset({SOURCE_MEMORY, SOURCE_WIKI, SOURCE_SESSIONS, SOURCE_ALL})


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    """A single search hit. Mirrors OpenClaw's ``MemorySearchResult``."""

    id: str
    path: str
    start_line: int
    end_line: int
    score: float
    source: str  # one of VALID_SOURCES
    text: str
    citation: str | None = None


class MemorySearchManager(ABC):
    """Abstract search interface. Mirrors OpenClaw's ``MemorySearchManager``.

    Backends (builtin, lancedb, qmd) implement ``search`` and
    ``close``. The host owns the lifecycle: ``open()`` creates
    one manager per agent, ``close()`` releases resources.
    """

    @abstractmethod
    def search(
        self,
        agent_id: str,
        query: str,
        *,
        max_results: int = 4,
        min_score: float = 0.0,
        source: str = SOURCE_MEMORY,
    ) -> list[MemorySearchResult]: ...

    @abstractmethod
    def get(
        self,
        agent_id: str,
        path: str,
        *,
        from_line: int = 1,
        lines: int | None = None,
        source: str = SOURCE_MEMORY,
    ) -> dict[str, Any] | None: ...

    @abstractmethod
    def close(self) -> None: ...


__all__ = [
    "SOURCE_ALL",
    "SOURCE_MEMORY",
    "SOURCE_SESSIONS",
    "SOURCE_WIKI",
    "VALID_SOURCES",
    "MemorySearchManager",
    "MemorySearchResult",
]
