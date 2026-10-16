"""recall_run — embedded sub-agent dispatch.

OpenClaw parity: mirrors ``extensions/active-memory/recall-run.ts``.

Phase 4.2b step 3: ports the sub-agent runner. The flow is:

1. Resolve ``workspaceDir`` / ``agentDir`` / ``modelRef``.
2. Build a deterministic sub-agent session key under the
   parent session.
3. Choose a transcript dir:
   - ``persistTranscripts``: persistent dir under
     ``resolvePersistentTranscriptBaseDir``.
   - otherwise: a transient temp dir (cleaned on exit).
4. Create the runtime session entry via
   ``api.runtime.agent.session.patchSessionEntry`` (rejects
   if the session already exists).
5. Build the recall prompt and dispatch the embedded
   agent via ``api.runtime.agent.runEmbeddedAgent``.
6. On success: read the merged transcript state, build
   the final ``RecallSubagentResult``.
7. On error: attach partial-timeout data, decide
   ``unavailable`` / ``failed`` based on the error shape.
8. Cleanup: persist the transcript artifact (if requested)
   + ``cleanupSessionLifecycleArtifacts`` + temp workspace
   cleanup.

The default ``runEmbeddedAgent`` stub returns
``{ payloads: [] }`` so the plugin can boot without a
real LLM agent. The host overrides the stub to dispatch
the actual run via the harness.

Surface
-------
- ``apply_active_memory_runtime_config_snapshot`` — overlay
  active-memory config onto the runtime config snapshot.
- ``require_transient_workspace_dir`` — raise if a transient
  workspace dir is missing.
- ``collect_active_memory_transcript_sources`` — build the
  initial ``[runtime, file, ?activeSessionFile]`` list.
- ``persist_active_memory_transcript_artifact`` — write the
  merged transcript events to a JSONL artifact.
- ``cleanup_active_memory_recall_session`` — best-effort
  retry loop around ``cleanupSessionLifecycleArtifacts``.
- ``run_recall_subagent`` — the top-level entry point.

Dependencies
============
- ``jarvis_sdk.parse_agent_session_key``
- ``jarvis_sdk.resolve_agent_workspace_dir`` /
  ``resolve_agent_dir``
- ``extensions.active_memory.config`` —
  ``is_missing_registered_memory_tools_error``,
  ``require_transient_workspace_dir``,
  ``resolve_persistent_transcript_base_dir``,
  ``resolve_safe_transcript_dir``.
- ``extensions.active_memory.prompt.build_recall_prompt``
- ``extensions.active_memory.query.get_model_ref``
- ``extensions.active_memory.recall_state.to_single_line_log_value``
- ``extensions.active_memory.session.resolve_recall_run_channel_context``
- ``extensions.active_memory.transcript_result.{attach_partial_timeout_data, read_memory_tool_result_evidence, read_partial_assistant_text_from_sources}``
- ``extensions.active_memory.transcript_watch.{read_active_memory_search_debug_from_run_result, read_active_memory_session_file_from_run_result, read_merged_active_memory_transcript_state}``
- ``extensions.active_memory.transcript.{file_transcript_source, transcript_source_from_returned_session_file}``
- ``extensions.active_memory.types`` — recall-flow types
  and constants.
"""

# pyright: reportArgumentType=false
# pyright: reportAssignmentType=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportOptionalMemberAccess=false
# ruff: noqa: SIM105, S110, S112, S324, PLR0911, PLR0912, PLR0915, N803, N806, PLR2004, C901

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, cast

from jarvis_sdk import (
    parse_agent_session_key,
    resolve_agent_dir,
    resolve_agent_workspace_dir,
)

