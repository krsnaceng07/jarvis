"""Gateway protocol version.

Mirrors OpenClaw's ``packages/gateway-protocol/version.ts``.
Bump this when the RPC framing or required method set changes in
a way older clients cannot tolerate. Minor/patch additions are
additive — do not bump the protocol version for those.

The version is sent as ``X-JARVIS-Protocol-Version`` on every
HTTP response and in the ``version`` field of WS hello frames.
"""

from __future__ import annotations

#: Current gateway protocol version string.
#: Follows semver; major bump on breaking framing changes.
PROTOCOL_VERSION: str = "1.0.0"

__all__ = ["PROTOCOL_VERSION"]
