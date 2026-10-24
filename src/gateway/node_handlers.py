"""jarvis.gateway.node_handlers — RPC handlers for node management, pairing, and command execution.

Implements node RPC methods defined in Gateway Protocol:
  - node.list
  - node.describe
  - node.pair.list
  - node.pair.approve
  - node.pair.reject
  - node.pair.remove
  - node.invoke
  - node.skills.update
  - node.pluginTools.update
"""

from __future__ import annotations

import logging
import platform
import time
import uuid
from typing import Any, Callable

from .node_command_policy import is_node_command_allowed

_log = logging.getLogger("jarvis.gateway.nodes")


class NodeRegistry:
    """In-memory registry of paired and active nodes."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._pairing_requests: dict[str, dict[str, Any]] = {}
        self._node_executors: dict[str, Callable[..., Any]] = {}

        # Initialize local default node
        self.register_node(
            node_id="local-node",
            display_name="JARVIS Local Node",
            platform_name=platform.system(),
            commands=[
                "system.status",
                "system.ping",
                "system.info",
            ],
            capabilities=["system", "commands"],
            paired=True,
            connected=True,
        )

    def register_node(
        self,
        node_id: str,
        display_name: str,
        platform_name: str = "",
        commands: list[str] | None = None,
        capabilities: list[str] | None = None,
        paired: bool = True,
        connected: bool = True,
        executor: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        node: dict[str, Any] = {
            "nodeId": node_id,
            "displayName": display_name,
            "platform": platform_name or platform.system(),
            "commands": sorted(commands or []),
            "capabilities": sorted(capabilities or []),
            "paired": paired,
            "connected": connected,
            "active": connected,
            "lastSeen": int(time.time() * 1000),
        }
        self._nodes[node_id] = node
        if executor:
            self._node_executors[node_id] = executor
        return node

    def list_nodes(self) -> list[dict[str, Any]]:
        return list(self._nodes.values())

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    def create_pairing_request(
        self,
        node_id: str,
        display_name: str,
        platform_name: str = "",
        commands: list[str] | None = None,
    ) -> dict[str, Any]:
        req_id = f"pair-{uuid.uuid4().hex[:8]}"
        req: dict[str, Any] = {
            "requestId": req_id,
            "nodeId": node_id,
            "displayName": display_name,
            "platform": platform_name or platform.system(),
            "commands": sorted(commands or []),
            "requestedAt": int(time.time() * 1000),
        }
        self._pairing_requests[req_id] = req
        return req

    def list_pairing_requests(self) -> list[dict[str, Any]]:
        return list(self._pairing_requests.values())

    def approve_pairing(self, request_id_or_node_id: str) -> bool:
        # Match by requestId or nodeId
        req = self._pairing_requests.get(request_id_or_node_id)
        if not req:
            for r in list(self._pairing_requests.values()):
                if r["nodeId"] == request_id_or_node_id:
                    req = r
                    break
        if not req:
            return False

        req_id = req["requestId"]
        node_id = req["nodeId"]
        self.register_node(
            node_id=node_id,
            display_name=req["displayName"],
            platform_name=req.get("platform", ""),
            commands=req.get("commands", []),
            paired=True,
            connected=True,
        )
        self._pairing_requests.pop(req_id, None)
        return True

    def reject_pairing(self, request_id_or_node_id: str) -> bool:
        if request_id_or_node_id in self._pairing_requests:
            del self._pairing_requests[request_id_or_node_id]
            return True
        for req_id, req in list(self._pairing_requests.items()):
            if req["nodeId"] == request_id_or_node_id:
                del self._pairing_requests[req_id]
                return True
        return False

    def remove_node(self, node_id: str) -> bool:
        if node_id in self._nodes:
            del self._nodes[node_id]
            self._node_executors.pop(node_id, None)
            return True
        return False

    def execute_invocation(
        self,
        node_id: str,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        node = self.get_node(node_id)
        if not node:
            return {
                "ok": False,
                "error": {"code": "NODE_NOT_FOUND", "message": f"Node '{node_id}' not found"},
            }

        # Check command policy
        allowlist = set(node.get("commands", []))
        check = is_node_command_allowed({
            "command": command,
            "declared_commands": list(node.get("commands", [])),
            "allowlist": allowlist,
        })
        if not check.get("ok"):
            return {
                "ok": False,
                "error": {
                    "code": "COMMAND_DENIED",
                    "message": f"Command '{command}' is denied by node security policy: {check.get('reason')}",
                },
            }

        # Check executor
        executor = self._node_executors.get(node_id)
        if executor:
            import inspect

            if inspect.iscoroutinefunction(executor):
                import asyncio
                res = asyncio.run(executor(command, params or {}))
            else:
                res = executor(command, params or {})
            return {"ok": True, "payload": res}

        # Built-in handling for local-node
        if node_id == "local-node":
            if command == "system.status":
                return {
                    "ok": True,
                    "payload": {
                        "nodeId": "local-node",
                        "status": "ready",
                        "platform": platform.platform(),
                        "time": time.time(),
                    },
                }
            if command == "system.ping":
                return {"ok": True, "payload": {"pong": True}}
            if command == "system.info":
                return {
                    "ok": True,
                    "payload": {
                        "platform": platform.platform(),
                        "pythonVersion": platform.python_version(),
                    },
                }

        return {
            "ok": False,
            "error": {
                "code": "COMMAND_NOT_IMPLEMENTED",
                "message": f"Command '{command}' has no active handler on node '{node_id}'",
            },
        }


# Global or gateway-scoped node registry
_global_node_registry = NodeRegistry()


def get_global_node_registry() -> NodeRegistry:
    return _global_node_registry


def make_node_handlers(gateway: Any = None) -> dict[str, Callable[..., Any]]:
    """Return dictionary of JSON-RPC handlers for node.* operations."""
    registry = _global_node_registry

    def handle_node_list(params: dict[str, Any] | None = None) -> dict[str, Any]:
        nodes = registry.list_nodes()
        active_id = "local-node" if any(n["nodeId"] == "local-node" for n in nodes) else (nodes[0]["nodeId"] if nodes else None)
        return {
            "ts": int(time.time() * 1000),
            "activeNodeId": active_id,
            "nodes": nodes,
        }

    def handle_node_describe(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        node_id = params.get("nodeId", "")
        if not node_id:
            return {"error": {"code": -32602, "message": "nodeId is required"}}
        node = registry.get_node(node_id)
        if not node:
            return {"error": {"code": -32001, "message": f"Node '{node_id}' not found"}}
        return {"node": node}

    def handle_node_pair_list(params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"requests": registry.list_pairing_requests()}

    def handle_node_pair_approve(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        req_id = params.get("requestId") or params.get("nodeId", "")
        if not req_id:
            return {"error": {"code": -32602, "message": "requestId or nodeId is required"}}
        approved = registry.approve_pairing(req_id)
        return {"approved": approved}

    def handle_node_pair_reject(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        req_id = params.get("requestId") or params.get("nodeId", "")
        if not req_id:
            return {"error": {"code": -32602, "message": "requestId or nodeId is required"}}
        rejected = registry.reject_pairing(req_id)
        return {"rejected": rejected}

    def handle_node_pair_remove(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        node_id = params.get("nodeId", "")
        if not node_id:
            return {"error": {"code": -32602, "message": "nodeId is required"}}
        removed = registry.remove_node(node_id)
        return {"removed": removed}

    def handle_node_invoke(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        node_id = params.get("nodeId", "local-node")
        command = params.get("command", "")
        cmd_params = params.get("params", {})
        if not command:
            return {"error": {"code": -32602, "message": "command is required"}}
        return registry.execute_invocation(node_id, command, cmd_params)

    def handle_node_skills_update(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        node_id = params.get("nodeId", "local-node")
        skills = params.get("skills", [])
        node = registry.get_node(node_id)
        if node:
            node["skills"] = skills
        return {"ok": True, "nodeId": node_id, "skillsCount": len(skills)}

    def handle_node_plugin_tools_update(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        node_id = params.get("nodeId", "local-node")
        tools = params.get("tools", [])
        node = registry.get_node(node_id)
        if node:
            node["pluginTools"] = tools
        return {"ok": True, "nodeId": node_id, "toolsCount": len(tools)}

    return {
        "node.list": handle_node_list,
        "node.describe": handle_node_describe,
        "node.pair.list": handle_node_pair_list,
        "node.pair.approve": handle_node_pair_approve,
        "node.pair.reject": handle_node_pair_reject,
        "node.pair.remove": handle_node_pair_remove,
        "node.invoke": handle_node_invoke,
        "node.skills.update": handle_node_skills_update,
        "node.pluginTools.update": handle_node_plugin_tools_update,
    }
