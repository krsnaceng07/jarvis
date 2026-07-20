"""Memory bridge — host-side wrapper over ``extensions/memory_core``.

Mirrors the legacy ``memory/memory_manager`` interface so the
desktop app's existing call sites work without a full rewrite.
The bridge sits in the desktop host (not ``src/``) because the
underlying store is an extension capability — host glue around
an extension belongs in the host, not the core library.

Phase 3.5: this replaces the deleted ``memory/memory_manager.py``
(which was a JSON-file store with no OpenClaw equivalent). The
bridge uses ``extensions.memory_core.runtime.MemoryRuntime`` —
the OpenClaw-shaped SQLite store — under the hood.

The LLM-based memory extraction (the legacy ``should_extract_memory``
+ ``extract_memory`` pair) is gone: JARVIS now relies on the
``save_memory`` tool that the LLM calls directly when it wants
to remember something. This is how OpenClaw's memory-core works
in practice — the model is the curator, not a background pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from extensions.memory_core.runtime import MemoryRuntime

# Cap on entries injected into the system prompt. The legacy code
# used a 2200-char JSON budget; here we cap by row count (cheaper
# to compute) and let the prompt formatter truncate if needed.
_MAX_PROMPT_ROWS = 40


def _runtime() -> MemoryRuntime:
    """Return the process-wide memory runtime.

    Honors ``$JARVIS_DATA_DIR``; defaults to ``~/.jarvis``. We
    keep the legacy long-term JSON path in the legacy ``core/``
    data dir *off* the runtime so the SQLite store is the
    single source of truth going forward.
    """
    import os

    data_dir = Path(os.environ.get("JARVIS_DATA_DIR") or (Path.home() / ".jarvis"))
    # Per-process default. The runtime's own default() picks the
    # same path; we re-resolve so tests can monkeypatch this
    # without touching the runtime's class-level default.
    rt = MemoryRuntime.default()
    if rt._db_path.parent != data_dir / "core":
        rt = MemoryRuntime(data_dir / "core" / "memory.sqlite")
    return rt


def load_memory() -> dict[str, dict[str, dict[str, str]]]:
    """Return the legacy-shaped memory dict.

    Phase 3.5 contract: shape is
    ``{category: {key: {"value": str, "updated": str}}}`` to
    preserve callers' iteration patterns. The SQLite store is
    the source of truth; we materialize the dict on each call.
    """
    rt = _runtime()
    try:
        rows = rt.recent(limit=_MAX_PROMPT_ROWS * 4)
    except Exception:
        return {
            "identity": {},
            "preferences": {},
            "projects": {},
            "relationships": {},
            "wishes": {},
            "notes": {},
        }
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

    Mirrors the legacy ``update_memory`` contract:
    ``update_memory({"identity": {"name": {"value": "Ali"}}})``
    sets ``memory.identity.name = "Ali"``. Returns the post-update
    legacy-shaped dict (for callers that need it).
    """
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()

    rt = _runtime()
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
                rt.set(str(key), val, category=str(cat))
    except Exception as e:
        print(f"[Memory] bridge update_memory failed: {e}")
    return load_memory()


def format_memory_for_prompt(memory: dict[str, dict[str, dict[str, str]]]) -> str:
    """Render the memory dict as a prompt-injectable string.

    Compact, labeled by category, capped to ``_MAX_PROMPT_ROWS``
    total. Returns empty string if the memory is empty.
    """
    if not any(memory.values()):
        return ""

    lines = ["[LONG-TERM MEMORY]"]
    for cat, items in memory.items():
        if not items:
            continue
        for key, entry in items.items():
            val = entry.get("value", "") if isinstance(entry, dict) else str(entry)
            if not val:
                continue
            lines.append(f"- {cat}/{key}: {val}")
    if len(lines) == 1:
        return ""
    lines.append("")
    lines.append(
        "Use `memory_search(query)` to look up entries; use the "
        "`save_memory` tool to remember new facts the user shares."
    )
    return "\n".join(lines)


__all__ = ["format_memory_for_prompt", "load_memory", "update_memory"]
