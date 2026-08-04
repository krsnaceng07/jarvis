"""jarvis.config.gateway_control_ui_origins — gateway Control UI allowed origins.

OpenClaw parity: mirrors
``openclaw-main/src/config/gateway-control-ui-origins.ts``.
"""
from __future__ import annotations

from typing import List, Optional, TypedDict


#: Default gateway port used by the dispatch config when none is configured.
DEFAULT_GATEWAY_PORT = 7433


#: Non-loopback gateway bind modes that require explicit Control UI origins.
GatewayNonLoopbackBindMode = str  # "lan" | "tailnet" | "custom" | "auto"


def is_gateway_non_loopback_bind_mode(bind) -> bool:
    return bind in ("lan", "tailnet", "custom", "auto")


def has_configured_control_ui_allowed_origins(params: dict) -> bool:
    """Return whether Control UI origin config is explicit enough.

    Mirrors :func:`hasConfiguredControlUiAllowedOrigins`
    (``shared/config/gateway-control-ui-origins.ts``).
    """
    if params.get("dangerouslyAllowHostHeaderOriginFallback") is True:
        return True
    allowed = params.get("allowedOrigins")
    return (
        isinstance(allowed, list)
        and any(isinstance(o, str) and o.strip() for o in allowed)
    )


def resolve_gateway_port_with_default(port, fallback: int = DEFAULT_GATEWAY_PORT) -> int:
    if isinstance(port, (int, float)) and port > 0:
        return int(port)
    return fallback


def build_default_control_ui_allowed_origins(params: dict) -> List[str]:
    """Build loopback plus custom-bind Control UI origins.

    Mirrors :func:`buildDefaultControlUiAllowedOrigins`
    (``shared/config/gateway-control-ui-origins.ts``).
    """
    origins: set = {
        f"http://localhost:{params['port']}",
        f"http://127.0.0.1:{params['port']}",
    }
    custom = (params.get("customBindHost") or "").strip()
    if params.get("bind") == "custom" and custom:
        origins.add(f"http://{custom}:{params['port']}")
    return sorted(origins)


def ensure_control_ui_allowed_origins_for_non_loopback_bind(
    config: dict,
    *,
    default_port: Optional[int] = None,
    require_control_ui_enabled: Optional[bool] = None,
    runtime_bind=None,
    runtime_port=None,
    is_container_environment: Optional[bool] = None,
) -> dict:
    """Seed safe default Control UI origins before non-loopback bind startup.

    Mirrors :func:`ensureControlUiAllowedOriginsForNonLoopbackBind`
    (``shared/config/gateway-control-ui-origins.ts``).
    """
    bind = runtime_bind if runtime_bind is not None else (config.get("gateway") or {}).get("bind")
    effective_bind = bind if bind is not None else ("auto" if is_container_environment else None)
    if not is_gateway_non_loopback_bind_mode(effective_bind):
        return {"config": config, "seededOrigins": None, "bind": None}
    if (
        require_control_ui_enabled
        and (config.get("gateway") or {}).get("controlUi", {}).get("enabled") is False
    ):
        return {"config": config, "seededOrigins": None, "bind": effective_bind}
    if has_configured_control_ui_allowed_origins({
        "allowedOrigins": (config.get("gateway") or {}).get("controlUi", {}).get("allowedOrigins"),
        "dangerouslyAllowHostHeaderOriginFallback": (
            config.get("gateway") or {}
        ).get("controlUi", {}).get("dangerouslyAllowHostHeaderOriginFallback"),
    }):
        return {"config": config, "seededOrigins": None, "bind": effective_bind}
    port = resolve_gateway_port_with_default(
        runtime_port if runtime_port is not None else (config.get("gateway") or {}).get("port"),
        default_port if default_port is not None else DEFAULT_GATEWAY_PORT,
    )
    seeded = build_default_control_ui_allowed_origins({
        "port": port,
        "bind": effective_bind,
        "customBindHost": (config.get("gateway") or {}).get("customBindHost"),
    })
    gateway = dict(config.get("gateway") or {})
    control_ui = dict(gateway.get("controlUi") or {})
    control_ui["allowedOrigins"] = seeded
    gateway["controlUi"] = control_ui
    new_config = dict(config)
    new_config["gateway"] = gateway
    return {"config": new_config, "seededOrigins": seeded, "bind": effective_bind}


__all__ = [
    "DEFAULT_GATEWAY_PORT",
    "GatewayNonLoopbackBindMode",
    "is_gateway_non_loopback_bind_mode",
    "has_configured_control_ui_allowed_origins",
    "resolve_gateway_port_with_default",
    "build_default_control_ui_allowed_origins",
    "ensure_control_ui_allowed_origins_for_non_loopback_bind",
]
