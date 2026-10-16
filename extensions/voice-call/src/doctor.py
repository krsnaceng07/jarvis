"""Doctor diagnostics and automated repair for Voice Call configuration."""

from __future__ import annotations

from typing import Any

from jarvis_sdk import Ok, Result

from .config import VoiceCallConfig, resolve_voice_call_config
from .config_compat import migrate_legacy_voice_call_config
from .phone_utils import is_valid_e164_phone_number, normalize_e164_phone_number
from .setup import get_voice_call_setup_status


async def run_voice_call_doctor(
    config: dict[str, Any] | None = None,
    fix: bool = False,
) -> Result[dict[str, Any], str]:
    """Execute diagnostic checks on Voice Call config, repairing legacy shapes if fix=True."""
    raw = config or {}
    migrated = migrate_legacy_voice_call_config(raw)
    repairs: list[str] = []

    if migrated != raw:
        repairs.append("Migrated legacy configuration keys to canonical structure")

    # Check fromNumber normalization
    raw_from = migrated.get("fromNumber") or migrated.get("from_number")
    if raw_from and not is_valid_e164_phone_number(str(raw_from)):
        try:
            norm = normalize_e164_phone_number(str(raw_from))
            if fix:
                migrated["fromNumber"] = norm
                repairs.append(f"Normalized fromNumber to E.164: {norm}")
            else:
                repairs.append(f"fromNumber '{raw_from}' should be normalized to '{norm}'")
        except ValueError:
            repairs.append(f"fromNumber '{raw_from}' is not a valid E.164 phone number")

    # Check toNumber normalization
    raw_to = migrated.get("toNumber") or migrated.get("to_number")
    if raw_to and not is_valid_e164_phone_number(str(raw_to)):
        try:
            norm = normalize_e164_phone_number(str(raw_to))
            if fix:
                migrated["toNumber"] = norm
                repairs.append(f"Normalized toNumber to E.164: {norm}")
            else:
                repairs.append(f"toNumber '{raw_to}' should be normalized to '{norm}'")
        except ValueError:
            repairs.append(f"toNumber '{raw_to}' is not a valid E.164 phone number")

    cfg_res = resolve_voice_call_config(migrated if fix else raw)
    cfg = cfg_res.unwrap() if cfg_res.is_ok else VoiceCallConfig()

    setup_status = get_voice_call_setup_status(cfg)

    return Ok(
        {
            "ok": setup_status.ok,
            "repairs": repairs,
            "fixed": fix and len(repairs) > 0,
            "config": migrated if fix else raw,
            "checks": [{"id": c.id, "ok": c.ok, "message": c.message} for c in setup_status.checks],
        }
    )
