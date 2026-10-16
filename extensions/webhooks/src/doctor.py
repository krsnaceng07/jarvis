"""Doctor diagnostics for Webhooks plugin.

OpenClaw parity: mirrors doctor checks for configured routes,
secrets validity, and path collisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import resolve_webhooks_plugin_config


@dataclass(frozen=True, slots=True)
class DoctorFinding:
    """Diagnostic check result."""

    check_id: str
    status: str  # "ok", "warn", "error"
    message: str
    remediation: str | None = None


def run_webhooks_doctor_checks(
    raw_config: dict[str, Any] | None = None,
) -> list[DoctorFinding]:
    """Run all Webhooks diagnostics."""
    findings: list[DoctorFinding] = []

    try:
        routes = resolve_webhooks_plugin_config(raw_config)
        if not routes:
            findings.append(
                DoctorFinding(
                    check_id="webhooks/routes-configured",
                    status="ok",
                    message="No webhook routes configured (plugin idle)",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    check_id="webhooks/routes-configured",
                    status="ok",
                    message=f"Configured {len(routes)} active webhook route(s)",
                )
            )

            # Check paths
            paths = [r.path for r in routes]
            findings.append(
                DoctorFinding(
                    check_id="webhooks/paths-validity",
                    status="ok",
                    message=f"All route paths are valid and unique: {paths}",
                )
            )

    except Exception as exc:
        findings.append(
            DoctorFinding(
                check_id="webhooks/routes-configured",
                status="error",
                message=f"Invalid webhook route configuration: {exc}",
                remediation="Check webhooks.routes configuration for missing sessionKey, secret, or path collisions.",
            )
        )

    return findings
