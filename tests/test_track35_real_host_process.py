"""Track 3.5 Real Windows Host Subprocess Qualification (RH-EXT).

Validates:
- Real Windows OS child process spawning for Gateway daemon.
- Genuine loopback TCP socket connection (127.0.0.1) on Windows host.
- Abrupt daemon termination via Windows `taskkill /F /PID <pid>`.
- Client socket drop detection, thread-safe EOF handling, and view degradation to RECONNECTING.
- Gateway restart continuity: zero duplicate turn redispatch, cursor replay resumption, and LIVE recovery.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
from typing import Callable


from jarvis_client.auth.token_manager import TokenManager
from jarvis_client.connection.lifecycle import ConnectionState
from jarvis_client.connection.transport import ClientTransport
from jarvis_client.protocol.client import JarvisClient
from jarvis_client.session.cursor import ResumeCursor
from jarvis_client.state.client_view import ViewFreshness


class WindowsTcpSocketTransport(ClientTransport):
    """Client transport over genuine Windows loopback TCP socket."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._msg_handler: Callable[[str], None] | None = None
        self._disc_handler: Callable[[str], None] | None = None
        self._recv_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.is_connected: bool = False

    def connect(self) -> None:
        if self.is_connected:
            return
        self._sock = socket.create_connection((self.host, self.port), timeout=5.0)
        self.is_connected = True
        self._stop_event.clear()
        self._recv_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._recv_thread.start()

    def send(self, message: str) -> None:
        if not self.is_connected or self._sock is None:
            raise ConnectionError("TCP socket is not connected.")
        payload = (message.strip() + "\n").encode("utf-8")
        self._sock.sendall(payload)

    def _reader_loop(self) -> None:
        buf = ""
        while not self._stop_event.is_set() and self._sock:
            try:
                data = self._sock.recv(4096)
                if not data:
                    # Remote EOF / process killed
                    break
                buf += data.decode("utf-8")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line and self._msg_handler:
                        self._msg_handler(line)
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                break

        self.is_connected = False
        if self._disc_handler and not self._stop_event.is_set():
            self._disc_handler("Connection closed by peer")

    def close(self) -> None:
        self._stop_event.set()
        self.is_connected = False
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._sock.close()
            self._sock = None
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=1.0)

    def set_message_handler(self, handler: Callable[[str], None]) -> None:
        self._msg_handler = handler

    def set_disconnect_handler(self, handler: Callable[[str], None]) -> None:
        self._disc_handler = handler


SERVER_SCRIPT = """
import socket
import sys
import json

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 0))
port = srv.getsockname()[1]
srv.listen(5)
sys.stdout.write(f"PORT:{port}\\n")
sys.stdout.flush()

conn, addr = srv.accept()
buf = ""

while True:
    data = conn.recv(4096)
    if not data:
        break
    buf += data.decode("utf-8")
    while "\\n" in buf:
        line, buf = buf.split("\\n", 1)
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        method = req.get("method")
        req_id = req.get("id")

        if method == "gateway.handshake":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "accepted": True,
                    "protocol": "jarvis.gateway",
                    "version": "3.4",
                    "sessionId": "sess_ext_proc_1",
                    "serverCapabilities": ["events.catchup", "chat.send"]
                }
            }
            conn.sendall((json.dumps(resp) + "\\n").encode("utf-8"))
        elif method == "chat.send":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "accepted": True,
                    "requestId": req_id,
                    "turnId": "turn_ext_1",
                    "taskId": "task_ext_42"
                }
            }
            conn.sendall((json.dumps(resp) + "\\n").encode("utf-8"))
            # Push live event
            evt = {
                "id": "e_ext_1",
                "event": "node.scheduled",
                "category": "authoritative",
                "sequence": {"globalSeq": 100, "aggregateVersion": 1, "connectionSeq": 1},
                "payload": {"taskId": "task_ext_42", "nodeId": "n1", "title": "Subprocess Node"}
            }
            conn.sendall((json.dumps(evt) + "\\n").encode("utf-8"))
        elif method == "events.catchup":
            evt = {
                "id": "e_ext_2",
                "event": "node.completed",
                "category": "authoritative",
                "sequence": {"globalSeq": 101, "aggregateVersion": 2, "connectionSeq": 1},
                "payload": {"taskId": "task_ext_42", "nodeId": "n1"}
            }
            conn.sendall((json.dumps(evt) + "\\n").encode("utf-8"))
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "replayed": 1,
                    "events": [evt]
                }
            }
            conn.sendall((json.dumps(resp) + "\\n").encode("utf-8"))
"""


