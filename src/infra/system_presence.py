"""src.infra.system_presence — in-memory Gateway presence registry.

OpenClaw parity: mirrors ``src/infra/system-presence.ts``.

Presence is a lightweight, best-effort view of:
  - the Gateway itself (self entry seeded at startup)
  - user-visible clients connected to the Gateway (UI, WebChat, nodes, etc.)

## Merge/dedupe key priority (mirrors OpenClaw)
  1. paired deviceId
  2. client instanceId (case-insensitive)
  3. connection id (last resort — causes duplicates on reconnect)

## TTL & bounded size
  TTL:         5 minutes (entries older than this are pruned on listSystemPresence)
  Max entries: 200 (oldest by ts are dropped when exceeded)

## Ephemeral mode filtering
  Clients in ``cli``, ``backend``, or ``probe`` mode are excluded from the
  registry. ``test`` mode stays tracked.

## Loopback IP filtering
  Loopback IPs (127.x, ::1) are not recorded so SSH-tunnelled clients do not
  appear to come from localhost.

Public surface
--------------
``SystemPresence``           — typed entry shape
``SystemPresenceUpdate``     — returned by update_system_presence
``upsert_presence``          — raw key+partial upsert (WS connect path)
``update_system_presence``   — rich merge from system-event beacon payload
``list_system_presence``     — prune + list (sorted newest first)
``pick_gateway_self_presence``
                             — extract gateway self entry from a presence list
``normalize_node_presence_alive_reason``
                             — normalize node alive reason strings
``NODE_PRESENCE_ALIVE_EVENT``
``NODE_PRESENCE_ACTIVITY_EVENT``
``EPHEMERAL_CLIENT_MODES``   — set of modes that are NOT tracked
``is_loopback_ip``           — predicate for loopback address filtering
"""

from __future__ import annotations

import platform
import re
import socket
import uuid
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constants (mirrors system-presence.ts)
# ---------------------------------------------------------------------------

TTL_MS: int = 5 * 60 * 1000   # 5 minutes
MAX_ENTRIES: int = 200

# Gateway self entry's stable instanceId for this process.
SELF_INSTANCE_ID: str = str(uuid.uuid4())

# Modes whose clients are excluded from the presence registry.
# test-mode stays tracked (used as stand-ins for real clients).
EPHEMERAL_CLIENT_MODES: frozenset[str] = frozenset({"cli", "backend", "probe"})

# Node presence event names (mirrors shared/node-presence.ts)
NODE_PRESENCE_ALIVE_EVENT: str = "node.presence.alive"
NODE_PRESENCE_ACTIVITY_EVENT: str = "node.presence.activity"

_NODE_PRESENCE_ALIVE_REASONS: frozenset[str] = frozenset({
    "background",
    "silent_push",
    "bg_app_refresh",
    "significant_location",
    "manual",
    "connect",
})


# ---------------------------------------------------------------------------
# Loopback detection
# ---------------------------------------------------------------------------


def is_loopback_ip(ip: str | None) -> bool:
    """Return True when *ip* is a loopback / tunnel-local address.

    Mirrors the loopback-omission logic in the WS connect handler.
    """
    if not ip:
        return False
    stripped = ip.strip()
    return stripped.startswith("127.") or stripped == "::1" or stripped == "localhost"


# ---------------------------------------------------------------------------
# Node presence alive reason
# ---------------------------------------------------------------------------


def normalize_node_presence_alive_reason(value: object) -> str:
    """Normalize an untrusted node presence trigger value.

    Mirrors ``normalizeNodePresenceAliveReason``.
    Defaults unknown input to ``"background"``.
    """
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _NODE_PRESENCE_ALIVE_REASONS:
            return normalized
    return "background"


