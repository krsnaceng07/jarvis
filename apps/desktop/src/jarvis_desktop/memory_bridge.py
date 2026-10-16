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

    return {"status": "saved", "category": category, "key": key, "value": cleaned}


def format_memory_for_prompt(
    memory: dict[str, dict[str, dict[str, str]]],
    workspace_dir: Path | str | None = None,
) -> str:
    """Render memory files and SQLite state as a prompt-injectable string.

    Mirrors OpenClaw bootstrap injection:
    - Injects USER.md directives if available.
    - Injects MEMORY.md curated notes if available.
    - Injects SQLite recent memory entries as supplement.
    """
    mem_file_content, user_file_content = load_bootstrap_memory(workspace_dir)

    sections: list[str] = []

    if user_file_content:
        sections.append(f"[USER PREFERENCES & DIRECTIVES (USER.md)]\n{user_file_content}\n")

    if mem_file_content:
        sections.append(f"[CURATED CORE MEMORY (MEMORY.md)]\n{mem_file_content}\n")

    # Add SQLite rows if neither file has content, or as compact facts supplement
    if any(memory.values()):
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
                mem_lines.append(f"- {key}: {val}")
            context_blocks.append(
                "<trigger_memories>\n" + "\n".join(mem_lines) + "\n</trigger_memories>"
            )
    except Exception as e:
        print(f"[Memory] Trigger memories match failed: {e}")

    return "\n\n".join(context_blocks)


__all__ = [
    "format_memory_for_prompt",
    "get_turn_memory_context",
    "load_bootstrap_memory",
    "load_memory",
    "save_fact",
    "update_memory",
]
