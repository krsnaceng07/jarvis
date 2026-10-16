"""Doctor health inspection and automatic repair provider for Google Meet."""

from __future__ import annotations

import time
from typing import Any

from jarvis_sdk import Ok, Result

from .config import resolve_google_meet_config
from .config_compat import migrate_legacy_google_meet_config
from .oauth import refresh_google_meet_oauth_token


async def run_google_meet_doctor(
    *,
    config: dict[str, Any],
    fix: bool = False,
) -> Result[dict[str, Any], str]:
    """Inspect and optionally repair Google Meet configuration and dependencies."""
    checks: list[dict[str, Any]] = []
    fixes_applied: list[str] = []
    current_config = dict(config)

    # 1. Check legacy configuration
    migrated_cfg, changed = migrate_legacy_google_meet_config(current_config)
    if changed:
        if fix:
            current_config = migrated_cfg
            fixes_applied.append("Migrated legacy configuration keys to modern structure.")
            checks.append(
                {
                    "id": "config.legacy_keys",
                    "status": "fixed",
                    "message": "Migrated legacy configuration keys to modern format.",
                }
            )
        else:
            checks.append(
                {
                    "id": "config.legacy_keys",
                    "status": "warn",
                    "message": "Configuration contains deprecated legacy keys. Run with --fix to migrate.",
                }
            )
    else:
        checks.append(
            {
                "id": "config.legacy_keys",
                "status": "ok",
                "message": "Configuration format is canonical.",
            }
        )

    # 2. Resolve configuration
    cfg_res = resolve_google_meet_config(current_config)
    if not cfg_res.is_ok:
        checks.append(
            {
                "id": "config.resolution",
                "status": "error",
                "message": f"Failed to resolve configuration: {cfg_res.error}",
            }
        )
        return Ok(
            {
                "ok": False,
                "checks": checks,
                "fixesApplied": fixes_applied,
                "config": current_config,
            }
        )

    cfg = cfg_res.unwrap()
    checks.append(
        {
            "id": "config.resolution",
            "status": "ok",
            "message": f"Configuration resolved (default transport: {cfg.default_transport}, mode: {cfg.default_mode}).",
        }
    )

    # 3. Check OAuth tokens & expiry
    if cfg.oauth and cfg.oauth.client_id:
        if cfg.oauth.refresh_token:
            # Check if access token is expired
            now_ms = int(time.time() * 1000)
            is_expired = cfg.oauth.expires_at is not None and (
                cfg.oauth.expires_at * 1000 < now_ms
                if cfg.oauth.expires_at < 1e11
                else cfg.oauth.expires_at < now_ms
            )
            if is_expired:
                if fix and cfg.oauth.client_secret:
                    ref_res = await refresh_google_meet_oauth_token(
                        client_id=cfg.oauth.client_id,
                        client_secret=cfg.oauth.client_secret,
                        refresh_token=cfg.oauth.refresh_token,
                    )
                    if ref_res.is_ok:
                        tokens = ref_res.unwrap()
                        current_config.setdefault("oauth", {})["accessToken"] = tokens.access_token
                        current_config["oauth"]["expiresAt"] = tokens.expires_at
                        fixes_applied.append("Refreshed expired OAuth access token.")
                        checks.append(
                            {
                                "id": "oauth.tokens",
                                "status": "fixed",
                                "message": "OAuth access token was expired and has been refreshed.",
                            }
                        )
                    else:
                        checks.append(
                            {
                                "id": "oauth.tokens",
                                "status": "warn",
                                "message": f"OAuth access token is expired and refresh failed: {ref_res.error}",
                            }
                        )
                else:
                    checks.append(
                        {
                            "id": "oauth.tokens",
                            "status": "warn",
                            "message": "OAuth access token is expired. Run `jarvis googlemeet auth refresh` or use --fix.",
                        }
                    )
            else:
                checks.append(
                    {
                        "id": "oauth.tokens",
                        "status": "ok",
                        "message": "OAuth credentials configured with valid refresh token.",
                    }
                )
        else:
            checks.append(
                {
                    "id": "oauth.tokens",
                    "status": "warn",
                    "message": "OAuth client_id configured without refresh_token. Run `jarvis googlemeet auth login`.",
                }
            )
    else:
        checks.append(
            {
                "id": "oauth.tokens",
                "status": "info",
                "message": "OAuth not configured (required for Google Meet REST API & Calendar).",
            }
        )

    # 4. Check Transport & Audio
    if cfg.chrome and cfg.chrome.launch:
        checks.append(
            {
                "id": "chrome.launch",
                "status": "ok",
                "message": f"Chrome transport configured (audio backend: {cfg.chrome.audio_backend}, format: {cfg.chrome.audio_format}).",
            }
        )

    all_ok = all(c["status"] in ("ok", "fixed", "info") for c in checks)

    return Ok(
        {
            "ok": all_ok,
            "checks": checks,
            "fixesApplied": fixes_applied,
            "config": current_config,
        }
    )
