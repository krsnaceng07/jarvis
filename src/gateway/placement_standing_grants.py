"""Placement-scoped standing grants for dangerous plugin-owned node launches.

OpenClaw parity: mirrors
``openclaw-main/src/gateway/operator-approval-placement-grants.ts``.

Grants live only for the Gateway process (a process-local map); the
durable parent approval and the current placement remain the
authorization owners at every use. Every dispatch revalidates: standing
placement, environment attachment, node/pairing identity, approval
status/decision/epoch, and the 30-day TTL.

Table DDL below is verbatim OpenClaw canonical shape (subset: the two
tables this runtime reads). Tables are created lazily via
:func:`ensure_placement_grant_tables` on first grant-runtime use —
``CREATE TABLE IF NOT EXISTS`` only, no version bump (additive
surface). The ``operator_approvals`` table already ships in the state
DB; only its ``(approval_id, status, decision, runtime_epoch)``
projection is read here.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Callable

#: Standing-grant time to live. Mirrors ``PLACEMENT_GRANT_TTL_MS``.
PLACEMENT_GRANT_TTL_MS: int = 30 * 24 * 60 * 60 * 1000

#: Canonical DDL for the placement table (verbatim OpenClaw shape).
WORKER_SESSION_PLACEMENTS_DDL = (
    "CREATE TABLE IF NOT EXISTS worker_session_placements ("
    "session_id TEXT NOT NULL PRIMARY KEY, "
    "agent_id TEXT NOT NULL, "
    "session_key TEXT NOT NULL, "
    "execution_mode TEXT CHECK (execution_mode IN ('worker-turn', 'remote-exec')), "
    "state TEXT NOT NULL CHECK (state IN ('local', 'requested', 'provisioning', "
    "'syncing', 'starting', 'active', 'draining', 'reconciling', 'reclaimed', 'failed')), "
    "environment_id TEXT, "
    "transition_generation INTEGER NOT NULL DEFAULT 0 CHECK (transition_generation >= 0), "
    "active_owner_epoch INTEGER CHECK (active_owner_epoch IS NULL OR active_owner_epoch >= 1), "
    "workspace_base_manifest_ref TEXT, "
    "remote_workspace_dir TEXT, "
    "worker_bundle_hash TEXT, "
    "last_transcript_ack_cursor INTEGER CHECK "
    "(last_transcript_ack_cursor IS NULL OR last_transcript_ack_cursor >= 0), "
    "last_live_event_ack_cursor INTEGER CHECK "
    "(last_live_event_ack_cursor IS NULL OR last_live_event_ack_cursor >= 0), "
    "recovery_error TEXT, "
    "turn_claim_owner TEXT CHECK (turn_claim_owner IN ('local', 'worker')), "
    "turn_claim_id TEXT, "
    "turn_claim_run_id TEXT, "
    "turn_claim_generation INTEGER CHECK "
    "(turn_claim_generation IS NULL OR turn_claim_generation >= 0), "
    "turn_claim_owner_epoch INTEGER CHECK "
    "(turn_claim_owner_epoch IS NULL OR turn_claim_owner_epoch >= 1)"
    ");"
)

#: Canonical DDL for the environments table (verbatim OpenClaw shape;
#: only the attachment projection is read here).
WORKER_ENVIRONMENTS_DDL = (
    "CREATE TABLE IF NOT EXISTS worker_environments ("
    "environment_id TEXT NOT NULL PRIMARY KEY, "
    "provider_id TEXT NOT NULL, "
    "profile_id TEXT NOT NULL, "
    "profile_snapshot_json TEXT NOT NULL, "
    "provision_operation_id TEXT NOT NULL UNIQUE, "
    "lease_id TEXT, "
    "node_setup_id TEXT, "
    "node_device_id TEXT, "
    "ssh_host TEXT, "
    "ssh_port INTEGER CHECK (ssh_port IS NULL OR (ssh_port >= 1 AND ssh_port <= 65535)), "
    "ssh_user TEXT, "
    "ssh_host_key TEXT, "
    "ssh_key_ref_json TEXT, "
    "desktop_json TEXT, "
    "state TEXT NOT NULL CHECK (state IN ('requested', 'provisioning', 'bootstrapping', "
    "'ready', 'attached', 'idle', 'draining', 'destroying', 'destroyed', 'failed', "
    "'orphaned')), "
    "bootstrap_bundle_hash TEXT, "
    "bootstrap_openclaw_version TEXT, "
    "bootstrap_protocol_features_json TEXT, "
    "bootstrap_install_kind TEXT, "
    "owner_epoch INTEGER NOT NULL DEFAULT 0 CHECK (owner_epoch >= 0), "
    "teardown_terminal_state TEXT CHECK (teardown_terminal_state IN ('destroyed', 'failed')), "
    "attached_session_ids_json TEXT NOT NULL DEFAULT '[]', "
    "created_at_ms INTEGER NOT NULL, "
    "updated_at_ms INTEGER NOT NULL, "
    "state_changed_at_ms INTEGER NOT NULL, "
    "idle_since_at_ms INTEGER, "
    "destroy_requested_at_ms INTEGER, "
    "last_error TEXT, "
    "shared_host INTEGER"
    ");"
)


def ensure_placement_grant_tables(conn: sqlite3.Connection) -> None:
    """Create placement/env tables when absent. Idempotent; additive only."""
    conn.executescript(WORKER_SESSION_PLACEMENTS_DDL + WORKER_ENVIRONMENTS_DDL)
    conn.commit()


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _find_placement(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    cur = conn.execute(
        "SELECT session_id, agent_id, session_key, execution_mode, state, "
        "environment_id, active_owner_epoch, remote_workspace_dir, "
        "transition_generation AS generation "
        "FROM worker_session_placements WHERE session_id = ?",
        (session_id,),
    )
    return _row_dict(cur.fetchone())


def _read_environment(conn: sqlite3.Connection, environment_id: str) -> dict[str, Any]:
    cur = conn.execute(
        "SELECT state, node_device_id, owner_epoch, attached_session_ids_json "
        "FROM worker_environments WHERE environment_id = ?",
        (environment_id,),
    )
    return _row_dict(cur.fetchone())


def _read_approval(conn: sqlite3.Connection, approval_id: str) -> dict[str, Any]:
    cur = conn.execute(
        "SELECT status, decision, runtime_epoch FROM operator_approvals WHERE approval_id = ?",
        (approval_id,),
    )
    return _row_dict(cur.fetchone())


def _has_exact_attached_session(value: Any, session_id: str) -> bool:
    """Mirror ``hasExactAttachedSession`` (single-element JSON array)."""
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return False
    return isinstance(parsed, list) and len(parsed) == 1 and parsed[0] == session_id


def _is_placement_binding_current(conn: sqlite3.Connection, binding: dict[str, Any]) -> bool:
    """Mirror ``isPlacementBindingCurrent``."""
    placement = _find_placement(conn, binding.get("sessionId", ""))
    if (
        not placement
        or placement.get("state") != "active"
        or placement.get("execution_mode") != "remote-exec"
        or placement.get("agent_id") != binding.get("agentId")
        or placement.get("session_key") != binding.get("sessionKey")
        or placement.get("environment_id") != binding.get("environmentId")
        or placement.get("active_owner_epoch") != binding.get("ownerEpoch")
        or placement.get("generation") != binding.get("placementGeneration")
        or placement.get("remote_workspace_dir") != binding.get("cwd")
    ):
        return False
    environment = _read_environment(conn, binding.get("environmentId", ""))
    return (
        bool(environment)
        and environment.get("state") == "attached"
        and environment.get("node_device_id") == binding.get("nodeId")
        and environment.get("owner_epoch") == binding.get("ownerEpoch")
        and _has_exact_attached_session(
            environment.get("attached_session_ids_json"), binding.get("sessionId", "")
        )
    )


def _placement_grant_key(binding: dict[str, Any]) -> str:
    """Mirror ``placementGrantKey``."""
    return json.dumps(
        [
            binding.get("pluginId"),
            binding.get("command"),
            binding.get("approvalScope"),
            binding.get("agentId"),
            binding.get("sessionId"),
        ]
    )


def resolve_placement_binding(
    conn: sqlite3.Connection, params: dict[str, Any]
) -> dict[str, Any] | None:
    """Resolve the exact active node-backed placement. Mirrors
    ``resolvePlacementStandingGrantBinding``: blank inputs fail, the
    agent/session must match exactly ONE active remote-exec row, and the
    binding must verify current. Returns the binding dict or ``None``."""
    for key in (
        "pluginId",
        "command",
        "approvalScope",
        "agentId",
        "sessionKey",
        "nodeId",
        "pairingGeneration",
    ):
        value = params.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
    cur = conn.execute(
        "SELECT session_id FROM worker_session_placements "
        "WHERE agent_id = ? AND session_key = ? AND state = 'active' "
        "AND execution_mode = 'remote-exec' LIMIT 2",
        (params["agentId"], params["sessionKey"]),
    )
    candidates = cur.fetchall()
    if len(candidates) != 1:
        return None
    placement = _find_placement(conn, candidates[0]["session_id"])
    if (
        not placement
        or placement.get("state") != "active"
        or placement.get("execution_mode") != "remote-exec"
        or not placement.get("environment_id")
        or not placement.get("active_owner_epoch")
        or not placement.get("remote_workspace_dir")
    ):
        return None
    binding = {
        "pluginId": params["pluginId"],
        "command": params["command"],
        "approvalScope": params["approvalScope"],
        "agentId": params["agentId"],
        "sessionKey": params["sessionKey"],
        "sessionId": placement["session_id"],
        "nodeId": params["nodeId"],
        "pairingGeneration": params["pairingGeneration"],
        "environmentId": placement["environment_id"],
        "ownerEpoch": placement["active_owner_epoch"],
        "placementGeneration": placement["generation"],
        "cwd": placement["remote_workspace_dir"],
    }
    return binding if _is_placement_binding_current(conn, binding) else None


class PlacementStandingGrantRuntime:
    """Process-local standing-grant store over durable placement/approval rows.

    Mirrors ``createPlacementStandingGrantRuntime``: ``retain`` stores a
    verified grant (capped at 30 days); ``validate``/``consume`` re-check
    node identity, pairing generation, binding fields, placement currency,
    and the parent approval (same epoch, ``allowed`` + ``allow-always``)
    inside one synchronous commit section. Stale grants are dropped with
    their outcome code (``no-grant`` / ``expired`` / ``approval-missing`` /
    ``approval-not-allow-always`` / ``placement-missing`` /
    ``placement-changed`` / ``node-changed`` / ``pairing-changed``).
    """

    def __init__(
        self,
        conn_factory: Callable[[], sqlite3.Connection],
        runtime_epoch: str,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self._conn_factory = conn_factory
        self._runtime_epoch = runtime_epoch
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._grants: dict[str, dict[str, Any]] = {}

    def retain(self, grant: dict[str, Any]) -> bool:
        """Store a verified standing grant. *grant* carries the binding
        plus ``approvalId``, ``nowMs``, and optional ``expiresAtMs``."""
        now_ms = grant.get("nowMs")
        if not isinstance(now_ms, (int, float)):
            return False
        max_expires = now_ms + PLACEMENT_GRANT_TTL_MS
        requested = grant.get("expiresAtMs")
        expires_at = (
            min(requested, max_expires) if isinstance(requested, (int, float)) else max_expires
        )
        if expires_at <= now_ms:
            return False
        try:
            conn = self._conn_factory()
            try:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    if not _is_placement_binding_current(conn, grant):
                        conn.rollback()
                        return False
                    approval = _read_approval(conn, grant.get("approvalId", ""))
                    if (
                        not approval
                        or approval.get("runtime_epoch") != self._runtime_epoch
                        or approval.get("status") != "allowed"
                        or approval.get("decision") != "allow-always"
                    ):
                        conn.rollback()
                        return False
                    conn.commit()
                except Exception:
                    conn.rollback()
                    return False
                finally:
                    conn.close()
            except Exception:
                return False
        except Exception:
            return False
        retained = {
            key: grant[key]
            for key in (
                "pluginId",
                "command",
                "approvalScope",
                "agentId",
                "sessionKey",
                "sessionId",
                "nodeId",
                "pairingGeneration",
                "environmentId",
                "ownerEpoch",
                "placementGeneration",
                "cwd",
            )
            if key in grant
        }
        retained["mintedByApprovalId"] = grant.get("approvalId")
        retained["expiresAtMs"] = expires_at
        self._grants[_placement_grant_key(retained)] = retained
        return True

    def _resolve_retained(self, binding: dict[str, Any]) -> dict[str, Any]:
        # Database errors propagate (mirrors the TS transaction, which has
        # no catch): only policy decisions return outcome codes.
        now_ms = self._now_ms()
        key = _placement_grant_key(binding)
        grant = self._grants.get(key)
        if grant is None:
            return {"outcome": "no-grant"}
        if grant.get("expiresAtMs", 0) <= now_ms:
            del self._grants[key]
            return {"outcome": "expired"}
        if grant.get("nodeId") != binding.get("nodeId"):
            del self._grants[key]
            return {"outcome": "node-changed"}
        if grant.get("pairingGeneration") != binding.get("pairingGeneration"):
            del self._grants[key]
            return {"outcome": "pairing-changed"}
        conn = self._conn_factory()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                matches = (
                    grant.get("sessionKey") == binding.get("sessionKey")
                    and grant.get("environmentId") == binding.get("environmentId")
                    and grant.get("ownerEpoch") == binding.get("ownerEpoch")
                    and grant.get("placementGeneration") == binding.get("placementGeneration")
                    and grant.get("cwd") == binding.get("cwd")
                )
                if not matches or not _is_placement_binding_current(conn, binding):
                    del self._grants[key]
                    outcome = (
                        "placement-changed"
                        if _find_placement(conn, binding.get("sessionId", ""))
                        else "placement-missing"
                    )
                    conn.commit()
                    return {"outcome": outcome}
                approval = _read_approval(conn, grant.get("mintedByApprovalId", ""))
                if not approval:
                    del self._grants[key]
                    conn.commit()
                    return {"outcome": "approval-missing"}
                if (
                    approval.get("runtime_epoch") != self._runtime_epoch
                    or approval.get("status") != "allowed"
                    or approval.get("decision") != "allow-always"
                ):
                    del self._grants[key]
                    conn.commit()
                    return {"outcome": "approval-not-allow-always"}
                conn.commit()
                return {"outcome": "consumed", "grant": grant}
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

    def validate(self, binding: dict[str, Any]) -> dict[str, Any]:
        """Check a retained grant without consuming it (same outcomes)."""
        return self._resolve_retained(binding)

    def consume(self, binding: dict[str, Any]) -> dict[str, Any]:
        """Check a retained grant (same outcomes; consumption is
        idempotent by binding — revalidation decides every use)."""
        return self._resolve_retained(binding)


__all__ = [
    "PLACEMENT_GRANT_TTL_MS",
    "WORKER_ENVIRONMENTS_DDL",
    "WORKER_SESSION_PLACEMENTS_DDL",
    "PlacementStandingGrantRuntime",
    "ensure_placement_grant_tables",
    "resolve_placement_binding",
]
