"""Tests for src/infra/system_presence.py.

Mirrors behavioral contracts from OpenClaw's:
  - infra/system-presence.test.ts
  - infra/system-presence.version.test.ts
  - shared/node-presence.test.ts
  - commands/gateway-presence.test.ts
"""

from __future__ import annotations

import time
import uuid
import pytest

from src.infra.system_presence import (
    EPHEMERAL_CLIENT_MODES,
    TTL_MS,
    SystemPresence,
    SystemPresenceUpdate,
    is_loopback_ip,
    list_system_presence,
    normalize_node_presence_alive_reason,
    pick_gateway_self_presence,
    reset_presence_registry,
    update_system_presence,
    upsert_presence,
    _entries,
    _current_ms,
)


@pytest.fixture(autouse=True)
def _reset():
    """Reset the presence registry before each test."""
    reset_presence_registry()
    yield
    reset_presence_registry()


# ============================================================
# is_loopback_ip
# ============================================================


def test_loopback_127():
    assert is_loopback_ip("127.0.0.1") is True


def test_loopback_127_range():
    assert is_loopback_ip("127.255.0.1") is True


def test_loopback_ipv6():
    assert is_loopback_ip("::1") is True


def test_loopback_localhost():
    assert is_loopback_ip("localhost") is True


def test_loopback_lan_ip_not_loopback():
    assert is_loopback_ip("192.168.1.10") is False


def test_loopback_none():
    assert is_loopback_ip(None) is False


def test_loopback_empty():
    assert is_loopback_ip("") is False


# ============================================================
# normalize_node_presence_alive_reason
# ============================================================


def test_normalize_alive_reason_valid():
    assert normalize_node_presence_alive_reason("background") == "background"
    assert normalize_node_presence_alive_reason("connect") == "connect"
    assert normalize_node_presence_alive_reason("manual") == "manual"


def test_normalize_alive_reason_unknown_defaults_background():
    assert normalize_node_presence_alive_reason("bogus") == "background"
    assert normalize_node_presence_alive_reason(None) == "background"
    assert normalize_node_presence_alive_reason(42) == "background"


def test_normalize_alive_reason_case_insensitive():
    assert normalize_node_presence_alive_reason("CONNECT") == "connect"


# ============================================================
# upsert_presence
# ============================================================


def test_upsert_presence_creates_entry():
    instance_id = str(uuid.uuid4())
    upsert_presence(instance_id, {"host": "testhost", "mode": "ui", "reason": "connect", "instanceId": instance_id})
    entries = list_system_presence()
    found = [e for e in entries if e.instance_id and e.instance_id.lower() == instance_id.lower()]
    assert len(found) == 1
    assert found[0].host == "testhost"


def test_upsert_presence_merges_roles():
    """Mirrors: it("merges roles and scopes for the same device")"""
    device_id = str(uuid.uuid4())
    upsert_presence(device_id, {"deviceId": device_id, "host": "openclaw", "roles": ["operator"], "scopes": ["operator.admin"], "reason": "connect"})
    upsert_presence(device_id, {"deviceId": device_id, "roles": ["node"], "scopes": ["system.run"], "reason": "connect"})

    all_entries = list_system_presence()
    entry = next((e for e in all_entries if e.device_id == device_id), None)
    assert entry is not None
    assert "operator" in entry.roles
    assert "node" in entry.roles
    assert "operator.admin" in entry.scopes
    assert "system.run" in entry.scopes


def test_upsert_presence_ephemeral_modes_excluded():
    for mode in EPHEMERAL_CLIENT_MODES:
        key = f"ephemeral-{mode}-{uuid.uuid4()}"
        upsert_presence(key, {"host": "cli-host", "mode": mode, "reason": "connect"})

    all_entries = list_system_presence()
    for mode in EPHEMERAL_CLIENT_MODES:
        assert not any(e.host == "cli-host" and e.mode == mode for e in all_entries)


