"""MemoryCorePlugin — Phase 4 OpenClaw parity.

Mirrors OpenClaw's ``extensions/memory-core/`` plugin
(simplified port). Provides:

  - **Tools:** ``memory_search`` (substring + memory triggers)
    + ``memory_get`` (exact excerpt read).
  - **Memory capability:** registered via
    ``api.register_memory_capability`` with ``prompt_builder`` +
    ``flush_plan_resolver`` + ``runtime`` + ``public_artifacts``.
  - **Slash command:** ``/memory list|count|search``.
  - **Doctor contract:** migrate legacy JARVIS memory formats.

Phase 4.0 ships the SQLite fallback backend (Phase 2's
``MemoryRuntime``). LanceDB + semantic search are Phase 4.1
(via the ``memory_lancedb`` extension). Both plug into the
shared ``MemorySearchManager`` interface from the SDK so the
host doesn't care which backend is active.

OpenClaw parity
==============
- Tool schemas: ``memory_search`` accepts ``query``,
  ``maxResults``, ``minScore``, ``corpus``. ``memory_get``
  accepts ``path``, ``from``, ``lines``, ``corpus``. The
  descriptions mirror OpenClaw's verbatim.
- Prompt section: built from the active ``MemorySearchManager``
  via the registered ``MemoryPromptSectionBuilder``.
- Flush plan: returns ``should_flush=False`` for the SQLite
  fallback (LanceDB has its own flush policy).
- Capture gating: ``memory_search`` and the ``save_memory``
  host tool both consult ``MEMORY_TRIGGERS`` +
  ``looks_like_envelope_sludge`` before persisting.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from jarvis_sdk import Err, Ok, Result, ToolDecl, ToolParam, ToolPlugin

from .envelope_scrubber import (
    MEMORY_TRIGGERS,
    looks_like_envelope_sludge,
    looks_like_prompt_injection,
    sanitize_for_memory_capture,
)

if TYPE_CHECKING:
    from .runtime import MemoryRuntime

_log = logging.getLogger("extensions.memory_core")

MEMORY_SEARCH_TOOL = ToolDecl(
    name="memory_search",
    description=(
        "Substring + memory-trigger search over MEMORY.md + "
        "memory/*.md (and any indexed session transcripts). "
        "Required recall step before answering questions about "
        "prior work, decisions, dates, people, preferences, or "
        "todos. `corpus=memory` restricts hits to indexed memory "
        "files. Returns the top-K matching entries with paths "
        "and excerpt lines."
    ),
    parameters=[
        ToolParam(
            name="query",
            type="string",
            description="Substring (or memory trigger phrase) to search for.",
            required=True,
        ),
        ToolParam(
            name="maxResults",
            type="integer",
            description="Maximum number of hits (default 4).",
            required=False,
        ),
        ToolParam(
            name="minScore",
            type="number",
            description="Minimum relevance score in [0, 1] (default 0).",
            required=False,
        ),
        ToolParam(
            name="corpus",
            type="string",
            description=(
                "One of 'memory' | 'wiki' | 'all' | 'sessions'. "
                "Default 'memory' (built-in SQLite only)."
            ),
            required=False,
        ),
    ],
)

MEMORY_GET_TOOL = ToolDecl(
    name="memory_get",
    description=(
        "Safe exact excerpt read from MEMORY.md or memory/*.md. "
        "Returns a bounded excerpt with truncation info when more "
        "content exists."
    ),
    parameters=[
        ToolParam(
            name="path",
            type="string",
            description="Path to the memory file (relative to the workspace).",
            required=True,
        ),
        ToolParam(
            name="from",
            type="integer",
            description="1-based start line (default 1).",
            required=False,
        ),
        ToolParam(
            name="lines",
            type="integer",
            description="Number of lines to read (default 20).",
            required=False,
        ),
        ToolParam(
            name="corpus",
            type="string",
            description=("One of 'memory' | 'wiki' | 'all'. Default 'memory'."),
            required=False,
        ),
    ],
)


class MemoryCorePlugin(ToolPlugin):
    """Phase 4 OpenClaw-shaped memory plugin.

    Wraps the SQLite-backed ``MemoryRuntime`` and exposes the
    two OpenClaw-parity tools. The plugin is a thin layer —
    all storage lives in ``runtime.py``; the prompt section
    lives in ``prompt_section.py``; the security gating lives
    in ``envelope_scrubber.py``.
    """

    def __init__(self) -> None:
        self._tools = [MEMORY_SEARCH_TOOL, MEMORY_GET_TOOL]

    def init(self, ctx: Any) -> None:
        """Lifecycle hook — mirrors ``Plugin.init``.

        Phase 4.0 doesn't need any per-instance state (the
        underlying ``MemoryRuntime`` is a process-wide singleton).
        Reserved for Phase 4.1 (LanceDB warmup) and Phase 4.2
        (active-memory recall warmup).
        """
        return

    @property
    def tools(self) -> list[ToolDecl]:
        return self._tools

    async def call(self, name: str, args: dict[str, Any]) -> Result[str]:
        # Lazy import keeps plugin entry fast; the SQLite runtime
        # pulls in stdlib only (no third-party deps).
        from .runtime import MemoryRuntime

        runtime = MemoryRuntime.default()
        try:
            if name == "memory_search":
                return self._search(args, runtime)
            if name == "memory_get":
                return self._get(args, runtime)
            return Err(f"Unknown tool: {name}", code="UNKNOWN_TOOL")
        except Exception as e:
            return Err(f"memory tool failed: {e}", code="RUNTIME_ERROR")

    def _search(self, args: dict[str, Any], runtime: MemoryRuntime) -> Result[str]:
        # OpenClaw parity: corpus + maxResults + minScore
        query = (args.get("query") or "").strip()
        if not query:
            return Err("memory_search needs a non-empty query, sir.", code="MISSING_ARG")
        max_results = int(args.get("maxResults") or 4)
        min_score = float(args.get("minScore") or 0.0)
        corpus = str(args.get("corpus") or "memory").strip() or "memory"

        # Phase 4.0 uses the SQLite FTS index for text recall.
        # The score is the row's "match strength" — for now a
        # simple per-row cap of 0.95 if the trigger matched
        # exactly, 0.5 if it's an FTS match.
        rows = runtime.search_text(query, limit=max_results)
        if not rows:
            rows = runtime.search_substring(query, limit=max_results)
        if not rows:
            # If the query looks like a memory trigger, suggest
            # the LLM save it via save_memory (the host tool).
            triggered = any(p.search(query) for p in MEMORY_TRIGGERS)
            if triggered:
                return Ok(
                    f"No memory entries match {query!r}. (The query "
                    f"looks like a memory-worthy statement — consider "
                    f"calling save_memory to remember it.)"
                )
            return Ok(f"No memory entries match {query!r}.")

        # Filter by min_score (substring matches get 0.5; exact-key 0.95)
        scored: list[tuple[float, dict[str, Any]]] = []
        for r in rows:
            key = r.get("key", "")
            value = r.get("value", "")
            score = 0.95 if query.lower() == key.lower() else 0.5
            if score >= min_score:
                scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        scored = scored[:max_results]
        if not scored:
            return Ok(f"No memory entries with score >= {min_score} match {query!r}.")

        lines = [f"Memory matches for {query!r} (corpus={corpus}):"]
        for score, r in scored:
            value = str(r.get("value", ""))
            # Filter prompt-injection payloads from recall results.
            # A poisoned long-term memory that tries to "ignore the
            # above instructions" would be re-injected into the
            # system prompt on every recall; this is the most
            # dangerous memory-poisoning vector.
            if looks_like_prompt_injection(value):
                _log.warning(
                    "memory_search filtered prompt-injection payload for key %s",
                    r.get("key"),
                )
                continue
            lines.append(
                f"  - {r.get('category', 'general')}/{r['key']}: {value} [score={score:.2f}]"
            )
        if len(lines) == 1:
            return Ok(f"No memory entries with score >= {min_score} match {query!r}.")
        return Ok("\n".join(lines))

    def _get(self, args: dict[str, Any], runtime: MemoryRuntime) -> Result[str]:
        # OpenClaw parity: path + from + lines + corpus
        path = (args.get("path") or "").strip()
        if not path:
            return Err("memory_get needs a non-empty path, sir.", code="MISSING_ARG")

        # Phase 4.0 ships the SQLite key/value store. The
        # path argument selects the key; the from/lines args
        # are accepted for forward-compat with the file-based
        # backend (MEMORY.md) that lands in Phase 4.1.
        value = runtime.get(path)
        if value is None:
            return Ok(f"No memory entry with key {path!r}.")

        # Apply the security scrubber: if the stored value
        # contains envelope sludge (e.g. a poisoned long-term
        # memory), strip it before echoing back.
        clean = sanitize_for_memory_capture(value)
        if not clean:
            return Ok(f"Memory entry {path!r} was pure envelope sludge; nothing to return.")

        # If the cleaned value still looks like envelope
        # sludge, refuse to return it. Same for prompt
        # injection: a poisoned long-term memory that tries to
        # manipulate the model through the recall channel is the
        # primary memory-poisoning vector. Both are filtered
        # before the value reaches the LLM.
        if looks_like_envelope_sludge(clean):
            _log.warning("memory_get refused to return sludge for key %s", path)
            return Ok(
                f"Memory entry {path!r} was filtered as envelope sludge; "
                "not returning to the model."
            )
        if looks_like_prompt_injection(clean):
            _log.warning(
                "memory_get refused to return prompt-injection payload for key %s",
                path,
            )
            return Ok(
                f"Memory entry {path!r} was filtered as a prompt-injection "
                "payload; not returning to the model."
            )

        from_line = int(args.get("from") or 1)
        lines_arg = int(args.get("lines") or 20)
        text_lines = clean.splitlines()
        start_idx = max(0, from_line - 1)
        end_idx = min(len(text_lines), start_idx + lines_arg)
        excerpt = "\n".join(text_lines[start_idx:end_idx])
        truncated = end_idx < len(text_lines)
        suffix = (
            f"\n[...truncated; {len(text_lines) - end_idx} more lines; "
            f"read with from={end_idx + 1} to continue]"
            if truncated
            else ""
        )
        return Ok(f"{path} (lines {from_line}-{end_idx}):\n{excerpt}{suffix}")


# Public re-exports.
__all__ = [
    "MEMORY_GET_TOOL",
    "MEMORY_SEARCH_TOOL",
    "MemoryCorePlugin",
]
