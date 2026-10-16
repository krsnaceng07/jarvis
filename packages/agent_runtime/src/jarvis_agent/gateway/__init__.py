"""Track 3.4 — Multi-Session Gateway Integration, Streaming Runtime & Protocol Seam.

Exports protocol models, errors, versioning, session registry, and dispatcher components.
"""

from jarvis_agent.gateway.errors import (
    GatewayError,
    GatewayErrorCode,
    GatewayException,
)
from jarvis_agent.gateway.models import (
    MAX_EVENT_BYTES,
    MAX_REQUEST_BYTES,
    MAX_STREAM_CHUNK_BYTES,
    ClientIdentity,
    ConnectionContext,
    ConnectionState,
    DeliveryStatus,
    EnrichedGatewayEvent,
    EventCategory,
    GatewayEvent,
    GatewayRequest,
    GatewayResponse,
    ResumeCursor,
    RPCError,
    RPCMethod,
    RPCRequest,
    RPCResponse,
    SequenceTriad,
    StreamChunkPayload,
)
from jarvis_agent.gateway.version import (
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    SUPPORTED_FEATURES,
    ProtocolCapabilities,
    ProtocolHandshake,
)

__all__ = [
    "GatewayErrorCode",
    "GatewayError",
    "GatewayException",
    "MAX_REQUEST_BYTES",
    "MAX_EVENT_BYTES",
    "MAX_STREAM_CHUNK_BYTES",
    "ConnectionState",
    "EventCategory",
    "DeliveryStatus",
    "ClientIdentity",
    "ConnectionContext",
    "SequenceTriad",
    "ResumeCursor",
    "StreamChunkPayload",
    "EnrichedGatewayEvent",
    "GatewayEvent",
    "GatewayRequest",
    "GatewayResponse",
    "RPCError",
    "RPCMethod",
    "RPCRequest",
    "RPCResponse",
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "SUPPORTED_FEATURES",
    "ProtocolCapabilities",
    "ProtocolHandshake",
]
