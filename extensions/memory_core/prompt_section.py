"""Prompt section — system-prompt injection for the memory capability.

Mirrors OpenClaw's ``extensions/memory-core/src/prompt-section.ts``.
The host calls ``build(build_options)`` to get the memory
section that goes into the agent's system prompt.

The function is intentionally side-effect-free (no I/O) so
the host can cache the result. The host also consults
``flush_plan(build_options)`` before a compaction to decide
whether the agent should flush unsaved memory.

Phase 4.0 ships a compact header + a list of recent entries.
The OpenClaw host may also pass ``build_options`` containing
``agent_id``, ``workspace_dir``, and a ``recently_mentioned``
list; we honor those for parity.
"""

from __future__ import annotations

from typing import Any

from jarvis_sdk import MemoryFlushPlan

# Capped prompt size for the memory section. Mirrors the
# OpenClaw default of 2200 characters (see
# ``DEFAULT_QMD_LIMITS.maxInjectedChars`` in the OpenClaw
# backend-config). Phase 4.0 ships the SQLite fallback; the
# limit is enforced in characters rather than tokens (the
# host token-estimates the section on the way in).
_MAX_PROMPT_CHARS = 2_200


def build(build_options: dict[str, Any] | None = None) -> str:
    """Render the memory prompt section.

    Mirrors OpenClaw's ``buildPromptSection``. Returns a short
    header + the operator's pinned facts; capped at
    ``_MAX_PROMPT_CHARS`` characters.

    Parameters
    ----------
    build_options
        Optional dict. Honored keys:
          - ``agent_id``: filter to one agent's memory
          - ``workspace_dir``: the workspace root for resolving
            ``memory/*.md`` files (Phase 4.1+)
          - ``recently_mentioned``: list of keys to surface first
    """
    from .runtime import MemoryRuntime

    options = build_options or {}
    agent_id = options.get("agent_id")
    recently_mentioned = options.get("recently_mentioned") or []

    try:
        runtime = MemoryRuntime.default()
        rows = runtime.recent(limit=40)
        if agent_id and not rows:
            rows = runtime.search_text("", limit=10)
    except Exception:
        return ""

    if not rows:
        return ""

    # Sort: recently-mentioned first, then by recency.
    recency_index = {r["key"]: i for i, r in enumerate(rows)}
    rows.sort(
        key=lambda r: (
            0 if r["key"] in set(recently_mentioned) else 1,
            recency_index.get(r["key"], 0),
        )
    )

    lines: list[str] = ["[JARVIS MEMORY]"]
    used = len(lines[0]) + 1
    for r in rows:
        key = r["key"]
        value = r["value"]
        category = r.get("category", "general")
        line = f"- {category}/{key}: {value}"
        if used + len(line) + 1 > _MAX_PROMPT_CHARS:
            break
        lines.append(line)
        used += len(line) + 1

    if len(lines) == 1:
        return ""
    lines.append(
        "\nUse `memory_search(query)` to find specific entries; use "
        "the `save_memory` core tool to remember new facts the user "
        "shares."
    )
    return "\n".join(lines)


def flush_plan(build_options: dict[str, Any] | None = None) -> MemoryFlushPlan:
    """Decide whether to flush before compaction.

    Mirrors OpenClaw's ``buildMemoryFlushPlan``. The Phase 4.0
    SQLite fallback doesn't need a pre-compaction flush
    (compaction is a host-level concern; memory is on disk).
    LanceDB + qmd backends may override this with their own
    flush policy.
    """
    return MemoryFlushPlan(
        should_flush=False,
        reason="memory_core (SQLite fallback): no pre-compaction flush needed",
    )


__all__ = ["build", "flush_plan"]
