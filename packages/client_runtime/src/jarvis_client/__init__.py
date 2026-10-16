"""jarvis_client: Track 3.5 Client Runtime SDK.

Decoupled client runtime for Desktop HUD, Web Frontend, and Headless CLI.
Communicates strictly with the Gateway via Track 3.4 JSON-RPC / WebSocket.
"""

from jarvis_client.adapters.cli.cli_adapter import CliAdapter
from jarvis_client.adapters.desktop.hud_adapter import DesktopHudAdapter, DesktopSignalPayload
from jarvis_client.adapters.web.web_adapter import (
    DEFAULT_ALLOWED_ORIGINS,
    WebSessionAdapter,
    WebTabContext,
    is_allowed_origin,
)
from jarvis_client.auth.secure_store import SecureCredentialStore
from jarvis_client.auth.token_manager import CredentialState as TokenLifecycleState, TokenManager
from jarvis_client.commands.approval import build_approval_response_frame
from jarvis_client.commands.cancellation import (
    CancellationAcceptance,
    build_cancellation_frame,
    parse_cancellation_acceptance,
)
from jarvis_client.commands.chat import (
    ChatAcceptance,
    build_chat_send_frame,
    parse_chat_acceptance,
)
from jarvis_client.connection.backoff import BackoffPolicy
from jarvis_client.connection.heartbeat import ClientHeartbeatManager
from jarvis_client.connection.lifecycle import ConnectionLifecycle, ConnectionState
from jarvis_client.connection.transport import ClientTransport, LoopbackTransport
from jarvis_client.errors import (
    AmbiguousRequestError,
    AuthenticationError,
    ClientErrorCode,
    JarvisClientException,
    OfflineError,
    StaleActionError,
)
from jarvis_client.events.decoder import (
    CURRENT_EVENT_SCHEMA_VERSION,
    DecodedEvent,
    EventDecoder,
)
from jarvis_client.events.ordering import SequenceOrderingGuard
from jarvis_client.events.reducer import ClientEventReducer
from jarvis_client.protocol.client import JarvisClient
from jarvis_client.protocol.frames import (
    MAX_CLIENT_FRAME_BYTES,
    RPCRequestFrame,
    RPCResponseFrame,
)
from jarvis_client.protocol.handshake import (
    CLIENT_PROTOCOL_VERSION,
    HandshakeRequest,
    HandshakeResponse,
    validate_server_handshake,
)
from jarvis_client.session.cursor import CursorStore, ResumeCursor
from jarvis_client.session.reconciliation import (
    RequestOutcomeStatus,
    RequestReconciler,
)
from jarvis_client.session.session import ClientSession
from jarvis_client.state.client_view import (
    ClientViewState,
    NodeViewState,
    TaskViewState,
    ViewFreshness,
)
from jarvis_client.state.health import ClientDiagnostics, DiagnosticHealthStatus

__all__ = [
    # Main Client
    "JarvisClient",
    # Adapters
    "DesktopHudAdapter",
    "DesktopSignalPayload",
    "WebSessionAdapter",
    "WebTabContext",
    "is_allowed_origin",
    "DEFAULT_ALLOWED_ORIGINS",
    "CliAdapter",
    # Connection & Transport
    "ClientTransport",
    "LoopbackTransport",
    "ConnectionLifecycle",
    "ConnectionState",
    "BackoffPolicy",
    "ClientHeartbeatManager",
    # Auth
    "TokenManager",
    "TokenLifecycleState",
    "SecureCredentialStore",
    # Session & Cursor
    "ClientSession",
    "ResumeCursor",
    "CursorStore",
    "RequestReconciler",
    "RequestOutcomeStatus",
    # Protocol & Frames
    "MAX_CLIENT_FRAME_BYTES",
    "CLIENT_PROTOCOL_VERSION",
    "HandshakeRequest",
    "HandshakeResponse",
    "validate_server_handshake",
    "RPCRequestFrame",
    "RPCResponseFrame",
    # Commands
    "build_chat_send_frame",
    "parse_chat_acceptance",
    "ChatAcceptance",
    "build_approval_response_frame",
    "build_cancellation_frame",
    "parse_cancellation_acceptance",
    "CancellationAcceptance",
    # Events & State
    "CURRENT_EVENT_SCHEMA_VERSION",
    "EventDecoder",
    "DecodedEvent",
    "SequenceOrderingGuard",
    "ClientEventReducer",
    "ClientViewState",
    "TaskViewState",
    "NodeViewState",
    "ViewFreshness",
    "ClientDiagnostics",
    "DiagnosticHealthStatus",
    # Errors
    "ClientErrorCode",
    "JarvisClientException",
    "AuthenticationError",
    "StaleActionError",
    "AmbiguousRequestError",
    "OfflineError",
]
