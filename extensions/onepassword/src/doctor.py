"""Doctor health checks and diagnostics for 1Password plugin.

OpenClaw parity: mirrors doctor checks for op executable availability,
service-account token readiness, permissions, and config integrity.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import OnepasswordConfig, parse_onepassword_config
from .op_cli import resolve_op_binary
from .token import check_token_permissions, get_token_file_path, verify_token_prerequisites


@dataclass(frozen=True, slots=True)
class DoctorFinding:
    """Single diagnostic finding."""

    check_id: str
    status: str  # "ok", "warn", "error"
    message: str
    remediation: str | None = None


def run_doctor_checks(
    raw_config: dict[str, Any] | None = None,
    state_dir: Path | None = None,
) -> list[DoctorFinding]:
    """Run all 1Password doctor diagnostics."""
    findings: list[DoctorFinding] = []

    # 1. Config Validation
    try:
        config = parse_onepassword_config(raw_config)
        findings.append(
            DoctorFinding(
                check_id="onepassword/config-validity",
                status="ok",
                message=f"Configuration is valid ({len(config.items)} registered item(s))",
            )
        )
    except Exception as exc:
        findings.append(
            DoctorFinding(
                check_id="onepassword/config-validity",
                status="error",
                message=f"Invalid 1Password configuration: {exc}",
                remediation="Correct items, slugs, or policy definitions in config.json.",
            )
        )
        config = OnepasswordConfig()

    # 2. op CLI Executable Check
    op_path, op_err = resolve_op_binary(config.op_bin)
    if op_path:
        findings.append(
            DoctorFinding(
                check_id="onepassword/op-executable",
                status="ok",
                message=f"1Password CLI binary found at {op_path}",
            )
        )
    else:
        findings.append(
            DoctorFinding(
                check_id="onepassword/op-executable",
                status="error",
                message=f"1Password CLI executable not found: {op_err}",
                remediation="Install 1Password CLI ('op') or configure 'opBin' path in plugin config.",
            )
        )

    # 3. Token File Check
    token_path = get_token_file_path(state_dir)
    token_ready, token_err = verify_token_prerequisites(state_dir)
    if token_ready:
        findings.append(
            DoctorFinding(
                check_id="onepassword/token-file",
                status="ok",
                message=f"Service-account token file found and non-empty at {token_path}",
            )
        )
        # Check permissions
        warnings = check_token_permissions(token_path)
        for w in warnings:
            findings.append(
                DoctorFinding(
                    check_id="onepassword/token-permissions",
                    status="warn",
                    message=w,
                    remediation="Set token file permissions to 600 (read/write only by owner).",
                )
            )
    else:
        findings.append(
            DoctorFinding(
                check_id="onepassword/token-file",
                status="error",
                message=f"Service-account token not ready: {token_err}",
                remediation=(
                    f"Create {token_path} containing your 1Password service account token: "
                    f"mkdir -p {token_path.parent} && chmod 700 {token_path.parent} && "
                    f"printf '%s' \"$OP_SERVICE_ACCOUNT_TOKEN\" > {token_path} && chmod 600 {token_path}"
                ),
            )
        )

    return findings
