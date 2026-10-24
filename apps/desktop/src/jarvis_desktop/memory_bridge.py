"""Memory bridge — host-side wrapper over ``extensions/memory_core``.

OpenClaw-parity memory bridge:
1. Dual persistence: SQLite index (MemoryRuntime) + workspace Markdown files (MEMORY.md, USER.md).
2. Lane 1 deterministic recall:
   - Bootstrap context injection with character bounds (MEMORY.md 20k, USER.md 5k).
   - Dynamic standing intents matching via FTS5 (<standing_intents> block).
   - Dynamic trigger memory injection (<trigger_memories> block).
3. User model directives with in-place supersession in USER.md.
4. Security gating via envelope_scrubber.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
import threading
from typing import Any

from extensions.memory_core.envelope_scrubber import (
    looks_like_envelope_sludge,
    looks_like_prompt_injection,
    sanitize_for_memory_capture,
)
from extensions.memory_core.runtime import MemoryRuntime

# Character budgets matching OpenClaw bootstrap-files.ts
MAX_MEMORY_MD_CHARS = 20_000
MAX_USER_MD_CHARS = 5_000
_MAX_PROMPT_ROWS = 40


def _runtime() -> MemoryRuntime:
    """Return the process-wide memory runtime.

    Honors ``$JARVIS_DATA_DIR``; defaults to canonical path via
    ``resolve_memory_db_path()`` or ``MemoryRuntime.default()``.
    """
    env_dir = os.environ.get("JARVIS_DATA_DIR")
    rt = MemoryRuntime.default()
    if env_dir:
        target_parent = Path(env_dir) / "core"
        if rt._db_path.parent != target_parent:
            rt = MemoryRuntime(target_parent / "memory.sqlite")
    return rt


def resolve_workspace_dir(workspace_dir: Path | str | None = None) -> Path:
    """Resolve active agent workspace directory."""
    if workspace_dir:
        return Path(workspace_dir)
    env_ws = os.environ.get("JARVIS_WORKSPACE")
    if env_ws:
        return Path(env_ws)
    return Path(__file__).resolve().parents[4]


def load_bootstrap_memory(workspace_dir: Path | str | None = None) -> tuple[str, str]:
    """Read MEMORY.md and USER.md from the workspace within bounded character limits.

    Mirrors OpenClaw's bootstrap-files.ts:
    - MEMORY.md capped to 20,000 chars.
    - USER.md capped to 5,000 chars.
    """
    ws = resolve_workspace_dir(workspace_dir)
    mem_file = ws / "MEMORY.md"
    user_file = ws / "USER.md"

    mem_content = ""
    user_content = ""

    if mem_file.is_file():
        try:
            raw = mem_file.read_text(encoding="utf-8").strip()
            mem_content = raw[:MAX_MEMORY_MD_CHARS]
        except Exception as e:
            print(f"[Memory] Failed to read {mem_file}: {e}")

    if user_file.is_file():
        try:
            raw = user_file.read_text(encoding="utf-8").strip()
            user_content = raw[:MAX_USER_MD_CHARS]
        except Exception as e:
            print(f"[Memory] Failed to read {user_file}: {e}")

    return mem_content, user_content


def load_memory() -> dict[str, dict[str, dict[str, str]]]:
    """Return the legacy-shaped memory dict from SQLite.

    Phase 3.5 contract: shape is
    ``{category: {key: {"value": str, "updated": str}}}`` to
    preserve callers' iteration patterns.
    """
    fallback: dict[str, dict[str, dict[str, str]]] = {
        "identity": {},
        "preferences": {},
        "projects": {},
        "relationships": {},
        "wishes": {},
        "notes": {},
    }
    try:
        rt = _runtime()
        rows = rt.recent(limit=_MAX_PROMPT_ROWS * 4)
    except Exception as e:
        print(f"[Memory] bridge load_memory failed: {e}")
        return fallback

    out: dict[str, dict[str, dict[str, str]]] = {
        "identity": {},
        "preferences": {},
        "projects": {},
        "relationships": {},
        "wishes": {},
        "notes": {},
    }
    for r in rows:
        cat = r.get("category", "notes")
        if cat not in out:
            out[cat] = {}
        out[cat][r["key"]] = {
            "value": r["value"],
            "updated": r.get("updated_at", ""),
        }
    return out


def update_memory(memory_update: dict[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    """Apply a category-keyed update to the memory store.

    Updates SQLite and keeps workspace files in sync.
    """
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()

    try:
        for cat, items in memory_update.items():
            if not isinstance(items, dict):
                continue
            for key, entry in items.items():
                if isinstance(entry, dict) and "value" in entry:
                    val = str(entry["value"])
                else:
                    val = str(entry)
                if not val.strip():
                    continue
                save_fact(category=str(cat), key=str(key), value=val)
    except Exception as e:
        print(f"[Memory] bridge update_memory failed: {e}")
    return load_memory()


def save_fact(
    category: str,
    key: str,
    value: str,
    trigger_phrase: str | None = None,
    importance: int | None = None,
    project: str | None = None,
    workspace_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Save an important fact with provenance, security scrubbing, and dual persistence.

    1. Envelope scrubber defense against prompt injection / sludge.
    2. Writes to SQLite with origin='owner'.
    3. Syncs to USER.md (for preferences/identity directives) or MEMORY.md (for facts/notes).
    """
    cleaned = sanitize_for_memory_capture(value)
    if looks_like_envelope_sludge(cleaned) or looks_like_prompt_injection(cleaned):
        print(f"[Memory] ⚠️ Rejected memory capture due to sludge/injection: {cleaned[:60]}")
        return {"status": "rejected", "reason": "security_scrub"}

    # Build annotations if provided
    tags = []
    if trigger_phrase:
        tags.append(f"<!-- trigger: {trigger_phrase} -->")
    if importance is not None:
        tags.append(f"<!-- importance: {importance} -->")
    if project:
        tags.append(f"<!-- project: {project} -->")

    tag_str = f" {' '.join(tags)}" if tags else ""
    full_val = f"{cleaned}{tag_str}"

    ws = resolve_workspace_dir(workspace_dir)
    today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")

    rt = _runtime()
    rt.set(
        key=str(key),
        value=full_val,
        category=str(category),
        origin="owner",
        trigger_phrase=trigger_phrase,
        importance=importance,
        project=project,
    )

    if workspace_dir:
        try:
            local_db = ws / "memory.sqlite"
            if local_db.resolve() != rt._db_path.resolve():
                from extensions.memory_core.runtime import MemoryRuntime

                MemoryRuntime(local_db).set(
                    key=str(key),
                    value=full_val,
                    category=str(category),
                    origin="owner",
                    trigger_phrase=trigger_phrase,
                    importance=importance,
                    project=project,
                )
        except Exception:
            pass

    # Sync to workspace files

    try:
        if category in ("preferences", "identity"):
            # Update USER.md as an imperative directive with in-place supersession
            user_file = ws / "USER.md"
            user_lines = (
                user_file.read_text(encoding="utf-8").splitlines() if user_file.is_file() else []
            )

            # Check if directive for this key already exists and supersede previous active ones
            new_lines = list(user_lines)
            for i, line in enumerate(new_lines):
                stripped = line.strip().lower()
                if stripped.startswith(f"- {key.lower()}:") or stripped.startswith(
                    f"- {key.lower()} :"
                ):
                    if "status: active" in new_lines[i]:
                        new_lines[i] = new_lines[i].replace("status: active", "status: superseded")
                    j = i - 1
                    while j >= 0 and not new_lines[j].strip():
                        j -= 1
                    if j >= 0 and "status: active" in new_lines[j]:
                        new_lines[j] = new_lines[j].replace("status: active", "status: superseded")

            # Ensure header
            if not any(line.strip().startswith("# User") for line in new_lines):
                new_lines.insert(0, "# User\n")

            # Append new active directive
            new_lines.append("")
            new_lines.append(f"<!-- observed: {today} | status: active -->")
            new_lines.append(f"- {key}: {cleaned}{tag_str}")

            user_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        else:
            # Append to MEMORY.md
            mem_file = ws / "MEMORY.md"
            mem_text = mem_file.read_text(encoding="utf-8") if mem_file.is_file() else ""
            if not mem_text.strip():
                mem_text = "# JARVIS Memory\n\n"
            entry_line = f"- {category}/{key}: {cleaned}{tag_str}"
            if entry_line not in mem_text:
                mem_file.write_text(mem_text.rstrip() + "\n" + entry_line + "\n", encoding="utf-8")
    except Exception as e:
        print(f"[Memory] Warning: markdown sync failed ({e})")

    # Dual-Write to LanceDB vector table (Phase 4.1 Hybrid Parity)
    try:
        from extensions.memory_lancedb import upsert_vector_memory

        upsert_vector_memory(category=str(category), key=str(key), value=cleaned)
    except Exception as e:
        print(f"[Memory] Warning: LanceDB vector upsert skipped ({e})")


