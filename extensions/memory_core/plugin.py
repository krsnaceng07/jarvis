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
        ToolParam(
            name="citations",
            type="boolean",
            description="Whether to include source line citations in results (default false).",
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

INTENT_TOOL = ToolDecl(
    name="intent",
    description="Creates, lists, or explicitly cancels event-conditioned standing intents. Time-based reminders continue to use scheduled tasks.",
    parameters=[
        ToolParam(
            name="action",
            type="string",
            description="One of 'create', 'list', or 'cancel'.",
            required=True,
        ),
        ToolParam(
            name="description",
            type="string",
            description="The event description (required for 'create').",
            required=False,
        ),
        ToolParam(
            name="triggerKeywords",
            type="string",
            description="Comma-separated trigger keywords (required for 'create').",
            required=False,
        ),
        ToolParam(
            name="channelId",
            type="string",
            description="Scope the intent to a specific channel (optional).",
            required=False,
        ),
        ToolParam(
            name="senderId",
            type="string",
            description="Scope the intent to a specific sender (optional).",
            required=False,
        ),
        ToolParam(
            name="expiryDays",
            type="integer",
            description="Days until intent expires. Default 90.",
            required=False,
        ),
        ToolParam(
            name="cooldownHours",
            type="integer",
            description="Hours before intent arms again after firing. Default 24.",
            required=False,
        ),
        ToolParam(
            name="maxFires",
            type="integer",
            description="Max number of times this intent can fire. Default 3.",
            required=False,
        ),
        ToolParam(
            name="intentId",
            type="string",
            description="The ID of the intent (required for 'cancel').",
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
        self._tools = [MEMORY_SEARCH_TOOL, MEMORY_GET_TOOL, INTENT_TOOL]

    def init(self, ctx: Any) -> None:
        """Lifecycle hook — mirrors ``Plugin.init``.

        Phase 4.0 doesn't need any per-instance state (the
        underlying ``MemoryRuntime`` is a process-wide singleton).
        Reserved for Phase 4.1 (LanceDB warmup) and Phase 4.2
        (active-memory recall warmup).

        Added: Trigger auto-reindexing on startup.
        """
        import os
        import threading

        workspace = os.environ.get("JARVIS_WORKSPACE") or os.getcwd()

        def _bg_index():
            try:
                from .memory_indexer import index_memory_files
                from .runtime import MemoryRuntime

                rt = MemoryRuntime.default()
                index_memory_files(workspace, rt)
            except Exception as e:
                print(f"Memory plugin auto-index failed: {e}")

        threading.Thread(target=_bg_index, daemon=True, name="MemoryIndexer").start()
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
                return await self._search(args, runtime)
            if name == "memory_get":
                return self._get(args, runtime)
            if name == "intent":
                return self._intent(args, runtime)
            return Err(f"Unknown tool: {name}", code="UNKNOWN_TOOL")
        except Exception as e:
            return Err(f"memory tool failed: {e}", code="RUNTIME_ERROR")

    def _intent(self, args: dict[str, Any], runtime: MemoryRuntime) -> Result[str]:
        action = (args.get("action") or "").strip()
        if not action:
            return Err(
                "intent tool requires an 'action' (create, list, cancel).", code="MISSING_ARG"
            )

        if action == "create":
            condition = (args.get("condition") or "").strip()
            description = (args.get("description") or condition).strip()
            if not description:
                return Err("intent action 'create' requires a 'description'.", code="MISSING_ARG")
            trigger_keywords = (args.get("triggerKeywords") or condition).strip()

            channel_id = args.get("channelId")
            sender_id = args.get("senderId")

            # The agent ID is extracted from context later, but we pass None here as plugin doesn't have it natively
            agent_id = None

            expiry_days = int(args.get("expiryDays", 90))
            cooldown_hours = int(args.get("cooldownHours", 24))
            max_fires = int(args.get("maxFires", 3))

            return Ok(
                runtime.create_intent(
                    description,
                    trigger_keywords,
                    agent_id,
                    channel_id,
                    sender_id,
                    expiry_days,
                    cooldown_hours,
                    max_fires,
                )
            )
        elif action == "list":
            return Ok(runtime.list_intents())
        elif action == "cancel":
            intent_id = (args.get("intentId") or "").strip()
            if not intent_id:
                return Err("intent action 'cancel' requires an 'intentId'.", code="MISSING_ARG")
            return Ok(runtime.cancel_intent(intent_id))
        else:
            return Err(f"Unknown intent action: {action}", code="INVALID_ARG")

    async def _search(self, args: dict[str, Any], runtime: MemoryRuntime) -> Result[str]:
        # OpenClaw parity: corpus + maxResults + minScore + citations
        query = (args.get("query") or "").strip()
        if not query:
            return Err("memory_search needs a non-empty query, sir.", code="MISSING_ARG")
        max_results = int(args.get("maxResults") or 4)
        min_score = float(args.get("minScore") or 0.0)
        corpus = str(args.get("corpus") or "memory").strip() or "memory"
        citations = bool(args.get("citations") or False)

        scored = runtime.search_ranked(
            query=query,
            limit=max_results,
            min_score=min_score,
            corpus=corpus,
            citations=citations,
        )

        if not scored:
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

        lines = [f"Memory matches for {query!r} (corpus={corpus}):"]
        for r in scored:
            value = str(r.get("value", ""))
            # Filter prompt-injection payloads from recall results.
            if looks_like_prompt_injection(value):
                _log.warning(
                    "memory_search filtered prompt-injection payload for key %s",
                    r.get("key"),
                )
                continue
            score_val = r.get("score", r.get("final_score", 0.0))
            lines.append(
                f"  - {r.get('category', 'general')}/{r['key']}: {value} [score={score_val:.2f}]"
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
            import os
            from pathlib import Path

            ws_dir = Path(os.environ.get("JARVIS_WORKSPACE") or Path.cwd())
            candidate = ws_dir / path
            if candidate.is_file():
                try:
                    value = candidate.read_text(encoding="utf-8")
                except Exception:
                    value = None

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

        # OpenClaw parity: line pagination & character budget
        from_line = max(1, int(args.get("from") or 1))
        lines_arg = max(1, int(args.get("lines") or 120))
        max_chars = 12_000

        text_lines = clean.splitlines()
        total_lines = len(text_lines)
        start_idx = from_line - 1
        end_idx = min(total_lines, start_idx + lines_arg)

        selected_lines = text_lines[start_idx:end_idx]
        more_remain = end_idx < total_lines

        included_lines = len(selected_lines)
        excerpt = "\n".join(selected_lines)
        while included_lines > 1 and len(excerpt) > max_chars:
            included_lines -= 1
            excerpt = "\n".join(selected_lines[:included_lines])

        char_cap_truncated = included_lines < len(selected_lines)
        is_truncated = char_cap_truncated or more_remain
        next_from = from_line + included_lines if is_truncated else None

        if is_truncated and next_from is not None:
            excerpt = f"{excerpt}\n\n[More content available. Use from={next_from} to continue.]"

        return Ok(excerpt)


# Public re-exports.
__all__ = [
    "MEMORY_GET_TOOL",
    "MEMORY_SEARCH_TOOL",
    "MemoryCorePlugin",
]
