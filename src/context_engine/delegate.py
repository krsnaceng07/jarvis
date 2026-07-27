"""Context-engine delegates bridge custom engines to built-in compaction and memory prompt paths.

OpenClaw parity: ``src/context-engine/delegate.ts``. The compact runtime
is loaded through a lazy runtime boundary
(``src.agents.embedded_agent_runner.compact_runtime``) so no static edge
into the embedded runner graph exists; tests monkeypatch
``_load_compact_runtime`` exactly as the TS tests ``vi.mock`` the module.
"""
from __future__ import annotations

import math
import os
from typing import Any, Awaitable, Callable

from src.plugins.memory_state import (
    MemoryPromptSectionParams,
    PreparedMemoryPromptSection,
    build_memory_prompt_section,
    get_active_prepared_memory_prompt_section,
    prepare_memory_prompt_section,
)
from src.sessions.session_transcript_runtime import parse_sqlite_session_file_marker
from src.shared.lazy_runtime import create_lazy_runtime_module, import_runtime_module
from src.shared.structured_prompt_section import normalize_structured_prompt_section

__all__ = [
    "build_memory_system_prompt_addition",
    "delegate_compaction_to_runtime",
    "prepare_memory_system_prompt_addition",
]


def _import_compact_runtime() -> Any:
    # Load through the dedicated runtime boundary without introducing another
    # source-level static edge into the embedded runner graph.
    return import_runtime_module("src.agents.embedded_agent_runner.compact_runtime")


_load_compact_runtime = create_lazy_runtime_module(_import_compact_runtime)


def _build_compaction_result_session_target(
    *,
    agent_id: str | None,
    session_file: str | None,
    session_id: str | None,
    session_key: str | None,
    session_target: dict[str, Any] | None,
) -> dict[str, Any] | None:
    sqlite_marker = parse_sqlite_session_file_marker(session_file)
    marker_session_id = sqlite_marker.session_id if sqlite_marker else None
    resolved_session_id = (
        marker_session_id if marker_session_id is not None else session_id
    )
    if not resolved_session_id:
        return None
    target = session_target or {}
    resolved_agent_id = (
        target.get("agentId")
        or agent_id
        or (sqlite_marker.agent_id if sqlite_marker else None)
    )
    resolved_session_key = target.get("sessionKey") or session_key
    resolved_store_path = target.get("storePath") or (
        sqlite_marker.store_path if sqlite_marker else None
    )
    result: dict[str, Any] = {}
    if resolved_agent_id:
        result["agentId"] = resolved_agent_id
    result["sessionId"] = resolved_session_id
    if resolved_session_key:
        result["sessionKey"] = resolved_session_key
    if resolved_store_path:
        result["storePath"] = resolved_store_path
    if "threadId" in target:
        result["threadId"] = target["threadId"]
    return result