_backfill_checked = False
_backfill_lock = threading.Lock()


def ensure_lancedb_backfilled(
    force: bool = False,
    workspace_dir: Path | str | None = None,
) -> int:
    """Check LanceDB vector count against SQLite count; trigger backfill if needed.

    Ensures zero-config parity with OpenClaw memory-lancedb: existing SQLite
    memories are lazily vectorized and indexed into LanceDB upon startup.
    """
    global _backfill_checked
    if _backfill_checked and not force:
        return 0

    with _backfill_lock:
        if _backfill_checked and not force:
            return 0
        try:
            from extensions.memory_lancedb import (
                backfill_from_sqlite,
                count_vector_memories,
            )

            if workspace_dir:
                from extensions.memory_core.runtime import MemoryRuntime

                ws = resolve_workspace_dir(workspace_dir)
                rt = MemoryRuntime(ws / "memory.sqlite")
            else:
                rt = _runtime()

            with rt._conn_lock:
                rows = rt._conn.execute(
                    "SELECT key, value, category, updated_at FROM memory"
                ).fetchall()
            sqlite_rows = [dict(r) for r in rows]
            vec_count = count_vector_memories()

            if len(sqlite_rows) > vec_count or force:
                inserted = backfill_from_sqlite(sqlite_rows)
                _backfill_checked = True
                print(f"[Memory] Backfilled {inserted} records from SQLite into LanceDB")
                return inserted

            _backfill_checked = True
            return 0
        except Exception as e:
            print(f"[Memory] LanceDB backfill check failed: {e}")
            _backfill_checked = True
            return 0


