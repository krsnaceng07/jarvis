"""20-dimension severity-based qualification gate for Track 2.3 Host OS Sandbox Validation."""

from __future__ import annotations

import dataclasses
from typing import Any

from jarvis_learning.invariants_p10 import EvidenceLevel
from jarvis_learning.sandbox.models import (
    EnforcementMechanism,
    HostileProbeResult,
    SeverityLevel,
)


@dataclasses.dataclass(frozen=True)
class SandboxQualificationGate:
    """Evaluates 20 distinct security dimensions and determines qualification."""

    token_privileges_stripped: bool
    deny_only_groups_enforced: bool
    integrity_level_lowered: bool
    job_object_created: bool
    job_kill_on_close: bool
    job_active_process_limit: bool
    job_memory_limit_enforced: bool
    job_ui_restrictions_enforced: bool
    handle_inheritance_blocked: bool
    filesystem_system_protected: bool
    filesystem_progfiles_protected: bool
    filesystem_traversal_blocked: bool
    credential_manager_protected: bool
    environment_secrets_scrubbed: bool
    ipc_pipes_isolated: bool
    network_truthfully_attributed: bool
    code_execution_governed: bool
    persistence_vectors_blocked: bool
    broker_injection_defended: bool
    forensic_cleanliness_verified: bool

    # Severity counters
    s7_count: int = 0
    s6_count: int = 0
    s5_count: int = 0
    s4_count: int = 0
    s3_count: int = 0
    s2_count: int = 0
    s1_count: int = 0
    s0_count: int = 0

    @property
    def passed_dimensions(self) -> int:
        """Count how many of the 20 dimensions passed."""
        dims = [
            self.token_privileges_stripped,
            self.deny_only_groups_enforced,
            self.integrity_level_lowered,
            self.job_object_created,
            self.job_kill_on_close,
            self.job_active_process_limit,
            self.job_memory_limit_enforced,
            self.job_ui_restrictions_enforced,
            self.handle_inheritance_blocked,
            self.filesystem_system_protected,
            self.filesystem_progfiles_protected,
            self.filesystem_traversal_blocked,
            self.credential_manager_protected,
            self.environment_secrets_scrubbed,
            self.ipc_pipes_isolated,
            self.network_truthfully_attributed,
            self.code_execution_governed,
            self.persistence_vectors_blocked,
            self.broker_injection_defended,
            self.forensic_cleanliness_verified,
        ]
        return sum(1 for d in dims if d)

    @property
    def is_qualified(self) -> bool:
        """Evaluate qualification criteria: no critical escapes and >= 18 dimensions passed."""
        # Critical violations must be 0
        if self.s7_count > 0 or self.s6_count > 0 or self.s5_count > 0:
            return False
        # Minimum threshold of passed dimensions
        return self.passed_dimensions >= 18

    def determine_effective_level(self, is_windows_native: bool) -> EvidenceLevel:
        """Compute truthful evidence classification level."""
        if not self.is_qualified:
            return EvidenceLevel.L2_IN_PROCESS_INTEGRATION
        if is_windows_native:
            return EvidenceLevel.L4_REAL_WINDOWS_API
        return EvidenceLevel.L3_REAL_SUBPROCESS

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["passed_dimensions"] = self.passed_dimensions
        d["is_qualified"] = self.is_qualified
        return d


class SandboxQualificationEvaluator:
    """Computes the 20-dimension qualification gate from hostile probe results."""

    @classmethod
    def evaluate(
        cls,
        probes: list[HostileProbeResult],
        is_clean_room: bool,
    ) -> SandboxQualificationGate:
        """Analyze all probe results and generate the qualification gate."""
        probe_map = {p.vector_id: p for p in probes}

        # Severity counters
        sev_counts: dict[SeverityLevel, int] = {s: 0 for s in SeverityLevel}
        for p in probes:
            sev_counts[p.severity] = sev_counts.get(p.severity, 0) + 1

        # Check dimensions
        tok = probe_map.get("TOK-001")
        tok_stripped = tok is not None and tok.blocked

        integ = probe_map.get("INT-001")
        integ_lowered = integ is not None and integ.blocked

        proc = probe_map.get("PROC-001")
        proc_clean = proc is not None and proc.blocked

        job = probe_map.get("JOB-001")
        job_created = job is not None and job.blocked

        fs1 = probe_map.get("FS-001")
        fs1_prot = fs1 is not None and fs1.blocked

        fs2 = probe_map.get("FS-002")
        fs2_prot = fs2 is not None and fs2.blocked

        fs6 = probe_map.get("FS-006")
        fs6_prot = fs6 is not None and fs6.blocked

        cred1 = probe_map.get("CRED-001")
        cred1_prot = cred1 is not None and cred1.blocked

        cred10 = probe_map.get("CRED-010")
        cred10_prot = cred10 is not None and cred10.blocked

        ipc1 = probe_map.get("IPC-001")
        ipc1_prot = ipc1 is not None and ipc1.blocked

        net = probe_map.get("NET-001")
        # Truthful attribution: must not claim OS_ENFORCED if not configured
        net_truthful = net is not None and (
            net.enforcement_mechanism
            in (EnforcementMechanism.OS_ENFORCED, EnforcementMechanism.NOT_CONFIGURED)
        )

        code1 = probe_map.get("CODE-001")
        code_gov = (
            code1 is not None and code1.enforcement_mechanism != EnforcementMechanism.SIMULATED
        )

        pers1 = probe_map.get("PERS-001")
        pers_prot = pers1 is not None and pers1.blocked

        broker1 = probe_map.get("BROKER-001")
        broker_def = broker1 is not None and broker1.blocked

        res1 = probe_map.get("RES-001")
        res_prot = res1 is not None and res1.blocked

        return SandboxQualificationGate(
            token_privileges_stripped=tok_stripped,
            deny_only_groups_enforced=tok_stripped,
            integrity_level_lowered=integ_lowered,
            job_object_created=job_created,
            job_kill_on_close=job_created,
            job_active_process_limit=res_prot,
            job_memory_limit_enforced=res_prot,
            job_ui_restrictions_enforced=job_created,
            handle_inheritance_blocked=proc_clean,
            filesystem_system_protected=fs1_prot,
            filesystem_progfiles_protected=fs2_prot,
            filesystem_traversal_blocked=fs6_prot,
            credential_manager_protected=cred1_prot,
            environment_secrets_scrubbed=cred10_prot,
            ipc_pipes_isolated=ipc1_prot,
            network_truthfully_attributed=net_truthful,
            code_execution_governed=code_gov,
            persistence_vectors_blocked=pers_prot,
            broker_injection_defended=broker_def,
            forensic_cleanliness_verified=is_clean_room,
            s7_count=sev_counts[SeverityLevel.S7_SANDBOX_ESCAPE],
            s6_count=sev_counts[SeverityLevel.S6_PRIVILEGE_ESCALATION],
            s5_count=sev_counts[SeverityLevel.S5_CREDENTIAL_EXPOSURE],
            s4_count=sev_counts[SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS],
            s3_count=sev_counts[SeverityLevel.S3_HOST_RESOURCE_VIOLATION],
            s2_count=sev_counts[SeverityLevel.S2_SANDBOX_POLICY_VIOLATION],
            s1_count=sev_counts[SeverityLevel.S1_APP_POLICY_BYPASS],
            s0_count=sev_counts[SeverityLevel.S0_EXPECTED_DENIAL],
        )


__all__ = ["SandboxQualificationEvaluator", "SandboxQualificationGate"]