async def delegate_compaction_to_runtime(params: dict[str, Any]) -> dict[str, Any]:
    """Delegate a context-engine compaction request to the built-in runtime path.

    This is the same bridge used by the legacy context engine. Third-party
    engines can call it from their own ``compact()`` implementations when
    they do not own the compaction algorithm but still need ``/compact``
    and overflow recovery to use the stock runtime behavior.

    Note: ``compactionTarget`` is part of the public ``compact()``
    contract, but the built-in runtime compaction path does not expose
    that knob. This helper ignores it to preserve legacy behavior.
    """
    runtime = _load_compact_runtime()
    compact_direct = runtime.compact_embedded_agent_session_direct

    # runtimeContext carries host-resolved runtime fields set by internal
    # callers. Keep the public delegate keyed by session identity, not by the
    # active transcript artifact that the runtime may resolve internally.
    runtime_context: dict[str, Any] = dict(params.get("runtimeContext") or {})
    runtime_context_params = {
        key: value for key, value in runtime_context.items() if key != "sessionFile"
    }
    session_target = params.get("sessionTarget") or runtime_context.get("sessionTarget")
    agent_id = params.get("agentId") or runtime_context.get("agentId")
    session_key = params.get("sessionKey") or runtime_context.get("sessionKey")
    current_token_count = params.get("currentTokenCount")
    if current_token_count is None:
        candidate = runtime_context.get("currentTokenCount")
        if (
            isinstance(candidate, (int, float))
            and not isinstance(candidate, bool)
            and math.isfinite(candidate)
            and candidate > 0
        ):
            current_token_count = math.floor(candidate)

    call_params: dict[str, Any] = dict(runtime_context_params)
    if agent_id:
        call_params["agentId"] = agent_id
    call_params["sessionId"] = params.get("sessionId")
    if session_key:
        call_params["sessionKey"] = session_key
    if session_target:
        call_params["sessionTarget"] = session_target
    call_params["tokenBudget"] = params.get("tokenBudget")
    if current_token_count is not None:
        call_params["currentTokenCount"] = current_token_count
    call_params["force"] = params.get("force")
    call_params["customInstructions"] = params.get("customInstructions")
    call_params["abortSignal"] = params.get("abortSignal")
    workspace_dir = runtime_context.get("workspaceDir")
    call_params["workspaceDir"] = (
        workspace_dir if isinstance(workspace_dir, str) else os.getcwd()
    )

    result = await compact_direct(call_params)

    inner = result.get("result")
    result_session_target = (
        _build_compaction_result_session_target(
            agent_id=agent_id,
            session_file=inner.get("sessionFile"),
            session_id=inner.get("sessionId"),
            session_key=session_key,
            session_target=session_target,
        )
        if inner
        else None
    )

    mapped_inner: dict[str, Any] | None = None
    if inner:
        mapped_inner = {
            "summary": inner.get("summary"),
            "firstKeptEntryId": inner.get("firstKeptEntryId"),
            "tokensBefore": inner.get("tokensBefore"),
            "tokensAfter": inner.get("tokensAfter"),
            "details": inner.get("details"),
        }
        if inner.get("sessionId"):
            mapped_inner["sessionId"] = inner["sessionId"]
        # Core reports successors only through the typed sessionTarget; the
        # deprecated raw sessionFile field is reserved for shipped engines
        # reporting rotation to core, and post-flip core has no file path.
        if result_session_target:
            mapped_inner["sessionTarget"] = result_session_target

    return {
        "ok": result.get("ok"),
        "compacted": result.get("compacted"),
        "reason": result.get("reason"),
        "result": mapped_inner,
    }


def _render_memory_system_prompt_addition(
    params: MemoryPromptSectionParams,
    prepared: PreparedMemoryPromptSection | None = None,
) -> str | None:
    lines = build_memory_prompt_section(params, prepared)
    if not lines:
        return None
    normalized = normalize_structured_prompt_section("\n".join(lines))
    return normalized or None


def build_memory_system_prompt_addition(
    params: MemoryPromptSectionParams,
) -> str | None:
    """Build a context-engine-ready systemPromptAddition from the active memory
    plugin prompt path, letting non-legacy engines opt into the same
    memory/wiki guidance the legacy engine gets via system prompt assembly."""
    prepared = get_active_prepared_memory_prompt_section()
    if prepared is None:
        return _render_memory_system_prompt_addition(params)
    tools, citations_mode, agent_id, agent_session_key, sandboxed = prepared.context
    context_params = MemoryPromptSectionParams(
        available_tools=params.available_tools,
        citations_mode=(
            params.citations_mode if params.citations_mode is not None else citations_mode
        ),
        agent_id=params.agent_id if params.agent_id is not None else agent_id,
        agent_session_key=(
            params.agent_session_key
            if params.agent_session_key is not None
            else agent_session_key
        ),
        sandboxed=params.sandboxed if params.sandboxed is not None else sandboxed,
    )
    return _render_memory_system_prompt_addition(context_params, prepared)


async def prepare_memory_system_prompt_addition(
    params: MemoryPromptSectionParams,
) -> str | None:
    """Prepare memory state asynchronously, then render it without prompt-path I/O."""
    prepared = await prepare_memory_prompt_section(params)
    return _render_memory_system_prompt_addition(params, prepared)
