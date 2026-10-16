"""Comprehensive test suite for Track 2.3 Host OS Sandbox & Execution Boundary Harness.

Validates:
- Win32 token engine, privilege stripping, and differential computation
- Win32 Job Object containment, process/memory limits, UI restrictions
- Handle inheritance isolation and handle leakage auditing
- Filesystem guard (System32, Program Files, Traversal, ADS, SSH keys)
- Credential guard (Credential Manager, DPAPI keys, Environment secrets)
- IPC guard (Named pipes, shared memory, clipboard UIPI)
- Network guard (TCP, UDP, SOCK_RAW, truthful attribution)
- Code execution guard and WDAC/AppLocker detection
- Persistence guard (Startup, Registry Run, Scheduled Task, Service)
- Device guard (PhysicalDrive0, C: volume, device namespace)
- Capability broker authorization, command injection, path traversal
- Resource guard (Memory, process flood, handle flood)
- Restricted process launcher and sanitized environment
- Hostile attack matrix across all 16 vector families
- Independent reference oracle and canonical expectations
- Event hash chain and cryptographic DPAPI/HMAC sealing
- 20-dimension qualification gate and truthful evidence classification
- Master SandboxValidationHarness orchestrator
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from jarvis_learning.invariants_p10 import EvidenceLevel
from jarvis_learning.sandbox.broker_guard import BrokerGuard, CapabilityBroker
from jarvis_learning.sandbox.code_guard import CodeGuard
from jarvis_learning.sandbox.credential_guard import CredentialGuard
from jarvis_learning.sandbox.device_guard import DeviceGuard
from jarvis_learning.sandbox.evidence_sealer import EventHashChain, SandboxEvidenceSealer
from jarvis_learning.sandbox.filesystem_guard import FilesystemGuard
from jarvis_learning.sandbox.handle_isolator import HandleIsolator
from jarvis_learning.sandbox.hostile_matrix import HostileAttackMatrix
from jarvis_learning.sandbox.ipc_guard import IpcGuard
from jarvis_learning.sandbox.models import (
    BoundaryVerdict,
    EnforcementMechanism,
    HostileProbeResult,
    IntegrityLevel,
    SeverityLevel,
    TokenDifferential,
    TokenStateSnapshot,
    VectorFamily,
)
from jarvis_learning.sandbox.network_guard import NetworkGuard
from jarvis_learning.sandbox.persistence_guard import PersistenceGuard
from jarvis_learning.sandbox.qualification import (
    SandboxQualificationEvaluator,
)
from jarvis_learning.sandbox.resource_guard import ResourceGuard
from jarvis_learning.sandbox.restricted_launcher import RestrictedProcessLauncher
from jarvis_learning.sandbox.sandbox_lab_harness import SandboxValidationHarness
from jarvis_learning.sandbox.sandbox_oracle import (
    SandboxReferenceOracle,
)
from jarvis_learning.sandbox.win32_job import Win32JobObjectEngine
from jarvis_learning.sandbox.win32_token import Win32TokenEngine


def test_models_serialization():
    """Verify dataclasses and enums serialize cleanly to dictionaries."""
    probe = HostileProbeResult(
        vector_id="TEST-001",
        family=VectorFamily.FILESYSTEM,
        name="TestProbe",
        target="C:\\Windows",
        attempt_details="Test write attempt",
        win32_error_code=5,
        win32_error_name="ERROR_ACCESS_DENIED",
        enforcement_mechanism=EnforcementMechanism.OS_ENFORCED,
        severity=SeverityLevel.S0_EXPECTED_DENIAL,
        blocked=True,
        duration_ms=1.5,
        details={"extra": "info"},
    )
    d = probe.to_dict()
    assert d["vector_id"] == "TEST-001"
    assert d["family"] == "FILESYSTEM"
    assert d["enforcement_mechanism"] == "OS_ENFORCED"
    assert d["severity"] == "S0_EXPECTED_DENIAL"
    assert d["blocked"] is True


def test_token_engine_snapshot():
    """Verify Win32TokenEngine captures current process token state snapshot."""
    snap = Win32TokenEngine.snapshot_current_process()
    assert isinstance(snap, TokenStateSnapshot)
    assert isinstance(snap.integrity_level, IntegrityLevel)
    assert len(snap.username) > 0
    assert snap.session_id >= 0


def test_token_engine_restricted_token_creation():
    """Verify Win32TokenEngine creates restricted token with stripped privileges."""
    base_snap = Win32TokenEngine.snapshot_current_process()
    restr_token = Win32TokenEngine.create_restricted_token(
        target_integrity=IntegrityLevel.LOW,
        disable_max_privileges=True,
    )
    assert isinstance(restr_token, TokenStateSnapshot)
    assert restr_token.is_restricted_token is True

    diff = Win32TokenEngine.compute_differential(base_snap, restr_token)
    assert isinstance(diff, TokenDifferential)
    assert diff.is_strictly_confined is True


def test_handle_isolator_audit():
    """Verify HandleIsolator audits process handle leakage and returns report."""
    audit = HandleIsolator.audit_handle_leakage()
    assert "is_clean" in audit
    assert "total_handles_scanned" in audit
    assert isinstance(audit["is_clean"], bool)


def test_job_engine_lifecycle():
    """Verify Win32JobObjectEngine creates job, queries PIDs, and terminates cleanly."""
    job = Win32JobObjectEngine(
        kill_on_close=True,
        max_processes=4,
        memory_limit_bytes=64 * 1024 * 1024,
        apply_ui_restrictions=True,
    )
    pids = job.get_assigned_pids()
    assert isinstance(pids, list)
    job.close()
    # Double close should be a safe no-op
    job.close()


def test_filesystem_guard_system32(tmp_path: Path):
    """Verify FS-001 probe denies write to Windows System32 directory."""
    res = FilesystemGuard.probe_system_directory_write(tmp_path)
    assert res.vector_id == "FS-001"
    assert res.family == VectorFamily.FILESYSTEM
    assert res.blocked is True
    assert res.enforcement_mechanism == EnforcementMechanism.OS_ENFORCED
    assert res.severity == SeverityLevel.S0_EXPECTED_DENIAL


def test_filesystem_guard_program_files(tmp_path: Path):
    """Verify FS-002 probe denies write to Program Files directory."""
    res = FilesystemGuard.probe_program_files_write(tmp_path)
    assert res.vector_id == "FS-002"
    assert res.blocked is True
    assert res.enforcement_mechanism == EnforcementMechanism.OS_ENFORCED


def test_filesystem_guard_traversal(tmp_path: Path):
    """Verify FS-006 probe detects and prevents traversal escaping scratch directory."""
    res = FilesystemGuard.probe_traversal_escape(tmp_path)
    assert res.vector_id == "FS-006"
    assert res.blocked is True
    assert res.enforcement_mechanism == EnforcementMechanism.APPLICATION_ENFORCED


def test_filesystem_guard_alternate_data_stream(tmp_path: Path):
    """Verify FS-012 probe audits Alternate Data Stream creation."""
    res = FilesystemGuard.probe_alternate_data_stream(tmp_path)
    assert res.vector_id == "FS-012"
    assert res.blocked is True


def test_filesystem_guard_ssh_keys():
    """Verify FS-014 probe audits host SSH private key directory."""
    res = FilesystemGuard.probe_ssh_key_read()
    assert res.vector_id == "FS-014"
    assert isinstance(res.blocked, bool)


def test_credential_guard_windows_credential_manager():
    """Verify CRED-001 probe executes CredEnumerateW query safely."""
    res = CredentialGuard.probe_windows_credential_manager()
    assert res.vector_id == "CRED-001"
    assert res.family == VectorFamily.CREDENTIAL


def test_credential_guard_dpapi_keys():
    """Verify CRED-002 probe checks DPAPI master key directory access."""
    res = CredentialGuard.probe_dpapi_user_keys()
    assert res.vector_id == "CRED-002"
    assert isinstance(res.blocked, bool)


def test_credential_guard_environment_secrets():
    """Verify CRED-010 probe detects leaked secrets in environment."""
    # Test clean environment
    clean_env = {"PATH": "C:\\Windows\\System32", "TEMP": "C:\\Temp"}
    res_clean = CredentialGuard.probe_environment_secrets(clean_env)
    assert res_clean.blocked is True
    assert res_clean.severity == SeverityLevel.S0_EXPECTED_DENIAL

    # Test dirty environment with leaked API key
    dirty_env = {"OPENAI_API_KEY": "sk-12345", "TEMP": "C:\\Temp"}
    res_dirty = CredentialGuard.probe_environment_secrets(dirty_env)
    assert res_dirty.blocked is False
    assert res_dirty.severity == SeverityLevel.S5_CREDENTIAL_EXPOSURE


def test_ipc_guard_probes():
    """Verify IPC guard probes for named pipes, shared memory, and clipboard."""
    p_pipe = IpcGuard.probe_privileged_named_pipe()
    assert p_pipe.vector_id == "IPC-001"
    assert p_pipe.blocked is True

    p_mem = IpcGuard.probe_shared_memory_mapping()
    assert p_mem.vector_id == "IPC-003"
    assert p_mem.blocked is True

    p_clip = IpcGuard.probe_clipboard_access()
    assert p_clip.vector_id == "IPC-008"


def test_network_guard_truthful_attribution():
    """Verify network probes execute and truthfully classify enforcement without false OS_ENFORCED claims."""
    res_raw = NetworkGuard.probe_raw_socket()
    assert res_raw.vector_id == "NET-005"
    assert res_raw.enforcement_mechanism == EnforcementMechanism.OS_ENFORCED

    # Outbound TCP probe must never claim OS_ENFORCED unless blocked by OS firewall
    res_tcp = NetworkGuard.probe_outbound_tcp("1.1.1.1", 443, timeout=0.1)
    if res_tcp.blocked and res_tcp.win32_error_code == 10013:
        assert res_tcp.enforcement_mechanism == EnforcementMechanism.OS_ENFORCED
    else:
        assert res_tcp.enforcement_mechanism == EnforcementMechanism.NOT_CONFIGURED


def test_code_guard_dropped_scripts(tmp_path: Path):
    """Verify CodeGuard attempts dropped script execution and audits policy enforcement."""
    res_bat = CodeGuard.probe_dropped_script(tmp_path, ".bat", "CODE-001", "BatchProbe")
    assert res_bat.vector_id == "CODE-001"
    assert not (tmp_path / "probe_payload.bat").exists()

    status = CodeGuard.detect_system_code_integrity()
    assert "applocker_configured" in status
    assert "wdac_configured" in status


def test_persistence_guard_probes():
    """Verify persistence guard probes for startup folder, registry, and service creation."""
    res_start = PersistenceGuard.probe_startup_folder_write()
    assert res_start.vector_id == "PERS-001"

    res_reg = PersistenceGuard.probe_registry_run_key_write()
    assert res_reg.vector_id == "PERS-002"
    assert res_reg.blocked is True

    res_svc = PersistenceGuard.probe_service_creation()
    assert res_svc.vector_id == "PERS-004"
    assert res_svc.blocked is True


def test_device_guard_probes():
    """Verify device guard probes for physical drive, volume, and device namespace access."""
    res_drive = DeviceGuard.probe_raw_physical_drive(0)
    assert res_drive.vector_id == "DEV-001"
    assert res_drive.blocked is True

    res_vol = DeviceGuard.probe_raw_volume("C:")
    assert res_vol.vector_id == "DEV-002"
    assert res_vol.blocked is True

    res_dev = DeviceGuard.probe_device_namespace()
    assert res_dev.vector_id == "DEV-003"
    assert res_dev.blocked is True


def test_broker_guard_capability_authorization(tmp_path: Path):
    """Verify CapabilityBroker defends against ungranted capabilities, command injection, and traversal."""
    broker = CapabilityBroker(allowed_capabilities={"fs.read"}, sandbox_root=tmp_path)

    # 1. Unauthorized capability
    ok, err = broker.execute_request("os.exec", {})
    assert ok is False
    assert "UNAUTHORIZED_CAPABILITY" in err

    # 2. Command injection
    ok, err = broker.execute_request("fs.read", {"cmd": "dir & whoami"})
    assert ok is False
    assert "COMMAND_INJECTION_DETECTED" in err

    # 3. Path traversal
    ok, err = broker.execute_request("fs.read", {"filepath": str(tmp_path / ".." / "cmd.exe")})
    assert ok is False
    assert "PATH_CONFINEMENT_VIOLATION" in err

    # Run guard probe suite
    probes = BrokerGuard.run_all_probes(tmp_path)
    assert len(probes) == 3
    assert all(p.blocked for p in probes)


def test_resource_guard_limits():
    """Verify resource protection probes test memory bounds, process table quotas, and handle limits."""
    res_mem = ResourceGuard.probe_memory_exhaustion(limit_bytes=1024 * 1024)
    assert res_mem.vector_id == "RES-001"
    assert res_mem.blocked is True

    res_proc = ResourceGuard.probe_process_flood(max_allowed=2)
    assert res_proc.vector_id == "RES-002"
    assert res_proc.blocked is True

    res_hnd = ResourceGuard.probe_handle_flood(max_handles=100)
    assert res_hnd.vector_id == "RES-003"
    assert res_hnd.blocked is True


def test_restricted_launcher_environment_sanitization():
    """Verify RestrictedProcessLauncher strips secret variables while retaining safe system vars."""
    dirty_env = {
        "SYSTEMROOT": "C:\\Windows",
        "PATH": "C:\\Windows\\System32",
        "OPENAI_API_KEY": "sk-secret",
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "USER_TOKEN": "token-123",
        "MY_SECRET_PARAM": "shhh",
        "SAFE_APP_VAR": "value",
    }
    clean = RestrictedProcessLauncher.sanitize_environment(dirty_env)
    assert "SYSTEMROOT" in clean
    assert "PATH" in clean
    assert "OPENAI_API_KEY" not in clean
    assert "AWS_SECRET_ACCESS_KEY" not in clean
    assert "USER_TOKEN" not in clean
    assert "MY_SECRET_PARAM" not in clean
    assert clean.get("SAFE_APP_VAR") == "value"


def test_clean_room_worker_invocation():
    """Verify clean-room worker process executes under launcher and outputs JSON snapshot."""
    res = RestrictedProcessLauncher.launch_worker(
        [sys.executable, "-m", "jarvis_learning.sandbox.clean_room_worker", "--mode", "snapshot"],
        timeout=10.0,
    )
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert "integrity_level" in data
    assert "username" in data


def test_hostile_attack_matrix_execution(tmp_path: Path):
    """Verify HostileAttackMatrix runs all 16 vector families and records forensic diffs."""
    matrix = HostileAttackMatrix(tmp_path)
    probes, diffs = matrix.run_all_vectors()

    assert len(probes) >= 16
    assert len(diffs) >= 10
    families_represented = {p.family for p in probes}
    assert VectorFamily.FILESYSTEM in families_represented
    assert VectorFamily.TOKEN in families_represented
    assert VectorFamily.JOB in families_represented
    assert VectorFamily.CREDENTIAL in families_represented
    assert VectorFamily.IPC in families_represented
    assert VectorFamily.NETWORK in families_represented
    assert VectorFamily.NEGATIVE_CONTROL in families_represented

    # Verify negative control succeeded in approved scratch dir
    neg = next(p for p in probes if p.family == VectorFamily.NEGATIVE_CONTROL)
    assert neg.blocked is True  # blocked=True means test check succeeded as expected


def test_sandbox_reference_oracle():
    """Verify independent reference oracle evaluates canonical expectations and assigns verdicts."""
    probe_pass = HostileProbeResult(
        vector_id="FS-001",
        family=VectorFamily.FILESYSTEM,
        name="Test",
        target="C:\\Windows",
        attempt_details="Test",
        win32_error_code=5,
        win32_error_name="ERROR_ACCESS_DENIED",
        enforcement_mechanism=EnforcementMechanism.OS_ENFORCED,
        severity=SeverityLevel.S0_EXPECTED_DENIAL,
        blocked=True,
        duration_ms=1.0,
    )
    verdict, _ = SandboxReferenceOracle.evaluate_probe(probe_pass)
    assert verdict == BoundaryVerdict.PASS

    # A failed vector where an escape happened
    probe_fail = HostileProbeResult(
        vector_id="FS-001",
        family=VectorFamily.FILESYSTEM,
        name="Test",
        target="C:\\Windows",
        attempt_details="Test",
        win32_error_code=None,
        win32_error_name=None,
        enforcement_mechanism=EnforcementMechanism.OS_ENFORCED,
        severity=SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS,
        blocked=False,
        duration_ms=1.0,
    )
    verdict_fail, _ = SandboxReferenceOracle.evaluate_probe(probe_fail)
    assert verdict_fail == BoundaryVerdict.FAIL


def test_event_hash_chain():
    """Verify EventHashChain appends events incrementally and produces deterministic hashes."""
    chain = EventHashChain()
    assert chain.current_hash == "0" * 64
    assert chain.event_count == 0

    h1 = chain.add_event({"event": 1, "data": "alpha"})
    assert len(h1) == 64
    assert chain.event_count == 1

    h2 = chain.add_event({"event": 2, "data": "beta"})
    assert len(h2) == 64
    assert h2 != h1
    assert chain.event_count == 2


def test_evidence_sealer_and_verification():
    """Verify SandboxEvidenceSealer computes SHA-256 digest, HMAC attestation, and verifies authenticity."""
    payload = {
        "track": "TRACK_2.3",
        "title": "Sandbox Validation",
        "timestamp": 1726700000.0,
        "results": [1, 2, 3],
    }
    digest = SandboxEvidenceSealer.compute_sha256_digest(payload)
    assert len(digest) == 64

    attestation = SandboxEvidenceSealer.sign_attestation(digest)
    payload["attestation"] = attestation

    # Verification must succeed on unmodified payload
    assert SandboxEvidenceSealer.verify_seal(payload) is True

    # Tampering with payload must cause verification failure
    tampered = dict(payload)
    tampered["results"] = [1, 2, 999]
    assert SandboxEvidenceSealer.verify_seal(tampered) is False


def test_qualification_gate_evaluation():
    """Verify 20-dimension SandboxQualificationGate enforces severity limits and computes evidence level."""
    probes = [
        HostileProbeResult(
            "TOK-001",
            VectorFamily.TOKEN,
            "T",
            "T",
            "T",
            None,
            None,
            EnforcementMechanism.OS_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "INT-001",
            VectorFamily.INTEGRITY,
            "I",
            "I",
            "I",
            None,
            None,
            EnforcementMechanism.OS_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "PROC-001",
            VectorFamily.PROCESS,
            "P",
            "P",
            "P",
            None,
            None,
            EnforcementMechanism.OS_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "JOB-001",
            VectorFamily.JOB,
            "J",
            "J",
            "J",
            None,
            None,
            EnforcementMechanism.OS_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "FS-001",
            VectorFamily.FILESYSTEM,
            "F1",
            "F1",
            "F1",
            5,
            "ACCESS_DENIED",
            EnforcementMechanism.OS_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "FS-002",
            VectorFamily.FILESYSTEM,
            "F2",
            "F2",
            "F2",
            5,
            "ACCESS_DENIED",
            EnforcementMechanism.OS_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "FS-006",
            VectorFamily.FILESYSTEM,
            "F6",
            "F6",
            "F6",
            None,
            None,
            EnforcementMechanism.APPLICATION_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "CRED-001",
            VectorFamily.CREDENTIAL,
            "C1",
            "C1",
            "C1",
            None,
            None,
            EnforcementMechanism.OS_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "CRED-010",
            VectorFamily.CREDENTIAL,
            "C10",
            "C10",
            "C10",
            None,
            None,
            EnforcementMechanism.APPLICATION_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "IPC-001",
            VectorFamily.IPC,
            "IP1",
            "IP1",
            "IP1",
            None,
            None,
            EnforcementMechanism.OS_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "NET-001",
            VectorFamily.NETWORK,
            "N1",
            "N1",
            "N1",
            None,
            None,
            EnforcementMechanism.NOT_CONFIGURED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            False,
            1.0,
        ),
        HostileProbeResult(
            "CODE-001",
            VectorFamily.CODE,
            "CD1",
            "CD1",
            "CD1",
            None,
            None,
            EnforcementMechanism.APPLICATION_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "PERS-001",
            VectorFamily.PERSISTENCE,
            "PR1",
            "PR1",
            "PR1",
            None,
            None,
            EnforcementMechanism.OS_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "BROKER-001",
            VectorFamily.BROKER,
            "B1",
            "B1",
            "B1",
            None,
            None,
            EnforcementMechanism.APPLICATION_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
        HostileProbeResult(
            "RES-001",
            VectorFamily.RESOURCE,
            "R1",
            "R1",
            "R1",
            None,
            None,
            EnforcementMechanism.APPLICATION_ENFORCED,
            SeverityLevel.S0_EXPECTED_DENIAL,
            True,
            1.0,
        ),
    ]

    gate = SandboxQualificationEvaluator.evaluate(probes, is_clean_room=True)
    assert gate.passed_dimensions >= 18
    assert gate.is_qualified is True
    level = gate.determine_effective_level(is_windows_native=True)
    assert level == EvidenceLevel.L4_REAL_WINDOWS_API


def test_sandbox_validation_harness_full(tmp_path: Path):
    """Verify master SandboxValidationHarness orchestrates a complete, cryptographically sealed run."""
    harness = SandboxValidationHarness(scratch_dir=tmp_path)
    manifest = harness.run_validation()

    assert manifest["track"] == "TRACK_2.3"
    assert manifest["seal_verified"] is True
    assert "event_hash_chain_final" in manifest
    assert manifest["total_events_chained"] > 0
    assert manifest["oracle_evaluation"]["overall_verdict"] == "PASS"
    assert manifest["governance_status"]["live_training_enabled"] is False
    assert manifest["governance_status"]["operator_approval_required"] is True
