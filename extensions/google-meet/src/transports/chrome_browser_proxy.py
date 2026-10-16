"""Chrome browser proxy helper functions for local and paired nodes."""

from __future__ import annotations

from typing import Any
from .google_meet_platform_constants import GOOGLE_MEET_BROWSER_NODE_ADAPTER


def as_browser_tabs(value: Any) -> list[dict[str, Any]]:
    """Cast response to a list of browser tab dicts."""
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict) and isinstance(value.get("tabs"), list):
        return [x for x in value["tabs"] if isinstance(x, dict)]
    return []


def read_browser_tab(value: Any) -> dict[str, Any] | None:
    """Extract single browser tab dict if valid."""
    if isinstance(value, dict) and (
        value.get("targetId") or value.get("target_id") or value.get("url")
    ):
        return value
    return None


async def resolve_chrome_node_info(params: dict[str, Any]) -> dict[str, Any]:
    runtime = params.get("runtime")
    requested_node = params.get("requestedNode") or params.get("requested_node")
    if runtime and hasattr(runtime, "nodes"):
        try:
            return await runtime.nodes.resolve_node_info(
                requested_node=requested_node,
                adapter=GOOGLE_MEET_BROWSER_NODE_ADAPTER,
            )
        except Exception:
            pass
    return {
        "nodeId": requested_node or "local",
        "displayName": requested_node or "local node",
    }


async def resolve_chrome_node(params: dict[str, Any]) -> str:
    info = await resolve_chrome_node_info(params)
    return str(info.get("nodeId") or info.get("node_id") or "local")


async def call_browser_proxy_on_node(params: dict[str, Any]) -> Any:
    runtime = params.get("runtime")
    node_id = params.get("nodeId") or params.get("node_id") or "local"
    method = params.get("method", "GET")
    path = params.get("path", "")
    body = params.get("body")
    timeout_ms = params.get("timeoutMs") or params.get("timeout_ms", 10000)

    if runtime and hasattr(runtime, "nodes"):
        return await runtime.nodes.call_browser_proxy(
            node_id=node_id,
            method=method,
            path=path,
            body=body,
            timeout_ms=timeout_ms,
            adapter=GOOGLE_MEET_BROWSER_NODE_ADAPTER,
        )
    return None
