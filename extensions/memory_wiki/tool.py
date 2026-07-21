"""tool — Memory Wiki 5 wiki tools (Phase 4.3f-mr3).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/tool.ts``.

The memory-wiki plugin exposes 5 tools to
the agent runtime:

- ``wiki_status`` — vault mode + health +
  Obsidian CLI availability.
- ``wiki_search`` — search wiki pages (and
  the memory corpus when shared search is
  enabled).
- ``wiki_lint`` — surface structural
  issues + provenance gaps + contradictions
  + open questions.
- ``wiki_apply`` — apply narrow wiki
  mutations (``create_synthesis`` /
  ``update_metadata``).
- ``wiki_get`` — read a wiki page by id or
  relative path (or fall back to the memory
  corpus when shared search is enabled).

Each tool factory takes the resolved wiki
config + the optional app config + an
optional :class:`WikiToolMemoryContext`
(``agentId`` / ``agentSessionKey`` /
``sandboxed``) and returns a
:class:`WikiTool` dict (the Python port of
the OpenClaw ``AnyAgentTool``).

The dependency modules (status, lint,
source-sync) are stubbed in 4.3f-mr3; the
full implementations land in 4.3g.
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
from collections.abc import Callable  # noqa: TCH003 — needed for builder type hints
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .apply import (
    apply_memory_wiki_mutation,
    normalize_memory_wiki_mutation_input,
)
from .lint import lint_memory_wiki_vault
from .query import (
    WIKI_SEARCH_MODES,
    WikiSearchMode,
    get_memory_wiki_page,
    search_memory_wiki,
)
from .source_sync import sync_memory_wiki_imported_sources
from .status import (
    MemoryWikiStatus,
    render_memory_wiki_status,
    resolve_memory_wiki_status,
)

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# ── tool context ──────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WikiToolMemoryContext:
    """The agent + session + sandbox context.

    Mirrors the OpenClaw
    ``WikiToolMemoryContext`` shape.
    """

    agent_id: str | None = None
    agent_session_key: str | None = None
    sandboxed: bool = False


# ── tool result shape ─────────────────────────────────────


@dataclass
class WikiToolTextContent:
    """A single text content block in the tool result.

    Mirrors the OpenClaw tool result
    ``{ type: "text", text: "..." }`` shape.
    """

    type: str = "text"
    text: str = ""


@dataclass
class WikiToolResult:
    """A wiki tool's return value.

    Mirrors the OpenClaw tool result
    ``{ content, details }`` shape.
    """

    content: list[WikiToolTextContent] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


# OpenClaw's ``AnyAgentTool`` type
# (``{ name, label, description, parameters,
# execute }``). The Python port uses a
# matching dict shape so the host runtime can
# register the tool via the SDK's tool
# surface.
WikiTool = dict[str, Any]


# ── helpers ───────────────────────────────────────────────


def format_wiki_tool_report_path(config: ResolvedMemoryWikiConfig, report_path: str) -> str:
    """Format a lint report path as vault-relative.

    Mirrors the OpenClaw
    ``formatWikiToolReportPath``. Returns the
    input ``report_path`` unchanged when it
    lives outside the vault root.
    """
    try:
        vault_root = os.path.abspath(config.vault.path)
        resolved = os.path.abspath(report_path)
        relative = os.path.relpath(resolved, vault_root)
    except (OSError, ValueError):
        return report_path
    if not relative or relative.startswith("..") or os.path.isabs(relative):
        return report_path
    return relative.replace("\\", "/")


async def sync_imported_sources_if_needed(
    config: ResolvedMemoryWikiConfig, app_config: Any = None
) -> None:
    """Sync imported sources (best-effort) before each tool call.

    Mirrors the OpenClaw
    ``syncImportedSourcesIfNeeded``. The full
    implementation lands in 4.3g; the
    current stub returns a no-op.
    """
    await sync_memory_wiki_imported_sources(config=config, app_config=app_config)


# ── wiki_status ───────────────────────────────────────────


def create_wiki_status_tool(
    config: ResolvedMemoryWikiConfig,
    app_config: Any = None,
    memory_context: WikiToolMemoryContext | None = None,
) -> WikiTool:
    """Build the ``wiki_status`` tool.

    Mirrors the OpenClaw
    ``createWikiStatusTool``. Returns the
    current vault status (mode + render
    mode + bridge state + Obsidian CLI
    availability + active agents).
    """
    memory_context = memory_context or WikiToolMemoryContext()

    async def _execute(_tool_call_id: str, _raw_params: Any) -> WikiToolResult:
        await sync_imported_sources_if_needed(config, app_config)
        status: MemoryWikiStatus = resolve_memory_wiki_status(
            config, caller_agent_id=memory_context.agent_id
        )
        return WikiToolResult(
            content=[WikiToolTextContent(text=render_memory_wiki_status(status))],
            details={
                "vaultPath": status.vault_path,
                "vaultMode": status.vault_mode,
                "renderMode": status.render_mode,
                "obsidianCliAvailable": status.obsidian_cli_available,
                "unsafeLocalPath": status.unsafe_local_path,
                "bridgeEnabled": status.bridge_enabled,
                "agentIds": status.agent_ids,
            },
        )

    return _build_tool(
        name="wiki_status",
        label="Wiki Status",
        description=(
            "Inspect the current memory wiki vault mode, health, " "and Obsidian CLI availability."
        ),
        parameters={"type": "object", "additionalProperties": False},
        execute=_execute,
    )


# ── wiki_search ───────────────────────────────────────────


def create_wiki_search_tool(
    config: ResolvedMemoryWikiConfig,
    app_config: Any = None,
    memory_context: WikiToolMemoryContext | None = None,
) -> WikiTool:
    """Build the ``wiki_search`` tool.

    Mirrors the OpenClaw
    ``createWikiSearchTool``. Searches the
    wiki corpus (the shared-memory fallback
    is added in 4.3f-mr2.5).
    """
    memory_context = memory_context or WikiToolMemoryContext()

    async def _execute(_tool_call_id: str, raw_params: Any) -> WikiToolResult:
        params = raw_params if isinstance(raw_params, dict) else {}
        query_text = str(params.get("query", "") or "").strip()
        if not query_text:
            return WikiToolResult(
                content=[
                    WikiToolTextContent(text="query is required"),
                ],
                details={"results": []},
            )
        max_results_raw = params.get("maxResults")
        max_results = (
            int(max_results_raw)
            if isinstance(max_results_raw, int) and max_results_raw >= 1
            else None
        )
        mode_value = params.get("mode")
        mode: WikiSearchMode | None = mode_value if mode_value in WIKI_SEARCH_MODES else None
        await sync_imported_sources_if_needed(config, app_config)
        # ``search_memory_wiki`` is sync
        # (it does only filesystem reads).
        # Wrapping it in ``asyncio.to_thread``
        # lets the await surface match the
        # OpenClaw tool contract without
        # blocking the event loop.
        results = await asyncio.to_thread(
            search_memory_wiki,
            config=config,
            query=query_text,
            max_results=max_results,
            mode=mode,
        )
        if not results:
            return WikiToolResult(
                content=[
                    WikiToolTextContent(text="No wiki or memory results."),
                ],
                details={"results": []},
            )
        lines: list[str] = []
        for index, result in enumerate(results, start=1):
            parts = [f"{index}. {result.title} ({result.corpus}/{result.kind})"]
            parts.append(f"Path: {result.path}")
            if isinstance(result.start_line, int) and isinstance(result.end_line, int):
                parts.append(f"Lines: {result.start_line}-{result.end_line}")
            if result.provenance_label:
                parts.append(f"Provenance: {result.provenance_label}")
            if result.matched_claim_id:
                parts.append(f"Claim: {result.matched_claim_id}")
            if result.evidence_kinds:
                parts.append(f"Evidence: {', '.join(result.evidence_kinds)}")
            parts.append(f"Snippet: {result.snippet}")
            lines.append("\n".join(parts))
        return WikiToolResult(
            content=[WikiToolTextContent(text="\n\n".join(lines))],
            details={"results": [dataclasses.asdict(r) for r in results]},
        )

    return _build_tool(
        name="wiki_search",
        label="Wiki Search",
        description=(
            "Search wiki pages and, when shared search is enabled, "
            "the active memory corpus by title, path, id, or body text."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "maxResults": {"type": "integer", "minimum": 1},
                "backend": {
                    "type": "string",
                    "enum": ["auto", "builtin", "shared", "lancedb", "sql"],
                },
                "corpus": {
                    "type": "string",
                    "enum": ["wiki", "memory", "all"],
                },
                "mode": {"type": "string", "enum": list(WIKI_SEARCH_MODES)},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        execute=_execute,
    )


# ── wiki_lint ─────────────────────────────────────────────


def create_wiki_lint_tool(
    config: ResolvedMemoryWikiConfig,
    app_config: Any = None,
) -> WikiTool:
    """Build the ``wiki_lint`` tool.

    Mirrors the OpenClaw
    ``createWikiLintTool``. Surfaces
    structural issues + provenance gaps +
    contradictions + open questions.
    """
    # ``app_config`` is part of the
    # signature for OpenClaw parity but the
    # current lint implementation is
    # in-vault only.
    _ = app_config

    async def _execute(_tool_call_id: str, _raw_params: Any) -> WikiToolResult:
        await sync_imported_sources_if_needed(config, app_config)
        result = lint_memory_wiki_vault(config)
        contradictions = len(result.issues_by_category.get("contradictions", []))
        open_questions = len(result.issues_by_category.get("open-questions", []))
        provenance = len(result.issues_by_category.get("provenance", []))
        errors = sum(1 for issue in result.issues if issue.severity == "error")
        warnings = sum(1 for issue in result.issues if issue.severity == "warning")
        report_path_str = (
            format_wiki_tool_report_path(config, result.report_path)
            if result.report_path is not None
            else "(not yet implemented in 4.3f-mr3)"
        )
        if result.issue_count == 0:
            summary = "No wiki lint issues."
        else:
            summary = "\n".join(
                [
                    f"Issues: {result.issue_count} total "
                    f"({errors} errors, {warnings} warnings)",
                    f"Contradictions: {contradictions}",
                    f"Open questions: {open_questions}",
                    f"Provenance gaps: {provenance}",
                    f"Report: {report_path_str}",
                ]
            )
        return WikiToolResult(
            content=[WikiToolTextContent(text=summary)],
            details={
                "issueCount": result.issue_count,
                "issues": [dataclasses.asdict(issue) for issue in result.issues],
                "issuesByCategory": {
                    key: [dataclasses.asdict(issue) for issue in issues]
                    for key, issues in result.issues_by_category.items()
                },
                "reportPath": report_path_str,
            },
        )

    return _build_tool(
        name="wiki_lint",
        label="Wiki Lint",
        description=(
            "Lint the wiki vault and surface structural issues, "
            "provenance gaps, contradictions, and open questions."
        ),
        parameters={"type": "object", "additionalProperties": False},
        execute=_execute,
    )


# ── wiki_apply ────────────────────────────────────────────


def create_wiki_apply_tool(
    config: ResolvedMemoryWikiConfig,
    app_config: Any = None,
) -> WikiTool:
    """Build the ``wiki_apply`` tool.

    Mirrors the OpenClaw
    ``createWikiApplyTool``. Applies narrow
    mutations (``create_synthesis`` /
    ``update_metadata``) without freeform
    markdown surgery.
    """
    _ = app_config  # OpenClaw parity

    async def _execute(_tool_call_id: str, raw_params: Any) -> WikiToolResult:
        mutation = normalize_memory_wiki_mutation_input(raw_params)
        await sync_imported_sources_if_needed(config, app_config)
        # ``apply_memory_wiki_mutation`` is
        # sync (it drives the per-vault async
        # lock via ``asyncio.run``). Wrap
        # it in ``asyncio.to_thread`` so we
        # don't recurse into ``asyncio.run``
        # from inside the event loop.
        result = await asyncio.to_thread(
            apply_memory_wiki_mutation,
            config=config,
            mutation=mutation,
        )
        action = "Updated" if result.changed else "No changes for"
        # The full ``ApplyMutationResult``
        # includes the compile summary; the
        # 4.3f-mr2 dataclass keeps a slim
        # version, so we surface the
        # ``scanned_count`` etc. instead of
        # ``updated_files``.
        compile_lines: list[str] = [
            f"Pages scanned: {result.scanned_count}",
            f"Invalid: {result.invalid_count}",
            f"Ignored: {result.ignored_count}",
        ]
        compile_summary = (
            f"Refreshed compile ({'; '.join(compile_lines)})."
            if result.changed
            else "Compile re-run, no changes."
        )
        return WikiToolResult(
            content=[
                WikiToolTextContent(
                    text=(
                        f"{action} {result.page_path} via " f"{result.operation}. {compile_summary}"
                    ),
                )
            ],
            details={
                "changed": result.changed,
                "operation": result.operation,
                "pagePath": result.page_path,
                "pageId": result.page_id,
                "scannedCount": result.scanned_count,
                "invalidCount": result.invalid_count,
                "ignoredCount": result.ignored_count,
            },
        )

    return _build_tool(
        name="wiki_apply",
        label="Wiki Apply",
        description=(
            "Apply narrow wiki mutations for syntheses and page "
            "metadata without freeform markdown surgery."
        ),
        parameters={
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "enum": [
                        "create_synthesis",
                        "update_metadata",
                        "synthesis",
                        "metadata",
                    ],
                },
                "title": {"type": "string", "minLength": 1},
                "body": {"type": "string", "minLength": 1},
                "lookup": {"type": "string", "minLength": 1},
                "sourceIds": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
                "claims": {"type": "array", "items": {"type": "object"}},
                "contradictions": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
                "questions": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "status": {"type": "string", "minLength": 1},
            },
            "required": ["op"],
            "additionalProperties": False,
        },
        execute=_execute,
    )


# ── wiki_get ──────────────────────────────────────────────


def create_wiki_get_tool(
    config: ResolvedMemoryWikiConfig,
    app_config: Any = None,
    memory_context: WikiToolMemoryContext | None = None,
) -> WikiTool:
    """Build the ``wiki_get`` tool.

    Mirrors the OpenClaw
    ``createWikiGetTool``. Reads a wiki page
    by id or relative path; the memory
    fallback is added in 4.3f-mr2.5.
    """
    memory_context = memory_context or WikiToolMemoryContext()

    async def _execute(_tool_call_id: str, raw_params: Any) -> WikiToolResult:
        params = raw_params if isinstance(raw_params, dict) else {}
        lookup = str(params.get("lookup", "") or "").strip()
        if not lookup:
            return WikiToolResult(
                content=[
                    WikiToolTextContent(text="lookup is required"),
                ],
                details={"found": False},
            )
        from_line_raw = params.get("fromLine")
        from_line = (
            int(from_line_raw) if isinstance(from_line_raw, int) and from_line_raw >= 1 else None
        )
        line_count_raw = params.get("lineCount")
        line_count = (
            int(line_count_raw) if isinstance(line_count_raw, int) and line_count_raw >= 1 else None
        )
        await sync_imported_sources_if_needed(config, app_config)
        # ``get_memory_wiki_page`` is sync
        # (filesystem reads + frontmatter
        # parsing). Wrap in ``asyncio.to_thread``
        # so the await surface matches the
        # OpenClaw tool contract.
        result = await asyncio.to_thread(
            get_memory_wiki_page,
            config=config,
            lookup=lookup,
            from_line=from_line,
            line_count=line_count,
        )
        if result is None:
            return WikiToolResult(
                content=[
                    WikiToolTextContent(
                        text=f"Wiki page not found: {lookup}",
                    )
                ],
                details={"found": False},
            )
        return WikiToolResult(
            content=[WikiToolTextContent(text=result.content)],
            details={
                "found": True,
                "corpus": result.corpus,
                "path": result.path,
                "title": result.title,
                "kind": result.kind,
                "id": result.id,
                "fromLine": result.from_line,
                "lineCount": result.line_count,
                "totalLines": result.total_lines,
                "truncated": result.truncated,
            },
        )

    return _build_tool(
        name="wiki_get",
        label="Wiki Get",
        description=(
            "Read a wiki page by id or relative path, or fall back to "
            "the active memory corpus when shared search is enabled."
        ),
        parameters={
            "type": "object",
            "properties": {
                "lookup": {"type": "string", "minLength": 1},
                "fromLine": {"type": "integer", "minimum": 1},
                "lineCount": {"type": "integer", "minimum": 1},
                "backend": {
                    "type": "string",
                    "enum": ["auto", "builtin", "shared", "lancedb", "sql"],
                },
                "corpus": {
                    "type": "string",
                    "enum": ["wiki", "memory", "all"],
                },
            },
            "required": ["lookup"],
            "additionalProperties": False,
        },
        execute=_execute,
    )


# ── tool registration helper ──────────────────────────────


def _build_tool(
    *,
    name: str,
    label: str,
    description: str,
    parameters: dict[str, Any],
    execute: Callable[..., Any],
) -> WikiTool:
    """Build the standard :class:`WikiTool` dict shape.

    Mirrors the OpenClaw
    ``AnyAgentTool`` shape.
    """
    return {
        "name": name,
        "label": label,
        "description": description,
        "parameters": parameters,
        "execute": execute,
    }


def create_wiki_tools(
    config: ResolvedMemoryWikiConfig,
    app_config: Any = None,
    memory_context: WikiToolMemoryContext | None = None,
) -> list[WikiTool]:
    """Build all 5 wiki tools in OpenClaw's order.

    Returns a list of
    ``[wiki_status, wiki_search, wiki_lint,
    wiki_apply, wiki_get]``. The host
    runtime can register the list with the
    SDK's tool surface.
    """
    return [
        create_wiki_status_tool(config, app_config, memory_context),
        create_wiki_search_tool(config, app_config, memory_context),
        create_wiki_lint_tool(config, app_config),
        create_wiki_apply_tool(config, app_config),
        create_wiki_get_tool(config, app_config, memory_context),
    ]


def reset_memory_wiki_tool_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
    "WikiTool",
    "WikiToolMemoryContext",
    "WikiToolResult",
    "WikiToolTextContent",
    "create_wiki_apply_tool",
    "create_wiki_get_tool",
    "create_wiki_lint_tool",
    "create_wiki_search_tool",
    "create_wiki_status_tool",
    "create_wiki_tools",
    "format_wiki_tool_report_path",
    "reset_memory_wiki_tool_state_for_tests",
    "sync_imported_sources_if_needed",
]