# ---------------------------------------------------------------------------
# SystemPresence shape
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SystemPresence:
    """One entry in the presence registry.

    Mirrors ``SystemPresence`` from ``infra/system-presence.ts``.
    ``text`` and ``ts`` are always set.
    """

    text: str
    ts: int  # ms since epoch

    host: str | None = None
    ip: str | None = None
    version: str | None = None
    platform: str | None = None
    device_family: str | None = None
    model_identifier: str | None = None
    last_input_seconds: int | None = None
    mode: str | None = None
    reason: str | None = None
    device_id: str | None = None
    roles: list[str] | None = None
    scopes: list[str] | None = None
    instance_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON output / wire protocol."""
        d: dict[str, Any] = {"text": self.text, "ts": self.ts}
        for attr, key in [
            ("host", "host"),
            ("ip", "ip"),
            ("version", "version"),
            ("platform", "platform"),
            ("device_family", "deviceFamily"),
            ("model_identifier", "modelIdentifier"),
            ("last_input_seconds", "lastInputSeconds"),
            ("mode", "mode"),
            ("reason", "reason"),
            ("device_id", "deviceId"),
            ("roles", "roles"),
            ("scopes", "scopes"),
            ("instance_id", "instanceId"),
        ]:
            val = getattr(self, attr)
            if val is not None:
                d[key] = val
        return d


@dataclass(slots=True)
class SystemPresenceUpdate:
    """Result of :func:`update_system_presence`.

    Mirrors ``SystemPresenceUpdate``.
    """

    key: str
    next: SystemPresence
    previous: SystemPresence | None = None
    changes: dict[str, Any] = field(default_factory=dict)
    changed_keys: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# In-memory registry
# ---------------------------------------------------------------------------
# Module-level singleton. Mirrors the module-level ``entries`` Map.

_entries: dict[str, SystemPresence] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_key(raw: str | None) -> str | None:
    """Lowercase-strip presence key. Mirrors ``normalizePresenceKey``."""
    if not isinstance(raw, str):
        return None
    stripped = raw.strip().lower()
    return stripped if stripped else None


def _current_ms() -> int:
    import time
    return int(time.time() * 1000)


def _merge_string_list(*lists: list[str] | None) -> list[str] | None:
    """Union-merge string lists, preserving order and deduplicating.

    Mirrors ``mergeStringList``.
    """
    seen: dict[str, None] = {}
    for lst in lists:
        if not isinstance(lst, list):
            continue
        for item in lst:
            if isinstance(item, str):
                stripped = item.strip()
                if stripped:
                    seen[stripped] = None
    return list(seen.keys()) if seen else None


def _resolve_platform() -> str:
    """Build a human-readable platform string. Mirrors ``initSelfPresence``."""
    sys_platform = platform.system().lower()
    release = platform.release()
    if sys_platform == "darwin":
        return f"macos {platform.mac_ver()[0]}"
    if sys_platform == "windows":
        return f"windows {release}"
    return f"{sys_platform} {release}"


def _resolve_device_family() -> str:
    sys_platform = platform.system().lower()
    if sys_platform == "darwin":
        return "Mac"
    if sys_platform == "windows":
        return "Windows"
    if sys_platform == "linux":
        return "Linux"
    return sys_platform


def _resolve_host() -> str:
    return socket.gethostname()


def _resolve_primary_ip() -> str | None:
    """Best-effort LAN IPv4; falls back to None for loopback."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            return None if is_loopback_ip(ip) else ip
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Self-presence seeding
# ---------------------------------------------------------------------------


def _init_self_presence() -> None:
    """Seed the gateway self entry. Called once at module load."""
    host = _resolve_host()
    ip = _resolve_primary_ip()
    version = _resolve_jarvis_version()
    sys_platform = _resolve_platform()
    device_family = _resolve_device_family()
    model_identifier = platform.machine() or None

    text = (
        f"Gateway: {host}"
        + (f" ({ip})" if ip else "")
        + f" · app {version} · mode gateway · reason self"
    )
    entry = SystemPresence(
        text=text,
        ts=_current_ms(),
        host=host,
        ip=ip,
        version=version,
        platform=sys_platform,
        device_family=device_family,
        model_identifier=model_identifier,
        mode="gateway",
        reason="self",
        instance_id=SELF_INSTANCE_ID,
    )
    key = host.lower()
    _entries[key] = entry