from .config import (
    is_missing_registered_memory_tools_error,
    require_transient_workspace_dir,
    resolve_persistent_transcript_base_dir,
    resolve_safe_transcript_dir,
)
from .prompt import build_recall_prompt
from .query import get_model_ref
from .recall_state import to_single_line_log_value
from .session import resolve_recall_run_channel_context
from .transcript import (
    file_transcript_source,
    transcript_source_from_returned_session_file,
)
from .transcript_result import (
    attach_partial_timeout_data,
    read_memory_tool_result_evidence,
    read_partial_assistant_text_from_sources,
)
from .transcript_watch import (
    read_active_memory_search_debug_from_run_result,
    read_active_memory_session_file_from_run_result,
    read_merged_active_memory_transcript_state,
)
from .types import (
    ACTIVE_MEMORY_CLEANUP_RETRY_DELAYS_MS,
    ACTIVE_MEMORY_RECALL_LANE,
    ActiveMemoryTranscriptSource,
    RecallSubagentResult,
    ResolvedActiveRecallPluginConfig,
)


def apply_active_memory_runtime_config_snapshot(
    runtime_config: Any,
    config: ResolvedActiveRecallPluginConfig,
) -> Any:
    """Overlay active-memory config onto the runtime config snapshot.

    Mirrors OpenClaw's ``applyActiveMemoryRuntimeConfigSnapshot``.
    The active-memory plugin is enabled/disabled in the
    snapshot's ``plugins`` section based on ``config.enabled``
    + ``config.agents``.
    """
    if not isinstance(runtime_config, dict):
        return {**runtime_config} if runtime_config else {}
    snapshot = dict(runtime_config)
    plugins_section = snapshot.get("plugins")
    if not isinstance(plugins_section, dict):
        plugins_section = {}
        snapshot["plugins"] = plugins_section
    active_memory_entry: dict[str, Any] = {
        "enabled": bool(config.get("enabled", True)),
    }
    agents = config.get("agents") or []
    if agents:
        active_memory_entry["agents"] = dict(agents) if isinstance(agents, dict) else list(agents)
    plugins_section["active-memory"] = active_memory_entry
    return snapshot


def collect_active_memory_transcript_sources(
    params: dict[str, Any],
) -> list[ActiveMemoryTranscriptSource]:
    """Build the initial transcript-sources list.

    Mirrors OpenClaw's ``collectActiveMemoryTranscriptSources``.
    Always includes the runtime source + the artifact file
    source; optionally includes the active session file if
    it differs from the artifact file.
    """
    sources: list[ActiveMemoryTranscriptSource] = [params["runtimeSource"]]
    sources.append(file_transcript_source(params["artifactSessionFile"]))
    if (
        params.get("activeSessionFile")
        and params["activeSessionFile"] != params["artifactSessionFile"]
    ):
        sources.append(
            transcript_source_from_returned_session_file(
                {
                    "sessionFile": params["activeSessionFile"],
                    "sessionKey": params["activeSessionKey"],
                }
            )
        )
    return sources


async def persist_active_memory_transcript_artifact(params: dict[str, Any]) -> None:
    """Write the merged transcript events to a JSONL artifact.

    Mirrors OpenClaw's ``persistActiveMemoryTranscriptArtifact``.
    Reads the runtime sources, deduplicates by serialized
    event JSON, and writes the merged list to
    ``params.sessionFile`` as JSONL (mode 0o600).
    """
    session_file = params["sessionFile"]
    seen: set[str] = set()
    events: list[Any] = []
    for source in params.get("sources") or ():
        if not isinstance(source, dict) or source.get("kind") != "runtime":
            continue
        target = source.get("target") or {}
        try:
            from jarvis_sdk import read_session_transcript_events

            runtime_events = await read_session_transcript_events(target)
        except Exception:
            continue
        for event in runtime_events:
            serialized = json.dumps(event, default=str)
            if serialized in seen:
                continue
            seen.add(serialized)
            events.append(event)
    if not events:
        return
    path = Path(session_file)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with contextlib.suppress(OSError):
        os.chmod(path.parent, 0o700)
    payload = "\n".join(json.dumps(e, default=str) for e in events) + "\n"
    await asyncio.to_thread(path.write_text, payload, encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


async def cleanup_active_memory_recall_session(params: dict[str, Any]) -> None:
    """Best-effort retry loop around ``cleanupSessionLifecycleArtifacts``.

    Mirrors OpenClaw's ``cleanupActiveMemoryRecallSession``.
    Retries up to ``len(ACTIVE_MEMORY_CLEANUP_RETRY_DELAYS_MS)``
    times with the configured delays, raising the last error
    if all attempts fail.
    """
    parsed = parse_agent_session_key(params["sessionKey"]) or {}
    session_key_segment_prefix = parsed.get("rest") or params["sessionKey"]
    last_error: BaseException | None = None
    for delay_ms in ACTIVE_MEMORY_CLEANUP_RETRY_DELAYS_MS:
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)
        try:
            from jarvis_sdk import cleanup_session_lifecycle_artifacts

            result = cleanup_session_lifecycle_artifacts(
                {
                    "agentId": params["agentId"],
                    "archiveRemovedEntryTranscripts": False,
                    "orphanTranscriptMinAgeMs": 0,
                    "sessionKeySegmentPrefix": session_key_segment_prefix,
                    "storePath": params["storePath"],
                    "transcriptContentMarker": f'"runId":"{params["sessionId"]}"',
                }
            )
            if result.get("removedEntries") != 1:
                raise RuntimeError(
                    f"active-memory recall cleanup removed {result.get('removedEntries')} sessions"
                )
            return
        except Exception as exc:
            last_error = exc
    if isinstance(last_error, BaseException):
        raise last_error
    raise RuntimeError(f"active-memory recall cleanup failed: {last_error!r}")


