"""jarvis.shared.gateway_bind_url — gateway listener URL resolution.

OpenClaw parity: mirrors ``openclaw-main/src/shared/gateway-bind-url.ts``.
"""
from __future__ import annotations

from typing import Optional, TypedDict, Union


GatewayBindUrlResult = Union[
    dict,  # {"url": str, "source": str} | {"error": str} | None
    None,
]


class GatewayBindUrl(TypedDict, total=False):
    url: str
    source: str  # "gateway.bind=custom" | "gateway.bind=tailnet" | "gateway.bind=lan"
    error: str


def resolve_gateway_bind_url(params: dict) -> Optional[dict]:
    """Resolve the externally advertised gateway URL for non-loopback bind modes.

    Mirrors :func:`resolveGatewayBindUrl` (``shared/gateway-bind-url.ts``).
    """
    bind = params.get("bind") or "loopback"
    if bind == "custom":
        custom_host = params.get("customBindHost")
        host = custom_host.strip() if isinstance(custom_host, str) and custom_host.strip() else ""
        if host:
            return {
                "url": f"{params['scheme']}://{host}:{params['port']}",
                "source": "gateway.bind=custom",
            }
        return {"error": "gateway.bind=custom requires gateway.customBindHost."}

    if bind == "tailnet":
        host = params.get("pickTailnetHost")()
        if host:
            return {
                "url": f"{params['scheme']}://{host}:{params['port']}",
                "source": "gateway.bind=tailnet",
            }
        return {"error": "gateway.bind=tailnet set, but no tailnet IP was found."}

    if bind == "lan":
        host = params.get("pickLanHost")()
        if host:
            return {
                "url": f"{params['scheme']}://{host}:{params['port']}",
                "source": "gateway.bind=lan",
            }
        return {"error": "gateway.bind=lan set, but no private LAN IP was found."}

    # Loopback/default and unknown bind values do not need an advertised non-local URL.
    return None


__all__ = ["resolve_gateway_bind_url"]
