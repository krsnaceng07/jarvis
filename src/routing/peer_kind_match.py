"""jarvis.routing.peer_kind_match — peer-kind compatibility.

OpenClaw parity: mirrors ``src/routing/peer-kind-match.ts``.
"""

from __future__ import annotations


def peer_kind_matches(binding_kind: str, peer_kind: str) -> bool:
    """Return whether a binding peer kind matches an inbound peer kind.

    Mirrors ``peerKindMatches``: exact match, plus group↔channel
    equivalence in both directions.
    """
    if binding_kind == peer_kind:
        return True
    if binding_kind == "group" and peer_kind == "channel":
        return True
    if binding_kind == "channel" and peer_kind == "group":
        return True
    return False


__all__ = ["peer_kind_matches"]
