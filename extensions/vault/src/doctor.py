"""Doctor health checks and diagnostics for HashiCorp Vault plugin.

OpenClaw parity: mirrors doctor checks for VAULT_ADDR, auth credentials,
token files, and KV engine mount settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import resolve_vault_config


@dataclass(frozen=True, slots=True)
class DoctorFinding:
    """Diagnostic check result."""

    check_id: str
    status: str  # "ok", "warn", "error"
    message: str
    remediation: str | None = None


def run_vault_doctor_checks(
    raw_config: dict[str, Any] | None = None,
) -> list[DoctorFinding]:
    """Run all HashiCorp Vault diagnostics."""
    findings: list[DoctorFinding] = []
    cfg = resolve_vault_config(raw_config)

    # 1. Check VAULT_ADDR
    if not cfg.vault_addr:
        findings.append(
            DoctorFinding(
                check_id="vault/address-configured",
                status="error",
                message="VAULT_ADDR environment variable or vaultAddr config is not set",
                remediation="Export VAULT_ADDR=https://vault.example.com or configure 'vaultAddr'.",
            )
        )
    elif not (cfg.vault_addr.startswith("http://") or cfg.vault_addr.startswith("https://")):
        findings.append(
            DoctorFinding(
                check_id="vault/address-configured",
                status="error",
                message=f"VAULT_ADDR '{cfg.vault_addr}' must start with http:// or https://",
                remediation="Ensure VAULT_ADDR contains the complete URL with scheme.",
            )
        )
    else:
        findings.append(
            DoctorFinding(
                check_id="vault/address-configured",
                status="ok",
                message=f"Vault server address is configured ({cfg.vault_addr})",
            )
        )

    # 2. Check Auth Configuration
    method = cfg.auth_method
    if method == "token":
        if cfg.token:
            findings.append(
                DoctorFinding(
                    check_id="vault/auth-credentials",
                    status="ok",
                    message="Vault client token is set (VAULT_TOKEN)",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    check_id="vault/auth-credentials",
                    status="error",
                    message="VAULT_TOKEN is missing or empty for auth method 'token'",
                    remediation="Export VAULT_TOKEN=<token> or switch to token_file/jwt/kubernetes auth.",
                )
            )
    elif method == "token_file":
        if not cfg.token_file:
            findings.append(
                DoctorFinding(
                    check_id="vault/auth-credentials",
                    status="error",
                    message="VAULT_TOKEN_FILE path is not configured for auth method 'token_file'",
                    remediation="Export VAULT_TOKEN_FILE=/path/to/token.",
                )
            )
        elif not Path(cfg.token_file).expanduser().exists():
            findings.append(
                DoctorFinding(
                    check_id="vault/auth-credentials",
                    status="error",
                    message=f"Vault token file not found at {cfg.token_file}",
                    remediation="Ensure Vault Agent or sink process has created the token file.",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    check_id="vault/auth-credentials",
                    status="ok",
                    message=f"Vault token file exists at {cfg.token_file}",
                )
            )
    elif method in ("jwt", "kubernetes"):
        if not cfg.auth_role:
            findings.append(
                DoctorFinding(
                    check_id="vault/auth-credentials",
                    status="error",
                    message=f"OPENCLAW_VAULT_AUTH_ROLE is required for auth method '{method}'",
                    remediation="Export OPENCLAW_VAULT_AUTH_ROLE=<role-name>.",
                )
            )
        jwt_f = cfg.get_effective_jwt_file()
        if not jwt_f or not Path(jwt_f).expanduser().exists():
            findings.append(
                DoctorFinding(
                    check_id="vault/auth-credentials",
                    status="error",
                    message=f"JWT/workload token file not found at {jwt_f}",
                    remediation="Ensure Kubernetes service account or workload identity token is projected.",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    check_id="vault/auth-credentials",
                    status="ok",
                    message=f"Workload identity file exists at {jwt_f} with role '{cfg.auth_role}'",
                )
            )

    # 3. Check KV Configuration
    findings.append(
        DoctorFinding(
            check_id="vault/kv-config",
            status="ok",
            message=f"KV engine configured: mount='{cfg.kv_mount}', version={cfg.kv_version}",
        )
    )

    return findings
