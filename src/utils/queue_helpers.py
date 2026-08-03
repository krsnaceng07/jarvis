"""jarvis.utils.queue_helpers — shared queue overflow, debounce, and collection helpers.

OpenClaw parity: mirrors ``openclaw-main/src/utils/queue-helpers.ts``.

Public surface:

- :func:`preview_queue_summary_prompt`
- :func:`apply_queue_runtime_settings`
- :func:`should_skip_queue_item`
- :func:`count_pending_queue_items`
- :func:`drain_queue_items`
- :func:`summarize_dropped_queue_items`
- :func:`build_queue_summary_prompt`
- :func:`resolve_debounce_ms`
- :func:`merge_queue_summary`
- :func:`drain_queue_collection`

Phase 8.1 — focused minimal port of OpenClaw ``queue-helpers.ts``.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Set


# Installable hooks ---------------------------------------------------------

_drain_queue_items_hook = None
_summarize_dropped_queue_items_hook = None
_build_queue_summary_prompt_hook = None
_resolve_debounce_ms_hook = None
_merge_queue_summary_hook = None
_drain_queue_collection_hook = None
_preview_queue_summary_prompt_hook = None
_apply_queue_runtime_settings_hook = None
_should_skip_queue_item_hook = None
_count_pending_queue_items_hook = None


def set_drain_queue_items_hook(fn) -> None:
    global _drain_queue_items_hook
    _drain_queue_items_hook = fn


def set_summarize_dropped_queue_items_hook(fn) -> None:
    global _summarize_dropped_queue_items_hook
    _summarize_dropped_queue_items_hook = fn


def set_build_queue_summary_prompt_hook(fn) -> None:
    global _build_queue_summary_prompt_hook
    _build_queue_summary_prompt_hook = fn


def set_resolve_debounce_ms_hook(fn) -> None:
    global _resolve_debounce_ms_hook
    _resolve_debounce_ms_hook = fn


def set_merge_queue_summary_hook(fn) -> None:
    global _merge_queue_summary_hook
    _merge_queue_summary_hook = fn


def set_drain_queue_collection_hook(fn) -> None:
    global _drain_queue_collection_hook
    _drain_queue_collection_hook = fn


def set_preview_queue_summary_prompt_hook(fn) -> None:
    global _preview_queue_summary_prompt_hook
    _preview_queue_summary_prompt_hook = fn


def set_apply_queue_runtime_settings_hook(fn) -> None:
    global _apply_queue_runtime_settings_hook
    _apply_queue_runtime_settings_hook = fn


def set_should_skip_queue_item_hook(fn) -> None:
    global _should_skip_queue_item_hook
    _should_skip_queue_item_hook = fn


def set_count_pending_queue_items_hook(fn) -> None:
    global _count_pending_queue_items_hook
    _count_pending_queue_items_hook = fn


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _elide_queue_text(text: str, limit: int = 140) -> str:
    if len(text) <= limit:
        return text
    truncated = text[: max(0, limit - 1)].rstrip()
    return f"{truncated}…"


def _build_queue_summary_line(text: str, limit: int = 160) -> str:
    cleaned = " ".join(text.split()).strip()
    return _elide_queue_text(cleaned, limit)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def preview_queue_summary_prompt(
    params: Dict[str, Any],
) -> Optional[str]:
    """Build a summary prompt preview without mutating the source queue state.

    Mirrors :func:`previewQueueSummaryPrompt` (``utils/queue-helpers.ts``).
    """
    if _preview_queue_summary_prompt_hook is not None:
        v = _preview_queue_summary_prompt_hook(params)
        return v
    return build_queue_summary_prompt(params)


def build_queue_summary_prompt(params: Dict[str, Any]) -> Optional[str]:
    """Build the human-facing prompt that announces dropped items.

    Mirrors :func:`buildQueueSummaryPrompt` (``utils/queue-helpers.ts``).
    """
    if _build_queue_summary_prompt_hook is not None:
        v = _build_queue_summary_prompt_hook(params)
        return v
    state = params.get("state") if isinstance(params.get("state"), dict) else {}
    noun = params.get("noun", "item")
    title = params.get("title")
    if not state or state.get("droppedCount", 0) <= 0:
        return None
    summary_lines = state.get("summaryLines") or []
    if not summary_lines:
        return None
    head = title or f"Earlier {noun}s were dropped from the queue."
    bullets = "\n".join(f"- {line}" for line in summary_lines[:3])
    return f"{head}\n\n{bullets}"


def apply_queue_runtime_settings(params: Dict[str, Any]) -> None:
    """Apply runtime queue settings while preserving previous values for omitted fields.

    Mirrors :func:`applyQueueRuntimeSettings` (``utils/queue-helpers.ts``).
    """
    if _apply_queue_runtime_settings_hook is not None:
        _apply_queue_runtime_settings_hook(params)
        return
    target = params.get("target") if isinstance(params.get("target"), dict) else None
    settings = params.get("settings") if isinstance(params.get("settings"), dict) else None
    if not target or not settings:
        return
    target["mode"] = settings.get("mode", target.get("mode"))
    if isinstance(settings.get("debounceMs"), (int, float)):
        target["debounceMs"] = max(0, int(settings["debounceMs"]))
    if isinstance(settings.get("cap"), (int, float)) and settings["cap"] > 0:
        target["cap"] = int(settings["cap"])
    if settings.get("dropPolicy") is not None:
        target["dropPolicy"] = settings["dropPolicy"]


def should_skip_queue_item(params: Dict[str, Any]) -> bool:
    """Run optional duplicate detection before an item enters a queue.

    Mirrors :func:`shouldSkipQueueItem` (``utils/queue-helpers.ts``).
    """
    if _should_skip_queue_item_hook is not None:
        return bool(_should_skip_queue_item_hook(params))
    dedupe = params.get("dedupe")
    if not callable(dedupe):
        return False
    return bool(dedupe(params.get("item"), params.get("items") or []))


def count_pending_queue_items(
    items: Optional[Iterable[Any]],
    in_flight: Optional[Set[Any]] = None,
) -> int:
    """Count identities that are still pending in the queue, excluding in-flight ones.

    Mirrors :func:`countPendingQueueItems` (``utils/queue-helpers.ts``).
    """
    if _count_pending_queue_items_hook is not None:
        return int(_count_pending_queue_items_hook({"items": items, "inFlight": in_flight}))
    if not items:
        return 0
    if not in_flight:
        return sum(1 for _ in items)
    return sum(1 for item in items if item not in in_flight)


def resolve_debounce_ms(value: Any, default_ms: int = 0) -> int:
    """Resolve a debounce-ms input into a non-negative integer.

    Mirrors :func:`resolveDebounceMs` (``utils/queue-helpers.ts``).
    """
    if _resolve_debounce_ms_hook is not None:
        return int(_resolve_debounce_ms_hook({"value": value, "defaultMs": default_ms}))
    if isinstance(value, (int, float)) and value == value and value >= 0:
        return int(value)
    return max(0, int(default_ms or 0))


def summarize_dropped_queue_items(
    items: List[Dict[str, Any]],
    limit: int = 3,
) -> List[str]:
    """Summarize dropped items as one short line each.

    Mirrors :func:`summarizeDroppedQueueItems` (``utils/queue-helpers.ts``).
    """
    if _summarize_dropped_queue_items_hook is not None:
        v = _summarize_dropped_queue_items_hook({"items": items, "limit": limit})
        return v if isinstance(v, list) else []
    out: List[str] = []
    for entry in items[: max(1, int(limit))]:
        if not isinstance(entry, dict):
            continue
        text = entry.get("text") or entry.get("summary") or entry.get("preview") or ""
        out.append(_build_queue_summary_line(str(text)))
    return out


def merge_queue_summary(
    state: Optional[Dict[str, Any]],
    dropped_items: List[Dict[str, Any]],
    limit: int = 3,
) -> Dict[str, Any]:
    """Merge dropped items into a queue summary state.

    Mirrors :func:`mergeQueueSummary` (``utils/queue-helpers.ts``).
    """
    if _merge_queue_summary_hook is not None:
        v = _merge_queue_summary_hook({"state": state, "droppedItems": dropped_items, "limit": limit})
        return v if isinstance(v, dict) else {}
    base = dict(state) if isinstance(state, dict) else {}
    base.setdefault("droppedCount", 0)
    base.setdefault("summaryLines", [])
    base["droppedCount"] = int(base.get("droppedCount") or 0) + len(dropped_items)
    base["summaryLines"] = summarize_dropped_queue_items(dropped_items, limit)
    return base


def drain_queue_items(
    items: List[Any],
    sink: Callable[[Any], None],
    *,
    cap: Optional[int] = None,
    drop_policy: str = "summarize",
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Drain a queue into ``sink`` honoring the cap and drop policy.

    Mirrors :func:`drainQueueItems` (``utils/queue-helpers.ts``).
    """
    if _drain_queue_items_hook is not None:
        v = _drain_queue_items_hook(
            {"items": items, "sink": sink, "cap": cap, "dropPolicy": drop_policy, "state": state}
        )
        return v if isinstance(v, dict) else {}
    summary_state: Dict[str, Any] = {
        "dropPolicy": drop_policy,
        "droppedCount": 0,
        "summaryLines": [],
    }
    if state is not None:
        summary_state.update(state)
    delivered: List[Any] = []
    if cap is not None and cap > 0 and len(items) > cap:
        overflow = len(items) - cap
        if drop_policy == "summarize":
            summary_state = merge_queue_summary(
                summary_state, [{"text": str(item)} for item in items[cap:]], 3
            )
        elif drop_policy == "old":
            summary_state["droppedCount"] += overflow
        elif drop_policy == "new":
            items = items[:cap]
            summary_state["droppedCount"] += overflow
    for item in items[: cap] if cap else items:
        try:
            sink(item)
            delivered.append(item)
        except Exception:
            summary_state["droppedCount"] += 1
    summary_state["summaryLines"] = summary_state.get("summaryLines", [])[:3]
    return {
        "delivered": delivered,
        "summary": summary_state,
    }