def test_upsert_presence_test_mode_stays_tracked():
    key = str(uuid.uuid4())
    upsert_presence(key, {"host": "test-client", "mode": "test", "reason": "connect", "instanceId": key})
    all_entries = list_system_presence()
    assert any(e.instance_id and e.instance_id.lower() == key.lower() for e in all_entries)


def test_upsert_presence_omits_loopback_ip():
    key = str(uuid.uuid4())
    upsert_presence(key, {"host": "tunnelled", "ip": "127.0.0.1", "mode": "ui", "instanceId": key})
    all_entries = list_system_presence()
    entry = next((e for e in all_entries if e.instance_id and e.instance_id.lower() == key.lower()), None)
    assert entry is not None
    assert entry.ip is None


def test_upsert_presence_lan_ip_kept():
    key = str(uuid.uuid4())
    upsert_presence(key, {"host": "local", "ip": "10.0.0.5", "mode": "ui", "instanceId": key})
    all_entries = list_system_presence()
    entry = next((e for e in all_entries if e.instance_id and e.instance_id.lower() == key.lower()), None)
    assert entry is not None
    assert entry.ip == "10.0.0.5"


def test_upsert_presence_key_is_case_insensitive():
    """Same instanceId in different cases should resolve to one entry."""
    instance_id_upper = str(uuid.uuid4()).upper()
    instance_id_lower = instance_id_upper.lower()

    upsert_presence(instance_id_upper, {"host": "first", "mode": "ui", "instanceId": instance_id_upper})
    upsert_presence(instance_id_lower, {"host": "second", "mode": "ui", "instanceId": instance_id_lower})

    all_entries = list_system_presence()
    matches = [e for e in all_entries if (e.instance_id or "").lower() == instance_id_lower]
    assert len(matches) == 1
    assert matches[0].host == "second"  # last write wins for host


# ============================================================
# update_system_presence
# ============================================================


def test_update_system_presence_dedupes_by_instance_id():
    """Mirrors: it("dedupes entries across sources by case-insensitive instanceId key")"""
    instance_id_upper = f"AaBb-{uuid.uuid4()}".upper()
    instance_id_lower = instance_id_upper.lower()

    upsert_presence(instance_id_upper, {
        "host": "openclaw",
        "mode": "ui",
        "instanceId": instance_id_upper,
        "reason": "connect",
    })

    update_system_presence({
        "text": "Node: Peter-Mac-Studio (10.0.0.1) · app 2.0.0 · last input 5s ago · mode ui · reason beacon",
        "instanceId": instance_id_lower,
        "host": "Peter-Mac-Studio",
        "ip": "10.0.0.1",
        "mode": "ui",
        "version": "2.0.0",
        "lastInputSeconds": 5,
        "reason": "beacon",
    })

    all_entries = list_system_presence()
    matches = [e for e in all_entries if (e.instance_id or "").lower() == instance_id_lower]
    assert len(matches) == 1
    assert matches[0].host == "Peter-Mac-Studio"
    assert matches[0].ip == "10.0.0.1"
    assert matches[0].last_input_seconds == 5


def test_update_system_presence_returns_update_object():
    result = update_system_presence({"text": "test", "host": "mymac", "mode": "ui", "reason": "beacon"})
    assert isinstance(result, SystemPresenceUpdate)
    assert result.key
    assert result.next.host == "mymac"


def test_update_system_presence_tracks_changes():
    key = str(uuid.uuid4())
    update_system_presence({"instanceId": key, "text": "t", "host": "host1", "mode": "ui"})
    result = update_system_presence({"instanceId": key, "text": "t", "host": "host2", "mode": "ui"})
    assert "host" in result.changed_keys
    assert result.changes["host"] == "host2"


def test_update_system_presence_no_change_on_same_values():
    key = str(uuid.uuid4())
    update_system_presence({"instanceId": key, "text": "t", "host": "same", "mode": "ui"})
    result = update_system_presence({"instanceId": key, "text": "t", "host": "same", "mode": "ui"})
    assert "host" not in result.changed_keys


