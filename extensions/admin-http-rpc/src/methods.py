"""Admin HTTP RPC method allowlist and path definitions.

Mirrors OpenClaw's ``extensions/admin-http-rpc/src/methods.ts``.
"""

from __future__ import annotations

ADMIN_HTTP_RPC_ROUTE_PATH: str = "/api/v1/admin/rpc"

ADMIN_HTTP_RPC_ALLOWED_METHOD_GROUPS: dict[str, list[str]] = {
    "discovery": [
        "commands.list",
    ],
    "gateway": [
        "health",
        "status",
        "logs.tail",
        "usage.status",
        "usage.cost",
        "gateway.restart.request",
        "gateway.suspend.prepare",
        "gateway.suspend.status",
        "gateway.suspend.resume",
    ],
    "config": [
        "config.get",
        "config.schema",
        "config.schema.lookup",
        "config.set",
        "config.patch",
        "config.apply",
    ],
    "channels": [
        "channels.status",
        "channels.start",
        "channels.stop",
        "channels.logout",
    ],
    "web": [
        "web.login.start",
        "web.login.wait",
    ],
    "models": [
        "models.list",
        "models.authStatus",
    ],
    "agents": [
        "agents.list",
        "agents.create",
        "agents.update",
        "agents.delete",
    ],
    "approvals": [
        "exec.approvals.get",
        "exec.approvals.set",
        "exec.approvals.node.get",
        "exec.approvals.node.set",
    ],
    "cron": [
        "cron.status",
        "cron.list",
        "cron.get",
        "cron.runs",
        "cron.add",
        "cron.update",
        "cron.remove",
        "cron.run",
    ],
    "devices": [
        "device.pair.list",
        "device.pair.approve",
        "device.pair.reject",
        "device.pair.remove",
    ],
    "nodes": [
        "node.list",
        "node.describe",
        "node.pair.list",
        "node.pair.approve",
        "node.pair.reject",
        "node.pair.remove",
        "node.rename",
    ],
    "tasks": [
        "tasks.list",
        "tasks.get",
        "tasks.cancel",
    ],
    "diagnostics": [
        "doctor.memory.status",
        "update.status",
    ],
}

ADMIN_HTTP_RPC_ALLOWED_METHODS: frozenset[str] = frozenset(
    method for group in ADMIN_HTTP_RPC_ALLOWED_METHOD_GROUPS.values() for method in group
)


def is_admin_http_rpc_allowed_method(method: str) -> bool:
    """Check whether a Gateway RPC method is exposed over Admin HTTP RPC."""
    if not method or not isinstance(method, str):
        return False
    return method.strip() in ADMIN_HTTP_RPC_ALLOWED_METHODS


def list_admin_http_rpc_allowed_methods() -> list[str]:
    """List all Gateway RPC methods exposed over Admin HTTP RPC (sorted)."""
    return sorted(ADMIN_HTTP_RPC_ALLOWED_METHODS)


__all__ = [
    "ADMIN_HTTP_RPC_ALLOWED_METHODS",
    "ADMIN_HTTP_RPC_ALLOWED_METHOD_GROUPS",
    "ADMIN_HTTP_RPC_ROUTE_PATH",
    "is_admin_http_rpc_allowed_method",
    "list_admin_http_rpc_allowed_methods",
]
