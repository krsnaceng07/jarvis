"""jarvis.config.schema_node_capabilities — node-capability field help/labels.

OpenClaw parity: mirrors
``openclaw-main/src/config/schema.node-capabilities.ts``.
"""
from __future__ import annotations


#: User-facing help strings for the gateway node-capability fields.
NODE_CAPABILITY_FIELD_HELP: dict = {
    "gateway.nodes.pluginTools":
        "Controls whether paired nodes may publish agent-visible plugin tool descriptors.",
    "gateway.nodes.pluginTools.enabled":
        "Accept agent-visible plugin tool descriptors published by paired nodes (default: true). "
        "Set false to ignore and remove all node-published plugin tools.",
    "gateway.nodes.skills": "Controls whether paired nodes may publish agent-visible skills.",
    "gateway.nodes.skills.enabled":
        "Accept skills published by paired nodes while they are connected (default: true). "
        "Set false to ignore node-published skills.",
}


#: User-facing labels for the gateway node-capability fields.
NODE_CAPABILITY_FIELD_LABELS: dict = {
    "gateway.nodes.pluginTools": "Gateway Node Plugin Tools",
    "gateway.nodes.pluginTools.enabled": "Gateway Node Plugin Tools Enabled",
    "gateway.nodes.skills": "Gateway Node Skills",
    "gateway.nodes.skills.enabled": "Gateway Node Skills Enabled",
    "gateway.nodes.allowCommands": "Gateway Node Allowlist (Extra Commands)",
}


__all__ = [
    "NODE_CAPABILITY_FIELD_HELP",
    "NODE_CAPABILITY_FIELD_LABELS",
]
