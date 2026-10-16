"""jarvis_learning.training.named_pipe_ipc — Windows Named Pipe IPC & Protocol Framing.

Enforces:
1. INV-P9-IPC-001: Structured framing (protocol_version, worker_epoch, sequence_number, message_id, payload_digest).
2. INV-P9-IPC-002: Stale epoch messages are immediately rejected.
3. INV-P9-IPC-003: Idempotent message deduplication via message_id cache.
4. Native Windows Named Pipe transport (PipeListener / PipeClient) with cross-platform fallback.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

IPC_PROTOCOL_VERSION = "1.0.0"


class IpcMessageType(enum.StrEnum):
    """Supported IPC message types across host-worker boundary."""

    HANDSHAKE = "HANDSHAKE"
    HEARTBEAT = "HEARTBEAT"
    EVENT_DISPATCH = "EVENT_DISPATCH"
    SHADOW_RESULT = "SHADOW_RESULT"
    ACK = "ACK"
    CANCEL = "CANCEL"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class IpcMessage:
    """Structured, immutable IPC frame exchanging between host and worker."""

    message_id: str
    sequence_number: int
    session_id: str
    worker_id: str
    worker_epoch: int
    connection_epoch: int
    protocol_version: str
    message_type: str
    payload_digest: str
    payload: dict[str, Any]
    timestamp_monotonic: float = field(default_factory=time.monotonic)
    timestamp_wallclock: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        *,
        message_type: str | IpcMessageType,
        payload: dict[str, Any],
        session_id: str = "desktop:hud",
        worker_id: str = "worker_default",
        worker_epoch: int = 1,
        connection_epoch: int = 1,
        sequence_number: int = 1,
    ) -> IpcMessage:
        raw_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(raw_payload).hexdigest()
        return cls(
            message_id=f"msg_{uuid.uuid4().hex[:12]}",
            sequence_number=sequence_number,
            session_id=session_id,
            worker_id=worker_id,
            worker_epoch=worker_epoch,
            connection_epoch=connection_epoch,
            protocol_version=IPC_PROTOCOL_VERSION,
            message_type=str(message_type),
            payload_digest=digest,
            payload=payload,
        )

    def verify_digest(self) -> bool:
        """Verify that payload matches the declared payload_digest."""
        raw_payload = json.dumps(self.payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        expected = hashlib.sha256(raw_payload).hexdigest()
        return self.payload_digest == expected

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IpcMessage:
        return cls(
            message_id=str(data["message_id"]),
            sequence_number=int(data["sequence_number"]),
            session_id=str(data["session_id"]),
            worker_id=str(data["worker_id"]),
            worker_epoch=int(data["worker_epoch"]),
            connection_epoch=int(data["connection_epoch"]),
            protocol_version=str(data.get("protocol_version", IPC_PROTOCOL_VERSION)),
            message_type=str(data["message_type"]),
            payload_digest=str(data["payload_digest"]),
            payload=dict(data.get("payload", {})),
            timestamp_monotonic=float(data.get("timestamp_monotonic", time.monotonic())),
            timestamp_wallclock=float(data.get("timestamp_wallclock", time.time())),
        )


def get_default_pipe_name(session_id: str = "desktop") -> str:
    """Generate canonical Windows Named Pipe path for session."""
    clean_id = session_id.replace(":", "_").replace("/", "_").replace("\\", "_")
    if sys.platform == "win32":
        return rf"\\.\pipe\jarvis_learning_ipc_{clean_id}_{os.getpid()}"
    # Cross-platform fallback address
    return f"127.0.0.1:{65400 + (os.getpid() % 100)}"


class WindowsNamedPipeServer:
    """Host-side Windows Named Pipe IPC listener managing connections and validation."""

    def __init__(self, pipe_name: str | None = None, session_id: str = "desktop") -> None:
        self.pipe_name = pipe_name or get_default_pipe_name(session_id)
        self.session_id = session_id
        self._listener: Any = None
        self._conn: Any = None
        self._lock = threading.Lock()
        self._is_running = False
        self._thread: threading.Thread | None = None

        self.current_connection_epoch = 0
        self.current_worker_epoch = 0
        self.last_heartbeat_monotonic = 0.0
        self.last_seen_sequence = 0
        self._seen_message_ids: set[str] = set()

        self.total_messages_received = 0
        self.total_stale_epoch_drops = 0
        self.total_duplicate_drops = 0
        self.total_digest_mismatches = 0
        self.message_handlers: dict[str, list[Callable[[IpcMessage], None]]] = {}

    def register_handler(
        self, msg_type: str | IpcMessageType, handler: Callable[[IpcMessage], None]
    ) -> None:
        key = str(msg_type)
        if key not in self.message_handlers:
            self.message_handlers[key] = []
        self.message_handlers[key].append(handler)

    def start(self) -> None:
        """Initialize listener and accept connection in background thread."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True

            if sys.platform == "win32":
                from multiprocessing.connection import PipeListener

                self._listener = PipeListener(self.pipe_name)
            else:
                from multiprocessing.connection import Listener

                host, port = self.pipe_name.split(":")
                self._listener = Listener((host, int(port)), family="AF_INET")

            self._thread = threading.Thread(
                target=self._server_loop, daemon=True, name="named_pipe_server"
            )
            self._thread.start()
            logger.info("WindowsNamedPipeServer started on %s", self.pipe_name)

    def _server_loop(self) -> None:
        while self._is_running:
            try:
                conn = self._listener.accept()
                with self._lock:
                    self._conn = conn
                    self.current_connection_epoch += 1
                logger.info(
                    "WindowsNamedPipeServer accepted connection (epoch %d)",
                    self.current_connection_epoch,
                )

                while self._is_running:
                    msg_data = conn.recv()
                    msg = IpcMessage.from_dict(msg_data)
                    self._handle_incoming_message(msg, conn)

            except EOFError:
                logger.info("WindowsNamedPipeServer connection closed by client")
            except Exception as e:
                if self._is_running:
                    logger.warning("WindowsNamedPipeServer connection error: %s", e)
            finally:
                with self._lock:
                    if self._conn:
                        try:
                            self._conn.close()
                        except Exception:
                            pass
                        self._conn = None

    def _handle_incoming_message(self, msg: IpcMessage, conn: Any) -> None:
        self.total_messages_received += 1

        # 1. Digest verification (INV-P9-IPC-001)
        if not msg.verify_digest():
            self.total_digest_mismatches += 1
            logger.error("IPC frame digest mismatch for %s; dropping", msg.message_id)
            return

        # 2. Handshake handling
        if msg.message_type == IpcMessageType.HANDSHAKE:
            self.current_worker_epoch = msg.worker_epoch
            self.last_heartbeat_monotonic = time.monotonic()
            self._send_ack(conn, msg)
            logger.info(
                "IPC Handshake successful: worker_id=%s epoch=%d", msg.worker_id, msg.worker_epoch
            )
            return

        # 3. Epoch verification (INV-P9-IPC-002)
        if msg.worker_epoch < self.current_worker_epoch:
            self.total_stale_epoch_drops += 1
            logger.warning(
                "Stale worker epoch message rejected: received=%d current=%d (id=%s)",
                msg.worker_epoch,
                self.current_worker_epoch,
                msg.message_id,
            )
            return

        # 4. Duplicate rejection (INV-P9-IPC-003)
        if msg.message_id in self._seen_message_ids:
            self.total_duplicate_drops += 1
            logger.debug("Duplicate message ignored: %s", msg.message_id)
            self._send_ack(conn, msg)
            return

        self._seen_message_ids.add(msg.message_id)
        if len(self._seen_message_ids) > 2000:
            self._seen_message_ids.clear()

        # 5. Heartbeat tracking
        if msg.message_type == IpcMessageType.HEARTBEAT:
            self.last_heartbeat_monotonic = time.monotonic()
            self._send_ack(conn, msg)
            return

        # 6. Dispatch to registered handlers
        handlers = self.message_handlers.get(msg.message_type, [])
        for h in handlers:
            try:
                h(msg)
            except Exception as ex:
                logger.error("Error executing handler for %s: %s", msg.message_type, ex)

        self._send_ack(conn, msg)

    def _send_ack(self, conn: Any, origin: IpcMessage) -> None:
        try:
            ack = IpcMessage.create(
                message_type=IpcMessageType.ACK,
                payload={"ack_message_id": origin.message_id, "sequence": origin.sequence_number},
                session_id=self.session_id,
                worker_epoch=self.current_worker_epoch,
                connection_epoch=self.current_connection_epoch,
            )
            conn.send(ack.to_dict())
        except Exception:
            pass

    def send_message(self, message: IpcMessage) -> bool:
        """Send a message to the connected child worker."""
        with self._lock:
            if not self._conn:
                return False
            try:
                self._conn.send(message.to_dict())
                return True
            except Exception as e:
                logger.error("Failed to send message over pipe: %s", e)
                return False

    def stop(self) -> None:
        """Stop server and clean up handles."""
        self._is_running = False
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
            if self._listener:
                try:
                    self._listener.close()
                except Exception:
                    pass
                self._listener = None


