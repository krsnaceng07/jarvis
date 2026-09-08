"""Tests for placement standing grants (resolve/retain/validate/consume).

OpenClaw parity: ``openclaw-main/src/gateway/operator-approval-placement-grants.ts``.
Exercised against real SQLite using the module's verbatim DDL plus a
minimal ``operator_approvals`` projection table (the full approvals
table ships in the state DB; only four columns are read here).
"""

from __future__ import annotations

import sqlite3
import tempfile

import pytest

from src.gateway.placement_standing_grants import (
    PLACEMENT_GRANT_TTL_MS,
    PlacementStandingGrantRuntime,
    ensure_placement_grant_tables,
    resolve_placement_binding,
)

EPOCH = "epoch-1"
NOW = 1_700_000_000_000


def _factory():
    """File-backed scratch DB factory. Every call opens a FRESH connection
    (the runtime closes connections after use, like production)."""
    path = tempfile.mktemp(suffix=".sqlite")
    setup = sqlite3.connect(path)
    setup.row_factory = sqlite3.Row
    ensure_placement_grant_tables(setup)
    setup.execute(
        "CREATE TABLE operator_approvals (approval_id TEXT PRIMARY KEY, status TEXT, "
        "decision TEXT, runtime_epoch TEXT)"
    )
    setup.commit()
    setup.close()

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    return factory


def _exec(factory, sql, params=()):
    conn = factory()
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _seed(factory, *, approval_decision="allow-always", approval_epoch=EPOCH):
    conn = factory()
    try:
        conn.execute(
            "INSERT INTO worker_session_placements (session_id, agent_id, session_key, "
            "execution_mode, state, environment_id, active_owner_epoch, "
            "remote_workspace_dir, transition_generation) VALUES ('sess-1', 'main', "
            "'agent:main:main', 'remote-exec', 'active', 'env-1', 3, '/ws', 7)"
        )
        conn.execute(
            "INSERT INTO worker_environments (environment_id, provider_id, profile_id, "
            "profile_snapshot_json, provision_operation_id, node_device_id, state, "
            "owner_epoch, attached_session_ids_json, created_at_ms, updated_at_ms, "
            "state_changed_at_ms) VALUES ('env-1', 'crabbox', 'p1', '{}', 'op-1', "
            "'node-1', 'attached', 3, '[\"sess-1\"]', 0, 0, 0)"
        )
        conn.execute(
            "INSERT INTO operator_approvals (approval_id, status, decision, runtime_epoch) "
            "VALUES ('appr-1', 'allowed', ?, ?)",
            (approval_decision, approval_epoch),
        )
        conn.commit()
    finally:
        conn.close()


def _input():
    return {
        "pluginId": "codex",
        "command": "codex.exec-server.stdio.v1",
        "approvalScope": "codex.exec-server",
        "agentId": "main",
        "sessionKey": "agent:main:main",
        "nodeId": "node-1",
        "pairingGeneration": "pg-1",
    }


def _open(factory):
    conn = factory()
    conn.row_factory = sqlite3.Row
    return conn


def _runtime(factory):
    now = [NOW]
    rt = PlacementStandingGrantRuntime(factory, EPOCH, now_ms=lambda: now[0])
    return rt, now


def _retained(factory):
    rt, now = _runtime(factory)
    conn = _open(factory)
    try:
        binding = resolve_placement_binding(conn, _input())
    finally:
        conn.close()
    assert binding is not None
    assert binding["sessionId"] == "sess-1"
    assert binding["environmentId"] == "env-1"
    assert binding["ownerEpoch"] == 3
    assert binding["placementGeneration"] == 7
    assert binding["cwd"] == "/ws"
    assert rt.retain({**binding, "approvalId": "appr-1", "nowMs": NOW}) is True
    return rt, now, binding


def _resolve(factory, params):
    conn = _open(factory)
    try:
        return resolve_placement_binding(conn, params)
    finally:
        conn.close()


def _table_names(factory):
    conn = _open(factory)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_ensure_is_idempotent():
    factory = _factory()
    conn = _open(factory)
    try:
        ensure_placement_grant_tables(conn)
        ensure_placement_grant_tables(conn)
    finally:
        conn.close()
    tables = _table_names(factory)
    assert {"worker_session_placements", "worker_environments"} <= tables


def test_resolve_binding_happy_path():
    factory = _factory()
    _seed(factory)
    binding = _resolve(factory, _input())
    assert binding is not None
    assert binding["sessionId"] == "sess-1"


