"""session — canonical session key, recall-run channel context, status lines.

OpenClaw parity: mirrors ``extensions/active-memory/session.ts``.

Phase 4.2b step 2: ports the session-lookup helpers and the
debug / status-line persistence used by the recall loop to
leave a trail in the session registry after every recall
attempt.

Surface
-------
- ``resolve_canonical_session_key_from_session_id`` —
  walk the agent's session entries, return the
  ``sessionKey`` of the most recently updated entry whose
  ``sessionId`` matches. Returns ``None`` when no match or
  the registry raises.
- ``resolve_recall_run_channel_context`` — given the
  current ``messageProvider`` / ``channelId`` /
  ``sessionKey`` / ``sessionId``, resolve the
  ``{messageChannel, messageProvider}`` to pass to the
  embedded recall sub-agent. Skips scoped conversation ids
  (``":"`` / ``"/"``) so the bundled-plugin dirName
  validation doesn't throw.
- ``resolve_status_update_agent_id`` — extract the agent
  id from a status-update context (explicit, or parsed
  from the session key).
- ``format_elapsed_ms_compact`` — render an elapsed-ms
  value as ``"120ms"`` / ``"1.5s"`` / ``"0ms"``.
- ``build_plugin_status_line`` / ``build_persisted_debug_summary`` —
  format the status line and the debug summary that
  ``persistPluginStatusLines`` writes back to the session.
- ``persist_plugin_status_lines`` — write
  ``{pluginId: "active-memory", lines: [...]}`` to the
  session's ``pluginDebugEntries`` via
  ``api.runtime.agent.session.patchSessionEntry``. Skips
  silently when no lines are available and no existing
  entry to update.

Dependencies
============
- ``extensions.active_memory.types`` — recall-flow types
  and constants.
- ``jarvis_sdk.normalize_optional_string`` +
  ``unique_strings`` (string-coerce).
"""

from __future__ import annotations

import contextlib
import math
import re
from typing import Any

from jarvis_sdk import normalize_optional_string, unique_strings

from .types import (
    ACTIVE_MEMORY_DEBUG_PREFIX,
    ACTIVE_MEMORY_STATUS_PREFIX,
    ActiveMemorySearchDebug,
    ActiveRecallResult,
    PluginDebugEntry,
    ResolvedActiveRecallPluginConfig,
)

_AGENT_KEY_RE = re.compile(r"^agent:([^:]+):", re.IGNORECASE)
_DEBUG_LINE_LOG_PREFIX = "active-memory"


# ── Canonical session key ────────────────────────────────────────


def resolve_canonical_session_key_from_session_id(params: dict[str, Any]) -> str | None:
    """Walk the agent's session entries, return the most recent match.

    Mirrors OpenClaw's
    ``resolveCanonicalSessionKeyFromSessionId``. The
    matching entry's ``updatedAt`` is used to break ties.
    Returns ``None`` when no entry matches or the registry
    raises.
    """
    session_id = (params.get("sessionId") or "").strip()
    if not session_id:
        return None
    api = params.get("api")
    if api is None:
        return None
    try:
        entries = api.runtime.agent.session.list_session_entries(
            {"agentId": params.get("agentId", "")}
        )
    except Exception:
        return None
    best_match: dict[str, Any] | None = None
    for pair in entries or ():
        if not isinstance(pair, tuple) or len(pair) != 2:
            continue
        session_key, entry = pair
        if not entry or not isinstance(entry, dict):
            continue
        candidate_session_id = (entry.get("sessionId") or "").strip()
        if isinstance(entry.get("sessionId"), str) and candidate_session_id == session_id:
            raw_updated_at = entry.get("updatedAt")
            updated_at = raw_updated_at if isinstance(raw_updated_at, int | float) else 0
            if best_match is None or updated_at > best_match["updatedAt"]:
                best_match = {"sessionKey": session_key, "updatedAt": updated_at}
    if best_match is None:
        return None
    canonical = (best_match["sessionKey"] or "").strip()
    return canonical or None


# ── Recall run channel context ────────────────────────────────────


