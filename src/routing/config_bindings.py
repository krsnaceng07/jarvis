"""jarvis.routing.config_bindings — configured-binding list normalization.

OpenClaw parity: mirrors ``src/config/bindings.ts``.
(Placed under routing/ because JARVIS has no src/config/ package yet;
the routing modules are the only consumers in Phase 5.13.)

Non-object entries are preserved here (missing ``type`` means legacy
route binding) — downstream consumers like ``resolve_route`` skip
non-object bindings themselves, matching the TS behavior.
"""

from __future__ import annotations

from typing import Any


def _normalize_binding_type(binding: Any) -> str:
    # Missing `type` is the legacy/default route binding shape.
    binding_type = binding.get("type") if isinstance(binding, dict) else None
    return "acp" if binding_type == "acp" else "route"


def is_route_binding(binding: Any) -> bool:
    """Narrows a configured binding to the channel route form."""
    return _normalize_binding_type(binding) == "route"


def _is_acp_binding(binding: Any) -> bool:
    return _normalize_binding_type(binding) == "acp"


def list_configured_bindings(cfg: dict[str, Any]) -> list[Any]:
    """Return the configured binding list, treating missing/non-array config as empty."""
    bindings = cfg.get("bindings")
    return bindings if isinstance(bindings, list) else []


def list_route_bindings(cfg: dict[str, Any]) -> list[Any]:
    """List channel route bindings, including legacy bindings without an explicit type."""
    return [b for b in list_configured_bindings(cfg) if is_route_binding(b)]


def list_acp_bindings(cfg: dict[str, Any]) -> list[Any]:
    """List ACP conversation bindings only."""
    return [b for b in list_configured_bindings(cfg) if _is_acp_binding(b)]


__all__ = [
    "is_route_binding",
    "list_acp_bindings",
    "list_configured_bindings",
    "list_route_bindings",
]
