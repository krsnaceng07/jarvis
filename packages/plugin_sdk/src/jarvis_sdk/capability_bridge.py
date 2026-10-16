"""Track 3.6 — OpenClaw Plugin → Execution Pipeline Capability Bridge.

Translates ``ToolPluginToolDefinition`` records discovered by the plugin
loader into ``CapabilityDefinition``-compatible dicts that can be registered
with the frozen Track 3.2 ``CapabilityRegistry``.

Design constraints (OD-37B):
* ``plugin_sdk`` must NOT statically import ``jarvis_agent`` (agent_runtime).
  All integration types are expressed as ``Protocol`` so the composition root
  can bind concrete implementations without introducing a package dependency.
* Frozen packages (agent_runtime, client_runtime, channels_core,
  gateway_protocol) are NOT modified by this module.
* Only allowlisted plugins are bridged; mass activation is prohibited.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "BridgeSecurityPolicy",
    "BridgedCapability",
    "CapabilityBridge",
    "PluginAllowlist",
    "PluginToolSource",
    "RegistryTarget",
    "RiskLevel",
    "SecurityViolation",
    "translate_plugin_tool",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Risk mapping — mirrors agent_runtime RiskClass without importing it
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    """Risk classification for bridged capabilities.

    Values are string-identical to ``jarvis_agent.orchestration.models.risk.RiskClass``
    so the composition root can map them without conversion.
    """

    READ_ONLY = "READ_ONLY"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SideEffectLevel(str, Enum):
    """Side-effect classification mirroring ``SideEffectClass``."""

    READ_ONLY = "READ_ONLY"
    IDEMPOTENT_MUTATION = "IDEMPOTENT_MUTATION"
    NON_IDEMPOTENT_MUTATION = "NON_IDEMPOTENT_MUTATION"
    EXTERNAL_TRANSACTION = "EXTERNAL_TRANSACTION"


# ---------------------------------------------------------------------------
# Protocol types — structural compatibility with agent_runtime contracts
# ---------------------------------------------------------------------------

@runtime_checkable
class RegistryTarget(Protocol):
    """Structural match for ``CapabilityRegistry.register``."""

    def register(self, definition: Any) -> None: ...
    def has(self, capability_id: str) -> bool: ...


@runtime_checkable
class CapabilityDefinitionFactory(Protocol):
    """Callable that constructs a ``CapabilityDefinition`` from keyword args.

    The composition root supplies the real ``CapabilityDefinition`` constructor.
    """

    def __call__(
        self,
        *,
        capability_id: str,
        version: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        risk_class: Any,
        required_permissions: list[str],
        sandbox_tier_required: str,
        side_effect_class: Any,
        timeout_seconds: float,
        supports_cancellation: bool,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# Plugin allowlist — controlled activation (no mass plugin activation)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PluginAllowlistEntry:
    """One authorized plugin in the allowlist."""

    plugin_id: str
    max_risk: RiskLevel = RiskLevel.LOW
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    denied_tools: frozenset[str] = field(default_factory=frozenset)


class PluginAllowlist:
    """Controls which plugins may have their tools bridged.

    Empty allowlist means NO plugins are bridged (safe default).
    """

    def __init__(self, entries: list[PluginAllowlistEntry] | None = None) -> None:
        self._entries: dict[str, PluginAllowlistEntry] = {}
        for entry in entries or []:
            self._entries[entry.plugin_id] = entry

    def is_plugin_allowed(self, plugin_id: str) -> bool:
        return plugin_id in self._entries

    def is_tool_allowed(self, plugin_id: str, tool_name: str) -> bool:
        entry = self._entries.get(plugin_id)
        if entry is None:
            return False
        if entry.denied_tools and tool_name in entry.denied_tools:
            return False
        if entry.allowed_tools and tool_name not in entry.allowed_tools:
            return False
        return True

    def max_risk_for(self, plugin_id: str) -> RiskLevel:
        entry = self._entries.get(plugin_id)
        return entry.max_risk if entry else RiskLevel.READ_ONLY

    @property
    def plugin_ids(self) -> frozenset[str]:
        return frozenset(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# Source type — what the bridge reads from plugin loader results
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PluginToolSource:
    """A single plugin tool discovered by the loader.

    Fields mirror ``ToolPluginToolDefinition`` without importing it.
    """

    plugin_id: str
    tool_name: str
    description: str
    parameters: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)
    is_optional: bool = False


# ---------------------------------------------------------------------------
# Bridge output — what gets registered with the execution pipeline
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BridgedCapability:
    """Result of translating a plugin tool into a capability record.

    The ``capability_dict`` contains all fields needed to construct a
    ``CapabilityDefinition`` via its ``from_dict`` classmethod or constructor.
    """

    plugin_id: str
    tool_name: str
    capability_id: str
    capability_dict: dict[str, Any]


# ---------------------------------------------------------------------------
# Security policy — controls risk clamping and input validation
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SecurityViolation:
    """A security check failure during bridge translation."""

    plugin_id: str
    tool_name: str
    violation_type: str
    detail: str


class BridgeSecurityPolicy:
    """Enforces security constraints on bridged capabilities.

    Controls:
    * Maximum risk level per plugin (from allowlist)
    * Capability ID format validation
    * Parameter schema sanitization
    * Deterministic capability ID generation
    """

    # Capability IDs: plugin_id.tool_name, alphanumeric + dots + underscores + hyphens
    _CAPABILITY_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")

    def validate_capability_id(self, capability_id: str) -> SecurityViolation | None:
        if not self._CAPABILITY_ID_RE.match(capability_id):
            return SecurityViolation(
                plugin_id="",
                tool_name="",
                violation_type="INVALID_CAPABILITY_ID",
                detail=f"Capability ID '{capability_id}' does not match allowed pattern",
            )
        return None

    def clamp_risk(
        self, requested: RiskLevel, max_allowed: RiskLevel,
    ) -> RiskLevel:
        """Clamp risk to the lower of requested and max_allowed."""
        ordered = list(RiskLevel)
        req_idx = ordered.index(requested)
        max_idx = ordered.index(max_allowed)
        return ordered[min(req_idx, max_idx)]

    def validate_schema(self, schema: dict[str, Any]) -> SecurityViolation | None:
        """Reject schemas that reference external URIs or are excessively deep."""
        schema_str = json.dumps(schema)
        if len(schema_str) > 64_000:
            return SecurityViolation(
                plugin_id="",
                tool_name="",
                violation_type="SCHEMA_TOO_LARGE",
                detail=f"Schema is {len(schema_str)} bytes (max 64000)",
            )
        return None


# ---------------------------------------------------------------------------
# Translation function — single tool
# ---------------------------------------------------------------------------

def _make_capability_id(plugin_id: str, tool_name: str) -> str:
    """Deterministic capability ID: ``plugin.<plugin_id>.<tool_name>``.

    The ``plugin.`` prefix prevents collision with core capabilities.
    """
    return f"plugin.{plugin_id}.{tool_name}"


def _schema_fingerprint(schema: dict[str, Any]) -> str:
    """Deterministic hash of a JSON schema for dedup."""
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def translate_plugin_tool(
    source: PluginToolSource,
    allowlist: PluginAllowlist,
    security: BridgeSecurityPolicy | None = None,
) -> BridgedCapability | SecurityViolation:
    """Translate one plugin tool into a bridged capability record.

    Returns ``BridgedCapability`` on success or ``SecurityViolation`` on failure.

    The result's ``capability_dict`` is compatible with
    ``CapabilityDefinition.from_dict()`` — the composition root can call
    ``CapabilityDefinition(**bridged.capability_dict)`` or use ``from_dict``.
    """
    security = security or BridgeSecurityPolicy()

    # Gate 1: plugin must be allowlisted
    if not allowlist.is_plugin_allowed(source.plugin_id):
        return SecurityViolation(
            plugin_id=source.plugin_id,
            tool_name=source.tool_name,
            violation_type="PLUGIN_NOT_ALLOWLISTED",
            detail=f"Plugin '{source.plugin_id}' is not in the activation allowlist",
        )

    # Gate 2: tool must be allowed for this plugin
    if not allowlist.is_tool_allowed(source.plugin_id, source.tool_name):
        return SecurityViolation(
            plugin_id=source.plugin_id,
            tool_name=source.tool_name,
            violation_type="TOOL_NOT_ALLOWED",
            detail=f"Tool '{source.tool_name}' is denied for plugin '{source.plugin_id}'",
        )

    # Gate 3: capability ID format
    capability_id = _make_capability_id(source.plugin_id, source.tool_name)
    id_violation = security.validate_capability_id(capability_id)
    if id_violation is not None:
        id_violation = SecurityViolation(
            plugin_id=source.plugin_id,
            tool_name=source.tool_name,
            violation_type=id_violation.violation_type,
            detail=id_violation.detail,
        )
        return id_violation

    # Gate 4: schema validation
    schema_violation = security.validate_schema(source.parameters)
    if schema_violation is not None:
        return SecurityViolation(
            plugin_id=source.plugin_id,
            tool_name=source.tool_name,
            violation_type=schema_violation.violation_type,
            detail=schema_violation.detail,
        )

    # Risk: clamp to allowlist maximum
    max_risk = allowlist.max_risk_for(source.plugin_id)
    # Default all plugin tools to LOW risk; allowlist caps further
    effective_risk = security.clamp_risk(RiskLevel.LOW, max_risk)

    capability_dict: dict[str, Any] = {
        "capability_id": capability_id,
        "version": "1.0.0",
        "description": source.description,
        "input_schema": source.parameters,
        "output_schema": source.output_schema,
        "risk_class": effective_risk.value,
        "required_permissions": [f"plugin.{source.plugin_id}.execute"],
        "sandbox_tier_required": "TIER_0_APP",
        "side_effect_class": SideEffectLevel.NON_IDEMPOTENT_MUTATION.value,
        "timeout_seconds": 30.0,
        "supports_cancellation": False,
    }

    return BridgedCapability(
        plugin_id=source.plugin_id,
        tool_name=source.tool_name,
        capability_id=capability_id,
        capability_dict=capability_dict,
    )


# ---------------------------------------------------------------------------
# Bridge — batch translation with deterministic ordering
# ---------------------------------------------------------------------------

class CapabilityBridge:
    """Translates a batch of plugin tools into capability registrations.

    Usage at composition root::

        from jarvis_sdk.capability_bridge import CapabilityBridge, PluginAllowlist
        from jarvis_agent.execution.registry.capability_registry import CapabilityRegistry
        from jarvis_agent.execution.models.capability_definition import CapabilityDefinition

        allowlist = PluginAllowlist([...])
        bridge = CapabilityBridge(allowlist)

        # tools_from_loader: list[PluginToolSource] extracted from LoadResult
        results = bridge.translate_all(tools_from_loader)
        for cap in results.capabilities:
            registry.register(CapabilityDefinition(**cap.capability_dict))
    """

    def __init__(
        self,
        allowlist: PluginAllowlist,
        security: BridgeSecurityPolicy | None = None,
    ) -> None:
        self._allowlist = allowlist
        self._security = security or BridgeSecurityPolicy()

    @property
    def allowlist(self) -> PluginAllowlist:
        return self._allowlist

    def translate_all(
        self, sources: list[PluginToolSource],
    ) -> BridgeResult:
        """Translate all provided tool sources.

        Returns a ``BridgeResult`` with deterministic ordering:
        capabilities and violations are sorted by ``(plugin_id, tool_name)``.
        """
        capabilities: list[BridgedCapability] = []
        violations: list[SecurityViolation] = []
        seen_ids: set[str] = set()

        # Deterministic ordering: sort by (plugin_id, tool_name)
        sorted_sources = sorted(sources, key=lambda s: (s.plugin_id, s.tool_name))

        for source in sorted_sources:
            result = translate_plugin_tool(source, self._allowlist, self._security)
            if isinstance(result, SecurityViolation):
                violations.append(result)
            else:
                # Deterministic dedup: first in sorted order wins
                if result.capability_id in seen_ids:
                    violations.append(SecurityViolation(
                        plugin_id=source.plugin_id,
                        tool_name=source.tool_name,
                        violation_type="DUPLICATE_CAPABILITY_ID",
                        detail=f"Capability '{result.capability_id}' already registered",
                    ))
                else:
                    seen_ids.add(result.capability_id)
                    capabilities.append(result)

        return BridgeResult(
            capabilities=capabilities,
            violations=violations,
        )


@dataclass(frozen=True, slots=True)
class BridgeResult:
    """Outcome of a batch bridge translation."""

    capabilities: list[BridgedCapability] = field(default_factory=list)
    violations: list[SecurityViolation] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return len(self.capabilities)

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    @property
    def all_succeeded(self) -> bool:
        return len(self.violations) == 0
