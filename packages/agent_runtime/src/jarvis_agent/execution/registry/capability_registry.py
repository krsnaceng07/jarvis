"""Capability Registry with pre-registered built-ins and schema validation.

Maintains authoritative catalog of capabilities executable by Track 3.2 runtime,
validating command argument schemas and ensuring all capabilities declare explicit
risk classes, permissions, sandbox requirements, and timeouts.
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis_agent.execution.models.capability_definition import (
    CapabilityDefinition,
    SideEffectClass,
)
from jarvis_agent.orchestration.models.risk import RiskClass

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """Thread-safe registry for capability definitions with built-in defaults."""

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityDefinition] = {}
        self._register_builtins()

    def register(self, definition: CapabilityDefinition) -> None:
        """Register or update a capability definition."""
        self._capabilities[definition.capability_id] = definition
        logger.debug("Registered capability %s v%s", definition.capability_id, definition.version)

    def get(self, capability_id: str) -> CapabilityDefinition | None:
        """Retrieve capability definition by ID."""
        return self._capabilities.get(capability_id)

    def has(self, capability_id: str) -> bool:
        """Check if capability ID is registered."""
        return capability_id in self._capabilities

    def list_capabilities(self) -> list[CapabilityDefinition]:
        """Return list of all registered capabilities."""
        return list(self._capabilities.values())

    def validate_arguments(
        self, capability_id: str, arguments: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Validate arguments against capability input schema.

        Performs lightweight deterministic schema validation:
        checks for required keys and basic primitive types.
        """
        cap = self.get(capability_id)
        if not cap:
            return False, f"Unknown capability '{capability_id}'"

        schema = cap.input_schema
        if not schema:
            return True, None

        # Check required fields
        required = schema.get("required", [])
        for req_field in required:
            if req_field not in arguments:
                return False, f"Missing required argument '{req_field}' for capability '{capability_id}'"

        properties = schema.get("properties", {})
        for key, val in arguments.items():
            if key in properties:
                prop_spec = properties[key]
                expected_type = prop_spec.get("type")
                if expected_type:
                    valid, err = self._check_type(val, expected_type, key)
                    if not valid:
                        return False, err

        return True, None

    def _check_type(self, val: Any, expected_type: str, field_name: str) -> tuple[bool, str | None]:
        """Validate value against expected primitive JSON schema type."""
        if val is None:
            return True, None  # Nullability handled separately if required

        if expected_type == "string" and not isinstance(val, str):
            return False, f"Argument '{field_name}' must be a string, got {type(val).__name__}"
        if expected_type == "integer" and (not isinstance(val, int) or isinstance(val, bool)):
            return False, f"Argument '{field_name}' must be an integer, got {type(val).__name__}"
        if expected_type == "number" and (not isinstance(val, (int, float)) or isinstance(val, bool)):
            return False, f"Argument '{field_name}' must be a number, got {type(val).__name__}"
        if expected_type == "boolean" and not isinstance(val, bool):
            return False, f"Argument '{field_name}' must be a boolean, got {type(val).__name__}"
        if expected_type == "array" and not isinstance(val, (list, tuple)):
            return False, f"Argument '{field_name}' must be an array, got {type(val).__name__}"
        if expected_type == "object" and not isinstance(val, dict):
            return False, f"Argument '{field_name}' must be an object, got {type(val).__name__}"
        return True, None

    def _register_builtins(self) -> None:
        """Register the standard set of JARVIS core capabilities."""
        # Browser capabilities
        self.register(
            CapabilityDefinition(
                capability_id="browser.open",
                version="1.0.0",
                description="Open a browser tab or reuse existing tab by URL target.",
                input_schema={
                    "type": "object",
                    "required": ["url"],
                    "properties": {
                        "url": {"type": "string"},
                        "reuse_existing": {"type": "boolean"},
                    },
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.READ_ONLY,
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.IDEMPOTENT_MUTATION,
                timeout_seconds=30.0,
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="browser.navigate",
                version="1.0.0",
                description="Navigate current active tab to a new URL.",
                input_schema={
                    "type": "object",
                    "required": ["url"],
                    "properties": {"url": {"type": "string"}},
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.READ_ONLY,
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.IDEMPOTENT_MUTATION,
                timeout_seconds=30.0,
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="browser.click",
                version="1.0.0",
                description="Click a DOM element by selector.",
                input_schema={
                    "type": "object",
                    "required": ["selector"],
                    "properties": {"selector": {"type": "string"}},
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.LOW,
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.NON_IDEMPOTENT_MUTATION,
                timeout_seconds=15.0,
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="browser.media_control",
                version="1.0.0",
                description="Control media playback on active browser tab (play, pause, toggle).",
                input_schema={
                    "type": "object",
                    "required": ["action"],
                    "properties": {
                        "action": {"type": "string"},
                        "target_url": {"type": "string"},
                    },
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.READ_ONLY,
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.IDEMPOTENT_MUTATION,
                timeout_seconds=15.0,
            )
        )

        # Filesystem capabilities
        self.register(
            CapabilityDefinition(
                capability_id="filesystem.read",
                version="1.0.0",
                description="Read contents of a file within allowed directory roots.",
                input_schema={
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.READ_ONLY,
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.READ_ONLY,
                timeout_seconds=10.0,
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="filesystem.write",
                version="1.0.0",
                description="Atomically write contents to a file within allowed directory roots.",
                input_schema={
                    "type": "object",
                    "required": ["path", "content"],
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "overwrite": {"type": "boolean"},
                    },
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.MEDIUM,
                required_permissions=["filesystem.write"],
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.IDEMPOTENT_MUTATION,
                timeout_seconds=15.0,
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="filesystem.delete",
                version="1.0.0",
                description="Delete a file within allowed directory roots.",
                input_schema={
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.HIGH,
                required_permissions=["filesystem.delete"],
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.IDEMPOTENT_MUTATION,
                timeout_seconds=10.0,
            )
        )

        # Process capabilities
        self.register(
            CapabilityDefinition(
                capability_id="process.spawn",
                version="1.0.0",
                description="Spawn a tracked subprocess with resource limits and timeout.",
                input_schema={
                    "type": "object",
                    "required": ["command"],
                    "properties": {
                        "command": {"type": "string"},
                        "args": {"type": "array"},
                        "cwd": {"type": "string"},
                        "timeout_seconds": {"type": "number"},
                    },
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.MEDIUM,
                required_permissions=["process.spawn"],
                sandbox_tier_required="TIER_1_RESTRICTED_TOKEN",
                side_effect_class=SideEffectClass.NON_IDEMPOTENT_MUTATION,
                timeout_seconds=60.0,
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="process.kill",
                version="1.0.0",
                description="Terminate a spawned subprocess by PID or execution handle.",
                input_schema={
                    "type": "object",
                    "required": ["pid"],
                    "properties": {"pid": {"type": "integer"}},
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.MEDIUM,
                required_permissions=["process.kill"],
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.IDEMPOTENT_MUTATION,
                timeout_seconds=10.0,
            )
        )

        # Desktop capabilities
        self.register(
            CapabilityDefinition(
                capability_id="desktop.focus_window",
                version="1.0.0",
                description="Bring window matching title or pattern into foreground.",
                input_schema={
                    "type": "object",
                    "required": ["title"],
                    "properties": {"title": {"type": "string"}},
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.READ_ONLY,
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.IDEMPOTENT_MUTATION,
                timeout_seconds=10.0,
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="desktop.get_active_window",
                version="1.0.0",
                description="Query the currently focused active window handle and title.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                risk_class=RiskClass.READ_ONLY,
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.READ_ONLY,
                timeout_seconds=5.0,
            )
        )

        # System capabilities
        self.register(
            CapabilityDefinition(
                capability_id="system.get_volume",
                version="1.0.0",
                description="Query the current master audio volume level and mute status.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                risk_class=RiskClass.READ_ONLY,
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.READ_ONLY,
                timeout_seconds=5.0,
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="system.set_volume",
                version="1.0.0",
                description="Set the master audio volume level or mute status.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "level": {"type": "number"},
                        "muted": {"type": "boolean"},
                    },
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.LOW,
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.IDEMPOTENT_MUTATION,
                timeout_seconds=5.0,
            )
        )

        # Channel capabilities
        self.register(
            CapabilityDefinition(
                capability_id="channels.send_message",
                version="1.0.0",
                description="Send an outbound message via route-bound transport (Telegram/Discord).",
                input_schema={
                    "type": "object",
                    "required": ["content"],
                    "properties": {
                        "content": {"type": "string"},
                        "channel": {"type": "string"},
                        "target_id": {"type": "string"},
                    },
                },
                output_schema={"type": "object"},
                risk_class=RiskClass.LOW,
                sandbox_tier_required="TIER_0_APP",
                side_effect_class=SideEffectClass.NON_IDEMPOTENT_MUTATION,
                timeout_seconds=20.0,
            )
        )


__all__ = ["CapabilityRegistry"]