@pytest.mark.parametrize(
    "mutate",
    [
        {"nodeId": ""},
        {"agentId": "  "},
        {"pairingGeneration": None},
    ],
)
def test_resolve_binding_rejects_blank_inputs(mutate):
    factory = _factory()
    _seed(factory)
    params = {**_input(), **mutate}
    assert _resolve(factory, params) is None


def test_resolve_binding_requires_exactly_one_candidate():
    factory = _factory()
    _seed(factory)
    assert _resolve(factory, _input()) is not None
    _exec(
        factory,
        "INSERT INTO worker_session_placements (session_id, agent_id, session_key, "
        "execution_mode, state) VALUES ('sess-2', 'main', 'agent:main:main', "
        "'remote-exec', 'active')",
    )
    assert _resolve(factory, _input()) is None


def test_validate_consumed_happy_path():
    factory = _factory()
    _seed(factory)
    rt, _now, binding = _retained(factory)
    assert rt.validate(binding)["outcome"] == "consumed"
    assert rt.consume(binding)["outcome"] == "consumed"


def test_no_grant_without_retain():
    factory = _factory()
    _seed(factory)
    rt, _now, binding = _retained(factory)
    other = dict(binding)
    other["sessionId"] = "sess-9"
    assert rt.validate(other)["outcome"] == "no-grant"


def test_expired_grant():
    factory = _factory()
    _seed(factory)
    rt, now, binding = _retained(factory)
    now[0] = NOW + PLACEMENT_GRANT_TTL_MS + 1
    assert rt.validate(binding)["outcome"] == "expired"
    # Second read stays expired-free: the record was dropped.
    assert rt.validate(binding)["outcome"] == "no-grant"


def test_node_and_pairing_changes():
    factory = _factory()
    _seed(factory)
    rt, _now, binding = _retained(factory)
    moved = dict(binding, nodeId="node-2")
    assert rt.validate(moved)["outcome"] == "node-changed"
    rt2, _now2, binding2 = _retained(factory)
    repaired = dict(binding2, pairingGeneration="pg-2")
    assert rt2.validate(repaired)["outcome"] == "pairing-changed"


def test_placement_changed_and_missing():
    factory = _factory()
    _seed(factory)
    rt, _now, binding = _retained(factory)
    _exec(factory, "UPDATE worker_session_placements SET remote_workspace_dir = '/else'")
    assert rt.validate(binding)["outcome"] == "placement-changed"

    factory = _factory()
    _seed(factory)
    rt, _now, binding = _retained(factory)
    _exec(factory, "DELETE FROM worker_session_placements")
    assert rt.validate(binding)["outcome"] == "placement-missing"


def test_approval_outcomes():
    factory = _factory()
    _seed(factory)
    rt, _now, binding = _retained(factory)
    _exec(factory, "DELETE FROM operator_approvals")
    assert rt.validate(binding)["outcome"] == "approval-missing"

    factory = _factory()
    _seed(factory)
    rt, _now, binding = _retained(factory)
    _exec(factory, "UPDATE operator_approvals SET decision = 'allow-once'")
    assert rt.validate(binding)["outcome"] == "approval-not-allow-always"

    factory = _factory()
    _seed(factory)
    rt, _now, binding = _retained(factory)
    _exec(
        factory,
        "UPDATE operator_approvals SET decision = 'allow-always', runtime_epoch = 'epoch-2'",
    )
    assert rt.validate(binding)["outcome"] == "approval-not-allow-always"


def test_retain_rejects_without_current_binding_or_approval():
    factory = _factory()
    _seed(factory)
    rt, _now, _binding = _retained(factory)
    stale = dict(_binding, cwd="/else")
    assert rt.retain({**stale, "approvalId": "appr-1", "nowMs": NOW}) is False
    assert rt.retain({**_binding, "approvalId": "missing", "nowMs": NOW}) is False


def test_ttl_cap():
    factory = _factory()
    _seed(factory)
    rt, _now, binding = _retained(factory)
    assert rt.validate(binding)["grant"]["expiresAtMs"] == NOW + PLACEMENT_GRANT_TTL_MS
    rt2, _now2, binding2 = _retained(factory)
    assert dict(rt2._grants)  # retained under the same key
    custom = PlacementStandingGrantRuntime(factory, EPOCH, now_ms=lambda: NOW)
    assert (
        custom.retain({**binding2, "approvalId": "appr-1", "nowMs": NOW, "expiresAtMs": NOW + 1})
        is True
    )
    assert custom.validate(binding2)["grant"]["expiresAtMs"] == NOW + 1