async def run_recall_subagent(params: dict[str, Any]) -> RecallSubagentResult:
    """Top-level sub-agent dispatch.

    Mirrors OpenClaw's ``runRecallSubagent``. Returns the
    ``RecallSubagentResult`` from the embedded sub-agent
    (or ``{ rawReply: "NONE" }`` if no model is configured).
    """
    runtime_config = params.get("runtimeConfig")
    config: ResolvedActiveRecallPluginConfig = params["config"]
    agent_id: str = params.get("agentId", "")
    api = params.get("api")

    workspace_dir = resolve_agent_workspace_dir(runtime_config or {}, agent_id)
    agent_dir = resolve_agent_dir(runtime_config or {}, agent_id)

    model_ref: dict[str, str] | None = params.get("modelRef") or get_model_ref(
        runtime_config,
        agent_id,
        config,
        {
            "modelProviderId": params.get("currentModelProviderId"),
            "modelId": params.get("currentModelId"),
        },
    )
    if not model_ref:
        return {"rawReply": "NONE"}

    subagent_session_id = f"active-memory-{int(time.time() * 36):x}-{uuid.uuid4().hex[:8]}"
    parent_session_key: str | None = params.get("parentSessionKey")
    subagent_scope = parent_session_key or params.get("sessionId") or str(uuid.uuid4())
    subagent_suffix = (
        "active-memory:"
        + hashlib.sha1(
            f"{subagent_scope}:{params.get('query', '')}:{subagent_session_id}".encode()
        ).hexdigest()[:12]
    )
    subagent_session_key = (
        f"{parent_session_key}:{subagent_suffix}"
        if parent_session_key
        else f"agent:{agent_id}:{subagent_suffix}"
    )

    transient_workspace: dict[str, Any] | None = None
    if not config.get("persistTranscripts"):
        transient_workspace = _create_temp_workspace(prefix="jarvis-active-memory-")
    temp_dir = (transient_workspace or {}).get("dir")
    persisted_dir: str | None = None
    if config.get("persistTranscripts"):
        try:
            persisted_dir = resolve_safe_transcript_dir(
                resolve_persistent_transcript_base_dir(api, agent_id),
                config.get("transcriptDir") or "active-memory",
            )
        except Exception:
            persisted_dir = None
    artifact_session_file = (
        os.path.join(persisted_dir, f"{subagent_session_id}.jsonl")
        if persisted_dir is not None
        else os.path.join(require_transient_workspace_dir(temp_dir), "session.jsonl")
    )
    store_path = params.get("storePath") or ""
    runtime_session_file = _format_sqlite_session_file_marker(
        {
            "agentId": agent_id,
            "sessionId": subagent_session_id,
            "storePath": store_path,
        }
    )
    runtime_source: ActiveMemoryTranscriptSource = {
        "kind": "runtime",
        "target": {
            "agentId": agent_id,
            "sessionId": subagent_session_id,
            "sessionKey": subagent_session_key,
            "storePath": store_path,
        },
    }
    transcript_sources: list[ActiveMemoryTranscriptSource] = (
        collect_active_memory_transcript_sources(
            {
                "runtimeSource": runtime_source,
                "artifactSessionFile": artifact_session_file,
                "activeSessionKey": subagent_session_key,
            }
        )
    )

    harness_has_usable_memory_result = False
    harness_has_unavailable_memory_search_result = False
    transcript_artifact_persisted = False
    runtime_session_created = False
    try:
        if api is not None and hasattr(api.runtime.agent, "session"):
            try:
                api.runtime.agent.session.patch_session_entry(
                    {
                        "agentId": agent_id,
                        "fallbackEntry": {
                            "pluginOwnerId": getattr(api, "id", "active-memory"),
                            "sessionId": subagent_session_id,
                            "sessionFile": runtime_session_file,
                            "updatedAt": int(time.time() * 1000),
                        },
                        "replaceEntry": True,
                        "sessionKey": subagent_session_key,
                        "skipMaintenance": True,
                        "storePath": store_path,
                        "update": lambda _entry, context: (
                            None
                            if context.get("existingEntry")
                            else {
                                "pluginOwnerId": getattr(api, "id", "active-memory"),
                                "sessionId": subagent_session_id,
                                "sessionFile": runtime_session_file,
                                "updatedAt": int(time.time() * 1000),
                            }
                        ),
                    }
                )
            except Exception as exc:
                if "already exists" in str(exc):
                    raise RuntimeError(
                        f"active-memory recall session already exists: {subagent_session_key}"
                    ) from exc
                raise
        runtime_session_created = True
        if callable(params.get("onTranscriptSources")):
            params["onTranscriptSources"](transcript_sources)
        if persisted_dir:
            os.makedirs(persisted_dir, exist_ok=True, mode=0o700)
            with contextlib.suppress(OSError):
                os.chmod(persisted_dir, 0o700)
        prompt = build_recall_prompt(
            {
                "config": config,
                "query": params.get("query", ""),
                "searchQuery": params.get("searchQuery", ""),
            }
        )
        channel_context = resolve_recall_run_channel_context(
            {
                "api": api,
                "agentId": agent_id,
                "sessionKey": parent_session_key,
                "sessionId": params.get("sessionId"),
                "messageProvider": params.get("messageProvider"),
                "channelId": params.get("channelId"),
            }
        )
        embedded_config = apply_active_memory_runtime_config_snapshot(runtime_config, config)
        embedded_timeout_ms = (config.get("timeoutMs") or 0) + (
            config.get("setupGraceTimeoutMs") or 0
        )
        result = await _run_embedded_agent(
            api,
            {
                "sessionId": subagent_session_id,
                "sessionKey": subagent_session_key,
                "agentId": agent_id,
                "sessionTarget": {
                    "agentId": agent_id,
                    "sessionId": subagent_session_id,
                    "sessionKey": subagent_session_key,
                    "storePath": store_path,
                },
                "messageChannel": channel_context.get("messageChannel"),
                "messageProvider": channel_context.get("messageProvider"),
                "sessionFile": runtime_session_file,
                "workspaceDir": workspace_dir,
                "agentDir": agent_dir,
                "config": embedded_config,
                "prompt": prompt,
                "provider": model_ref.get("provider"),
                "model": model_ref.get("model"),
                "lane": ACTIVE_MEMORY_RECALL_LANE,
                "timeoutMs": embedded_timeout_ms,
                "runId": subagent_session_id,
                "trigger": "manual",
                "conversationRecall": params.get("conversationRecall"),
                "toolsAllow": list(config.get("toolsAllow") or ()),
                "disableMessageTool": True,
                "allowGatewaySubagentBinding": True,
                "bootstrapContextMode": "lightweight",
                "verboseLevel": "off",
                "thinkLevel": config.get("thinking") or "off",
                "fastMode": params.get("fastMode"),
                "reasoningLevel": "off",
                "silentExpected": True,
                "authProfileFailurePolicy": "local",
                "cliBackendDispatch": "subscription-auth",
                "cleanupBundleMcpOnRunEnd": True,
                "abortSignal": params.get("abortSignal"),
                "onAgentToolResult": lambda event: _on_tool_result(
                    event,
                    config.get("toolsAllow") or (),
                    _evidence_state(
                        harness_has_usable_memory_result,
                        harness_has_unavailable_memory_search_result,
                    ),
                ),
            },
        )
        active_session_file = (
            read_active_memory_session_file_from_run_result(result) or runtime_session_file
        )
        transcript_sources = collect_active_memory_transcript_sources(
            {
                "runtimeSource": runtime_source,
                "artifactSessionFile": artifact_session_file,
                "activeSessionFile": active_session_file,
                "activeSessionKey": subagent_session_key,
            }
        )
        if callable(params.get("onTranscriptSources")):
            params["onTranscriptSources"](transcript_sources)
        if _abort_signal_aborted(params.get("abortSignal")):
            reason = getattr(params.get("abortSignal"), "reason", None)
            if isinstance(reason, BaseException):
                raise reason
            err = RuntimeError("Operation aborted")
            if reason is not None:
                err = RuntimeError("Operation aborted")
                err.__cause__ = reason
            err.name = "AbortError"
            raise err
        raw_reply = "\n".join(
            text.strip()
            for text in (payload.get("text", "") for payload in (result.get("payloads") or []))
            if text and text.strip()
        ).strip()
        if config.get("persistTranscripts"):
            await persist_active_memory_transcript_artifact(
                {"sources": transcript_sources, "sessionFile": artifact_session_file}
            )
            transcript_artifact_persisted = True
        transcript_state = await read_merged_active_memory_transcript_state(
            {"sources": transcript_sources, "toolsAllow": config.get("toolsAllow") or ()}
        )
        search_debug = transcript_state.get("searchDebug")
        run_result_debug = read_active_memory_search_debug_from_run_result(result)
        if run_result_debug and (
            not isinstance(search_debug, dict) or not search_debug.get("backend")
        ):
            search_debug = run_result_debug
        else:
            search_debug = search_debug or run_result_debug
        return cast(
            RecallSubagentResult,
            {
                "rawReply": raw_reply or "NONE",
                "transcriptPath": (
                    artifact_session_file if config.get("persistTranscripts") else None
                ),
                "searchDebug": search_debug,
                "hasUsableMemoryResult": bool(transcript_state.get("hasUsableMemoryResult"))
                or harness_has_usable_memory_result,
                "hasUnavailableMemorySearchResult": bool(
                    transcript_state.get("hasUnavailableMemorySearchResult")
                )
                or harness_has_unavailable_memory_search_result,
            },
        )
    except BaseException as exc:
        if _abort_signal_aborted(params.get("abortSignal")):
            partial_reply = await read_partial_assistant_text_from_sources(transcript_sources)
            transcript_state = await read_merged_active_memory_transcript_state(
                {"sources": transcript_sources, "toolsAllow": config.get("toolsAllow") or ()}
            )
            attach_partial_timeout_data(
                exc,
                partial_reply,
                transcript_state.get("searchDebug"),
                bool(transcript_state.get("hasUnavailableMemorySearchResult"))
                or harness_has_unavailable_memory_search_result,
            )
        if not _abort_signal_aborted(
            params.get("abortSignal")
        ) and is_missing_registered_memory_tools_error(exc, config.get("toolsAllow") or ()):
            with contextlib.suppress(Exception):
                api.logger.debug(
                    "active-memory: no configured memory tools available; skipping sub-agent"
                )
            return {"rawReply": "NONE", "resultStatus": "unavailable"}
        if not _abort_signal_aborted(params.get("abortSignal")):
            with contextlib.suppress(Exception):
                api.logger.warn(
                    f"active-memory: memory sub-agent failed, skipping recall: "
                    f"{to_single_line_log_value(str(exc))}"
                )
            return {"rawReply": "NONE", "resultStatus": "failed"}
        raise exc
    finally:
        try:
            if runtime_session_created:
                if config.get("persistTranscripts") and not transcript_artifact_persisted:
                    with contextlib.suppress(Exception):
                        await persist_active_memory_transcript_artifact(
                            {
                                "sources": transcript_sources,
                                "sessionFile": artifact_session_file,
                            }
                        )
                with contextlib.suppress(Exception):
                    await cleanup_active_memory_recall_session(
                        {
                            "agentId": agent_id,
                            "sessionId": subagent_session_id,
                            "sessionKey": subagent_session_key,
                            "storePath": store_path,
                        }
                    )
        finally:
            with contextlib.suppress(Exception):
                if transient_workspace and transient_workspace.get("cleanup"):
                    transient_workspace["cleanup"]()


