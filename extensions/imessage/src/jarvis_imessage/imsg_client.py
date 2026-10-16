import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class IMsgClient:
    def __init__(self, cli_path: str, db_path: Optional[str] = None):
        self.cli_path = cli_path
        self.db_path = db_path
        self._process: Optional[asyncio.subprocess.Process] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._message_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._running = False

    async def start(self):
        cmd = [self.cli_path, "rpc"]
        if self.db_path:
            cmd.extend(["--db-path", self.db_path])

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._running = True
            asyncio.create_task(self._read_stdout())
            asyncio.create_task(self._read_stderr())
            logger.info("Started imsg RPC client")
        except Exception as e:
            logger.error(f"Failed to start imsg client: {e}")
            raise

    def on_message(self, callback: Callable[[Dict[str, Any]], None]):
        self._message_callback = callback

    async def _read_stdout(self):
        if not self._process or not self._process.stdout:
            return

        while self._running:
            line = await self._process.stdout.readline()
            if not line:
                break

            try:
                payload = json.loads(line.decode().strip())
                self._handle_rpc_payload(payload)
            except json.JSONDecodeError:
                logger.warning(f"Failed to decode imsg stdout: {line}")
            except Exception as e:
                logger.error(f"Error handling imsg payload: {e}")

    async def _read_stderr(self):
        if not self._process or not self._process.stderr:
            return

        while self._running:
            line = await self._process.stderr.readline()
            if not line:
                break
            logger.debug(f"imsg stderr: {line.decode().strip()}")

    def _handle_rpc_payload(self, payload: Dict[str, Any]):
        if "id" in payload and payload["id"] in self._pending_requests:
            future = self._pending_requests.pop(payload["id"])
            if "error" in payload:
                future.set_exception(Exception(payload["error"]))
            else:
                future.set_result(payload.get("result"))
        elif "method" in payload:
            if self._message_callback:
                # E.g. incoming message event from imsg
                self._message_callback(payload)

    async def _send_request(self, method: str, params: Dict[str, Any]) -> Any:
        if not self._process or not self._process.stdin or not self._running:
            raise RuntimeError("imsg client is not running")

        req_id = str(uuid.uuid4())
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}

        future = asyncio.get_event_loop().create_future()
        self._pending_requests[req_id] = future

        data = json.dumps(payload) + "\n"
        self._process.stdin.write(data.encode())
        await self._process.stdin.drain()

        return await future

    async def send_message(self, to: str, text: str) -> str:
        """Sends a text message and returns the message GUID."""
        res = await self._send_request("send-message", {"target": to, "text": text})
        return res.get("guid", "")

    async def send_media(self, to: str, file_path: str, text: Optional[str] = None) -> str:
        """Sends media to a target."""
        params = {"target": to, "file": file_path}
        if text:
            params["text"] = text

        res = await self._send_request("send-message", params)
        return res.get("guid", "")

    async def stop(self):
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except (ProcessLookupError, asyncio.TimeoutError):
                self._process.kill()
        logger.info("Stopped imsg RPC client")