def drain_queue_collection(
    items_by_source: Dict[str, List[Any]],
    sink: Callable[[str, Any], None],
    *,
    cap_per_source: Optional[int] = None,
    drop_policy: str = "summarize",
) -> Dict[str, Dict[str, Any]]:
    """Drain a per-source queue collection, preserving source order.

    Mirrors :func:`drainQueueCollection` (``utils/queue-helpers.ts``).
    """
    if _drain_queue_collection_hook is not None:
        v = _drain_queue_collection_hook(
            {"itemsBySource": items_by_source, "sink": sink, "capPerSource": cap_per_source, "dropPolicy": drop_policy}
        )
        return v if isinstance(v, dict) else {}
    results: Dict[str, Dict[str, Any]] = {}
    for source, items in items_by_source.items():
        per_source_sink = lambda item, _src=source, _s=sink: _s(_src, item)
        results[source] = drain_queue_items(
            items,
            per_source_sink,
            cap=cap_per_source,
            drop_policy=drop_policy,
        )
    return results


__all__ = [
    "preview_queue_summary_prompt",
    "build_queue_summary_prompt",
    "apply_queue_runtime_settings",
    "should_skip_queue_item",
    "count_pending_queue_items",
    "resolve_debounce_ms",
    "summarize_dropped_queue_items",
    "merge_queue_summary",
    "drain_queue_items",
    "drain_queue_collection",
    "set_drain_queue_items_hook",
    "set_summarize_dropped_queue_items_hook",
    "set_build_queue_summary_prompt_hook",
    "set_resolve_debounce_ms_hook",
    "set_merge_queue_summary_hook",
    "set_drain_queue_collection_hook",
    "set_preview_queue_summary_prompt_hook",
    "set_apply_queue_runtime_settings_hook",
    "set_should_skip_queue_item_hook",
    "set_count_pending_queue_items_hook",
]
