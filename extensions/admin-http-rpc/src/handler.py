"""Admin HTTP RPC request handler and execution dispatcher.

Mirrors OpenClaw's ``extensions/admin-http-rpc/src/handler.ts``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from .methods import (
    is_admin_http_rpc_allowed_method,
    list_admin_http_rpc_allowed_methods,
)

MAX_REQUEST_BYTES: int = 1024 * 1024  # 1 MB

ERROR_CODE_TO_HTTP_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "APPROVAL_NOT_FOUND": 404,
    "NOT_LINKED": 409,
    "NOT_PAIRED": 409,
    "UNAVAILABLE": 503,
    "AGENT_TIMEOUT": 504,
}


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """HTTP response representation for Gateway routes."""

    status: int
    headers: dict[str, str]
    body: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "headers": self.headers,
            "body": self.body,
        }


def _json_response(status: int, data: dict[str, Any]) -> HttpResponse:
    return HttpResponse(
        status=status,
        headers={"Content-Type": "application/json"},
        body=json.dumps(data),
    )


class AdminHttpRpcHandler:
    """Handler for Gateway Admin HTTP RPC POST /api/v1/admin/rpc."""

    def __init__(
        self,
        dispatch_method: Optional[Callable[[str, Any, Any], Awaitable[Any]]] = None,
    ) -> None:
        self._dispatch_method = dispatch_method

    async def handle_request(
        self,
        http_method: str,
        body_bytes: bytes,
        headers: Optional[dict[str, str]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> HttpResponse:
        """Process an incoming HTTP request for the Admin RPC route."""
        # 1. Enforce HTTP method POST
        if http_method.upper() != "POST":
            return HttpResponse(
                status=405,
                headers={"Allow": "POST", "Content-Type": "application/json"},
                body=json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": "METHOD_NOT_ALLOWED",
                            "message": f"Method {http_method} not allowed, use POST",
                        },
                    }
                ),
            )

        # 2. Enforce 1 MB body limit
        if len(body_bytes) > MAX_REQUEST_BYTES:
            return _json_response(
                413,
                {
                    "ok": False,
                    "error": {
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": f"Request body exceeds {MAX_REQUEST_BYTES} bytes limit",
                    },
                },
            )

        # 3. Parse JSON body
        try:
            body_text = body_bytes.decode("utf-8")
            payload = json.loads(body_text) if body_text.strip() else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            req_id = str(uuid.uuid4())
            return _json_response(
                400,
                {
                    "id": req_id,
                    "ok": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": f"Invalid JSON payload: {err}",
                    },
                },
            )

        if not isinstance(payload, dict):
            req_id = str(uuid.uuid4())
            return _json_response(
                400,
                {
                    "id": req_id,
                    "ok": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Request body must be a JSON object",
                    },
                },
            )

        # 4. Extract ID and method
        req_id = str(payload.get("id") or uuid.uuid4())
        method = payload.get("method")
        params = payload.get("params", {})

        if not method or not isinstance(method, str) or not method.strip():
            return _json_response(
                400,
                {
                    "id": req_id,
                    "ok": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Field 'method' is required and must be a non-empty string",
                    },
                },
            )

        method = method.strip()

        # 5. Check allowlist
        if not is_admin_http_rpc_allowed_method(method):
            return _json_response(
                400,
                {
                    "id": req_id,
                    "ok": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": f"Method '{method}' is not allowed over Admin HTTP RPC",
                    },
                },
            )

        # 6. Built-in discovery: commands.list
        if method == "commands.list":
            return _json_response(
                200,
                {
                    "id": req_id,
                    "ok": True,
                    "payload": {
                        "methods": list_admin_http_rpc_allowed_methods(),
                    },
                },
            )

        # 7. Gateway dispatcher
        if self._dispatch_method is None:
            # When running without a live dispatcher hook (e.g. standalone health)
            if method == "health":
                return _json_response(
                    200,
                    {
                        "id": req_id,
                        "ok": True,
                        "payload": {"status": "ok"},
                    },
                )
            return _json_response(
                503,
                {
                    "id": req_id,
                    "ok": False,
                    "error": {
                        "code": "UNAVAILABLE",
                        "message": "Gateway RPC dispatcher is not configured",
                    },
                },
            )

        try:
            result = await self._dispatch_method(method, params, context)
            if isinstance(result, dict) and result.get("ok") is False and "error" in result:
                err_dict = result["error"]
                code = err_dict.get("code", "INTERNAL_ERROR")
                status = ERROR_CODE_TO_HTTP_STATUS.get(code, 500)
                return _json_response(
                    status,
                    {
                        "id": req_id,
                        "ok": False,
                        "error": err_dict,
                    },
                )

            # Success result
            return _json_response(
                200,
                {
                    "id": req_id,
                    "ok": True,
                    "payload": result,
                },
            )

        except Exception as exc:
            err_code = getattr(exc, "code", "INTERNAL_ERROR")
            status = ERROR_CODE_TO_HTTP_STATUS.get(str(err_code), 500)
            return _json_response(
                status,
                {
                    "id": req_id,
                    "ok": False,
                    "error": {
                        "code": str(err_code),
                        "message": str(exc),
                    },
                },
            )


__all__ = [
    "AdminHttpRpcHandler",
    "ERROR_CODE_TO_HTTP_STATUS",
    "HttpResponse",
    "MAX_REQUEST_BYTES",
]
