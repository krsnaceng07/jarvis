"""Frame encoding and decoding for Track 3.5 client runtime.

Supports both JSON-RPC 2.0 and OpenClaw message envelopes.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Literal

from jarvis_client.errors import ClientErrorCode, JarvisClientException

MAX_CLIENT_FRAME_BYTES: int = 10 * 1024 * 1024  # 10 MB


@dataclass(frozen=True, slots=True)
class RPCRequestFrame:
    """Standard JSON-RPC 2.0 request frame."""

    id: str
    method: str
    params: dict[str, Any]
    jsonrpc: Literal["2.0"] = "2.0"

    def serialize(self) -> str:
        payload = {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "method": self.method,
            "params": self.params,
        }
        encoded = json.dumps(payload)
        if len(encoded.encode("utf-8")) > MAX_CLIENT_FRAME_BYTES:
            raise JarvisClientException(
                code=ClientErrorCode.FRAME_TOO_LARGE,
                message=f"Request frame exceeds {MAX_CLIENT_FRAME_BYTES} bytes limit.",
            )
        return encoded


@dataclass(frozen=True, slots=True)
class RPCResponseFrame:
    """Standard JSON-RPC 2.0 response frame."""

    id: str
    result: Any = None
    error: dict[str, Any] | None = None
    jsonrpc: str = "2.0"

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @classmethod
    def deserialize(cls, raw: str) -> RPCResponseFrame:
        if len(raw.encode("utf-8")) > MAX_CLIENT_FRAME_BYTES:
            raise JarvisClientException(
                code=ClientErrorCode.FRAME_TOO_LARGE,
                message="Incoming response frame exceeds size limit.",
            )
        try:
            parsed = json.loads(raw)
        except Exception as e:
            raise JarvisClientException(
                code=ClientErrorCode.PARSE_ERROR,
                message=f"Failed to parse response JSON: {e}",
            )
        if not isinstance(parsed, dict):
            raise JarvisClientException(
                code=ClientErrorCode.INVALID_REQUEST,
                message="Response must be a JSON object.",
            )
        return cls(
            id=str(parsed.get("id", "")),
            result=parsed.get("result"),
            error=parsed.get("error"),
            jsonrpc=str(parsed.get("jsonrpc", "2.0")),
        )


__all__ = ["MAX_CLIENT_FRAME_BYTES", "RPCRequestFrame", "RPCResponseFrame"]