class WindowsNamedPipeClient:
    """Worker-side client connecting to WindowsNamedPipeServer."""

    def __init__(
        self,
        pipe_name: str,
        worker_id: str,
        worker_epoch: int = 1,
        session_id: str = "desktop",
    ) -> None:
        self.pipe_name = pipe_name
        self.worker_id = worker_id
        self.worker_epoch = worker_epoch
        self.session_id = session_id
        self._conn: Any = None
        self._seq = 0
        self._is_connected = False

    def connect(self, timeout_seconds: float = 5.0) -> bool:
        """Connect to the named pipe server and complete handshake."""
        start = time.monotonic()
        while time.monotonic() - start < timeout_seconds:
            try:
                if sys.platform == "win32":
                    from multiprocessing.connection import PipeClient

                    self._conn = PipeClient(self.pipe_name)
                else:
                    from multiprocessing.connection import Client

                    host, port = self.pipe_name.split(":")
                    self._conn = Client((host, int(port)), family="AF_INET")

                self._is_connected = True
                # Send Handshake
                self._seq += 1
                handshake = IpcMessage.create(
                    message_type=IpcMessageType.HANDSHAKE,
                    payload={"worker_id": self.worker_id, "epoch": self.worker_epoch},
                    session_id=self.session_id,
                    worker_id=self.worker_id,
                    worker_epoch=self.worker_epoch,
                    sequence_number=self._seq,
                )
                self._conn.send(handshake.to_dict())
                # Wait for ACK
                ack_data = self._conn.recv()
                ack = IpcMessage.from_dict(ack_data)
                if ack.message_type == IpcMessageType.ACK:
                    return True
            except Exception:
                time.sleep(0.1)

        return False

    def send_heartbeat(self) -> bool:
        """Send periodic heartbeat to supervisor server."""
        if not self._is_connected or not self._conn:
            return False
        try:
            self._seq += 1
            hb = IpcMessage.create(
                message_type=IpcMessageType.HEARTBEAT,
                payload={"uptime_seconds": time.monotonic()},
                session_id=self.session_id,
                worker_id=self.worker_id,
                worker_epoch=self.worker_epoch,
                sequence_number=self._seq,
            )
            self._conn.send(hb.to_dict())
            return True
        except Exception:
            self._is_connected = False
            return False

    def send_result(self, payload: dict[str, Any]) -> bool:
        """Send shadow evaluation result to host."""
        if not self._is_connected or not self._conn:
            return False
        try:
            self._seq += 1
            msg = IpcMessage.create(
                message_type=IpcMessageType.SHADOW_RESULT,
                payload=payload,
                session_id=self.session_id,
                worker_id=self.worker_id,
                worker_epoch=self.worker_epoch,
                sequence_number=self._seq,
            )
            self._conn.send(msg.to_dict())
            return True
        except Exception:
            self._is_connected = False
            return False

    def close(self) -> None:
        self._is_connected = False
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
