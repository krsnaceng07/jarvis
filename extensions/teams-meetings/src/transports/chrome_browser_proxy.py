"""Browser proxy resolution and remote node dispatch for Teams Meetings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ResolvedChromeNodeInfo:
    node_id: str | None = None
    nodeId: str | None = None
    node_name: str | None = None
    nodeName: str | None = None


def resolve_chrome_node_info(
    config: Any,
    options: dict[str, Any] | None = None,
) -> ResolvedChromeNodeInfo:
    opts = options or {}
    node_id = (
        opts.get("node")
        or opts.get("nodeId")
        or getattr(getattr(config, "chrome_node", None), "node", None)
        or (config.get("chromeNode", {}).get("node") if isinstance(config, dict) else None)
    )
    return ResolvedChromeNodeInfo(
        node_id=node_id,
        nodeId=node_id,
    )
