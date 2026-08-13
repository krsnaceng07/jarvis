"""Gateway protocol validators.

Validates raw dict payloads against the Gateway schema shapes, returning
typed ``GatewayRequest`` / ``GatewayResponse`` objects or ``GatewayError`` on failure.
"""

from __future__ import annotations

from typing import Any

from .schema import GatewayError, GatewayRequest, GatewayResponse, RPCRequest, RPCResponse


def validate_request(raw: Any) -> tuple[GatewayRequest | RPCRequest, None] | tuple[None, GatewayError]:
    """Parse and validate a raw dict as either a ``GatewayRequest`` or a JSON-RPC ``RPCRequest``.

    Accepts both legacy Gateway frames (type='req') and JSON-RPC 2.0 frames (jsonrpc='2.0').
    """
    if not isinstance(raw, dict):
        return None, GatewayError.invalid_request("request must be a JSON object")

    # JSON-RPC 2.0 frame
    if raw.get("jsonrpc") == "2.0":
        method = raw.get("method")
        if not isinstance(method, str) or not method.strip():
            return None, GatewayError.invalid_request("'method' must be a non-empty string")
        id_ = raw.get("id", "")
        if not isinstance(id_, str):
            try:
                id_ = str(id_)
            except Exception:  # noqa: BLE001
                id_ = ""
        params = raw.get("params", {})
        if not isinstance(params, dict):
            return None, GatewayError.invalid_params("'params' must be a JSON object")
        return RPCRequest(method=method.strip(), id=id_, params=params), None

    # Legacy Gateway frame
    if raw.get("type") != "req":
        return None, GatewayError.invalid_request("request must have type='req'")

    method = raw.get("method")
    if not isinstance(method, str) or not method.strip():
        return None, GatewayError.invalid_request("'method' must be a non-empty string")

    id_ = raw.get("id", "")
    if not isinstance(id_, str):
        try:
            id_ = str(id_)
        except Exception:  # noqa: BLE001
            id_ = ""

    params = raw.get("params", {})
    if not isinstance(params, dict):
        return None, GatewayError.invalid_params("'params' must be a JSON object")

    return GatewayRequest(method=method.strip(), id=id_, params=params), None


def validate_response(raw: Any) -> tuple[GatewayResponse | RPCResponse, None] | tuple[None, GatewayError]:
    """Parse and validate a raw dict as either a ``GatewayResponse`` or an ``RPCResponse``."""
    if not isinstance(raw, dict):
        return None, GatewayError.invalid_request("response must be a JSON object")

    # JSON-RPC 2.0 response
    if raw.get("jsonrpc") == "2.0":
        id_ = raw.get("id", "")
        if "error" in raw and raw["error"] is not None:
            raw_err = raw["error"]
            if not isinstance(raw_err, dict):
                return None, GatewayError.internal_error("'error' must be a JSON object")
            code = raw_err.get("code", -32603)
            message = raw_err.get("message", "Unknown error")
            data = raw_err.get("data")
            error = GatewayError(code=code, message=message, data=data)
            return RPCResponse(id=str(id_), result=None, error=error), None
        return RPCResponse(id=str(id_), result=raw.get("result"), error=None), None

    # Legacy Gateway response
    if raw.get("type") != "res":
        return None, GatewayError.invalid_request("response must have type='res'")

    id_ = raw.get("id", "")
    if "error" in raw and raw["error"] is not None:
        raw_err = raw["error"]
        if not isinstance(raw_err, dict):
            return None, GatewayError.internal_error("'error' must be a JSON object")
        code = raw_err.get("code", -32603)
        message = raw_err.get("message", "Unknown error")
        data = raw_err.get("data")
        error = GatewayError(code=code, message=message, data=data)
        return GatewayResponse(id=str(id_), payload=None, error=error), None

    payload = raw.get("payload")
    return GatewayResponse(id=str(id_), payload=payload, error=None), None


__all__ = ["validate_request", "validate_response"]