def _resolve_jarvis_version() -> str:
    """Return the running Jarvis version, or 'unknown'."""
    try:
        import importlib.metadata
        return importlib.metadata.version("jarvis")
    except Exception:
        pass
    try:
        from pathlib import Path
        p = Path(__file__).parent.parent.parent / "version.txt"
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return "unknown"


def _ensure_self_presence() -> None:
    """Re-seed if the map was cleared (e.g. test teardown)."""
    if not _entries:
        _init_self_presence()


def _touch_self_presence() -> None:
    """Refresh the self entry's ts without changing any other field."""
    host = _resolve_host()
    key = host.lower()
    existing = _entries.get(key)
    if existing:
        import dataclasses
        fields = {f.name: getattr(existing, f.name) for f in dataclasses.fields(existing)}
        fields["ts"] = _current_ms()
        _entries[key] = SystemPresence(**fields)
    else:
        _init_self_presence()


# ---------------------------------------------------------------------------
# Presence text parser (node beacon text format)
# ---------------------------------------------------------------------------

_NODE_TEXT_RE = re.compile(
    r"Node:\s*([^ (]+)\s*\(([^)]+)\)\s*·\s*app\s*([^·]+?)\s*·\s*last input\s*([0-9]+)s ago"
    r"\s*·\s*mode\s*([^·]+?)\s*·\s*reason\s*(.+)$",
    re.IGNORECASE,
)
_GATEWAY_TEXT_RE = re.compile(
    r"^Gateway:\s*([^ (·]+)(?:\s*\(([^)]+)\))?",
    re.IGNORECASE,
)


def _parse_presence_text(text: str) -> dict[str, Any]:
    """Parse structured fields from a presence text string.

    Mirrors ``parsePresence`` from ``system-presence.ts``.
    Falls back to ``{}`` when the text doesn't match a known format.
    """
    trimmed = text.strip()
    m = _NODE_TEXT_RE.search(trimmed)
    if m:
        host, ip, version, last_input_str, mode, reason = m.groups()
        return {
            "host": host.strip(),
            "ip": ip.strip(),
            "version": version.strip(),
            "last_input_seconds": int(last_input_str),
            "mode": mode.strip(),
            "reason": reason.strip(),
        }
    return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def upsert_presence(key: str, presence: dict[str, Any]) -> None:
    """Upsert a partial presence entry by *key*.

    Mirrors ``upsertPresence``.

    Used by the WS connect handler when a client connects. The key is
    usually the client's instanceId or deviceId.

    Ephemeral-mode clients (cli, backend, probe) are silently ignored.
    Loopback IPs are omitted from the stored entry.
    """
    _ensure_self_presence()
    mode = (presence.get("mode") or "").strip().lower()
    if mode in EPHEMERAL_CLIENT_MODES:
        return

    normalized_key = _normalize_key(key) or _resolve_host().lower()
    existing = _entries.get(normalized_key) or {}
    existing_obj = existing if isinstance(existing, SystemPresence) else SystemPresence(text="", ts=0)

    # Omit loopback IPs (SSH tunnel caveat).
    ip = presence.get("ip")
    if is_loopback_ip(ip):
        ip = None

    merged = SystemPresence(
        text=(
            presence.get("text")
            or getattr(existing_obj, "text", "")
            or f"Node: {presence.get('host') or getattr(existing_obj, 'host', 'unknown')}"
              f" · mode {mode or getattr(existing_obj, 'mode', 'unknown')}"
        ),
        ts=_current_ms(),
        host=presence.get("host") or existing_obj.host,
        ip=ip or existing_obj.ip,
        version=presence.get("version") or existing_obj.version,
        platform=presence.get("platform") or existing_obj.platform,
        device_family=presence.get("deviceFamily") or existing_obj.device_family,
        model_identifier=presence.get("modelIdentifier") or existing_obj.model_identifier,
        last_input_seconds=presence.get("lastInputSeconds") or existing_obj.last_input_seconds,
        mode=mode or existing_obj.mode,
        reason=presence.get("reason") or existing_obj.reason,
        device_id=presence.get("deviceId") or existing_obj.device_id,
        roles=_merge_string_list(existing_obj.roles, presence.get("roles")),
        scopes=_merge_string_list(existing_obj.scopes, presence.get("scopes")),
        instance_id=presence.get("instanceId") or existing_obj.instance_id,
    )
    _entries[normalized_key] = merged


