"""runtime — MemoryDB: LanceDB-backed vector store + in-memory fallback.

OpenClaw parity: mirrors ``extensions/memory-lancedb/lancedb-store.ts``.

Defines ``MemoryDB``, the class that backs the
``memory_recall`` / ``memory_store`` / ``memory_forget``
tools. Internally we abstract over two backends:

1. **LanceDB** (preferred) — uses the lazily-loaded
   ``lancedb`` module. The native dep is heavy and may not
   be available on every platform, so callers detect
   availability with ``is_lancedb_available()``.
2. **In-memory numpy fallback** — used in tests and on
   platforms where ``lancedb`` fails to load. Same public
   interface, no on-disk state, suitable for unit tests.

Both backends implement the same ``MemoryStore`` protocol
(``store / search / list / query / delete / count / close``)
and both observe the same agent scoping rules from
``lancedb_schema``.
"""

from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

from .lancedb_runtime import (
    LanceDbModule,
    is_lancedb_available,
    load_lancedb_module,
)
from .lancedb_schema import (
    MEMORY_AGENT_ID_COLUMN,
    MEMORY_TABLE_NAME,
    has_agent_scope_column,
    is_valid_memory_id,
    legacy_memory_schema_error,
    memory_agent_predicate,
    quote_lance_sql_string,
)

_log = logging.getLogger("extensions.memory_lancedb.runtime")