def format_memory_for_prompt(
    memory: dict[str, dict[str, dict[str, str]]] | None = None,
    workspace_dir: Path | str | None = None,
    max_user_bytes: int = 5_120,
    max_memory_bytes: int = 20_480,
) -> str:
    """Render memory files and SQLite state as a prompt-injectable string.

    Mirrors OpenClaw bootstrap injection:
    - Injects USER.md directives if available (bounded by max_user_bytes).
    - Injects MEMORY.md curated notes if available (bounded by max_memory_bytes).
    - Injects SQLite recent memory entries as supplement.
    """
    ensure_lancedb_backfilled(workspace_dir=workspace_dir)

    mem_file_content, user_file_content = load_bootstrap_memory(workspace_dir)

    if user_file_content:
        encoded_user = user_file_content.encode("utf-8")
        if len(encoded_user) > max_user_bytes:
            user_file_content = encoded_user[:max_user_bytes].decode("utf-8", errors="ignore")

    if mem_file_content:
        encoded_mem = mem_file_content.encode("utf-8")
        if len(encoded_mem) > max_memory_bytes:
            mem_file_content = encoded_mem[:max_memory_bytes].decode("utf-8", errors="ignore")

    sections: list[str] = []

    if user_file_content:
        sections.append(f"[USER PREFERENCES & DIRECTIVES (USER.md)]\n{user_file_content}\n")

    if mem_file_content:
        sections.append(f"[CURATED CORE MEMORY (MEMORY.md)]\n{mem_file_content}\n")

    if memory is None:
        try:
            memory = load_memory()
        except Exception:
            memory = {}

    # Add SQLite rows if neither file has content, or as compact facts supplement
    if memory and any(memory.values()):
        sqlite_lines = ["[LONG-TERM MEMORY (ACTIVE STATE)]"]
        for cat, items in memory.items():
            if not items:
                continue
            for key, entry in items.items():
                val = entry.get("value", "") if isinstance(entry, dict) else str(entry)
                if not val:
                    continue
                sqlite_lines.append(f"- {cat}/{key}: {val}")
        if len(sqlite_lines) > 1:
            sections.append("\n".join(sqlite_lines))

    if not sections:
        return ""

    sections.append(
        "Use `memory_search(query)` to look up entries; use the "
        "`save_memory` tool to remember new facts the user shares; "
        "use `intent(action='create', ...)` for event-conditioned reminders."
    )
    return "\n\n".join(sections)


