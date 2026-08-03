"""jarvis.shared.node_match — node-match scoring and selection.

OpenClaw parity: mirrors ``openclaw-main/src/shared/node-match.ts``.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, TypedDict


class NodeMatchCandidate(TypedDict, total=False):
    """Fields accepted by shared CLI/API node-selection helpers.

    Mirrors :type:`NodeMatchCandidate` (``shared/node-match.ts``).
    """
    nodeId: str
    displayName: str
    remoteIp: str
    connected: bool
    clientId: str


class ScoredNodeMatch(TypedDict, total=False):
    node: NodeMatchCandidate
    matchScore: int
    selectionScore: int


def _normalize_lower(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _normalize_node_key(value: str) -> str:
    """Normalize a human node name into a stable fuzzy lookup key.

    Mirrors ``normalizeNodeKey`` (``shared/node-match.ts``).
    """
    nfc = unicodedata.normalize("NFC", value or "")
    # Drop emoji_component marks (variation selectors, keycaps) — but only
    # when preceded by another mark (preserve script marks on letters).
    out_chars: list = []
    prev_category = None
    for ch in nfc:
        cat = unicodedata.category(ch)
        # 'Mn' = nonspacing mark, 'Me' = enclosing mark, 'Mc' = spacing mark.
        is_mark = cat.startswith("M")
        # Drop "mark" only when NOT preceded by a letter/number (keep script marks
        # attached to surviving letters). Also drop emoji-component marks always.
        if is_mark:
            if prev_category not in ("L", "N", "M"):
                continue
        out_chars.append(ch)
        prev_category = "L" if cat.startswith("L") else ("N" if cat.startswith("N") else cat[:1])
    s = "".join(out_chars)
    # Replace any non-letter/non-mark/non-number with "-".
    s = "".join(ch if (ch.isalnum() or unicodedata.category(ch).startswith("M")) else "-" for ch in s)
    s = re.sub(r"^-+", "", s)
    s = re.sub(r"-+$", "", s)
    return s.lower()


def _compact_normalized_node_key(value: str) -> str:
    return value.replace("-", "")


def _list_known_nodes(nodes: List[NodeMatchCandidate]) -> str:
    return ", ".join(
        n.get("displayName") or n.get("remoteIp") or n.get("nodeId", "")
        for n in nodes
    )


def _format_node_candidate_label(node: NodeMatchCandidate) -> str:
    label = node.get("displayName") or node.get("remoteIp") or node.get("nodeId", "")
    details = [f"node={node.get('nodeId')}"]
    cid = node.get("clientId")
    if isinstance(cid, str) and cid:
        details.append(f"client={cid}")
    return f"{label} [{', '.join(details)}]"


def _is_current_openclaw_client(client_id) -> bool:
    return isinstance(client_id, str) and client_id.strip().lower().startswith("openclaw-")


def _is_legacy_clawdbot_client(client_id) -> bool:
    if not isinstance(client_id, str):
        return False
    s = client_id.strip().lower()
    return s.startswith("clawdbot-") or s.startswith("moldbot-")


def _pick_preferred_legacy_migration_match(
    matches: List[NodeMatchCandidate],
) -> Optional[NodeMatchCandidate]:
    current = [m for m in matches if _is_current_openclaw_client(m.get("clientId"))]
    if len(current) != 1:
        return None
    legacy_count = sum(1 for m in matches if _is_legacy_clawdbot_client(m.get("clientId")))
    if legacy_count == 0 or len(current) + legacy_count != len(matches):
        return None
    return current[0]


def _resolve_match_score(
    node: NodeMatchCandidate, query: str, query_normalized: str, allow_compact: bool
) -> int:
    if node.get("nodeId") == query:
        return 4000
    if isinstance(node.get("remoteIp"), str) and node.get("remoteIp") == query:
        return 3000
    name = node.get("displayName")
    if isinstance(name, str) and name:
        name_norm = _normalize_node_key(name)
        if name_norm and name_norm == query_normalized:
            return 2000
        if allow_compact and name_norm:
            if _compact_normalized_node_key(name_norm) == _compact_normalized_node_key(query_normalized):
                return 1900
    if len(query) >= 6 and node.get("nodeId", "").startswith(query):
        return 1000
    return 0


def _score_node_candidate(node: NodeMatchCandidate, match_score: int) -> int:
    score = match_score
    if node.get("connected") is True:
        score += 100
    if _is_current_openclaw_client(node.get("clientId")):
        score += 10
    elif _is_legacy_clawdbot_client(node.get("clientId")):
        score -= 10
    return score


def _resolve_scored_matches(
    nodes: List[NodeMatchCandidate], query: str, allow_compact: bool
) -> List[ScoredNodeMatch]:
    trimmed = query.strip() if isinstance(query, str) else ""
    if not trimmed:
        return []
    qn = _normalize_node_key(trimmed)
    out: List[ScoredNodeMatch] = []
    for node in nodes:
        m = _resolve_match_score(node, trimmed, qn, allow_compact)
        if m == 0:
            continue
        out.append({
            "node": node,
            "matchScore": m,
            "selectionScore": _score_node_candidate(node, m),
        })
    return out


def resolve_node_id_from_candidates(
    nodes: List[NodeMatchCandidate],
    query: str,
    allow_compact_display_name: bool = False,
) -> str:
    """Resolve a single node id or raise a readable error.

    Mirrors :func:`resolveNodeIdFromCandidates` (``shared/node-match.ts``).
    """
    q = query.strip() if isinstance(query, str) else ""
    if not q:
        raise ValueError("node required")
    matches = _resolve_scored_matches(nodes, q, allow_compact_display_name)
    if len(matches) == 1:
        return matches[0]["node"]["nodeId"]
    if len(matches) == 0:
        known = _list_known_nodes(nodes)
        suffix = f" (known: {known})" if known else ""
        raise ValueError(f"unknown node: {q}{suffix}")
    top_match = max(m["matchScore"] for m in matches)
    strongest = [m for m in matches if m["matchScore"] == top_match]
    if len(strongest) == 1:
        return strongest[0]["node"]["nodeId"]
    top_selection = max(m["selectionScore"] for m in strongest)
    final = [m for m in strongest if m["selectionScore"] == top_selection]
    if len(final) == 1:
        return final[0]["node"]["nodeId"]
    preferred = _pick_preferred_legacy_migration_match([m["node"] for m in final])
    if preferred is not None:
        return preferred["nodeId"]
    raise ValueError(
        "ambiguous node: "
        + q
        + " (matches: "
        + ", ".join(_format_node_candidate_label(m["node"]) for m in final)
        + ")"
    )


__all__ = [
    "NodeMatchCandidate",
    "ScoredNodeMatch",
    "resolve_node_id_from_candidates",
]