def test_update_system_presence_omits_loopback_ip():
    key = str(uuid.uuid4())
    update_system_presence({"instanceId": key, "text": "t", "ip": "127.0.0.1", "host": "h"})
    all_entries = list_system_presence()
    entry = next((e for e in all_entries if (e.instance_id or "").lower() == key.lower()), None)
    assert entry is not None
    assert entry.ip is None


def test_update_system_presence_merges_roles():
    key = str(uuid.uuid4())
    update_system_presence({"instanceId": key, "text": "t", "roles": ["admin"], "scopes": ["admin.read"]})
    update_system_presence({"instanceId": key, "text": "t", "roles": ["user"], "scopes": ["user.read"]})
    all_entries = list_system_presence()
    entry = next((e for e in all_entries if (e.instance_id or "").lower() == key.lower()), None)
    assert entry is not None
    assert "admin" in entry.roles
    assert "user" in entry.roles


def test_update_system_presence_key_priority_device_id_first():
    """deviceId takes priority over instanceId in key resolution."""
    device_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    update_system_presence({"deviceId": device_id, "instanceId": instance_id, "text": "t", "host": "h1"})
    update_system_presence({"deviceId": device_id, "text": "t2", "host": "h2"})

    all_entries = list_system_presence()
    # Should only have one entry with this deviceId
    matches = [e for e in all_entries if e.device_id == device_id]
    assert len(matches) == 1
    assert matches[0].host == "h2"


# ============================================================
# list_system_presence — TTL and bounded size
# ============================================================


def test_list_system_presence_returns_newest_first():
    k1 = str(uuid.uuid4())
    k2 = str(uuid.uuid4())
    upsert_presence(k1, {"host": "first", "mode": "ui", "instanceId": k1})
    time.sleep(0.01)
    upsert_presence(k2, {"host": "second", "mode": "ui", "instanceId": k2})

    entries = list_system_presence()
    hosts = [e.host for e in entries if e.host in ("first", "second")]
    assert hosts.index("second") < hosts.index("first")


def test_list_system_presence_prunes_expired(monkeypatch):
    """Entries older than TTL_MS should be removed."""
    key = str(uuid.uuid4())
    upsert_presence(key, {"host": "stale", "mode": "ui", "instanceId": key})

    # Advance the entry's ts into the past beyond TTL.
    old_ts = _current_ms() - TTL_MS - 1000
    _entries[key.lower()] = SystemPresence(
        text="stale",
        ts=old_ts,
        host="stale",
        mode="ui",
        instance_id=key,
    )

    entries = list_system_presence()
    assert not any(e.instance_id and e.instance_id.lower() == key.lower() for e in entries)


def test_list_system_presence_enforces_max_entries():
    """Oldest entries are dropped when the registry exceeds MAX_ENTRIES.

    _touch_self_presence runs after cap enforcement, so the self entry
    may push the count to MAX_ENTRIES+1. The key invariant is that cap
    enforcement reduced the roster — not that the final count is exactly
    MAX_ENTRIES (OpenClaw has the same post-prune self-touch behavior).
    """
    from src.infra import system_presence as sp
    original_max = sp.MAX_ENTRIES
    sp.MAX_ENTRIES = 4  # small cap for speed

    try:
        reset_presence_registry()
        for i in range(7):
            k = f"entry-{i}-{uuid.uuid4()}"
            upsert_presence(k, {"host": f"host-{i}", "mode": "ui", "instanceId": k})

        entries = list_system_presence()
        # Cap=4, 7 client entries + 1 self = 8 before enforcement.
        # After enforcement: at most cap entries remain, then self is re-touched
        # (may add 1 more), so final count is <= cap + 1.
        assert len(entries) <= sp.MAX_ENTRIES + 1
        # Also verify cap enforcement actually ran (8 > cap+1=5).
        assert len(entries) < 8
    finally:
        sp.MAX_ENTRIES = original_max


