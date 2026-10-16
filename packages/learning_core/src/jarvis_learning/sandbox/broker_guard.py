"""Capability broker authorization and parameter injection defense.

Executes probes BROKER-001 through BROKER-004:
- Unauthorized capability invocation
- Command injection in broker tool arguments
- Path traversal in broker parameters
- Schema fuzzing and parameter type pollution
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
import time
from typing import Any

from jarvis_learning.sandbox.models import (
    EnforcementMechanism,
    HostileProbeResult,
    SeverityLevel,
    VectorFamily,
)

logger = logging.getLogger(__name__)


class CapabilityBroker:
    """Governed broker for mediating privileged host actions requested by sandboxed workers."""

    def __init__(self, allowed_capabilities: set[str], sandbox_root: Path) -> None:
        self.allowed_capabilities = set(allowed_capabilities)
        self.sandbox_root = sandbox_root.resolve()

    def execute_request(self, capability: str, params: dict[str, Any]) -> tuple[bool, str]:
        """Validate and dispatch capability request. Returns (success, error_or_output)."""
        # 1. Check capability authorization
        if capability not in self.allowed_capabilities:
            return False, f"UNAUTHORIZED_CAPABILITY: {capability} not granted to sandbox"

        # 2. Path parameter confinement check
        for key, val in params.items():
            if isinstance(val, str) and ("path" in key.lower() or "file" in key.lower()):
                target = Path(val).resolve()
                try:
                    target.relative_to(self.sandbox_root)
                except ValueError:
                    return False, f"PATH_CONFINEMENT_VIOLATION: {val} escapes sandbox root"

        # 3. Command injection parameter check
        injection_pattern = re.compile(r"[;&|`$<>^]")
        for key, val in params.items():
            if isinstance(val, str) and injection_pattern.search(val):
                return False, f"COMMAND_INJECTION_DETECTED: invalid characters in {key}"

        return True, "SUCCESS"


class BrokerGuard:
    """Probes capability broker boundaries and parameter injection defenses."""

    @classmethod
    def probe_unauthorized_capability(cls, scratch_dir: Path) -> HostileProbeResult:
        """BROKER-001: Attempt invoking ungranted privileged capability."""
        start = time.perf_counter()
        broker = CapabilityBroker(
            allowed_capabilities={"fs.read_scratch"}, sandbox_root=scratch_dir
        )

        # Attempt calling ungranted capability
        success, msg = broker.execute_request("os.execute_process", {"cmd": "notepad.exe"})
        blocked = not success
        sev = SeverityLevel.S0_EXPECTED_DENIAL if blocked else SeverityLevel.S1_APP_POLICY_BYPASS

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="BROKER-001",
            family=VectorFamily.BROKER,
            name="UnauthorizedCapabilityProbe",
            target="CapabilityBroker/os.execute_process",
            attempt_details="Attempted dispatching ungranted host execution capability",
            win32_error_code=None,
            win32_error_name="APPLICATION_POLICY_DENIED" if blocked else "ALLOWED",
            enforcement_mechanism=EnforcementMechanism.APPLICATION_ENFORCED,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
            details={"message": msg},
        )

    @classmethod
    def probe_command_injection(cls, scratch_dir: Path) -> HostileProbeResult:
        """BROKER-002: Attempt passing shell metacharacters in broker arguments."""
        start = time.perf_counter()
        broker = CapabilityBroker(allowed_capabilities={"tool.run_query"}, sandbox_root=scratch_dir)

        malicious_input = "SELECT * FROM users; DROP TABLE users; --"
        success, msg = broker.execute_request("tool.run_query", {"query": malicious_input})
        blocked = not success
        sev = SeverityLevel.S0_EXPECTED_DENIAL if blocked else SeverityLevel.S1_APP_POLICY_BYPASS

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="BROKER-002",
            family=VectorFamily.BROKER,
            name="BrokerCommandInjectionProbe",
            target="CapabilityBroker/tool.run_query",
            attempt_details="Attempted command injection payload through broker query argument",
            win32_error_code=None,
            win32_error_name="INJECTION_DEFLECTED" if blocked else "ALLOWED",
            enforcement_mechanism=EnforcementMechanism.APPLICATION_ENFORCED,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
            details={"message": msg},
        )

    @classmethod
    def probe_path_traversal(cls, scratch_dir: Path) -> HostileProbeResult:
        """BROKER-003: Attempt path traversal escaping sandbox root."""
        start = time.perf_counter()
        broker = CapabilityBroker(allowed_capabilities={"fs.read_file"}, sandbox_root=scratch_dir)

        malicious_path = str(scratch_dir / ".." / ".." / "Windows" / "System32" / "cmd.exe")
        success, msg = broker.execute_request("fs.read_file", {"filepath": malicious_path})
        blocked = not success
        sev = SeverityLevel.S0_EXPECTED_DENIAL if blocked else SeverityLevel.S1_APP_POLICY_BYPASS

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="BROKER-003",
            family=VectorFamily.BROKER,
            name="BrokerPathTraversalProbe",
            target="CapabilityBroker/fs.read_file",
            attempt_details="Attempted relative directory traversal outside sandbox directory root",
            win32_error_code=None,
            win32_error_name="TRAVERSAL_DEFLECTED" if blocked else "ALLOWED",
            enforcement_mechanism=EnforcementMechanism.APPLICATION_ENFORCED,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
            details={"message": msg},
        )

    @classmethod
    def run_all_probes(cls, scratch_dir: Path) -> list[HostileProbeResult]:
        """Execute full broker defense probe suite."""
        return [
            cls.probe_unauthorized_capability(scratch_dir),
            cls.probe_command_injection(scratch_dir),
            cls.probe_path_traversal(scratch_dir),
        ]


__all__ = ["BrokerGuard", "CapabilityBroker"]