def update_system_presence(payload: dict[str, Any]) -> SystemPresenceUpdate:
    """Rich merge from a system-event beacon payload.

    Mirrors ``updateSystemPresence``.

    Key resolution priority (mirrors OpenClaw):
      1. payload.deviceId
      2. payload.instanceId
      3. parsed.instanceId
      4. parsed.host
      5. parsed.ip
      6. truncated text
      7. gateway hostname
    """
    _ensure_self_presence()
    text = payload.get("text") or ""
    parsed = _parse_presence_text(text)

    # Omit loopback IPs.
    ip_raw = payload.get("ip") or parsed.get("ip")
    ip = None if is_loopback_ip(ip_raw) else ip_raw

    # Key resolution.
    key = (
        _normalize_key(payload.get("deviceId"))
        or _normalize_key(payload.get("instanceId"))
        or _normalize_key(parsed.get("instanceId"))
        or _normalize_key(parsed.get("host"))
        or (parsed.get("ip") if not is_loopback_ip(parsed.get("ip")) else None)
        or (text[:64].lower().strip() if text else None)
        or _resolve_host().lower()
    )

    had_existing = key in _entries
    existing = _entries.get(key) or SystemPresence(text="", ts=0)

    merged = SystemPresence(
        text=text or parsed.get("text") or existing.text or "",
        ts=_current_ms(),
        host=payload.get("host") or parsed.get("host") or existing.host,
        ip=ip or existing.ip,
        version=payload.get("version") or parsed.get("version") or existing.version,
        platform=payload.get("platform") or existing.platform,
        device_family=payload.get("deviceFamily") or existing.device_family,
        model_identifier=payload.get("modelIdentifier") or existing.model_identifier,
        last_input_seconds=(
            payload.get("lastInputSeconds")
            or parsed.get("last_input_seconds")
            or existing.last_input_seconds
        ),
        mode=payload.get("mode") or parsed.get("mode") or existing.mode,
        reason=payload.get("reason") or parsed.get("reason") or existing.reason,
        device_id=payload.get("deviceId") or existing.device_id,
        roles=_merge_string_list(existing.roles, payload.get("roles")),
        scopes=_merge_string_list(existing.scopes, payload.get("scopes")),
        instance_id=payload.get("instanceId") or parsed.get("instanceId") or existing.instance_id,
    )
    _entries[key] = merged

    # Build change diff for tracked keys.
    track_keys = [("host", "host"), ("ip", "ip"), ("version", "version"),
                  ("mode", "mode"), ("reason", "reason")]
    changes: dict[str, Any] = {}
    changed_keys: list[str] = []
    for attr, label in track_keys:
        prev = getattr(existing, attr)
        nxt = getattr(merged, attr)
        if prev != nxt:
            changes[label] = nxt
            changed_keys.append(label)

    return SystemPresenceUpdate(
        key=key,
        previous=existing if had_existing else None,
        next=merged,
        changes=changes,
        changed_keys=changed_keys,
    )


