"""jarvis.config.bindings — agent binding config normalization.

OpenClaw parity: mirrors ``openclaw-main/src/config/bindings.ts``.
"""
from __future__ import annotations

from typing import List, TypedDict


class AgentRouteBinding(TypedDict, total=False):
    agentId: str
    match: dict
    type: str  # "route"


class AgentAcpBinding(TypedDict, total=False):
    agentId: str
    type: str  # "acp"
    cursor: dict


AgentBinding = dict  # AgentRouteBinding | AgentAcpBinding


def _normalize_binding_type(binding: dict) -> str:
    return "acp" if binding.get("type") == "acp" else "route"


def is_route_binding(binding: dict) -> bool:
    return _normalize_binding_type(binding) == "route"


def is_acp_binding(binding: dict) -> bool:
    return _normalize_binding_type(binding) == "acp"


def list_configured_bindings(cfg: dict) -> List[dict]:
    return cfg.get("bindings") if isinstance(cfg.get("bindings"), list) else []


def list_route_bindings(cfg: dict) -> List[dict]:
    return [b for b in list_configured_bindings(cfg) if is_route_binding(b)]


def list_acp_bindings(cfg: dict) -> List[dict]:
    return [b for b in list_configured_bindings(cfg) if is_acp_binding(b)]


__all__ = [
    "AgentRouteBinding",
    "AgentAcpBinding",
    "AgentBinding",
    "is_route_binding",
    "is_acp_binding",
    "list_configured_bindings",
    "list_route_bindings",
    "list_acp_bindings",
]
