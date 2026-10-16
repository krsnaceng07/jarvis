"""Protocol handshake, capability negotiation, and version validation for Track 3.5.

Ensures client and gateway align on protocol "jarvis.gateway" v3.4.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from jarvis_client.errors import ClientErrorCode, JarvisClientException

PROTOCOL_SPECIFICATION: str = "jarvis.gateway"
CLIENT_PROTOCOL_VERSION: str = "3.4"
MIN_COMPATIBLE_VERSION: str = "3.4"
MAX_COMPATIBLE_VERSION: str = "3.4"


@dataclass(frozen=True, slots=True)
class ClientCapabilities:
    """Capabilities advertised by client to gateway."""

    streaming: bool = True
    replay: bool = True
    approvals: bool = True
    cancellation: bool = True
    idempotency: bool = True
    backpressure: bool = True

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HandshakeRequest:
    """Client initiation frame for capability and version negotiation."""

    protocol: str = PROTOCOL_SPECIFICATION
    version: str = CLIENT_PROTOCOL_VERSION
    capabilities: ClientCapabilities = field(default_factory=ClientCapabilities)
    client_id: str = "jarvis_client"
    client_type: str = "desktop"

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "version": self.version,
            "capabilities": self.capabilities.to_dict(),
            "clientId": self.client_id,
            "clientType": self.client_type,
        }


@dataclass(frozen=True, slots=True)
class HandshakeResponse:
    """Gateway acceptance of protocol handshake."""

    accepted: bool
    protocol: str
    version: str
    supported_features: dict[str, bool]
    session_id: str | None = None
    server_time_utc: str = ""
    error_message: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HandshakeResponse:
        accepted = bool(data.get("accepted", False) or data.get("status") == "accepted")
        protocol = str(data.get("protocol", PROTOCOL_SPECIFICATION))
        version = str(data.get("version") or data.get("protocolVersion", ""))
        feat_raw = data.get("supportedFeatures") or data.get("serverCapabilities", {})
        if isinstance(feat_raw, list):
            supported_features = {k: True for k in feat_raw}
        elif isinstance(feat_raw, dict):
            supported_features = dict(feat_raw)
        else:
            supported_features = {}

        return cls(
            accepted=accepted,
            protocol=protocol,
            version=version,
            supported_features=supported_features,
            session_id=data.get("sessionId"),
            server_time_utc=str(data.get("serverTimeUtc", "")),
            error_message=data.get("errorMessage"),
        )


def validate_server_handshake(resp: HandshakeResponse | dict[str, Any]) -> HandshakeResponse:
    """Validate gateway response against client compatibility limits."""
    if isinstance(resp, dict):
        resp = HandshakeResponse.from_dict(resp)

    if not resp.accepted:
        raise JarvisClientException(
            code=ClientErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
            message=f"Gateway rejected handshake: {resp.error_message or 'unspecified failure'}",
        )
    if resp.protocol != PROTOCOL_SPECIFICATION:
        raise JarvisClientException(
            code=ClientErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
            message=f"Unsupported protocol '{resp.protocol}'; expected '{PROTOCOL_SPECIFICATION}'.",
        )
    if resp.version != CLIENT_PROTOCOL_VERSION:
        raise JarvisClientException(
            code=ClientErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
            message=f"Gateway protocol version '{resp.version}' incompatible with client '{CLIENT_PROTOCOL_VERSION}'.",
        )
    return resp


__all__ = [
    "PROTOCOL_SPECIFICATION",
    "CLIENT_PROTOCOL_VERSION",
    "ClientCapabilities",
    "HandshakeRequest",
    "HandshakeResponse",
    "validate_server_handshake",
]
