"""jarvis.config.zod_schema — root OpenClaw config Zod schema facade.

OpenClaw parity: mirrors ``openclaw-main/src/config/zod-schema.ts``.

Focused minimal port: exposes the OpenClaw root config schema as a
Python facade. The full ``OpenClawSchemaShape`` is delegated to the
caller-provided ``zod_schema_root_shape`` module until that lands.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


#: Top-level OpenClaw config schema (zod facade).
#: Mirrors :const:`OpenClawSchema`
#: (``shared/config/zod-schema.ts`).
OpenClawSchema: Any = None  # z.strictObject(OpenClawSchemaShape).superRefine(...)


def install_zod_default_locale() -> None:
    """Register the en() locale on the zod config so issues render with text.

    Mirrors :func:`installZodDefaultLocale`
    (``shared/config/zod-schema.ts`).
    """
    # The actual zod call lands with the zod validator port. The function
    # exists so callers can opt into the same locale registration step
    # the upstream source uses.
    return None


def validate_openclaw_schema(value: Any, *, normalize_agent_id_fn: Optional[Callable] = None) -> Optional[list]:
    """Validate a parsed config dict against the OpenClaw root schema.

    Returns a list of issue dicts on failure, or ``None`` when the
    caller has not wired a real schema validator yet.
    """
    if OpenClawSchema is None:
        return None
    if not normalize_agent_id_fn:
        return None
    issues: list = []
    agents = ((value or {}).get("agents") or {}).get("list") or []
    if agents:
        agent_ids = {a.get("id") for a in agents if isinstance(a, dict)}
        effective = {normalize_agent_id_fn(a.get("id") or "") for a in agents if isinstance(a, dict)}
        bindings = (value or {}).get("bindings")
        if isinstance(bindings, list):
            for idx, binding in enumerate(bindings):
                if not isinstance(binding, dict):
                    continue
                agent_id = binding.get("agentId")
                if isinstance(agent_id, str) and normalize_agent_id_fn(agent_id) not in effective:
                    issues.append({
                        "path": ["bindings", idx, "agentId"],
                        "message": f'Unknown agent id "{agent_id}" (not in agents.list).',
                    })
    return issues or None


__all__ = ["OpenClawSchema", "install_zod_default_locale", "validate_openclaw_schema"]
