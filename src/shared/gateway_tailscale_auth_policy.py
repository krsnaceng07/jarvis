"""jarvis.shared.gateway_tailscale_auth_policy — Tailscale auth policy.

OpenClaw parity: mirrors ``openclaw-main/src/shared/gateway-tailscale-auth-policy.ts``.
"""
from __future__ import annotations

from typing import Literal

GatewayAuthMode = Literal["token", "password", "trusted-proxy", "none"]
GatewayTailscaleMode = Literal["off", "serve", "funnel"]


def is_unsafe_gateway_tailscale_no_auth(params: dict) -> bool:
    """Return True when Tailscale exposure is set without gateway auth.

    Mirrors :func:`isUnsafeGatewayTailscaleNoAuth`
    (``shared/gateway-tailscale-auth-policy.ts``).
    """
    return (
        params.get("authMode") == "none"
        and params.get("tailscaleMode") in ("serve", "funnel")
    )


def format_unsafe_gateway_tailscale_no_auth_message(tailscale_mode: str) -> str:
    """Format the shared validation message for unsafe Tailscale no-auth exposure.

    Mirrors :func:`formatUnsafeGatewayTailscaleNoAuthMessage`
    (``shared/gateway-tailscale-auth-policy.ts``).
    """
    if tailscale_mode == "funnel":
        return (
            "gateway.tailscale.mode=funnel requires gateway.auth.mode=password; "
            "auth.mode=none cannot be used when exposing the gateway through Tailscale Funnel"
        )
    return (
        f"gateway.auth.mode=none cannot be used with gateway.tailscale.mode={tailscale_mode}; "
        "configure token, password, or trusted-proxy auth before exposing the gateway through Tailscale"
    )


__all__ = [
    "is_unsafe_gateway_tailscale_no_auth",
    "format_unsafe_gateway_tailscale_no_auth_message",
]
