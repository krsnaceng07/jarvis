"""jarvis.shared.node_resolve — node resolution from lists.

OpenClaw parity: mirrors ``openclaw-main/src/shared/node-resolve.ts``.
"""
from __future__ import annotations

from typing import Callable, List, Optional, TypeVar

from .node_match import NodeMatchCandidate, resolve_node_id_from_candidates

TNode = TypeVar("TNode", bound=NodeMatchCandidate)


def resolve_node_id_from_node_list(
    nodes: List[TNode],
    query: Optional[str] = None,
    options: Optional[dict] = None,
) -> str:
    """Resolve a user query to a node id, optionally via a default picker.

    Mirrors :func:`resolveNodeIdFromNodeList` (``shared/node-resolve.ts``).
    """
    options = options or {}
    q = (query or "").strip() if isinstance(query, str) else ""
    allow_default = options.get("allow_default")
    if allow_default is None:
        allow_default = options.get("allowDefault")
    compact = options.get("allow_compact_display_name")
    if compact is None:
        compact = options.get("allowCompactDisplayName")
    picker = options.get("pick_default_node")
    if picker is None:
        picker = options.get("pickDefaultNode")
    if not q:
        if allow_default is True and callable(picker):
            picked = picker(nodes)
            if picked is not None:
                return picked["nodeId"]
        raise ValueError("node required")
    return resolve_node_id_from_candidates(nodes, q, bool(compact))


def resolve_node_from_node_list(
    nodes: List[TNode],
    query: Optional[str] = None,
    options: Optional[dict] = None,
) -> TNode:
    """Resolve a full node entry, preserving synthetic defaults.

    Mirrors :func:`resolveNodeFromNodeList` (``shared/node-resolve.ts``).
    """
    node_id = resolve_node_id_from_node_list(nodes, query, options)
    for node in nodes:
        if node.get("nodeId") == node_id:
            return node
    return {"nodeId": node_id}  # type: ignore[return-value]


__all__ = ["resolve_node_id_from_node_list", "resolve_node_from_node_list"]
