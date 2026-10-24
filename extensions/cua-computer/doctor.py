"""extensions/cua-computer/doctor.py

Doctor diagnostics probe for CUA Computer extension.
Checks:
- Interactive desktop accessibility (OpenInputDesktop / SetThreadDesktop)
- Windows hook prerequisites and input synthesis support
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from src.doctor import DoctorFinding, Severity


def diagnose_computer_input(state_dir: Path, _config: dict[str, Any]) -> list[DoctorFinding]:
    """Diagnose Windows native input synthesis and low-level hook readiness."""
    findings: list[DoctorFinding] = []

    if sys.platform != "win32":
        findings.append(
            DoctorFinding(
                plugin_id="cua-computer",
                label="Non-Windows Host for Native Input",
                path=state_dir,
                count=1,
                severity=Severity.OK,
                message="CUA computer use is running on non-Windows; will use browser/mock fallback.",
            )
        )
        return findings

    try:
        from .src.win.backend import ensure_desktop_access

        has_access = ensure_desktop_access()
        if not has_access:
            findings.append(
                DoctorFinding(
                    plugin_id="cua-computer",
                    label="Desktop Station Access Denied",
                    path=state_dir,
                    count=1,
                    severity=Severity.WARNING,
                    message="Current thread could not attach to active input desktop; SendInput may fail if running as background service.",
                )
            )
    except Exception as e:
        findings.append(
            DoctorFinding(
                plugin_id="cua-computer",
                label="CUA Backend Init Error",
                path=state_dir,
                count=1,
                severity=Severity.ERROR,
                message=f"Failed initializing WindowsInputBackend: {e}",
            )
        )

    return findings


__all__ = ["diagnose_computer_input"]
