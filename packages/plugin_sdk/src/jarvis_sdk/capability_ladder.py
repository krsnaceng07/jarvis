"""Plugin Capability Ladder Contract — OpenClaw Parity Architecture.

Defines the hierarchical capability tiers and permission verification rules
for all JARVIS plugins and extensions.

Capability Tiers (Lowest to Highest privilege):
  - Tier 0 (METADATA_ONLY): Declarative manifests, config schemas, zero execution rights.
  - Tier 1 (READ_ONLY): Querying, inspection, read-only file access; no side-effects.
  - Tier 2 (CONVERSATIONAL): Interactive agent turn execution, user-supervised operations.
  - Tier 3 (MUTATING_SYSTEM): File mutation, process execution, service restart; system-level actions.
  - Tier 4 (AUTONOMOUS_BACKGROUND): Autonomous Claws, background worker daemons, scheduled cron.

Enforces the Invariant:
A plugin cannot request or execute capabilities beyond its granted Capability Ladder Tier.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from jarvis_normalization_core.result import Err, Ok, Result

logger = logging.getLogger("jarvis.plugin_sdk.capability_ladder")


class CapabilityTier(IntEnum):
    """Hierarchical capability tiers for plugins in ascending privilege order."""

    TIER_0_METADATA_ONLY = 0
    TIER_1_READ_ONLY = 1
    TIER_2_CONVERSATIONAL = 2
    TIER_3_MUTATING_SYSTEM = 3
    TIER_4_AUTONOMOUS_BACKGROUND = 4

    @classmethod
    def from_string(cls, val: str | None) -> CapabilityTier:
        """Parse string representation into CapabilityTier."""
        if not val:
            return cls.TIER_0_METADATA_ONLY
        norm = str(val).strip().lower().replace("-", "_").replace(" ", "_")
        # Check direct enum member name match (e.g. TIER_3_MUTATING_SYSTEM)
        try:
            return cls[norm.upper()]
        except KeyError:
            pass

        mapping = {
            "0": cls.TIER_0_METADATA_ONLY,
            "tier_0": cls.TIER_0_METADATA_ONLY,
            "tier_0_metadata_only": cls.TIER_0_METADATA_ONLY,
            "metadata": cls.TIER_0_METADATA_ONLY,
            "metadata_only": cls.TIER_0_METADATA_ONLY,
            "setup": cls.TIER_0_METADATA_ONLY,
            "setup_only": cls.TIER_0_METADATA_ONLY,
            "1": cls.TIER_1_READ_ONLY,
            "tier_1": cls.TIER_1_READ_ONLY,
            "tier_1_read_only": cls.TIER_1_READ_ONLY,
            "read_only": cls.TIER_1_READ_ONLY,
            "readonly": cls.TIER_1_READ_ONLY,
            "inspection": cls.TIER_1_READ_ONLY,
            "2": cls.TIER_2_CONVERSATIONAL,
            "tier_2": cls.TIER_2_CONVERSATIONAL,
            "tier_2_conversational": cls.TIER_2_CONVERSATIONAL,
            "conversational": cls.TIER_2_CONVERSATIONAL,
            "standard": cls.TIER_2_CONVERSATIONAL,
            "interactive": cls.TIER_2_CONVERSATIONAL,
            "tool": cls.TIER_2_CONVERSATIONAL,
            "3": cls.TIER_3_MUTATING_SYSTEM,
            "tier_3": cls.TIER_3_MUTATING_SYSTEM,
            "tier_3_mutating_system": cls.TIER_3_MUTATING_SYSTEM,
            "mutating": cls.TIER_3_MUTATING_SYSTEM,
            "mutating_system": cls.TIER_3_MUTATING_SYSTEM,
            "system": cls.TIER_3_MUTATING_SYSTEM,
            "full": cls.TIER_3_MUTATING_SYSTEM,
            "4": cls.TIER_4_AUTONOMOUS_BACKGROUND,
            "tier_4": cls.TIER_4_AUTONOMOUS_BACKGROUND,
            "tier_4_autonomous_background": cls.TIER_4_AUTONOMOUS_BACKGROUND,
            "autonomous": cls.TIER_4_AUTONOMOUS_BACKGROUND,
            "autonomous_background": cls.TIER_4_AUTONOMOUS_BACKGROUND,
            "background": cls.TIER_4_AUTONOMOUS_BACKGROUND,
            "claws": cls.TIER_4_AUTONOMOUS_BACKGROUND,
            "daemons": cls.TIER_4_AUTONOMOUS_BACKGROUND,
        }
        return mapping.get(norm, cls.TIER_1_READ_ONLY)


# Permission to minimum required CapabilityTier
PERMISSION_TIER_REQUIREMENTS: dict[str, CapabilityTier] = {
    # Read-only operations (Tier 1)
    "filesystem:read": CapabilityTier.TIER_1_READ_ONLY,
    "memory:read": CapabilityTier.TIER_1_READ_ONLY,
    "metrics:read": CapabilityTier.TIER_1_READ_ONLY,
    "inspect:system": CapabilityTier.TIER_1_READ_ONLY,
    "network:ingress": CapabilityTier.TIER_1_READ_ONLY,
    # Conversational interactive operations (Tier 2)
    "channel:send": CapabilityTier.TIER_2_CONVERSATIONAL,
    "channel:receive": CapabilityTier.TIER_2_CONVERSATIONAL,
    "tool:execute": CapabilityTier.TIER_2_CONVERSATIONAL,
    "llm:infer": CapabilityTier.TIER_2_CONVERSATIONAL,
    "network:egress": CapabilityTier.TIER_2_CONVERSATIONAL,
    "browser:navigate": CapabilityTier.TIER_2_CONVERSATIONAL,
    "browser:interact": CapabilityTier.TIER_2_CONVERSATIONAL,
    # Mutating system operations (Tier 3)
    "filesystem:write": CapabilityTier.TIER_3_MUTATING_SYSTEM,
    "filesystem:delete": CapabilityTier.TIER_3_MUTATING_SYSTEM,
    "process:exec": CapabilityTier.TIER_3_MUTATING_SYSTEM,
    "process:manage": CapabilityTier.TIER_3_MUTATING_SYSTEM,
    "memory:write": CapabilityTier.TIER_3_MUTATING_SYSTEM,
    "config:modify": CapabilityTier.TIER_3_MUTATING_SYSTEM,
    "system:power": CapabilityTier.TIER_3_MUTATING_SYSTEM,
    # Autonomous background worker operations (Tier 4)
    "claws:schedule": CapabilityTier.TIER_4_AUTONOMOUS_BACKGROUND,
    "claws:execute": CapabilityTier.TIER_4_AUTONOMOUS_BACKGROUND,
    "worker:background": CapabilityTier.TIER_4_AUTONOMOUS_BACKGROUND,
    "cron:register": CapabilityTier.TIER_4_AUTONOMOUS_BACKGROUND,
    "daemons:spawn": CapabilityTier.TIER_4_AUTONOMOUS_BACKGROUND,
}


@dataclass(frozen=True, slots=True)
class CapabilityViolationError:
    """Record representing a capability violation attempt."""

    plugin_id: str
    target_action: str
    required_permission: str
    required_tier: CapabilityTier
    granted_tier: CapabilityTier
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "target_action": self.target_action,
            "required_permission": self.required_permission,
            "required_tier": self.required_tier.name,
            "granted_tier": self.granted_tier.name,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CapabilityLadderContract:
    """Capability Ladder Contract for a specific plugin.

    Determines what operations, tools, and background daemons this plugin
    is authorized to declare and run.
    """

    plugin_id: str
    granted_tier: CapabilityTier
    declared_permissions: frozenset[str] = field(default_factory=frozenset)
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    quarantined: bool = False
    quarantine_reason: str | None = None

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any]) -> CapabilityLadderContract:
        """Construct and validate a CapabilityLadderContract from a plugin manifest."""
        plugin_id = str(manifest.get("id") or "unknown")
        contracts = manifest.get("contracts") or {}
        permissions_raw = contracts.get("permissions") or manifest.get("permissions") or []
        declared_perms = set(str(p) for p in permissions_raw)

        # Tool-capable plugins are inherently allowed to execute their declared actions.
        # Many legacy manifests describe the actual tool names in ``contracts.tools`` and
        # ``tools`` without separately listing the generic ``tool:execute`` permission,
        # so we add the implicit permission up front instead of incorrectly quarantining
        # otherwise valid tool plugins during registration.
        tool_contract_names = contracts.get("tools") or manifest.get("tools") or []
        if tool_contract_names and "tool:execute" not in declared_perms:
            declared_perms.add("tool:execute")

        declared_perms_frozen = frozenset(declared_perms)

        # Determine granted tier from explicit manifest declaration or infer from kind/permissions
        explicit_tier_str = contracts.get("capability_tier") or contracts.get("capability_level")
        if explicit_tier_str:
            granted_tier = CapabilityTier.from_string(str(explicit_tier_str))
        else:
            kind = str(manifest.get("kind") or "tool").lower()
            if kind in ("skill", "migration"):
                granted_tier = CapabilityTier.TIER_0_METADATA_ONLY
            elif kind in ("infra", "worker", "claws"):
                granted_tier = CapabilityTier.TIER_4_AUTONOMOUS_BACKGROUND
            else:
                # Infer minimum tier necessary for declared permissions
                max_perm_tier = CapabilityTier.TIER_1_READ_ONLY
                for p in declared_perms:
                    req = PERMISSION_TIER_REQUIREMENTS.get(p, CapabilityTier.TIER_2_CONVERSATIONAL)
                    if req > max_perm_tier:
                        max_perm_tier = req
                granted_tier = max(max_perm_tier, CapabilityTier.TIER_2_CONVERSATIONAL)

        # Tools authorized
        tools_list = manifest.get("tools") or []
        allowed_tools = frozenset(
            t["name"] if isinstance(t, dict) and "name" in t else getattr(t, "name", str(t))
            for t in tools_list
        )

        # Enforce Ladder Invariant during creation: check if any declared permission exceeds granted tier
        for perm in declared_perms:
            req_tier = PERMISSION_TIER_REQUIREMENTS.get(perm, CapabilityTier.TIER_2_CONVERSATIONAL)
            if req_tier > granted_tier:
                logger.warning(
                    "Plugin %s declared permission %s (requires %s) which exceeds granted tier %s; quarantining plugin.",
                    plugin_id,
                    perm,
                    req_tier.name,
                    granted_tier.name,
                )
                return cls(
                    plugin_id=plugin_id,
                    granted_tier=granted_tier,
                    declared_permissions=declared_perms_frozen,
                    allowed_tools=allowed_tools,
                    quarantined=True,
                    quarantine_reason=f"Permission {perm} requires {req_tier.name} exceeding granted {granted_tier.name}",
                )

        return cls(
            plugin_id=plugin_id,
            granted_tier=granted_tier,
            declared_permissions=declared_perms_frozen,
            allowed_tools=allowed_tools,
            quarantined=False,
            quarantine_reason=None,
        )

    def verify_action(
        self, action: str, required_permission: str | None = None
    ) -> Result[bool, CapabilityViolationError]:
        """Verify that this plugin is authorized to perform the requested action.

        Returns Ok(True) if verified, or Err(CapabilityViolationError).
        """
        if self.quarantined:
            return Err(
                CapabilityViolationError(
                    plugin_id=self.plugin_id,
                    target_action=action,
                    required_permission=required_permission or "none",
                    required_tier=self.granted_tier,
                    granted_tier=self.granted_tier,
                    reason=f"Plugin is quarantined: {self.quarantine_reason}",
                )
            )

        if not required_permission:
            return Ok(True)

        req_tier = PERMISSION_TIER_REQUIREMENTS.get(
            required_permission, CapabilityTier.TIER_2_CONVERSATIONAL
        )

        # Check Tier hierarchy
        if self.granted_tier < req_tier:
            return Err(
                CapabilityViolationError(
                    plugin_id=self.plugin_id,
                    target_action=action,
                    required_permission=required_permission,
                    required_tier=req_tier,
                    granted_tier=self.granted_tier,
                    reason=(
                        f"Action '{action}' requires tier {req_tier.name} ({req_tier.value}), "
                        f"but plugin only holds {self.granted_tier.name} ({self.granted_tier.value})"
                    ),
                )
            )

        # Check declared permission
        if (
            self.declared_permissions
            and required_permission not in self.declared_permissions
            and self.granted_tier < CapabilityTier.TIER_4_AUTONOMOUS_BACKGROUND
        ):
            return Err(
                CapabilityViolationError(
                    plugin_id=self.plugin_id,
                    target_action=action,
                    required_permission=required_permission,
                    required_tier=req_tier,
                    granted_tier=self.granted_tier,
                    reason=f"Permission '{required_permission}' was not declared in plugin manifest contracts",
                )
            )

        return Ok(True)

    def can_schedule_claws(self) -> bool:
        """True if plugin is authorized to schedule autonomous background Claws."""
        return (
            not self.quarantined
            and self.granted_tier >= CapabilityTier.TIER_4_AUTONOMOUS_BACKGROUND
            and ("claws:schedule" in self.declared_permissions or not self.declared_permissions)
        )

    def can_mutate_system(self) -> bool:
        """True if plugin is authorized to perform system-level mutations."""
        return not self.quarantined and self.granted_tier >= CapabilityTier.TIER_3_MUTATING_SYSTEM


__all__ = [
    "CapabilityLadderContract",
    "CapabilityTier",
    "CapabilityViolationError",
    "PERMISSION_TIER_REQUIREMENTS",
]