def _is_runnable_channel_name(channel: str) -> bool:
    """Scoped conversation ids (":" or "/") aren't runnable channel names."""
    return ":" not in channel and "/" not in channel


def resolve_recall_run_channel_context(params: dict[str, Any]) -> dict[str, str | None]:
    """Resolve the channel context for the embedded recall sub-agent.

    Mirrors OpenClaw's ``resolveRecallRunChannelContext``.
    Returns ``{"messageChannel": ..., "messageProvider": ...}``.
    Falls back to ``{}`` when no session key resolves.
    """
    explicit_channel = normalize_optional_string(params.get("channelId"))
    explicit_provider = normalize_optional_string(params.get("messageProvider"))
    runnable_explicit_channel = (
        explicit_channel
        if explicit_channel and _is_runnable_channel_name(explicit_channel)
        else None
    )
    trusted_explicit_channel = (
        runnable_explicit_channel
        if runnable_explicit_channel
        and runnable_explicit_channel != explicit_provider
        and (not explicit_provider or explicit_provider == "webchat")
        else None
    )

    def _resolve_return(params_local: dict[str, Any]) -> dict[str, str | None]:
        trusted_resolved_channel = (
            params_local.get("resolvedChannel")
            if params_local.get("resolvedChannelStrength") == "strong"
            else None
        )
        channel = (
            trusted_explicit_channel
            or trusted_resolved_channel
            or explicit_provider
            or runnable_explicit_channel
            or params_local.get("resolvedChannel")
        )
        return {"messageChannel": channel, "messageProvider": channel}

    api = params.get("api")
    resolved_session_key = normalize_optional_string(params.get("sessionKey")) or (
        resolve_canonical_session_key_from_session_id(
            {
                "api": api,
                "agentId": params.get("agentId", ""),
                "sessionId": params.get("sessionId"),
            }
        )
        if api is not None
        else None
    )
    if not resolved_session_key:
        return _resolve_return({})
    if api is None:
        return _resolve_return({})
    try:
        session_entry = api.runtime.agent.session.get_session_entry(
            {
                "agentId": params.get("agentId", ""),
                "sessionKey": resolved_session_key,
            }
        )
    except Exception:
        return _resolve_return({})
    if not isinstance(session_entry, dict):
        return _resolve_return({})
    raw_strong = normalize_optional_string(
        session_entry.get("lastChannel")
    ) or normalize_optional_string(session_entry.get("channel"))
    strong_entry_channel = (
        raw_strong if raw_strong and _is_runnable_channel_name(raw_strong) else None
    )
    origin = session_entry.get("origin") if isinstance(session_entry.get("origin"), dict) else None
    weak_entry_channel = (
        normalize_optional_string((origin or {}).get("provider")) if origin else None
    )
    resolved_channel = strong_entry_channel or weak_entry_channel
    return _resolve_return(
        {
            "resolvedChannel": resolved_channel,
            "resolvedChannelStrength": "strong"
            if strong_entry_channel
            else ("weak" if weak_entry_channel else None),
        }
    )


# ── Status update agent id ────────────────────────────────────────


def resolve_status_update_agent_id(ctx: dict[str, Any]) -> str:
    """Pick the agent id for a status update.

    Mirrors OpenClaw's ``resolveStatusUpdateAgentId``. Falls
    back to the agent id parsed from the session key
    (``agent:<id>:...``), or ``""``.
    """
    explicit = (ctx.get("agentId") or "").strip() if isinstance(ctx.get("agentId"), str) else ""
    if explicit:
        return explicit
    raw_key = ctx.get("sessionKey")
    session_key = raw_key.strip() if isinstance(raw_key, str) and raw_key else ""
    if not session_key:
        return ""
    match = _AGENT_KEY_RE.match(session_key)
    return (match.group(1).strip() if match else "") or ""


# ── Elapsed-ms formatting ────────────────────────────────────────