# ── Internal helpers ──────────────────────────────────────────────


def _format_sqlite_session_file_marker(params: dict[str, Any]) -> str:
    """Format a ``sqlite:<agent>:<id>:<store>[:scope]`` marker.

    Mirrors OpenClaw's ``formatSqliteSessionFileMarker``.
    Used to wire the sub-agent's ``sessionFile`` back into
    the host's session store via the runtime registry.
    """
    return f"sqlite:{params['agentId']}:{params['sessionId']}:{params['storePath']}"


def _create_temp_workspace(prefix: str = "jarvis-active-memory-") -> dict[str, Any]:
    """Create a transient workspace dir.

    Mirrors OpenClaw's ``tempWorkspace``. The default
    implementation uses ``tempfile.mkdtemp`` for stdlib
    parity (no external deps).
    """
    import tempfile

    dir_path = tempfile.mkdtemp(prefix=prefix)
    return {
        "dir": dir_path,
        "cleanup": lambda: _safe_rmtree(dir_path),
    }


def _safe_rmtree(path: str) -> None:
    """Best-effort recursive delete."""
    from shutil import rmtree

    with contextlib.suppress(Exception):
        rmtree(path, ignore_errors=True)


def _evidence_state(usable_flag: list[bool], unavailable_flag: list[bool]) -> None:
    """Mutable state container for the harness evidence flags."""
    return


