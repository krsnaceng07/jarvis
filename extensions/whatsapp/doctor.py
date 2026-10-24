"""WhatsApp doctor contract.

OpenClaw parity: Implements WhatsApp health checks, auth state diagnosis,
credential directory validation, and autonomous repair routines.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True, slots=True)
class WhatsAppDoctorStatus:
    healthy: bool
    detail: str = ""
    issues: list[str] = field(default_factory=list)
    repaired: list[str] = field(default_factory=list)


def collect_whatsapp_status_issues(
    account_id: str = "default",
    auth_dir: Optional[pathlib.Path] = None,
) -> List[Dict[str, Any]]:
    """Collect WhatsApp channel status issues matching OpenClaw parity."""
    resolved_auth_dir = auth_dir or (
        pathlib.Path.home() / ".jarvis" / "credentials" / "whatsapp" / account_id
    )
    creds_file = resolved_auth_dir / "creds.json"
    issues: List[Dict[str, Any]] = []

    if not creds_file.exists():
        issues.append({
            "channel": "whatsapp",
            "account_id": account_id,
            "kind": "auth",
            "message": "Not linked (no WhatsApp session creds.json found).",
            "fix": "Run: 'jarvis channels login whatsapp' or invoke the 'whatsapp_login' tool to pair via terminal QR code.",
            "auto_fixable": True,
        })
    else:
        try:
            with open(creds_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            registered = data.get("registered")
            is_linked = bool(registered is True or data.get("linked") is True)
            if not is_linked:
                issues.append({
                    "channel": "whatsapp",
                    "account_id": account_id,
                    "kind": "auth",
                    "message": "WhatsApp session exists but is marked unlinked/logged-out.",
                    "fix": "Run: 'jarvis channels login whatsapp' to refresh pairing.",
                    "auto_fixable": True,
                })
        except Exception as exc:
            issues.append({
                "channel": "whatsapp",
                "account_id": account_id,
                "kind": "auth",
                "message": f"WhatsApp credentials file is corrupted: {exc}",
                "fix": "Run: 'jarvis channels login whatsapp --force' to re-create clean credentials.",
                "auto_fixable": True,
            })

    return issues


def whatsapp_doctor_contract(
    auto_fix: bool = False,
    account_id: str = "default",
) -> WhatsAppDoctorStatus:
    """Run WhatsApp doctor diagnostics and optional auto-repair."""
    auth_dir = pathlib.Path.home() / ".jarvis" / "credentials" / "whatsapp" / account_id
    issues_found: list[str] = []
    repairs_applied: list[str] = []

    # 1. Directory presence
    if not auth_dir.exists():
        if auto_fix:
            auth_dir.mkdir(parents=True, exist_ok=True)
            repairs_applied.append(f"Created WhatsApp auth directory: {auth_dir}")
        else:
            issues_found.append(f"Missing WhatsApp credentials directory: {auth_dir}")

    # 2. Check credentials
    raw_issues = collect_whatsapp_status_issues(account_id=account_id, auth_dir=auth_dir)
    for issue in raw_issues:
        issues_found.append(issue["message"])

    # 3. Canonical config normalization
    cfg_path = pathlib.Path.home() / ".jarvis" / "config.json"
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            wa_cfg = cfg.get("channels", {}).get("whatsapp")
            if wa_cfg and not wa_cfg.get("authDir"):
                if auto_fix:
                    wa_cfg["authDir"] = str(auth_dir)
                    wa_cfg.setdefault("accountId", account_id)
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=2)
                    repairs_applied.append("Normalized WhatsApp authDir in config.json")
        except Exception:
            pass

    healthy = len(issues_found) == 0
    detail = (
        "WhatsApp channel credentials and directory are healthy and operational."
        if healthy
        else f"{len(issues_found)} issue(s) detected: {'; '.join(issues_found)}"
    )

    return WhatsAppDoctorStatus(
        healthy=healthy,
        detail=detail,
        issues=issues_found,
        repaired=repairs_applied,
    )


__all__ = [
    "WhatsAppDoctorStatus",
    "whatsapp_doctor_contract",
    "collect_whatsapp_status_issues",
]
