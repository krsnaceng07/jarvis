"""Protocol versioning and capability negotiation for Track 3.4."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException

PROTOCOL_NAME: str = "jarvis.gateway"
PROTOCOL_VERSION: str = "3.4"
SUPPORTED_FEATURES: frozenset[str] = frozenset(
    [
        "streaming",
        "replay",
        "approvals",
        "cancellation",
        "idempotency",
        "backpressure",
    ]
)


@dataclass(frozen=True, slots=True)
class ProtocolCapabilities:
    """Declared protocol capabilities for client/server negotiation."""

    streaming: bool = True
    replay: bool = True
    approvals: bool = True
    cancellation: bool = True
    idempotency: bool = True
    backpressure: bool = True

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProtocolHandshake:
    """Protocol handshake frame exchanged during connection setup."""

    protocol: str = PROTOCOL_NAME
    version: str = PROTOCOL_VERSION
    capabilities: ProtocolCapabilities = ProtocolCapabilities()

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "version": self.version,
            "capabilities": self.capabilities.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProtocolHandshake:
        proto = data.get("protocol", "")
        ver = data.get("version", "")
        caps_data = data.get("capabilities", {})
        caps = (
            ProtocolCapabilities(**caps_data)
            if isinstance(caps_data, dict)
            else ProtocolCapabilities()
        )
        return cls(protocol=proto, version=ver, capabilities=caps)

    def validate_compatibility(self) -> None:
        """Validate whether the client protocol and version are compatible with this host."""
        if self.protocol != PROTOCOL_NAME:
            raise GatewayException(
                code=GatewayErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                message=f"Unsupported protocol: '{self.protocol}'. Expected '{PROTOCOL_NAME}'.",
            )
        # We accept minor compatibility within 3.x
        parts = self.version.split(".")
        if not parts or parts[0] != "3":
            raise GatewayException(
                code=GatewayErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                message=f"Incompatible protocol major version '{self.version}'. Host requires 3.x.",
            )


__all__ = [
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "SUPPORTED_FEATURES",
    "ProtocolCapabilities",
    "ProtocolHandshake",
]