def _on_tool_result(event: Any, tools_allow: tuple | list, _state: Any) -> None:
    """Update the harness-side evidence flags from a tool result event."""
    evidence = read_memory_tool_result_evidence(
        {
            "toolName": event.get("toolName", ""),
            "result": event.get("result"),
            "isError": bool(event.get("isError")),
            "toolsAllow": tools_allow,
        }
    )
    if isinstance(_state, list) and len(_state) >= 2:
        _state[0] = _state[0] or evidence["hasUsableMemoryResult"]
        _state[1] = _state[1] or evidence["hasUnavailableMemorySearchResult"]


def _abort_signal_aborted(abort_signal: Any) -> bool:
    return abort_signal is not None and getattr(abort_signal, "aborted", False)


async def _run_embedded_agent(api: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Default no-op stub for ``api.runtime.agent.runEmbeddedAgent``.

    The host overrides this with the real LLM agent loop.
    Returns a no-payload result so the rest of the recall
    flow can run without a real LLM in the loop.
    """
    if api is None:
        return {"payloads": [], "meta": {}}
    runtime_agent = getattr(getattr(api, "runtime", None), "agent", None)
    runner = getattr(runtime_agent, "run_embedded_agent", None) if runtime_agent else None
    if callable(runner):
        return await runner(params)  # type: ignore[no-any-return]
    return {"payloads": [], "meta": {}}


__all__ = [
    "apply_active_memory_runtime_config_snapshot",
    "cleanup_active_memory_recall_session",
    "collect_active_memory_transcript_sources",
    "persist_active_memory_transcript_artifact",
    "run_recall_subagent",
]