def list_system_presence() -> list[SystemPresence]:
    """Return all live presence entries, newest first.

    Mirrors ``listSystemPresence``.

    Prunes expired entries (TTL=5 min) and enforces MAX_ENTRIES (200)
    by dropping oldest on overflow. Refreshes the self entry's ts.
    """
    _ensure_self_presence()

    now = _current_ms()

    # Prune expired.
    expired = [k for k, v in list(_entries.items()) if now - v.ts > TTL_MS]
    for k in expired:
        del _entries[k]

    # Enforce max size — drop oldest by ts (use module-level so tests can patch it).
    import src.infra.system_presence as _self
    max_entries = _self.MAX_ENTRIES
    if len(_entries) > max_entries:
        sorted_entries = sorted(_entries.items(), key=lambda kv: kv[1].ts)
        to_drop = len(_entries) - max_entries
        for k, _ in sorted_entries[:to_drop]:
            del _entries[k]

    _touch_self_presence()
    return sorted(_entries.values(), key=lambda e: e.ts, reverse=True)


def reset_presence_registry() -> None:
    """Clear the registry and re-seed the self entry.

    For use in tests only. Mirrors test teardown in OpenClaw tests.
    """
    _entries.clear()
    _init_self_presence()


# ---------------------------------------------------------------------------
# Gateway self presence picker (mirrors commands/gateway-presence.ts)
# ---------------------------------------------------------------------------


def _parse_legacy_gateway_text(text: str) -> dict[str, str]:
    m = _GATEWAY_TEXT_RE.match(text)
    if not m:
        return {}
    host = (m.group(1) or "").strip()
    ip = (m.group(2) or "").strip() if m.group(2) else ""
    result: dict[str, str] = {}
    if host:
        result["host"] = host
    if ip:
        result["ip"] = ip
    return result


def pick_gateway_self_presence(presence: list[Any]) -> dict[str, str | None] | None:
    """Pick host/ip/version/platform from the gateway self presence record.

    Mirrors ``pickGatewaySelfPresence`` (``commands/gateway-presence.ts``).
    Accepts a list of presence entry dicts (as returned by the wire protocol).
    """
    if not isinstance(presence, list):
        return None

    # Find gateway self entry.
    self_entry = next(
        (e for e in presence if isinstance(e, dict) and e.get("mode") == "gateway" and e.get("reason") == "self"),
        None,
    )
    if self_entry is None:
        # Back-compat: older payloads only had a text field.
        self_entry = next(
            (e for e in presence if isinstance(e, dict) and isinstance(e.get("text"), str) and e["text"].startswith("Gateway:")),
            None,
        )
    if self_entry is None:
        return None

    legacy = _parse_legacy_gateway_text(self_entry.get("text") or "")
    result: dict[str, str | None] = {
        "host": self_entry.get("host") or legacy.get("host"),
        "ip": self_entry.get("ip") or legacy.get("ip"),
        "version": self_entry.get("version"),
        "platform": self_entry.get("platform"),
        "deviceId": self_entry.get("deviceId"),
        "instanceId": self_entry.get("instanceId"),
    }
    # Strip None values except host (always include).
    return {k: v for k, v in result.items() if v is not None or k == "host"}


# ---------------------------------------------------------------------------
# Module init
# ---------------------------------------------------------------------------

_init_self_presence()


__all__ = [
    "EPHEMERAL_CLIENT_MODES",
    "MAX_ENTRIES",
    "NODE_PRESENCE_ACTIVITY_EVENT",
    "NODE_PRESENCE_ALIVE_EVENT",
    "SELF_INSTANCE_ID",
    "TTL_MS",
    "SystemPresence",
    "SystemPresenceUpdate",
    "is_loopback_ip",
    "list_system_presence",
    "normalize_node_presence_alive_reason",
    "pick_gateway_self_presence",
    "reset_presence_registry",
    "update_system_presence",
    "upsert_presence",
]