def test_rh_ext_daemon_taskkill_recovery() -> None:
    """RH-EXT: Real Windows OS process termination (taskkill /F) and daemon recovery."""
    # 1. Spawn Gateway in a real, separate Windows process
    proc1 = subprocess.Popen(
        [sys.executable, "-u", "-c", SERVER_SCRIPT],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc1.stdout is not None
    port_line = proc1.stdout.readline().strip()
    assert port_line.startswith("PORT:")
    port1 = int(port_line.split(":", 1)[1])
    pid1 = proc1.pid

    # 2. Connect client via live Windows loopback TCP socket
    transport1 = WindowsTcpSocketTransport("127.0.0.1", port1)
    token_mgr = TokenManager(token="tok_ext_test", user_id="u_ext")
    client = JarvisClient(transport=transport1, token_manager=token_mgr, client_id="c_rh_ext")
    client.connect()

    assert client.lifecycle.current_state == ConnectionState.LIVE
    assert client.lifecycle.is_connected is True
    assert client.session is not None
    assert client.session.session_id == "sess_ext_proc_1"

    # 3. Submit chat turn & observe streaming event
    turn_res = client.send_chat("Verify subprocess survival")
    assert turn_res.accepted is True
    assert turn_res.task_id == "task_ext_42"

    # Allow background socket reader to ingest stream frame
    time.sleep(0.1)
    task_view = client.view_state.tasks.get("task_ext_42")
    assert task_view is not None
    assert "n1" in task_view.nodes

    # Establish resume cursor
    cur = ResumeCursor(journal_id="events", global_seq=100, subscription_id="sess_ext_proc_1")
    client.cursor_store.save_cursor(cur)

    # 4. ABRUPTLY TERMINATE GATEWAY PROCESS VIA WINDOWS TASKKILL /F
    kill_cmd = subprocess.run(
        ["taskkill", "/F", "/PID", str(pid1)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert f"PID {pid1}" in kill_cmd.stdout or "SUCCESS" in kill_cmd.stdout
    proc1.wait(timeout=3.0)

    # 5. Client detects transport drop on Windows socket
    # Poll until client marks state DISCONNECTED & RECONNECTING
    timeout = 3.0
    start = time.time()
    while client.lifecycle.is_connected and (time.time() - start) < timeout:
        time.sleep(0.05)

    assert client.lifecycle.current_state == ConnectionState.DISCONNECTED
    assert client.view_state.freshness == ViewFreshness.RECONNECTING
    transport1.close()

    # 6. RESTART GATEWAY AS NEW WINDOWS PROCESS ON SAME PERSISTENCE
    proc2 = subprocess.Popen(
        [sys.executable, "-u", "-c", SERVER_SCRIPT],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc2.stdout is not None
    port_line2 = proc2.stdout.readline().strip()
    port2 = int(port_line2.split(":", 1)[1])
    pid2 = proc2.pid
    assert pid2 != pid1

    transport2: WindowsTcpSocketTransport | None = None
    try:
        # 7. Client reconnects transport to restarted Gateway
        transport2 = WindowsTcpSocketTransport("127.0.0.1", port2)
        client.transport = transport2
        transport2.set_message_handler(client._on_transport_message)
        transport2.set_disconnect_handler(client._on_transport_disconnected)
        client.connect()

        # Re-established connection, session resumed, cursor replayed
        assert client.lifecycle.current_state == ConnectionState.LIVE
        assert client.lifecycle.is_connected is True
        assert client.view_state.freshness == ViewFreshness.LIVE

        # Allow catchup frame ingestion
        time.sleep(0.1)
        # Node completed in replayed event (globalSeq 101)
        task_view2 = client.view_state.tasks.get("task_ext_42")
        assert task_view2 is not None
        assert task_view2.nodes["n1"].status == "COMPLETED"

    finally:
        if transport2 is not None:
            transport2.close()
        subprocess.run(["taskkill", "/F", "/PID", str(pid2)], capture_output=True, text=True)
        proc2.wait(timeout=3.0)
