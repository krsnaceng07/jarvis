"""Diagnostics and automated configuration repair for llama.cpp provider."""

from __future__ import annotations

from typing import Any

from jarvis_sdk import Ok, Result


async def run_llama_cpp_doctor(
    config: dict[str, Any] | None,
    *,
    fix: bool = False,
) -> Result[dict[str, Any], str]:
    """Inspect and repair llama.cpp provider configuration."""
    raw = dict(config or {})
    repairs: list[dict[str, str]] = []
    fixed = dict(raw)

    # 1. Ownership coherence: if localService is defined, ensure no conflicting external auth profile
    if "localService" in raw and "authProfile" in raw:
        repairs.append(
            {
                "id": "clean-managed-auth-profile",
                "message": "Removed conflicting external 'authProfile' on managed local server configuration",
            }
        )
        if fix:
            fixed.pop("authProfile", None)

    # 2. Check base_url format
    base_url = raw.get("baseUrl") or raw.get("base_url")
    if base_url and "@" in str(base_url):
        repairs.append(
            {
                "id": "sanitize-base-url-credentials",
                "message": "Detected embedded user credentials in baseUrl; stripped credentials from host authority",
            }
        )
        if fix:
            import urllib.parse

            p = urllib.parse.urlparse(str(base_url))
            netloc = p.hostname or "127.0.0.1"
            if p.port:
                netloc = f"{netloc}:{p.port}"
            fixed["baseUrl"] = urllib.parse.urlunparse(
                (p.scheme or "http", netloc, p.path, "", "", "")
            )

    return Ok(
        {
            "ok": True,
            "repairs": repairs,
            "fixed": fix and len(repairs) > 0,
            "config": fixed if fix else raw,
        }
    )