async def recall_relevant_memories(
    query: str,
    top_k: int = 4,
    workspace_dir: Path | str | None = None,
) -> str:
    """Recall relevant memories using unified hybrid search and format for active context injection."""
    if not query or not query.strip():
        return ""
    try:
        results = hybrid_search_memory(
            query=query,
            limit=top_k,
            workspace_dir=workspace_dir,
        )
        if not results:
            return ""
        lines: list[str] = []
        for r in results:
            cat = r.get("category", "general")
            key = r.get("key", "")
            val = r.get("value", "")
            if key and val:
                lines.append(f"- {cat}/{key}: {val}")
            elif val:
                lines.append(f"- {val}")
        return "\n".join(lines)
    except Exception as exc:
        print(f"[Memory] recall_relevant_memories failed: {exc}")
        return ""


def get_turn_memory_context(
    inbound_message: str,
    active_projects: list[str] | None = None,
    agent_id: str | None = None,
    channel_id: str | None = None,
    sender_id: str | None = None,
    workspace_dir: Path | str | None = None,
) -> str:
    """Resolve Lane 1 deterministic pre-prompt context:

    1. Standing intents matching the message.
    2. Deterministic trigger memory matching (top 3 hits).
    Returns formatted prepend context.
    """
    if not inbound_message or not inbound_message.strip():
        return ""

    if workspace_dir:
        from extensions.memory_core.runtime import MemoryRuntime

        ws = resolve_workspace_dir(workspace_dir)
        rt = MemoryRuntime(ws / "memory.sqlite")
    else:
        rt = _runtime()
    context_blocks: list[str] = []

    # 1. Standing intents
    try:
        triggered_intents = rt.get_triggered_intents(
            inbound_message=inbound_message,
            agent_id=agent_id,
            channel_id=channel_id,
            sender_id=sender_id,
        )
        if triggered_intents:
            intent_lines = []
            for item in triggered_intents[:3]:
                c_date = str(item.get("created_at", ""))[:10]
                desc = item.get("description", "")
                intent_lines.append(f"Standing intent (created {c_date}): {desc}")
            context_blocks.append(
                "<standing_intents>\n" + "\n".join(intent_lines) + "\n</standing_intents>"
            )
    except Exception as e:
        print(f"[Memory] Standing intents match failed: {e}")

    triggered_keys: set[str] = set()
    # 2. Trigger memory recall
    try:
        triggered_memories = rt.get_triggered_memory(
            message=inbound_message,
            active_projects=active_projects,
            limit=3,
        )
        if triggered_memories:
            mem_lines = []
            for hit in triggered_memories:
                key = hit.get("key", "")
                val = hit.get("value", "")
                triggered_keys.add(key)
                mem_lines.append(f"- {key}: {val}")
            context_blocks.append(
                "<trigger_memories>\n" + "\n".join(mem_lines) + "\n</trigger_memories>"
            )
    except Exception as e:
        print(f"[Memory] Trigger memories match failed: {e}")

    # 3. Hybrid semantic memory recall (LanceDB + SQLite FTS5 RRF)
    try:
        hybrid_hits = hybrid_search_memory(
            query=inbound_message,
            limit=3,
            workspace_dir=workspace_dir,
        )
        semantic_lines = []
        for hit in hybrid_hits:
            key = hit.get("key", "")
            val = hit.get("value", "")
            cat = hit.get("category", "notes")
            if key and key not in triggered_keys and val:
                semantic_lines.append(f"- {cat}/{key}: {val}")
        if semantic_lines:
            context_blocks.append(
                "<relevant_context_memories>\n" + "\n".join(semantic_lines) + "\n</relevant_context_memories>"
            )
    except Exception as e:
        print(f"[Memory] Hybrid semantic recall failed: {e}")

    return "\n\n".join(context_blocks)


