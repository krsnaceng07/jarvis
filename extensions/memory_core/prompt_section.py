"""Prompt section — the memory prompt builder.

Mirrors OpenClaw's ``extensions/memory-core/src/prompt-section.ts``.
The host calls ``build(config, ctx)`` to get the memory section that
goes into the agent's system prompt. The function is intentionally
side-effect-free (no I/O) so the host can cache the result.
"""
from __future__ import annotations

from typing import Any


def build(config: dict[str, Any] | None = None, ctx: dict[str, Any] | None = None) -> str:
    """Render the memory prompt section.

    Phase 2 ships a short header + the operator's pinned facts. A
    full FTS/semantic search integration lands in Phase 2.5.
    """
    ctx = ctx or {}
    config = config or {}
    cfg = config.get("memory", {}) if isinstance(config, dict) else {}
    if cfg.get("enabled") is False:
        return ""

    name = ctx.get("agent_id", "JARVIS")
    body = (
        f"# {name} Memory\n"
        "\n"
        "You have access to two memory tools:\n"
        "  - `memory_search(query)` — find entries by substring.\n"
        "  - `memory_get(key)` — fetch a single entry by key.\n"
        "\n"
        "Use them at the start of any task that might rely on prior "
        "work, decisions, or preferences. Before answering questions "
        "about people, dates, or projects, ALWAYS call `memory_search` "
        "first to surface relevant context.\n"
        "\n"
        "Write new memories with the `save_memory` core tool (the "
        "host routes it to this plugin's SQLite store).\n"
    )
    return body


def flush_plan(ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a flush plan (pre-compaction). Phase 2 is a no-op stub."""
    return {
        "should_flush": False,
        "reason": "memory_core: Phase 2 ships substring search only; flush deferred.",
    }


__all__ = ["build", "flush_plan"]
