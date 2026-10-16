"""jarvis_learning.evaluation.tool_registry — Canonical Centralized Tool Registry.

Enforces:
1. INV-P9-REG-001: Central canonical authority defining all 18 parameters for every tool in JARVIS.
2. Explicit classification of sensitivity tiers, side-effect levels, and shadow execution permissions.
3. Strict enforcement: no tool executes in shadow mode unless declared and permitted by the registry.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Mapping

from .tool_gateway import ToolSensitivityClass


class ToolCategory(enum.StrEnum):
    FILESYSTEM = "FILESYSTEM"
    PROCESS = "PROCESS"
    BROWSER = "BROWSER"
    SYSTEM = "SYSTEM"
    MEMORY = "MEMORY"
    COMMUNICATION = "COMMUNICATION"


class SideEffectLevel(enum.StrEnum):
    NONE = "NONE"  # Pure read-only
    LOCAL_TRANSIENT = "LOCAL_TRANSIENT"  # e.g. window focus, volume
    LOCAL_PERSISTENT = "LOCAL_PERSISTENT"  # e.g. file write, DB update
    EXTERNAL = "EXTERNAL"  # e.g. network call, message send, process kill


class ShadowExecutionMode(enum.StrEnum):
    DENIED = "DENIED"  # Never run in shadow mode
    SNAPSHOT_ONLY = "SNAPSHOT_ONLY"  # Run against static read-only snapshot
    SIMULATED_ONLY = "SIMULATED_ONLY"  # Run against virtual mock simulator
    LIVE_READ = "LIVE_READ"  # Safe live read-only access allowed


@dataclass(frozen=True, slots=True)
class ToolContractDefinition:
    """Formal 18-attribute specification for a tool in the JARVIS ecosystem."""

    tool_id: str
    tool_version: str
    category: str  # ToolCategory
    sensitivity: str  # ToolSensitivityClass
    requires_network: bool
    requires_credentials: bool
    side_effect_level: str  # SideEffectLevel
    supports_shadow: bool
    supports_simulation: bool
    supports_snapshot: bool
    supports_replay: bool
    requires_operator: bool
    allowed_in_active: bool
    allowed_in_shadow: bool
    risk_level: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    timeout_seconds: float
    cancellation_support: bool
    idempotency_support: bool
    metadata: dict[str, Any] = field(default_factory=dict)


# Canonical registry mapping of all standard JARVIS tools
CANONICAL_TOOL_REGISTRY: dict[str, ToolContractDefinition] = {
    # ── Filesystem Tools ──
    "read_file": ToolContractDefinition(
        tool_id="read_file",
        tool_version="1.0.0",
        category=ToolCategory.FILESYSTEM,
        sensitivity=ToolSensitivityClass.READ_ONLY_SENSITIVE,
        requires_network=False,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.NONE,
        supports_shadow=True,
        supports_simulation=False,
        supports_snapshot=True,
        supports_replay=True,
        requires_operator=False,
        allowed_in_active=True,
        allowed_in_shadow=True,
        risk_level="LOW",
        timeout_seconds=5.0,
        cancellation_support=True,
        idempotency_support=True,
    ),
    "write_file": ToolContractDefinition(
        tool_id="write_file",
        tool_version="1.0.0",
        category=ToolCategory.FILESYSTEM,
        sensitivity=ToolSensitivityClass.SIDE_EFFECTING,
        requires_network=False,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.LOCAL_PERSISTENT,
        supports_shadow=True,
        supports_simulation=True,
        supports_snapshot=False,
        supports_replay=True,
        requires_operator=True,
        allowed_in_active=True,
        allowed_in_shadow=False,  # Redirected to virtual diff buffer
        risk_level="HIGH",
        timeout_seconds=5.0,
        cancellation_support=True,
        idempotency_support=False,
    ),
    "delete_file": ToolContractDefinition(
        tool_id="delete_file",
        tool_version="1.0.0",
        category=ToolCategory.FILESYSTEM,
        sensitivity=ToolSensitivityClass.SIDE_EFFECTING,
        requires_network=False,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.LOCAL_PERSISTENT,
        supports_shadow=False,
        supports_simulation=True,
        supports_snapshot=False,
        supports_replay=False,
        requires_operator=True,
        allowed_in_active=True,
        allowed_in_shadow=False,
        risk_level="CRITICAL",
        timeout_seconds=5.0,
        cancellation_support=False,
        idempotency_support=False,
    ),
    # ── Process & System Tools ──
    "process": ToolContractDefinition(
        tool_id="process",
        tool_version="1.0.0",
        category=ToolCategory.PROCESS,
        sensitivity=ToolSensitivityClass.SIDE_EFFECTING,
        requires_network=False,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.LOCAL_TRANSIENT,
        supports_shadow=False,
        supports_simulation=True,
        supports_snapshot=False,
        supports_replay=False,
        requires_operator=True,
        allowed_in_active=True,
        allowed_in_shadow=False,
        risk_level="HIGH",
        timeout_seconds=10.0,
        cancellation_support=True,
        idempotency_support=False,
    ),
    "execute_shell": ToolContractDefinition(
        tool_id="execute_shell",
        tool_version="1.0.0",
        category=ToolCategory.PROCESS,
        sensitivity=ToolSensitivityClass.SIDE_EFFECTING,
        requires_network=True,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.LOCAL_PERSISTENT,
        supports_shadow=False,
        supports_simulation=True,
        supports_snapshot=False,
        supports_replay=False,
        requires_operator=True,
        allowed_in_active=True,
        allowed_in_shadow=False,
        risk_level="CRITICAL",
        timeout_seconds=30.0,
        cancellation_support=True,
        idempotency_support=False,
    ),
    "raw_socket_send": ToolContractDefinition(
        tool_id="raw_socket_send",
        tool_version="1.0.0",
        category=ToolCategory.COMMUNICATION,
        sensitivity=ToolSensitivityClass.FORBIDDEN,
        requires_network=True,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.EXTERNAL,
        supports_shadow=False,
        supports_simulation=False,
        supports_snapshot=False,
        supports_replay=False,
        requires_operator=True,
        allowed_in_active=False,
        allowed_in_shadow=False,
        risk_level="CRITICAL",
        timeout_seconds=1.0,
        cancellation_support=False,
        idempotency_support=False,
    ),
    # ── Browser Tools ──
    "read_browser_tabs": ToolContractDefinition(
        tool_id="read_browser_tabs",
        tool_version="1.0.0",
        category=ToolCategory.BROWSER,
        sensitivity=ToolSensitivityClass.READ_ONLY_SENSITIVE,
        requires_network=False,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.NONE,
        supports_shadow=True,
        supports_simulation=False,
        supports_snapshot=True,
        supports_replay=True,
        requires_operator=False,
        allowed_in_active=True,
        allowed_in_shadow=True,
        risk_level="LOW",
        timeout_seconds=5.0,
        cancellation_support=True,
        idempotency_support=True,
    ),
    "browser_navigate": ToolContractDefinition(
        tool_id="browser_navigate",
        tool_version="1.0.0",
        category=ToolCategory.BROWSER,
        sensitivity=ToolSensitivityClass.SIDE_EFFECTING,
        requires_network=True,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.EXTERNAL,
        supports_shadow=True,
        supports_simulation=True,
        supports_snapshot=False,
        supports_replay=True,
        requires_operator=False,
        allowed_in_active=True,
        allowed_in_shadow=False,
        risk_level="MEDIUM",
        timeout_seconds=15.0,
        cancellation_support=True,
        idempotency_support=True,
    ),
    "browser_click": ToolContractDefinition(
        tool_id="browser_click",
        tool_version="1.0.0",
        category=ToolCategory.BROWSER,
        sensitivity=ToolSensitivityClass.SIDE_EFFECTING,
        requires_network=False,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.LOCAL_TRANSIENT,
        supports_shadow=True,
        supports_simulation=True,
        supports_snapshot=False,
        supports_replay=True,
        requires_operator=False,
        allowed_in_active=True,
        allowed_in_shadow=False,
        risk_level="MEDIUM",
        timeout_seconds=5.0,
        cancellation_support=True,
        idempotency_support=False,
    ),
    # ── System Info & Time ──
    "get_current_time": ToolContractDefinition(
        tool_id="get_current_time",
        tool_version="1.0.0",
        category=ToolCategory.SYSTEM,
        sensitivity=ToolSensitivityClass.READ_ONLY_PUBLIC,
        requires_network=False,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.NONE,
        supports_shadow=True,
        supports_simulation=False,
        supports_snapshot=False,
        supports_replay=True,
        requires_operator=False,
        allowed_in_active=True,
        allowed_in_shadow=True,
        risk_level="LOW",
        timeout_seconds=1.0,
        cancellation_support=True,
        idempotency_support=True,
    ),
    "calculator": ToolContractDefinition(
        tool_id="calculator",
        tool_version="1.0.0",
        category=ToolCategory.SYSTEM,
        sensitivity=ToolSensitivityClass.READ_ONLY_PUBLIC,
        requires_network=False,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.NONE,
        supports_shadow=True,
        supports_simulation=False,
        supports_snapshot=False,
        supports_replay=True,
        requires_operator=False,
        allowed_in_active=True,
        allowed_in_shadow=True,
        risk_level="LOW",
        timeout_seconds=2.0,
        cancellation_support=True,
        idempotency_support=True,
    ),
    "summarize_text": ToolContractDefinition(
        tool_id="summarize_text",
        tool_version="1.0.0",
        category=ToolCategory.SYSTEM,
        sensitivity=ToolSensitivityClass.READ_ONLY_PUBLIC,
        requires_network=False,
        requires_credentials=False,
        side_effect_level=SideEffectLevel.NONE,
        supports_shadow=True,
        supports_simulation=False,
        supports_snapshot=False,
        supports_replay=True,
        requires_operator=False,
        allowed_in_active=True,
        allowed_in_shadow=True,
        risk_level="LOW",
        timeout_seconds=5.0,
        cancellation_support=True,
        idempotency_support=True,
    ),
}


class CentralToolRegistry:
    """Registry engine enforcing tool execution permissions and contract checks."""

    def __init__(self, custom_registry: dict[str, ToolContractDefinition] | None = None) -> None:
        self._registry: dict[str, ToolContractDefinition] = dict(
            custom_registry or CANONICAL_TOOL_REGISTRY
        )

    def get(self, tool_id: str) -> ToolContractDefinition | None:
        return self._registry.get(tool_id)

    def is_allowed_in_active(self, tool_id: str) -> bool:
        defn = self.get(tool_id)
        return defn.allowed_in_active if defn else False

    def is_allowed_in_shadow(self, tool_id: str) -> bool:
        defn = self.get(tool_id)
        return defn.allowed_in_shadow if defn else False

    def requires_simulation(self, tool_id: str) -> bool:
        defn = self.get(tool_id)
        if not defn:
            return True
        return defn.sensitivity in (
            ToolSensitivityClass.SIDE_EFFECTING,
            ToolSensitivityClass.SIMULATABLE,
            ToolSensitivityClass.FORBIDDEN,
        )

    def all_tools(self) -> Mapping[str, ToolContractDefinition]:
        return self._registry
