"""jarvis.agents.embedded_agent_runner.prompt_cache_observability — track prompt-cache snapshot changes.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/prompt-cache-observability.ts``.

Public surface:

- :func:`collect_prompt_cache_tool_names`
- :func:`begin_prompt_cache_observation`
- :func:`complete_prompt_cache_observation`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional


MAX_TRACKERS = 512
MIN_CACHE_BREAK_TOKEN_DROP = 1_000
MAX_STABLE_CACHE_READ_RATIO = 0.95

#: Process-local tracker map.
_TRACKERS: Dict[str, Dict[str, Any]] = {}


# Installable hooks ---------------------------------------------------------

_begin_prompt_cache_observation_hook = None
_complete_prompt_cache_observation_hook = None


def set_begin_prompt_cache_observation_hook(fn) -> None:
    global _begin_prompt_cache_observation_hook
    _begin_prompt_cache_observation_hook = fn


def set_complete_prompt_cache_observation_hook(fn) -> None:
    global _complete_prompt_cache_observation_hook
    _complete_prompt_cache_observation_hook = fn


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _digest_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _build_tracker_key(params: Dict[str, Any]) -> str:
    prompt_cache_key = (params.get("promptCacheKey") or "").strip()
    if prompt_cache_key:
        return prompt_cache_key
    session_key = (params.get("sessionKey") or "").strip()
    if session_key:
        return session_key
    return str(params.get("sessionId") or "")


def _build_tool_digest(tool_names: List[str]) -> str:
    return _digest_text(",".join(sorted(set(tool_names))))


def _set_tracker(key: str, tracker: Dict[str, Any]) -> None:
    if key in _TRACKERS:
        _TRACKERS.pop(key, None)
    elif len(_TRACKERS) >= MAX_TRACKERS:
        oldest_key = next(iter(_TRACKERS), None)
        if isinstance(oldest_key, str):
            _TRACKERS.pop(oldest_key, None)
    _TRACKERS[key] = tracker


def _diff_snapshots(
    previous: Dict[str, Any],
    next_snapshot: Dict[str, Any],
) -> Optional[List[Dict[str, Any]]]:
    changes: List[Dict[str, Any]] = []
    if (
        previous.get("provider") != next_snapshot.get("provider")
        or previous.get("modelId") != next_snapshot.get("modelId")
    ):
        changes.append(
            {
                "code": "model",
                "detail": (
                    f"{previous.get('provider')}/{previous.get('modelId')} -> "
                    f"{next_snapshot.get('provider')}/{next_snapshot.get('modelId')}"
                ),
            }
        )
    elif (previous.get("modelApi") or None) != (next_snapshot.get("modelApi") or None):
        changes.append(
            {
                "code": "model",
                "detail": (
                    f"{previous.get('modelApi') or 'unknown'} -> "
                    f"{next_snapshot.get('modelApi') or 'unknown'}"
                ),
            }
        )
    if previous.get("cacheRetention") != next_snapshot.get("cacheRetention"):
        changes.append(
            {
                "code": "cacheRetention",
                "detail": (
                    f"{previous.get('cacheRetention') or 'default'} -> "
                    f"{next_snapshot.get('cacheRetention') or 'default'}"
                ),
            }
        )
    if previous.get("transport") != next_snapshot.get("transport"):
        changes.append(
            {
                "code": "transport",
                "detail": (
                    f"{previous.get('transport') or 'default'} -> "
                    f"{next_snapshot.get('transport') or 'default'}"
                ),
            }
        )
    if previous.get("streamStrategy") != next_snapshot.get("streamStrategy"):
        changes.append(
            {
                "code": "streamStrategy",
                "detail": (
                    f"{previous.get('streamStrategy')} -> "
                    f"{next_snapshot.get('streamStrategy')}"
                ),
            }
        )
    if previous.get("systemPromptDigest") != next_snapshot.get("systemPromptDigest"):
        changes.append(
            {
                "code": "systemPrompt",
                "detail": "system prompt digest changed",
            }
        )
    if previous.get("toolDigest") != next_snapshot.get("toolDigest"):
        prev_count = previous.get("toolCount", 0)
        next_count = next_snapshot.get("toolCount", 0)
        changes.append(
            {
                "code": "tools",
                "detail": (
                    "tool set changed with same count"
                    if prev_count == next_count
                    else f"{prev_count} -> {next_count} tools"
                ),
            }
        )
    return changes if changes else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect_prompt_cache_tool_names(tools: Any) -> List[str]:
    """Return the trimmed non-empty tool names from a tools iterable."""
    names: List[str] = []
    for tool in tools or []:
        try:
            name = (getattr(tool, "name", None) or (tool.get("name") if isinstance(tool, dict) else None))
            if name:
                name = str(name).strip()
                if name:
                    names.append(name)
        except Exception:
            continue
    return names


def begin_prompt_cache_observation(params: Dict[str, Any]) -> Dict[str, Any]:
    """Start a prompt-cache observation for a session/run key.

    Mirrors :func:`beginPromptCacheObservation` (``prompt-cache-observability.ts``).
    """
    if _begin_prompt_cache_observation_hook is not None:
        return _begin_prompt_cache_observation_hook(params) or {}
    key = _build_tracker_key(params)
    snapshot = {
        "provider": params.get("provider"),
        "modelId": params.get("modelId"),
        "modelApi": params.get("modelApi"),
        "cacheRetention": params.get("cacheRetention"),
        "streamStrategy": params.get("streamStrategy"),
        "transport": params.get("transport"),
        "systemPromptDigest": _digest_text(params.get("systemPrompt") or ""),
        "toolDigest": _build_tool_digest(params.get("toolNames") or []),
        "toolCount": len(params.get("toolNames") or []),
        "toolNames": list(params.get("toolNames") or []),
    }
    previous = _TRACKERS.get(key)
    changes = _diff_snapshots(previous["snapshot"], snapshot) if previous else None
    _set_tracker(
        key,
        {
            "snapshot": snapshot,
            "lastCacheRead": previous.get("lastCacheRead") if previous else None,
            "pendingChanges": changes,
        },
    )
    return {
        "snapshot": snapshot,
        "changes": changes,
        "previousCacheRead": previous.get("lastCacheRead") if previous else None,
    }


def complete_prompt_cache_observation(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Complete a prompt-cache observation and detect a meaningful cache break.

    Mirrors :func:`completePromptCacheObservation` (``prompt-cache-observability.ts``).
    """
    if _complete_prompt_cache_observation_hook is not None:
        return _complete_prompt_cache_observation_hook(params)
    key = _build_tracker_key(params)
    tracker = _TRACKERS.get(key)
    if not tracker:
        return None
    usage = params.get("usage") if isinstance(params.get("usage"), dict) else None
    cache_read = usage.get("cacheRead") if usage else None
    if not isinstance(cache_read, (int, float)) or cache_read <= 0:
        tracker["pendingChanges"] = None
        return None
    previous_cache_read = tracker.get("lastCacheRead")
    tracker["lastCacheRead"] = cache_read
    if previous_cache_read is None or previous_cache_read <= 0:
        tracker["pendingChanges"] = None
        return None
    token_drop = previous_cache_read - cache_read
    has_meaningful_drop = (
        cache_read < previous_cache_read * MAX_STABLE_CACHE_READ_RATIO
        and token_drop >= MIN_CACHE_BREAK_TOKEN_DROP
    )
    if not has_meaningful_drop:
        tracker["pendingChanges"] = None
        return None
    result = {
        "previousCacheRead": previous_cache_read,
        "cacheRead": cache_read,
        "changes": tracker.get("pendingChanges"),
    }
    tracker["pendingChanges"] = None
    return result


__all__ = [
    "collect_prompt_cache_tool_names",
    "begin_prompt_cache_observation",
    "complete_prompt_cache_observation",
    "set_begin_prompt_cache_observation_hook",
    "set_complete_prompt_cache_observation_hook",
]