def hybrid_search_memory(
    query: str,
    limit: int = 8,
    category: str | None = None,
    workspace_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Hybrid semantic memory retrieval combining SQLite FTS5 (BM25) and LanceDB vector search.

    Uses standard Reciprocal Rank Fusion (RRF) with k=60:
        RRF_Score(d) = 1/(60 + rank_fts) + 1/(60 + rank_vec)

    Returns ranked records with provenance tags ('fts+vector', 'vector', 'fts').
    """
    if not query or not query.strip():
        return []

    # 1. Lexical retrieval (FTS5 BM25 + substring fallback)
    if workspace_dir:
        from extensions.memory_core.runtime import MemoryRuntime

        ws = resolve_workspace_dir(workspace_dir)
        rt = MemoryRuntime(ws / "memory.sqlite")
    else:
        rt = _runtime()

    fts_candidates: list[dict[str, Any]] = []
    try:
        raw_fts = rt.search_ranked(query=query, limit=max(limit * 3, 20))
        if category:
            raw_fts = [r for r in raw_fts if r.get("category") == category]
        fts_candidates = raw_fts
    except Exception as e:
        print(f"[Memory] Lexical search failed: {e}")

    # Map candidate (category, key) -> rank (1-indexed) and data
    fts_ranked: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for idx, item in enumerate(fts_candidates, 1):
        cat = str(item.get("category") or "notes")
        key = str(item.get("key") or "")
        if key:
            fts_ranked[(cat, key)] = (idx, item)

    # 2. Dense vector similarity search via LanceDB
    vec_candidates: list[dict[str, Any]] = []
    try:
        from extensions.memory_lancedb import search_vector_memory

        vec_candidates = search_vector_memory(
            query=query,
            limit=max(limit * 3, 20),
            category=category,
        )
    except Exception as e:
        print(f"[Memory] Vector search failed: {e}")

    vec_ranked: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for idx, item in enumerate(vec_candidates, 1):
        cat = str(item.get("category") or "notes")
        key = str(item.get("key") or "")
        if key:
            vec_ranked[(cat, key)] = (idx, item)

    # 3. Reciprocal Rank Fusion (k=60)
    rrf_k = 60.0
    all_keys = set(fts_ranked.keys()) | set(vec_ranked.keys())
    scored_items: list[dict[str, Any]] = []

    for cat, key in all_keys:
        in_fts = (cat, key) in fts_ranked
        in_vec = (cat, key) in vec_ranked

        rank_fts = fts_ranked[(cat, key)][0] if in_fts else None
        rank_vec = vec_ranked[(cat, key)][0] if in_vec else None

        score = 0.0
        if rank_fts is not None:
            score += 1.0 / (rrf_k + rank_fts)
        if rank_vec is not None:
            score += 1.0 / (rrf_k + rank_vec)

        if in_fts and in_vec:
            source = "fts+vector"
            val = fts_ranked[(cat, key)][1].get("value") or vec_ranked[(cat, key)][1].get("value")
        elif in_vec:
            source = "vector"
            val = vec_ranked[(cat, key)][1].get("value")
        else:
            source = "fts"
            val = fts_ranked[(cat, key)][1].get("value")

        scored_items.append(
            {
                "id": f"{cat}:{key}",
                "category": cat,
                "key": key,
                "value": val or "",
                "score": round(score, 6),
                "source": source,
                "rank_fts": rank_fts,
                "rank_vec": rank_vec,
            }
        )

    # Sort descending by RRF score
    scored_items.sort(key=lambda x: x["score"], reverse=True)
    return scored_items[:limit]


__all__ = [
    "ensure_lancedb_backfilled",
    "format_memory_for_prompt",
    "get_turn_memory_context",
    "hybrid_search_memory",
    "load_bootstrap_memory",
    "load_memory",
    "recall_relevant_memories",
    "save_fact",
    "update_memory",
]