def format_elapsed_ms_compact(elapsed_ms: int | float) -> str:
    """Render an elapsed-ms value as a short string.

    Mirrors OpenClaw's ``formatElapsedMsCompact``:
    ``<= 0`` → ``"0ms"``; ``>= 1000`` → ``"1.5s"``
    (1-decimal when fractional, integer otherwise);
    otherwise ``"<n>ms"``.
    """
    if not isinstance(elapsed_ms, int | float) or math.isnan(elapsed_ms) or elapsed_ms <= 0:
        return "0ms"
    if elapsed_ms >= 1000:
        seconds = elapsed_ms / 1000
        if seconds % 1 == 0:
            return f"{seconds:.0f}s"
        return f"{seconds:.1f}s"
    return f"{round(elapsed_ms)}ms"


# ── Status line + debug summary builders ──────────────────────────


def build_plugin_status_line(params: dict[str, Any]) -> str:
    """Format the per-recall status line.

    Mirrors OpenClaw's ``buildPluginStatusLine``. Includes
    ``status``, ``elapsed`` (compact), ``query=<queryMode>``,
    and ``summary=<n> chars`` if a non-empty summary is
    present.
    """
    result: ActiveRecallResult = params["result"]
    config: ResolvedActiveRecallPluginConfig = params["config"]
    parts = [
        ACTIVE_MEMORY_STATUS_PREFIX,
        f"status={result.get('status', 'unknown')}",
        f"elapsed={format_elapsed_ms_compact(result.get('elapsedMs', 0))}",
        f"query={config.get('queryMode', 'recent')}",
    ]
    summary = result.get("summary")
    if summary and len(summary) > 0:
        parts.append(f"summary={len(summary)} chars")
    return " ".join(parts)


def build_persisted_debug_summary(result: ActiveRecallResult) -> str | None:
    """Format the debug summary for persistence.

    Mirrors OpenClaw's ``buildPersistedDebugSummary``.
    ``timeout_partial`` gets a special marker noting the
    chars were not persisted.
    """
    if result.get("status") == "timeout_partial":
        summary = result.get("summary") or ""
        return f"timeout_partial: {len(summary)} chars recovered (not persisted)"
    return result.get("summary")


# ── Sanitize + debug line + persist ──────────────────────────────


def sanitize_debug_text(text: str) -> str:
    """Strip control characters + collapse whitespace.

    Mirrors OpenClaw's ``sanitizeDebugText``. Used to
    prevent stored debug values from injecting terminal
    control codes.
    """
    if not text:
        return ""
    sanitized_chars: list[str] = []
    for ch in text:
        code = ord(ch)
        is_control = (0x00 <= code <= 0x1F) or (0x7F <= code <= 0x9F)
        if not is_control:
            sanitized_chars.append(ch)
    return re.sub(r"\s+", " ", "".join(sanitized_chars)).strip()


def build_plugin_debug_line(params: dict[str, Any]) -> str | None:
    """Format the per-recall debug line.

    Mirrors OpenClaw's ``buildPluginDebugLine``. Returns
    ``None`` when no useful debug info is available.
    """
    summary = sanitize_debug_text(params.get("summary") or "")
    search_debug: ActiveMemorySearchDebug | dict[str, Any] | None = params.get("searchDebug")
    if not isinstance(search_debug, dict):
        search_debug = {}
    warning = sanitize_debug_text(search_debug.get("warning") or "")
    action = sanitize_debug_text(search_debug.get("action") or "")
    error = sanitize_debug_text(search_debug.get("error") or "")
    debug_parts: list[str] = []
    backend = sanitize_debug_text(search_debug.get("backend") or "")
    if backend:
        debug_parts.append(f"backend={backend}")
    configured_mode = sanitize_debug_text(search_debug.get("configuredMode") or "")
    if configured_mode:
        debug_parts.append(f"configuredMode={configured_mode}")
    effective_mode = sanitize_debug_text(search_debug.get("effectiveMode") or "")
    if effective_mode:
        debug_parts.append(f"effectiveMode={effective_mode}")
    fallback = sanitize_debug_text(search_debug.get("fallback") or "")
    if fallback:
        debug_parts.append(f"fallback={fallback}")
    search_ms = search_debug.get("searchMs")
    if isinstance(search_ms, int | float) and not math.isnan(search_ms):
        debug_parts.append(f"searchMs={max(0, round(search_ms))}")
    hits = search_debug.get("hits")
    if isinstance(hits, int | float) and not math.isnan(hits):
        debug_parts.append(f"hits={max(0, int(hits))}")
    prefix = " ".join(debug_parts)
    warning_action = (
        f"{warning} {action}"
        if warning and action and not summary
        else " | ".join(
            value
            for value in (
                warning,
                action if not summary else "",
            )
            if value
        )
    )
    messages = " | ".join(
        unique_strings([warning_action, summary] if not warning_action else [summary])
        if not warning_action
        else unique_strings([warning_action])
    )
    if prefix and messages:
        return f"{ACTIVE_MEMORY_DEBUG_PREFIX} {prefix} | {messages}"
    if prefix:
        return f"{ACTIVE_MEMORY_DEBUG_PREFIX} {prefix}"
    if messages:
        return f"{ACTIVE_MEMORY_DEBUG_PREFIX} {messages}"
    fallback_text = warning or summary or error
    if fallback_text:
        return f"{ACTIVE_MEMORY_DEBUG_PREFIX} {fallback_text}"
    return None


