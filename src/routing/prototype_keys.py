"""jarvis.routing.prototype_keys — blocked object-key guard.

OpenClaw parity: mirrors ``src/infra/prototype-keys.ts``.

In JS these keys enable prototype pollution when used as object
keys. Python dicts have no prototype chain, but the *contract*
is preserved so account/agent lookups reject the same key names
and stay wire-compatible with OpenClaw configs.
"""

from __future__ import annotations

BLOCKED_OBJECT_KEYS: frozenset[str] = frozenset({"__proto__", "prototype", "constructor"})


def is_blocked_object_key(key: object) -> bool:
    """Return True when ``key`` is a prototype-pollution-prone object key."""
    return isinstance(key, str) and key in BLOCKED_OBJECT_KEYS


__all__ = ["BLOCKED_OBJECT_KEYS", "is_blocked_object_key"]
