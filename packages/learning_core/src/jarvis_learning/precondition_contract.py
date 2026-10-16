"""Precondition Contracts for Learned Strategies.

Defines formal, machine-verifiable operational prerequisites:
- Required & forbidden tool capabilities
- Active state probes (e.g., window title, process running, DOM element present)
- Environment constraints (OS, architecture)
- Parameter type/bounds constraints
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(slots=True)
class StateProbe:
    """A lightweight read-only probe to verify environment state."""

    probe_tool: str
    expected_value: Any
    comparator: str = "equals"  # "equals", "contains", "truthy", "not_equals"

    def evaluate(self, actual_value: Any) -> bool:
        if self.comparator == "equals":
            return actual_value == self.expected_value
        elif self.comparator == "not_equals":
            return actual_value != self.expected_value
        elif self.comparator == "contains":
            if actual_value is None:
                return False
            return str(self.expected_value) in str(actual_value)
        elif self.comparator == "truthy":
            return bool(actual_value)
        return False


@dataclass(slots=True)
class PreconditionContract:
    """Formal contract required before a strategy can be applied."""

    required_capabilities: List[str] = field(default_factory=list)
    forbidden_capabilities: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    state_probes: List[StateProbe] = field(default_factory=list)
    environment_prerequisites: Dict[str, str] = field(default_factory=dict)
    parameter_constraints: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def check_satisfaction(
        self,
        context: Dict[str, Any],
        available_tools: Optional[List[str]] = None,
        tool_capabilities: Optional[Dict[str, List[str]]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Verify whether all preconditions are met in the current context."""
        # 1. Check OS / environment prerequisites
        if "os" in self.environment_prerequisites:
            target_os = self.environment_prerequisites["os"].lower()
            current_os = (
                "windows"
                if sys.platform.startswith("win")
                else "linux"
                if sys.platform.startswith("linux")
                else "darwin"
            )
            if target_os != current_os:
                return (
                    False,
                    f"Environment OS mismatch: requires {target_os}, current is {current_os}",
                )

        # 2. Check required tools
        if available_tools is not None:
            available_set = set(available_tools)
            for tool in self.required_tools:
                if tool not in available_set:
                    return False, f"Missing required tool: {tool}"

        # 3. Check capabilities
        if tool_capabilities is not None:
            all_caps: set[str] = set()
            for caps in tool_capabilities.values():
                all_caps.update(caps)

            for cap in self.required_capabilities:
                if cap not in all_caps:
                    return False, f"Missing required capability: {cap}"

            for cap in self.forbidden_capabilities:
                if cap in all_caps:
                    return False, f"Forbidden capability present: {cap}"

        # 4. Check state probes using context values
        for probe in self.state_probes:
            actual_val = context.get(probe.probe_tool)
            if not probe.evaluate(actual_val):
                return (
                    False,
                    f"State probe failed for '{probe.probe_tool}': expected {probe.expected_value} ({probe.comparator}), got {actual_val}",
                )

        # 5. Parameter constraints check against context arguments
        call_args = context.get("tool_args", {})
        if isinstance(call_args, dict):
            for param_name, constraints in self.parameter_constraints.items():
                if param_name in call_args:
                    val = call_args[param_name]
                    if "min" in constraints and isinstance(val, (int, float)):
                        if val < constraints["min"]:
                            return (
                                False,
                                f"Parameter {param_name}={val} below minimum {constraints['min']}",
                            )
                    if "max" in constraints and isinstance(val, (int, float)):
                        if val > constraints["max"]:
                            return (
                                False,
                                f"Parameter {param_name}={val} above maximum {constraints['max']}",
                            )
                    if "allowed" in constraints and isinstance(constraints["allowed"], list):
                        if val not in constraints["allowed"]:
                            return (
                                False,
                                f"Parameter {param_name}={val} not in allowed set {constraints['allowed']}",
                            )

        return True, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "required_capabilities": self.required_capabilities,
            "forbidden_capabilities": self.forbidden_capabilities,
            "required_tools": self.required_tools,
            "state_probes": [
                {
                    "probe_tool": p.probe_tool,
                    "expected_value": p.expected_value,
                    "comparator": p.comparator,
                }
                for p in self.state_probes
            ],
            "environment_prerequisites": self.environment_prerequisites,
            "parameter_constraints": self.parameter_constraints,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PreconditionContract:
        probes = [
            StateProbe(
                probe_tool=p["probe_tool"],
                expected_value=p["expected_value"],
                comparator=p.get("comparator", "equals"),
            )
            for p in data.get("state_probes", [])
        ]
        return cls(
            required_capabilities=list(data.get("required_capabilities", [])),
            forbidden_capabilities=list(data.get("forbidden_capabilities", [])),
            required_tools=list(data.get("required_tools", [])),
            state_probes=probes,
            environment_prerequisites=dict(data.get("environment_prerequisites", {})),
            parameter_constraints=dict(data.get("parameter_constraints", {})),
        )