# ── Domain types ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """One row in the memory table.

    Mirrors OpenClaw's ``MemoryEntry``.
    """

    id: str
    text: str
    vector: list[float]
    importance: float
    category: str
    created_at: int


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    """A single vector search hit.

    Mirrors OpenClaw's ``MemorySearchResult``.
    """

    entry: MemoryEntry
    score: float


# Mirrors ``MEMORY_QUERY_COLUMNS`` in OpenClaw.
MEMORY_QUERY_COLUMNS: tuple[str, ...] = (
    "id",
    "text",
    "importance",
    "category",
    "createdAt",
)


# ── MemoryStore protocol ────────────────────────────────────────


class MemoryStore(ABC):
    """Storage backend contract.

    Mirrors the public surface of OpenClaw's ``MemoryDB``.
    """

    @abstractmethod
    def store(
        self,
        agent_id: str,
        entry: MemoryEntryInput,
    ) -> MemoryEntry: ...

    @abstractmethod
    def search(
        self,
        agent_id: str,
        vector: list[float],
        limit: int = 5,
        min_score: float = 0.5,
    ) -> list[MemorySearchResult]: ...

    @abstractmethod
    def list(
        self,
        agent_id: str,
        limit: int | None = None,
        *,
        order_by_created_at: bool = False,
    ) -> list[MemoryEntry]: ...

    @abstractmethod
    def query(
        self,
        agent_id: str,
        *,
        columns: Iterable[str] = MEMORY_QUERY_COLUMNS,
        where: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    def delete(self, agent_id: str, memory_id: str) -> bool: ...

    @abstractmethod
    def count(self, agent_id: str) -> int: ...

    @abstractmethod
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class MemoryEntryInput:
    """Subset of ``MemoryEntry`` the caller supplies to ``store``."""

    text: str
    vector: list[float]
    importance: float
    category: str


# ── In-memory backend (test + fallback) ─────────────────────────


class InMemoryStore(MemoryStore):
    """Pure-Python vector store backed by a list + numpy.

    Uses only the standard library ``math`` module for
    distances so we don't pull ``numpy`` as a hard dep. The
    store is process-local; tests get hermetic state by
    instantiating one per test.
    """

    def __init__(self, vector_dim: int) -> None:
        self._vector_dim = vector_dim
        self._rows: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def store(
        self,
        agent_id: str,
        entry: MemoryEntryInput,
    ) -> MemoryEntry:
        if len(entry.vector) != self._vector_dim:
            raise ValueError(f"vector dim {len(entry.vector)} != store dim {self._vector_dim}")
        full = MemoryEntry(
            id=str(uuid.uuid4()),
            text=entry.text,
            vector=list(entry.vector),
            importance=entry.importance,
            category=entry.category,
            created_at=int(time.time() * 1000),
        )
        with self._lock:
            self._rows.append(
                {
                    "id": full.id,
                    "text": full.text,
                    "vector": full.vector,
                    "importance": full.importance,
                    "category": full.category,
                    "createdAt": full.created_at,
                    MEMORY_AGENT_ID_COLUMN: agent_id,
                }
            )
        return full

    def search(
        self,
        agent_id: str,
        vector: list[float],
        limit: int = 5,
        min_score: float = 0.5,
    ) -> list[MemorySearchResult]:
        if len(vector) != self._vector_dim:
            raise ValueError(f"vector dim {len(vector)} != store dim {self._vector_dim}")
        with self._lock:
            rows = [r for r in self._rows if r[MEMORY_AGENT_ID_COLUMN] == agent_id]
        scored: list[MemorySearchResult] = []
        for row in rows:
            distance = _l2_distance(vector, row["vector"])
            score = 1.0 / (1.0 + distance)
            if score >= min_score:
                scored.append(
                    MemorySearchResult(
                        entry=MemoryEntry(
                            id=row["id"],
                            text=row["text"],
                            vector=list(row["vector"]),
                            importance=row["importance"],
                            category=row["category"],
                            created_at=int(row["createdAt"]),
                        ),
                        score=score,
                    )
                )
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:limit]

    def list(
        self,
        agent_id: str,
        limit: int | None = None,
        *,
        order_by_created_at: bool = False,
    ) -> list[MemoryEntry]:
        with self._lock:
            rows = [r for r in self._rows if r[MEMORY_AGENT_ID_COLUMN] == agent_id]
        entries = [
            MemoryEntry(
                id=r["id"],
                text=r["text"],
                vector=list(r["vector"]),
                importance=r["importance"],
                category=r["category"],
                created_at=int(r["createdAt"]),
            )
            for r in rows
        ]
        if order_by_created_at:
            entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries if limit is None else entries[:limit]

    def query(
        self,
        agent_id: str,
        *,
        columns: Iterable[str] = MEMORY_QUERY_COLUMNS,
        where: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        cols = list(columns)
        with self._lock:
            rows = [r for r in self._rows if r[MEMORY_AGENT_ID_COLUMN] == agent_id]
        # The in-memory backend only supports agent-scoping here.
        # A non-agent ``where`` clause would require parsing — we
        # refuse it loudly so callers don't silently miss rows.
        if where is not None and where.strip() and where != memory_agent_predicate(agent_id):
            raise NotImplementedError(
                "InMemoryStore.query() does not support custom WHERE clauses; "
                "use the LanceDB backend for that."
            )
        out: list[dict[str, Any]] = []
        for r in rows:
            row_view: dict[str, Any] = {"id": r["id"]}
            for c in cols:
                if c == "id":
                    continue
                row_view[c] = r.get(c)
            out.append(row_view)
        return out if limit is None else out[:limit]

    def delete(self, agent_id: str, memory_id: str) -> bool:
        if not is_valid_memory_id(memory_id):
            raise ValueError(f"Invalid memory ID format: {memory_id}")
        with self._lock:
            before = len(self._rows)
            self._rows = [
                r
                for r in self._rows
                if not (r[MEMORY_AGENT_ID_COLUMN] == agent_id and r["id"] == memory_id)
            ]
            return len(self._rows) < before

    def count(self, agent_id: str) -> int:
        with self._lock:
            return sum(1 for r in self._rows if r[MEMORY_AGENT_ID_COLUMN] == agent_id)

    def close(self) -> None:
        with self._lock:
            self._rows.clear()


def _l2_distance(a: list[float], b: list[float]) -> float:
    """Return the L2 distance between two equal-length vectors.

    Mirrors the distance metric LanceDB returns as ``_distance``.
    """
    if len(a) != len(b):
        raise ValueError("vector length mismatch")
    return math.sqrt(sum((x - y) * (x - y) for x, y in zip(a, b, strict=False)))


# ── LanceDB backend ─────────────────────────────────────────────


class LanceDBStore(MemoryStore):
    """Vector store backed by the ``lancedb`` package.

    Mirrors OpenClaw's ``MemoryDB``. We lazy-init the table on
    first call; the connection and table are cached for the
    lifetime of the store. ``close()`` releases both.
    """

    SCHEMA_SENTINEL_ID = "__schema__"

    def __init__(
        self,
        db_path: str,
        vector_dim: int,
        storage_options: Mapping[str, str] | None = None,
    ) -> None:
        if not db_path:
            raise ValueError("LanceDBStore requires a non-empty db_path")
        if vector_dim < 1:
            raise ValueError("vector_dim must be a positive integer")
        self._db_path = db_path
        self._vector_dim = vector_dim
        self._storage_options = dict(storage_options or {})
        self._lock = threading.Lock()
        self._init_lock = threading.Lock()
        self._init_promise: list[Any] = []  # holds the init Future-like
        self._conn: Any | None = None
        self._table: Any | None = None

    @property
    def db_path(self) -> str:
        return self._db_path

    def _ensure_initialized(self) -> Any:
        if self._table is not None:
            return self._table
        with self._init_lock:
            if self._table is not None:
                return self._table
            if self._init_promise:
                return self._init_promise[0]
            promise: list[Any] = []
            self._init_promise.append(promise)
        try:
            table = self._do_initialize()
        except BaseException:
            with self._init_lock:
                self._init_promise.clear()
            raise
        promise.append(table)
        with self._init_lock:
            self._table = table
        return table

    def _do_initialize(self) -> Any:
        module: LanceDbModule = load_lancedb_module()
        connect_opts: dict[str, Any] = {}
        if self._storage_options:
            connect_opts["storage_options"] = dict(self._storage_options)
        db = module.connect(self._db_path, **connect_opts)
        try:
            table_names = db.table_names()
            table: Any
            if MEMORY_TABLE_NAME in table_names:
                table = db.open_table(MEMORY_TABLE_NAME)
                # ``table.schema`` is a property (returns the
                # current pyarrow Schema); calling it like a
                # method raises ``'Schema' object is not
                # callable``. Older versions of LanceDB exposed
                # ``.schema()`` as a method; the two are
                # equivalent and the property form is what
                # ``lancedb >= 0.10`` ships.
                table_schema = table.schema
                if not has_agent_scope_column(table_schema):
                    raise legacy_memory_schema_error()
            else:
                sentinel = {
                    "id": self.SCHEMA_SENTINEL_ID,
                    "text": "",
                    "vector": [0.0] * self._vector_dim,
                    "importance": 0.0,
                    "category": "other",
                    "createdAt": 0,
                    MEMORY_AGENT_ID_COLUMN: self.SCHEMA_SENTINEL_ID,
                }
                table = db.create_table(MEMORY_TABLE_NAME, [sentinel])
                table.delete(f"id = {quote_lance_sql_string(self.SCHEMA_SENTINEL_ID)}")
            self._conn = db
            return table
        except BaseException:
            try:
                db.close()
            except Exception as exc:
                _log.debug("lancedb close on init failure: %s", exc)
            raise

    def store(
        self,
        agent_id: str,
        entry: MemoryEntryInput,
    ) -> MemoryEntry:
        if len(entry.vector) != self._vector_dim:
            raise ValueError(f"vector dim {len(entry.vector)} != store dim {self._vector_dim}")
        table = self._ensure_initialized()
        full = MemoryEntry(
            id=str(uuid.uuid4()),
            text=entry.text,
            vector=list(entry.vector),
            importance=entry.importance,
            category=entry.category,
            created_at=int(time.time() * 1000),
        )
        stored = {
            "id": full.id,
            "text": full.text,
            "vector": full.vector,
            "importance": full.importance,
            "category": full.category,
            "createdAt": full.created_at,
            MEMORY_AGENT_ID_COLUMN: agent_id,
        }
        table.add([stored])
        return full

    def search(
        self,
        agent_id: str,
        vector: list[float],
        limit: int = 5,
        min_score: float = 0.5,
    ) -> list[MemorySearchResult]:
        if len(vector) != self._vector_dim:
            raise ValueError(f"vector dim {len(vector)} != store dim {self._vector_dim}")
        table = self._ensure_initialized()
        # LanceDB >= 0.10 merged ``vector_search`` into ``search``
        # (the method now auto-detects vector vs full-text
        # queries). Older versions still have ``vector_search``
        # as a separate method; the merged form works on
        # both via the ``.where(...).limit(...)`` builder.
        rows = (
            table.search(vector)
            .where(memory_agent_predicate(agent_id))
            .limit(limit)
            .to_list()
        )
        out: list[MemorySearchResult] = []
        for row in rows:
            distance = float(row.get("_distance", 0.0) or 0.0)
            score = 1.0 / (1.0 + distance)
            if score < min_score:
                continue
            out.append(
                MemorySearchResult(
                    entry=MemoryEntry(
                        id=str(row["id"]),
                        text=str(row["text"]),
                        vector=[float(x) for x in row["vector"]],
                        importance=float(row.get("importance", 0.0) or 0.0),
                        category=str(row.get("category", "other") or "other"),
                        created_at=int(row.get("createdAt", 0) or 0),
                    ),
                    score=score,
                )
            )
        return out

    def list(
        self,
        agent_id: str,
        limit: int | None = None,
        *,
        order_by_created_at: bool = False,
    ) -> list[MemoryEntry]:
        table = self._ensure_initialized()
        query = (
            table.query()
            .where(memory_agent_predicate(agent_id))
            .select(["id", "text", "importance", "category", "createdAt"])
        )
        if not order_by_created_at and limit is not None:
            query = query.limit(limit)
        rows = query.to_list()
        entries = [
            MemoryEntry(
                id=str(r["id"]),
                text=str(r["text"]),
                vector=[],
                importance=float(r.get("importance", 0.0) or 0.0),
                category=str(r.get("category", "other") or "other"),
                created_at=int(r.get("createdAt", 0) or 0),
            )
            for r in rows
        ]
        if order_by_created_at:
            entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries if limit is None else entries[:limit]

    def query(
        self,
        agent_id: str,
        *,
        columns: Iterable[str] = MEMORY_QUERY_COLUMNS,
        where: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        table = self._ensure_initialized()
        cols = list(columns)
        predicate = where if where else memory_agent_predicate(agent_id)
        query = table.query().where(predicate).select(cols)
        if limit is not None:
            query = query.limit(limit)
        return query.to_list()

    def delete(self, agent_id: str, memory_id: str) -> bool:
        if not is_valid_memory_id(memory_id):
            raise ValueError(f"Invalid memory ID format: {memory_id}")
        table = self._ensure_initialized()
        predicate = (
            f"({memory_agent_predicate(agent_id)}) AND "
            f"(id = {quote_lance_sql_string(memory_id)})"
        )
        if table.count_rows(predicate) == 0:
            return False
        table.delete(predicate)
        return True

    def count(self, agent_id: str) -> int:
        table = self._ensure_initialized()
        return int(table.count_rows(memory_agent_predicate(agent_id)))

    def close(self) -> None:
        with self._init_lock:
            try:
                if self._table is not None:
                    self._table.close()
            except Exception as exc:
                _log.debug("lancedb table close failed: %s", exc)
            try:
                if self._conn is not None:
                    self._conn.close()
            except Exception as exc:
                _log.debug("lancedb connection close failed: %s", exc)
            self._table = None
            self._conn = None
            self._init_promise.clear()


# ── Public facade (mirrors OpenClaw's `MemoryDB` class) ────────


@dataclass
class MemoryDB:
    """Public facade. Mirrors OpenClaw's ``MemoryDB`` class.

    Internally holds either a ``LanceDBStore`` or an
    ``InMemoryStore`` depending on availability and the
    ``force_in_memory`` flag. The host never sees the
    backend; only the public ``MemoryDB`` methods.
    """

    db_path: str
    vector_dim: int
    storage_options: Mapping[str, str] = field(default_factory=dict)
    force_in_memory: bool = False
    _backend: MemoryStore | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        backend: MemoryStore
        if self.force_in_memory or not is_lancedb_available():
            backend = InMemoryStore(self.vector_dim)
        else:
            try:
                backend = LanceDBStore(
                    self.db_path,
                    self.vector_dim,
                    self.storage_options,
                )
            except RuntimeError as exc:
                # LanceDB refused to load (e.g. unsupported native
                # platform). Fall back so the plugin still works.
                _log.warning("memory-lancedb: falling back to in-memory store: %s", exc)
                backend = InMemoryStore(self.vector_dim)
        self._backend = backend

    @property
    def backend(self) -> MemoryStore:
        if self._backend is None:  # pragma: no cover - defensive
            self._backend = InMemoryStore(self.vector_dim)
        return self._backend

    def store(
        self,
        agent_id: str,
        entry: MemoryEntryInput,
    ) -> MemoryEntry:
        return self.backend.store(agent_id, entry)

    def search(
        self,
        agent_id: str,
        vector: list[float],
        limit: int = 5,
        min_score: float = 0.5,
    ) -> list[MemorySearchResult]:
        return self.backend.search(agent_id, vector, limit, min_score)

    def list(
        self,
        agent_id: str,
        limit: int | None = None,
        *,
        order_by_created_at: bool = False,
    ) -> list[MemoryEntry]:
        return self.backend.list(agent_id, limit, order_by_created_at=order_by_created_at)

    def query(
        self,
        agent_id: str,
        *,
        columns: Iterable[str] = MEMORY_QUERY_COLUMNS,
        where: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.backend.query(agent_id, columns=columns, where=where, limit=limit)

    def delete(self, agent_id: str, memory_id: str) -> bool:
        return self.backend.delete(agent_id, memory_id)

    def count(self, agent_id: str) -> int:
        return self.backend.count(agent_id)

    def close(self) -> None:
        if self._backend is not None:
            self._backend.close()
            self._backend = None


__all__ = [
    "MEMORY_QUERY_COLUMNS",
    "InMemoryStore",
    "LanceDBStore",
    "MemoryDB",
    "MemoryEntry",
    "MemoryEntryInput",
    "MemorySearchResult",
    "MemoryStore",
]