async def persist_plugin_status_lines(params: dict[str, Any]) -> None:
    """Write the active-memory status + debug lines to the session.

    Mirrors OpenClaw's ``persistPluginStatusLines``. Silently
    returns if there's no ``sessionKey``; raises
    ``api.logger.debug`` if the host's ``patchSessionEntry``
    rejects the update.
    """
    session_key = (params.get("sessionKey") or "").strip()
    if not session_key:
        return
    debug_line = build_plugin_debug_line(
        {
            "summary": params.get("debugSummary"),
            "searchDebug": params.get("searchDebug"),
        }
    )
    agent_id = (params.get("agentId") or "").strip()
    status_line = params.get("statusLine")
    api = params.get("api")
    if not agent_id and (status_line or debug_line):
        return
    if api is None:
        return
    try:
        if not status_line and not debug_line:
            existing = api.runtime.agent.session.get_session_entry(
                {"agentId": agent_id, "sessionKey": session_key}
            )
            existing_entries = (
                existing.get("pluginDebugEntries") if isinstance(existing, dict) else None
            )
            if not isinstance(existing_entries, list):
                return
            if not any(
                isinstance(entry, dict) and entry.get("pluginId") == _DEBUG_LINE_LOG_PREFIX
                for entry in existing_entries
            ):
                return

        def _update(existing: Any) -> dict[str, Any]:
            existing_dict = existing if isinstance(existing, dict) else {}
            previous_entries = existing_dict.get("pluginDebugEntries")
            kept: list[PluginDebugEntry] = []
            if isinstance(previous_entries, list):
                for entry in previous_entries:
                    if (
                        isinstance(entry, dict)
                        and isinstance(entry.get("pluginId"), str)
                        and entry.get("pluginId") != _DEBUG_LINE_LOG_PREFIX
                    ):
                        kept.append(entry)  # type: ignore[arg-type]
            next_lines: list[str] = []
            if status_line:
                next_lines.append(status_line)
            if debug_line:
                next_lines.append(debug_line)
            if next_lines:
                kept.append(
                    {"pluginId": _DEBUG_LINE_LOG_PREFIX, "lines": next_lines}  # type: ignore[arg-type]
                )
            return {"pluginDebugEntries": kept if kept else None}

        await api.runtime.agent.session.patch_session_entry(
            {
                "agentId": agent_id,
                "sessionKey": session_key,
                "preserveActivity": True,
                "update": _update,
            }
        )
    except Exception as exc:
        with contextlib.suppress(Exception):
            api.logger.debug(
                f"{_DEBUG_LINE_LOG_PREFIX}: failed to persist session status note "
                f"({exc.__class__.__name__}: {exc})"
            )


__all__ = [
    "build_persisted_debug_summary",
    "build_plugin_debug_line",
    "build_plugin_status_line",
    "format_elapsed_ms_compact",
    "persist_plugin_status_lines",
    "resolve_canonical_session_key_from_session_id",
    "resolve_recall_run_channel_context",
    "resolve_status_update_agent_id",
    "sanitize_debug_text",
]
