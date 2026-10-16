"""jarvis.plugins.codex_supervision — Codex supervision & session catalog management.

OpenClaw parity: mirrors
``openclaw-main/src/mcp/codex-supervision-tools-serve.ts`` and
``openclaw-main/extensions/codex/src/session-catalog-types.ts``.

Features:
- `LEGACY_SUPERVISOR_TOOL_NAMES`: `codex_endpoint_probe`, `codex_sessions_list`, `codex_session_read`, `codex_session_send`, `codex_session_interrupt`.
- `CodexSupervisionConfig`: Dataclass containing `enabled`, `allow_raw_transcripts`, `allow_write_controls`.
- `CodexSessionCatalogConfig`: Dataclass containing `enabled`.
- `resolve_codex_supervision_config()`: Resolves supervision config from plugin options.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LEGACY_SUPERVISOR_TOOL_NAMES: list[str] = [
    "codex_endpoint_probe",
    "codex_sessions_list",
    "codex_session_read",
    "codex_session_send",
    "codex_session_interrupt",
]


@dataclass
class CodexSupervisionConfig:
    enabled: bool = False
    allow_raw_transcripts: bool = False
    allow_write_controls: bool = False


@dataclass
class CodexSessionCatalogConfig:
    enabled: bool = True


def resolve_codex_supervision_config(
    plugin_cfg: dict[str, Any] | None,
) -> CodexSupervisionConfig:
    """Resolve Codex supervision config options."""
    if not plugin_cfg or not isinstance(plugin_cfg, dict):
        return CodexSupervisionConfig()

    sup = plugin_cfg.get("supervision")
    if not isinstance(sup, dict):
        return CodexSupervisionConfig()

    return CodexSupervisionConfig(
        enabled=bool(sup.get("enabled", False)),
        allow_raw_transcripts=bool(sup.get("allowRawTranscripts", False)),
        allow_write_controls=bool(sup.get("allowWriteControls", False)),
    )


def resolve_codex_session_catalog_config(
    plugin_cfg: dict[str, Any] | None,
) -> CodexSessionCatalogConfig:
    """Resolve Codex session catalog config options."""
    if not plugin_cfg or not isinstance(plugin_cfg, dict):
        return CodexSessionCatalogConfig()

    cat = plugin_cfg.get("sessionCatalog")
    if not isinstance(cat, dict):
        return CodexSessionCatalogConfig()

    return CodexSessionCatalogConfig(
        enabled=bool(cat.get("enabled", True)),
    )


__all__ = [
    "LEGACY_SUPERVISOR_TOOL_NAMES",
    "CodexSessionCatalogConfig",
    "CodexSupervisionConfig",
    "resolve_codex_session_catalog_config",
    "resolve_codex_supervision_config",
]
