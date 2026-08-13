"""Gateway WS protocol schema — request, response, and event shapes.

Mirrors OpenClaw's ``packages/gateway-protocol/schema/`` cluster.
Every frame exchanged over the gateway WebSocket uses one of these shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


# ── RPC method enum ────────────────────────────────────────────────────


class RPCMethod(str, Enum):
    """Known gateway RPC method names."""

    # Sessions
    SESSIONS_CREATE = "sessions.create"
    SESSIONS_LIST = "sessions.list"
    SESSIONS_GET = "sessions.get"

    # Agents
    AGENTS_RUN = "agents.run"
    AGENTS_ABORT = "agents.abort"

    # Plugins
    PLUGINS_LIST = "plugins.list"

    # Config
    CONFIG_GET = "config.get"
    CONFIG_PATCH = "config.patch"

    # Channels
    CHANNELS_SEND = "channels.send"

    # Admin
    ADMIN_RELOAD = "admin.reload"
    ADMIN_STATUS = "admin.status"

    # Exec Approvals
    EXEC_APPROVALS_REQUEST = "exec.approvals.request"
    EXEC_APPROVALS_RESPOND = "exec.approvals.respond"


# ── Request ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    """A Gateway protocol request frame (OpenClaw format).

    Format: { "type": "req", "id": "...", "method": "...", "params": {...} }
    """

    method: str
    id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    type: Literal["req"] = "req"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "req", "method": self.method, "id": self.id, "params": self.params}


# ── Error ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GatewayError:
    """A Gateway protocol error object."""

    code: int
    message: str
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d

    # ── Convenience constructors ──────────────────────────────────────

    @classmethod
    def parse_error(cls, detail: str = "") -> GatewayError:
        return cls(-32700, "Parse error", detail or None)

    @classmethod
    def invalid_request(cls, detail: str = "") -> GatewayError:
        return cls(-32600, "Invalid request", detail or None)

    @classmethod
    def method_not_found(cls, method: str = "") -> GatewayError:
        return cls(-32601, f"Method not found: {method}", method or None)

    @classmethod
    def invalid_params(cls, detail: str = "") -> GatewayError:
        return cls(-32602, "Invalid params", detail or None)

    @classmethod
    def internal_error(cls, detail: str = "") -> GatewayError:
        return cls(-32603, "Internal error", detail or None)

    @classmethod
    def auth_error(cls, detail: str = "") -> GatewayError:
        return cls(-32001, "Unauthorized", detail or None)


# ── Response ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GatewayResponse:
    """A Gateway protocol response frame (OpenClaw format).

    Format: { "type": "res", "id": "...", "ok": bool, "payload": any, "error": GatewayError | None }
    """

    id: str = ""
    payload: Any = None
    error: GatewayError | None = None
    type: Literal["res"] = "res"

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": "res", "id": self.id, "ok": self.ok}
        if self.error is not None:
            d["error"] = self.error.to_dict()
        else:
            d["payload"] = self.payload
        return d


# ── Event ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GatewayEvent:
    """A Gateway protocol event frame (OpenClaw format).

    Format: { "type": "event", "event": "...", "payload": any, "seq": int | None, "stateVersion": int | None }
    """

    event: str
    payload: Any
    seq: int | None = None
    stateVersion: int | None = None
    type: Literal["event"] = "event"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": "event", "event": self.event, "payload": self.payload}
        if self.seq is not None:
            d["seq"] = self.seq
        if self.stateVersion is not None:
            d["stateVersion"] = self.stateVersion
        return d


__all__ = ["GatewayError", "RPCMethod", "GatewayRequest", "GatewayResponse", "GatewayEvent"]

# JSON-RPC 2.0 compatibility shapes expected by some tests


@dataclass(frozen=True, slots=True)
class RPCRequest:
    """JSON-RPC 2.0 request shape used by Gateway RPC handler tests.

    Format: { "jsonrpc": "2.0", "method": "...", "id": "...", "params": {...} }
    """

    method: str
    id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    jsonrpc: Literal["2.0"] = "2.0"

    def to_dict(self) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "method": self.method, "id": self.id, "params": self.params}


@dataclass(frozen=True, slots=True)
class RPCResponse:
    """JSON-RPC 2.0 response shape.

    Format: { "jsonrpc": "2.0", "id": "...", "result": any } or { "jsonrpc": "2.0", "id": "...", "error": {...} }
    """

    id: str = ""
    result: Any | None = None
    error: GatewayError | None = None
    jsonrpc: Literal["2.0"] = "2.0"

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id}
        if self.error is not None:
            d["error"] = self.error.to_dict()
        else:
            d["result"] = self.result
        return d


# Backwards RPC aliases
RPCError = GatewayError

__all__ += ["RPCError", "RPCRequest", "RPCResponse"]
