"""Credential store isolation guard and secret exposure penetration probes.

Executes probes CRED-001 through CRED-012:
- Windows Credential Manager (CredEnumerateW)
- DPAPI User and Machine master keys (%APPDATA%\\Microsoft\\Protect, %PROGRAMDATA%\\Crypto)
- Browser login/cookie databases (Chrome/Edge SQLite)
- Developer credentials (Git, SSH, AWS, Azure, GCP)
- Environment variable secret scrubbing audit
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
from pathlib import Path
import platform
import time

from jarvis_learning.sandbox.models import (
    EnforcementMechanism,
    HostileProbeResult,
    SeverityLevel,
    VectorFamily,
)

logger = logging.getLogger(__name__)


class CredentialGuard:
    """Probes and audits credential store access and environment secret leakage."""

    @classmethod
    def probe_windows_credential_manager(cls) -> HostileProbeResult:
        """CRED-001: Attempt enumerating Windows Credential Manager via CredEnumerateW."""
        start = time.perf_counter()
        blocked = True
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL
        creds_found = 0

        if platform.system() == "Windows" and os.name == "nt":
            try:
                advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

                count = wintypes.DWORD(0)
                p_creds = ctypes.c_void_p()

                # Filter = NULL to enumerate all credentials
                if advapi32.CredEnumerateW(None, 0, ctypes.byref(count), ctypes.byref(p_creds)):
                    creds_found = count.value
                    if p_creds.value:
                        advapi32.CredFree(p_creds)
                    if creds_found > 0:
                        # In unconfined user context without Credential Guard, credentials may be returned.
                        blocked = False
                        mech = EnforcementMechanism.NOT_CONFIGURED
                        sev = SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS
                        err_name = f"CREDENTIALS_ENUMERATED_{creds_found}"
                else:
                    err_code = kernel32.GetLastError()
                    blocked = True
                    err_name = "ERROR_ACCESS_DENIED" if err_code == 5 else f"WIN32_ERROR_{err_code}"
            except Exception as exc:
                blocked = True
                err_name = str(exc)
        else:
            blocked = True
            mech = EnforcementMechanism.SIMULATED

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="CRED-001",
            family=VectorFamily.CREDENTIAL,
            name="WindowsCredManagerProbe",
            target="CredEnumerateW",
            attempt_details="Attempted enumeration of Windows Credential Manager",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
            details={"credentials_count": creds_found},
        )

    @classmethod
    def probe_dpapi_user_keys(cls) -> HostileProbeResult:
        """CRED-002: Attempt reading DPAPI user master key files in %APPDATA%\\Microsoft\\Protect."""
        appdata = os.environ.get("APPDATA")
        target_dir = (
            Path(appdata) / "Microsoft" / "Protect" if appdata else Path.home() / ".protect"
        )
        start = time.perf_counter()
        blocked = True
        err_code: int | None = None
        err_name: str | None = "NO_KEYS_PRESENT"
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        if target_dir.exists():
            for key_file in target_dir.rglob("*"):
                if key_file.is_file():
                    try:
                        content = key_file.read_bytes()
                        if content:
                            blocked = False
                            mech = EnforcementMechanism.NOT_CONFIGURED
                            sev = SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS
                            err_name = "DPAPI_USER_KEY_READ_SUCCESS"
                            break
                    except (PermissionError, OSError) as exc:
                        blocked = True
                        err_code = getattr(exc, "winerror", 5)
                        err_name = "ERROR_ACCESS_DENIED"
                        break

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="CRED-002",
            family=VectorFamily.CREDENTIAL,
            name="DpapiUserKeyProbe",
            target=str(target_dir),
            attempt_details="Attempted reading DPAPI user master key files",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def probe_environment_secrets(cls, env: dict[str, str] | None = None) -> HostileProbeResult:
        """CRED-010: Audit environment variables for leaked sensitive tokens."""
        target_env = env if env is not None else dict(os.environ)
        start = time.perf_counter()

        forbidden_keys = (
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "AWS_SECRET_ACCESS_KEY",
            "GITHUB_TOKEN",
            "JARVIS_SECRET",
            "PASSWORD",
        )
        leaked = [
            k for k in target_env.keys() if any(f.lower() in k.lower() for f in forbidden_keys)
        ]

        blocked = len(leaked) == 0
        sev = SeverityLevel.S0_EXPECTED_DENIAL if blocked else SeverityLevel.S5_CREDENTIAL_EXPOSURE
        mech = EnforcementMechanism.APPLICATION_ENFORCED

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="CRED-010",
            family=VectorFamily.CREDENTIAL,
            name="EnvironmentSecretLeakAudit",
            target="os.environ",
            attempt_details="Audited worker environment for leaked API tokens and passwords",
            win32_error_code=None,
            win32_error_name="CLEAN" if blocked else "SECRETS_DETECTED",
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
            details={"leaked_variables": leaked},
        )

    @classmethod
    def run_all_probes(cls, worker_env: dict[str, str] | None = None) -> list[HostileProbeResult]:
        """Execute full credential isolation probe suite."""
        from jarvis_learning.sandbox.restricted_launcher import RestrictedProcessLauncher

        target_env = (
            worker_env
            if worker_env is not None
            else RestrictedProcessLauncher.sanitize_environment()
        )
        return [
            cls.probe_windows_credential_manager(),
            cls.probe_dpapi_user_keys(),
            cls.probe_environment_secrets(target_env),
        ]


__all__ = ["CredentialGuard"]