def test_list_system_presence_always_includes_gateway_self():
    """Gateway self entry is always present (re-seeded if cleared)."""
    entries = list_system_presence()
    self_entries = [e for e in entries if e.mode == "gateway" and e.reason == "self"]
    assert len(self_entries) >= 1


# ============================================================
# Gateway self presence (from list)
# ============================================================


def test_self_presence_entry_fields():
    entries = list_system_presence()
    self_entry = next((e for e in entries if e.mode == "gateway" and e.reason == "self"), None)
    assert self_entry is not None
    assert self_entry.host  # hostname must be set
    assert self_entry.instance_id == __import__("src.infra.system_presence", fromlist=["SELF_INSTANCE_ID"]).SELF_INSTANCE_ID


# ============================================================
# pick_gateway_self_presence
# ============================================================


def test_pick_gateway_self_presence_from_list():
    presence_list = [
        {"mode": "gateway", "reason": "self", "host": "myserver", "ip": "10.0.0.1", "version": "2.0.0", "platform": "linux 5.0"},
        {"mode": "ui", "reason": "connect", "host": "macbook"},
    ]
    result = pick_gateway_self_presence(presence_list)
    assert result is not None
    assert result["host"] == "myserver"
    assert result["ip"] == "10.0.0.1"
    assert result["version"] == "2.0.0"


def test_pick_gateway_self_presence_legacy_text():
    presence_list = [
        {"text": "Gateway: myserver (10.0.0.2) · app 1.5.0 · mode gateway · reason self"},
    ]
    result = pick_gateway_self_presence(presence_list)
    assert result is not None
    assert result["host"] == "myserver"
    assert result["ip"] == "10.0.0.2"


def test_pick_gateway_self_presence_no_gateway_entry():
    presence_list = [{"mode": "ui", "reason": "connect", "host": "macbook"}]
    assert pick_gateway_self_presence(presence_list) is None


def test_pick_gateway_self_presence_not_a_list():
    assert pick_gateway_self_presence(None) is None
    assert pick_gateway_self_presence({}) is None


def test_pick_gateway_self_presence_includes_instance_id():
    presence_list = [
        {"mode": "gateway", "reason": "self", "host": "gw", "instanceId": "abc-123"},
    ]
    result = pick_gateway_self_presence(presence_list)
    assert result["instanceId"] == "abc-123"


# ============================================================
# SystemPresence.to_dict
# ============================================================


def test_system_presence_to_dict():
    entry = SystemPresence(
        text="test",
        ts=1234567890,
        host="myhost",
        ip="10.0.0.1",
        mode="ui",
        roles=["admin"],
    )
    d = entry.to_dict()
    assert d["text"] == "test"
    assert d["ts"] == 1234567890
    assert d["host"] == "myhost"
    assert d["ip"] == "10.0.0.1"
    assert d["mode"] == "ui"
    assert d["roles"] == ["admin"]
    # None fields should be omitted
    assert "version" not in d
    assert "deviceId" not in d


def test_system_presence_to_dict_camel_case_keys():
    entry = SystemPresence(
        text="t",
        ts=0,
        device_family="Mac",
        model_identifier="MacBookPro18,1",
        last_input_seconds=30,
        device_id="d123",
        instance_id="i456",
    )
    d = entry.to_dict()
    assert "deviceFamily" in d
    assert "modelIdentifier" in d
    assert "lastInputSeconds" in d
    assert "deviceId" in d
    assert "instanceId" in d


# ============================================================
# Ephemeral mode constants
# ============================================================


def test_ephemeral_modes_set():
    assert "cli" in EPHEMERAL_CLIENT_MODES
    assert "backend" in EPHEMERAL_CLIENT_MODES
    assert "probe" in EPHEMERAL_CLIENT_MODES
    assert "test" not in EPHEMERAL_CLIENT_MODES
    assert "ui" not in EPHEMERAL_CLIENT_MODES
