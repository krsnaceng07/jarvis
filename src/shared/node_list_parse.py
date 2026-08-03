"""jarvis.shared.node_list_parse — pairing list / node list parsers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/node-list-parse.ts``.
"""
from __future__ import annotations

from typing import Any, List, Optional

from .node_list_types import NodeListNode, PairedNode, PairingList, PendingRequest


def _normalize_optional_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None


def _normalize_pending_request(row: Any) -> Optional[PendingRequest]:
    if not isinstance(row, dict):
        return None
    request_id = _normalize_optional_string(row.get("requestId"))
    node_id = _normalize_optional_string(row.get("nodeId"))
    if request_id is None or node_id is None:
        return None
    out: PendingRequest = {"requestId": request_id, "nodeId": node_id}
    for k in ("displayName", "platform", "version", "coreVersion", "uiVersion", "remoteIp"):
        v = _normalize_optional_string(row.get(k))
        if v is not None:
            out[k] = v  # type: ignore[literal-required]
    return out


def _normalize_paired_node(row: Any) -> Optional[PairedNode]:
    if not isinstance(row, dict):
        return None
    node_id = _normalize_optional_string(row.get("nodeId"))
    if node_id is None:
        return None
    out: PairedNode = {"nodeId": node_id}
    for k in (
        "displayName",
        "platform",
        "version",
        "coreVersion",
        "uiVersion",
        "remoteIp",
        "lastSeenReason",
    ):
        v = _normalize_optional_string(row.get(k))
        if v is not None:
            out[k] = v  # type: ignore[literal-required]
    return out


def parse_pairing_list(value: Any) -> PairingList:
    """Extract normalized pending and paired node arrays from a payload.

    Mirrors :func:`parsePairingList` (``shared/node-list-parse.ts``).
    """
    obj = value if isinstance(value, dict) else {}
    pending_raw = obj.get("pending") if isinstance(obj, dict) else None
    paired_raw = obj.get("paired") if isinstance(obj, dict) else None
    pending: List[PendingRequest] = []
    paired: List[PairedNode] = []
    if isinstance(pending_raw, list):
        for r in pending_raw:
            n = _normalize_pending_request(r)
            if n is not None:
                pending.append(n)
    if isinstance(paired_raw, list):
        for r in paired_raw:
            n = _normalize_paired_node(r)
            if n is not None:
                paired.append(n)
    return {"pending": pending, "paired": paired}


def parse_node_list(value: Any) -> List[NodeListNode]:
    """Extract the ``nodes`` array from a node.list response, treating
    malformed payloads as empty.

    Mirrors :func:`parseNodeList` (``shared/node-list-parse.ts``).
    """
    obj = value if isinstance(value, dict) else {}
    raw = obj.get("nodes") if isinstance(obj, dict) else None
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    return []


__all__ = ["parse_pairing_list", "parse_node_list"]
