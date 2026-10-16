"""src.security.policy_engine — Central Security Policy and Capability Engine.

Matches OpenClaw packages/plugin_sdk/src/jarvis_sdk/contract.py and agent_runtime security model:
- Explicit SecurityPrincipal with TrustLevel
- Capability-based authorization (can_exec_cmd, can_write_fs, etc.)
- Risk classification (LOW, MEDIUM, HIGH, CRITICAL)
- Confirmation and approval requirement determination
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Optional, Set


class TrustLevel(enum.IntEnum):
    UNTRUSTED = 0  # External webhook, public channel mention, untrusted web payload
    AUTHENTICATED = 1  # Verified channel user (e.g. regular Discord/Telegram user)
    OPERATOR = 2  # Verified host operator (desktop UI, local CLI)
    SYSTEM = 3  # Core internal runtime, migration tasks


class Capability(str, enum.Enum):
    FS_READ = "fs:read"
    FS_WRITE = "fs:write"
    FS_DELETE = "fs:delete"
    CMD_EXEC = "cmd:exec"
    PROCESS_KILL = "process:kill"
    NET_ACCESS = "net:access"
    BROWSER_AUTOMATE = "browser:automate"
    SECRET_READ = "secret:read"
    ADMIN_CONFIG = "admin:config"


class RiskLevel(str, enum.Enum):
    LOW = "low"  # Read public files, read ordinary web, search
    MEDIUM = "medium"  # Modify workspace files, open applications
    HIGH = "high"  # Terminate processes, modify configuration, delete files
    CRITICAL = "critical"  # Execute shell commands outside workspace, system path deletion


@dataclass(frozen=True, slots=True)
class SecurityPrincipal:
    principal_id: str
    trust_level: TrustLevel
    channel: str
    session_id: str
    capabilities: Set[Capability] = field(default_factory=set)

    @classmethod
    def local_operator(cls, session_id: str = "desktop_session") -> SecurityPrincipal:
        return cls(
            principal_id="local_operator",
            trust_level=TrustLevel.OPERATOR,
            channel="desktop",
            session_id=session_id,
            capabilities=set(Capability),
        )

    @classmethod
    def channel_user(cls, user_id: str, channel: str, session_id: str) -> SecurityPrincipal:
        return cls(
            principal_id=f"{channel}:{user_id}",
            trust_level=TrustLevel.AUTHENTICATED,
            channel=channel,
            session_id=session_id,
            capabilities={Capability.FS_READ, Capability.NET_ACCESS, Capability.BROWSER_AUTOMATE},
        )

    @classmethod
    def untrusted(cls, identifier: str = "untrusted_source") -> SecurityPrincipal:
        return cls(
            principal_id=identifier,
            trust_level=TrustLevel.UNTRUSTED,
            channel="external",
            session_id="untrusted",
            capabilities=set(),
        )


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    risk_level: RiskLevel
    requires_approval: bool
    reason: str
    sanitized_args: Optional[dict[str, Any]] = None


class SecurityPolicyEngine:
    """Central authorization engine evaluating principal, tool, and arguments."""

    TOOL_CAPABILITY_MAP: dict[str, Set[Capability]] = {
        "read": {Capability.FS_READ},
        "ls": {Capability.FS_READ},
        "write": {Capability.FS_WRITE},
        "edit": {Capability.FS_WRITE},
        "mkdir": {Capability.FS_WRITE},
        "remove_path": {Capability.FS_DELETE},
        "rename_path": {Capability.FS_WRITE},
        "exec": {Capability.CMD_EXEC},
        "process": {Capability.PROCESS_KILL},
        "open_path": {Capability.FS_READ},
        "browser": {Capability.BROWSER_AUTOMATE, Capability.NET_ACCESS},
    }

    TOOL_RISK_MAP: dict[str, RiskLevel] = {
        "read": RiskLevel.LOW,
        "ls": RiskLevel.LOW,
        "browser": RiskLevel.LOW,
        "open_path": RiskLevel.LOW,
        "write": RiskLevel.MEDIUM,
        "edit": RiskLevel.MEDIUM,
        "mkdir": RiskLevel.MEDIUM,
        "rename_path": RiskLevel.MEDIUM,
        "process": RiskLevel.HIGH,
        "remove_path": RiskLevel.HIGH,
        "exec": RiskLevel.CRITICAL,
    }

    def evaluate(
        self,
        principal: SecurityPrincipal,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> PolicyDecision:
        required_caps = self.TOOL_CAPABILITY_MAP.get(tool_name, set())
        missing_caps = required_caps - principal.capabilities
        if missing_caps:
            missing_names = sorted(c.value for c in missing_caps)
            return PolicyDecision(
                allowed=False,
                risk_level=RiskLevel.HIGH,
                requires_approval=False,
                reason=f"Principal '{principal.principal_id}' lacks required capabilities: {missing_names}",
            )

        base_risk = self.TOOL_RISK_MAP.get(tool_name, RiskLevel.MEDIUM)

        if tool_name == "remove_path" and arguments.get("recursive"):
            base_risk = RiskLevel.CRITICAL
        elif tool_name == "exec":
            base_risk = RiskLevel.CRITICAL
        elif tool_name == "process" and arguments.get("action") == "kill":
            base_risk = RiskLevel.HIGH

        requires_approval = (base_risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}) and (
            principal.trust_level < TrustLevel.OPERATOR
        )

        return PolicyDecision(
            allowed=True,
            risk_level=base_risk,
            requires_approval=requires_approval,
            reason="Policy check passed",
            sanitized_args=arguments,
        )
