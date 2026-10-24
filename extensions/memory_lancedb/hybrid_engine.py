"""hybrid_engine — Local Zero-Cost LanceDB + FastEmbed Hybrid Vector Store.

OpenClaw-parity hybrid memory component for JARVIS:
- FastEmbed BAAI/bge-small-en-v1.5 (384-dimensions, CPU ONNX runtime, <12ms).
- LanceDB local vector database stored at ~/.jarvis/core/lancedb/ (table: memories_vec).
- Thread-safe upsert, vector similarity search, and SQLite-to-LanceDB backfill.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import math
import os
import threading
from pathlib import Path
from typing import Any

_log = logging.getLogger("extensions.memory_lancedb.hybrid_engine")

TABLE_NAME = "memories_vec"
VECTOR_DIM = 384


class LocalEmbeddingEngine:
    """Local, zero-API-cost embedding provider using FastEmbed ONNX runtime."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name
        self._model: Any | None = None
        self._dims: int = VECTOR_DIM
        self._lock = threading.Lock()

    def _get_model(self) -> Any | None:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(model_name=self.model_name)
                return self._model
            except Exception as e:
                _log.warning(
                    "FastEmbed init failed, using deterministic local embedding fallback: %s", e
                )
                return None

    def embed(self, text: str) -> list[float]:
        """Embed a single text string into a 384-dim normalized vector."""
        if not text or not text.strip():
            return [0.0] * self._dims

        model = self._get_model()
        if model is not None:
            try:
                embeddings = list(model.embed([text]))
                if embeddings and len(embeddings) > 0:
                    v = embeddings[0]
                    if hasattr(v, "tolist"):
                        return v.tolist()
                    return [float(x) for x in v]
            except Exception as e:
                _log.warning("FastEmbed embed call failed (%s); using fallback", e)

        return self._fallback_embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple text strings in batch."""
        if not texts:
            return []
        model = self._get_model()
        if model is not None:
            try:
                embeddings = list(model.embed(texts))
                out: list[list[float]] = []
                for e in embeddings:
                    if hasattr(e, "tolist"):
                        out.append(e.tolist())
                    else:
                        out.append([float(x) for x in e])
                return out
            except Exception as e:
                _log.warning("FastEmbed batch failed: %s", e)
        return [self._fallback_embed(t) for t in texts]

    def _fallback_embed(self, text: str) -> list[float]:
        """Deterministic hash-based bag-of-words pseudo-embedding for testing/offline resilience."""
        vec = [0.0] * self._dims
        words = text.lower().split()
        if not words:
            vec[0] = 1.0
            return vec
        for w in words:
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dims
            sign = 1.0 if ((h >> 8) & 1) else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            return [x / norm for x in vec]
        vec[0] = 1.0
        return vec


class LanceDBHybridEngine:
    """LanceDB vector store backed by ~/.jarvis/core/lancedb/ with table memories_vec."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        embedder: LocalEmbeddingEngine | None = None,
    ) -> None:
        if db_path is None:
            env_dir = os.environ.get("JARVIS_LANCEDB_DIR") or os.environ.get("JARVIS_DATA_DIR")
            if env_dir:
                p = Path(env_dir)
                self.db_dir = p / "core" / "lancedb" if not str(p).endswith("lancedb") else p
            else:
                self.db_dir = Path.home() / ".jarvis" / "core" / "lancedb"
        else:
            self.db_dir = Path(db_path)

        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or LocalEmbeddingEngine()
        self._lock = threading.Lock()
        self._table: Any | None = None
        self._in_memory_records: dict[str, dict[str, Any]] = {}
        self._use_in_memory: bool = False

    def _get_table(self) -> Any | None:
        if self._table is not None:
            return self._table
        if self._use_in_memory:
            return None

        with self._lock:
            if self._table is not None:
                return self._table
            try:
                import lancedb

                db = lancedb.connect(str(self.db_dir))
                table_names: list[str] = []
                try:
                    if hasattr(db, "list_tables"):
                        lt = db.list_tables()
                        table_names = lt.tables if hasattr(lt, "tables") else list(lt)
                    elif hasattr(db, "table_names"):
                        table_names = list(db.table_names())
                except Exception:
                    table_names = []

                if TABLE_NAME in table_names:
                    self._table = db.open_table(TABLE_NAME)
                else:
                    sample = [
                        {
                            "id": "__sentinel__",
                            "category": "notes",
                            "key": "__sentinel__",
                            "value": "",
                            "text": "",
                            "vector": [0.0] * VECTOR_DIM,
                            "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
                        }
                    ]
                    tbl = db.create_table(TABLE_NAME, sample)
                    tbl.delete("id = '__sentinel__'")
                    self._table = tbl
                return self._table
            except Exception as e:
                _log.warning("LanceDB connection failed (%s); using in-memory vector store", e)
                self._use_in_memory = True
                return None

    def upsert(self, category: str, key: str, value: str) -> bool:
        """Upsert a memory record: embeds f'[{category}] {key}: {value}' and stores in LanceDB."""
        doc_id = f"{category}:{key}"
        text = f"[{category}] {key}: {value}"
        vector = self.embedder.embed(text)
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        record = {
            "id": doc_id,
            "category": category,
            "key": key,
            "value": value,
            "text": text,
            "vector": vector,
            "updated_at": now_iso,
        }

        table = self._get_table()
        if table is not None:
            with self._lock:
                try:
                    table.merge_insert(
                        "id"
                    ).when_matched_update_all().when_not_matched_insert_all().execute([record])
                    return True
                except Exception as e:
                    _log.warning(
                        "LanceDB merge_insert failed (%s); writing to in-memory fallback", e
                    )

        with self._lock:
            self._in_memory_records[doc_id] = record
            return True

    def search(
        self,
        query: str,
        limit: int = 10,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Vector similarity search in LanceDB. Returns ranked results with distance."""
        if not query or not query.strip():
            return []

        query_vec = self.embedder.embed(query)
        table = self._get_table()
        if table is not None:
            with self._lock:
                try:
                    q = table.search(query_vec)
                    if category:
                        safe_cat = category.replace("'", "''")
                        q = q.where(f"category = '{safe_cat}'")
                    hits = q.limit(limit).to_list()
                    results: list[dict[str, Any]] = []
                    for h in hits:
                        results.append(
                            {
                                "id": h.get("id"),
                                "category": h.get("category"),
                                "key": h.get("key"),
                                "value": h.get("value"),
                                "distance": float(h.get("_distance", 1.0)),
                                "updated_at": h.get("updated_at", ""),
                            }
                        )
                    return results
                except Exception as e:
                    _log.warning("LanceDB search failed (%s); falling back to in-memory search", e)

        # In-memory vector distance search fallback
        with self._lock:
            candidates = list(self._in_memory_records.values())

        if category:
            candidates = [c for c in candidates if c.get("category") == category]

        scored: list[dict[str, Any]] = []
        for c in candidates:
            vec = c.get("vector", [])
            dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(query_vec, vec, strict=False)))
            scored.append(
                {
                    "id": c.get("id"),
                    "category": c.get("category"),
                    "key": c.get("key"),
                    "value": c.get("value"),
                    "distance": dist,
                    "updated_at": c.get("updated_at", ""),
                }
            )
        scored.sort(key=lambda x: x["distance"])
        return scored[:limit]

    def backfill_from_sqlite(self, sqlite_rows: list[dict[str, Any]]) -> int:
        """One-time / startup backfill from SQLite rows into LanceDB vector store."""
        if not sqlite_rows:
            return 0

        table = self._get_table()
        existing_ids: set[str] = set()

        if table is not None:
            with self._lock:
                try:
                    df = table.search().select(["id"]).limit(10000).to_arrow()
                    existing_ids = set(df["id"].to_pylist())
                except Exception:
                    pass

        with self._lock:
            existing_ids.update(self._in_memory_records.keys())

        records_to_insert: list[dict[str, Any]] = []
        for row in sqlite_rows:
            cat = str(row.get("category") or "notes")
            key = str(row.get("key") or "")
            val = str(row.get("value") or "")
            if not key or not val:
                continue
            doc_id = f"{cat}:{key}"
            if doc_id in existing_ids:
                continue

            text = f"[{cat}] {key}: {val}"
            vec = self.embedder.embed(text)
            records_to_insert.append(
                {
                    "id": doc_id,
                    "category": cat,
                    "key": key,
                    "value": val,
                    "text": text,
                    "vector": vec,
                    "updated_at": str(
                        row.get("updated_at") or datetime.datetime.now(datetime.UTC).isoformat()
                    ),
                }
            )

        if not records_to_insert:
            return 0

        if table is not None:
            with self._lock:
                try:
                    table.add(records_to_insert)
                    return len(records_to_insert)
                except Exception as e:
                    _log.warning("LanceDB table.add batch failed (%s)", e)

        with self._lock:
            for r in records_to_insert:
                self._in_memory_records[r["id"]] = r
        return len(records_to_insert)

    def count(self) -> int:
        """Return total number of vector records in memories_vec."""
        table = self._get_table()
        if table is not None:
            with self._lock:
                try:
                    return table.count_rows()
                except Exception:
                    pass
        with self._lock:
            return len(self._in_memory_records)

    def clear(self) -> None:
        """Clear all records from memories_vec (useful for tests)."""
        table = self._get_table()
        if table is not None:
            with self._lock:
                try:
                    table.delete("id != ''")
                except Exception:
                    pass
        with self._lock:
            self._in_memory_records.clear()


# ── Global Module-level Singleton & Convenience APIs ───────────────

_default_engine: LanceDBHybridEngine | None = None
_engine_lock = threading.Lock()


def get_hybrid_engine(db_path: str | Path | None = None) -> LanceDBHybridEngine:
    """Return the global or custom-path LanceDBHybridEngine singleton."""
    global _default_engine
    if db_path is not None:
        return LanceDBHybridEngine(db_path=db_path)
    if _default_engine is not None:
        return _default_engine
    with _engine_lock:
        if _default_engine is not None:
            return _default_engine
        _default_engine = LanceDBHybridEngine()
        return _default_engine


def upsert_vector_memory(category: str, key: str, value: str) -> bool:
    """Embed and upsert memory record into LanceDB table."""
    return get_hybrid_engine().upsert(category=category, key=key, value=value)


def search_vector_memory(
    query: str,
    limit: int = 10,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Perform vector similarity search over LanceDB memories."""
    return get_hybrid_engine().search(query=query, limit=limit, category=category)


def backfill_from_sqlite(sqlite_rows: list[dict[str, Any]]) -> int:
    """Backfill memories from SQLite into LanceDB."""
    return get_hybrid_engine().backfill_from_sqlite(sqlite_rows)


def count_vector_memories() -> int:
    """Count records in LanceDB."""
    return get_hybrid_engine().count()
