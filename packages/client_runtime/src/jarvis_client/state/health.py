"""Client diagnostic health model for Track 3.5.

Distinguishes transport connectivity, session authorization, and runtime responsiveness.
Zero secret exposure in metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DiagnosticHealthStatus(str, Enum):
    """Overall client health classification."""

    CONNECTED = "connected"
    DEGRADED = "degraded"
    RECONNECTING = "reconnecting"
    OFFLINE = "offline"
    AUTH_REQUIRED = "auth_required"
    PROTOCOL_ERROR = "protocol_error"


@dataclass(frozen=True, slots=True)
class ClientDiagnostics:
    """Read-only metrics container for UI diagnostics and telemetry."""

    status: DiagnosticHealthStatus
    connection_id: str
    session_id: str
    client_id: str
    protocol_version: str
    last_global_seq: int
    last_connection_seq: int
    reconnect_count: int
    last_rtt_ms: float
    events_received: int
    events_quarantined: int
    telemetry_chunks_received: int
    is_live: bool


__all__ = ["DiagnosticHealthStatus", "ClientDiagnostics"]
