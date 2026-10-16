"""jarvis.plugins.plugin_bundle — compatible bundle detection and MCP tool name sanitization.

OpenClaw parity: mirrors
``openclaw-main/src/plugins/bundle-manifest.ts`` and
``openclaw-main/src/agents/agent-bundle-mcp-names.ts``.

Features:
- Bundle format detection order:
  1. Native plugin (`jarvis.plugin.json` / `openclaw.plugin.json`)
  2. Codex bundle (`.codex-plugin/plugin.json`)
  3. Cursor bundle (`.cursor-plugin/plugin.json`)
  4. Claude bundle (`.claude-plugin/plugin.json`)
  5. Agent Plugins bundle (`plugin.json`)
  6. Manifestless Claude layout (`skills/`, `commands/`, `.mcp.json`)
- MCP Tool Name Sanitization (`serverName__toolName`):
  - Max prefix: 30 chars
  - Max total: 64 chars
  - Separator: `__`
  - Sanitizes invalid characters and ensures letter start.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Set

PluginFormat = Literal["native", "bundle"]
BundleFormat = Literal["agent", "codex", "claude", "cursor", "unknown"]

TOOL_NAME_SEPARATOR: str = "__"
TOOL_NAME_MAX_PREFIX: int = 30
TOOL_NAME_MAX_TOTAL: int = 64
TOOL_NAME_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]")


@dataclass
class BundleDetectionResult:
    format_type: PluginFormat
    bundle_format: BundleFormat
    manifest_path: str = ""
    skills_roots: list[str] = field(default_factory=list)


def detect_plugin_bundle_format(dir_path: str | Path) -> BundleDetectionResult:
    """Detect plugin/bundle format following OpenClaw priority rules."""
    base = Path(dir_path)
    if not base.is_dir():
        return BundleDetectionResult(format_type="native", bundle_format="unknown")

    # 1. Native plugin check
    if (base / "jarvis.plugin.json").is_file() or (base / "openclaw.plugin.json").is_file():
        return BundleDetectionResult(
            format_type="native",
            bundle_format="unknown",
            manifest_path=str((base / "jarvis.plugin.json").resolve())
            if (base / "jarvis.plugin.json").is_file()
            else str((base / "openclaw.plugin.json").resolve()),
        )

    # 2. Codex bundle marker
    if (base / ".codex-plugin" / "plugin.json").is_file():
        return BundleDetectionResult(
            format_type="bundle",
            bundle_format="codex",
            manifest_path=str((base / ".codex-plugin" / "plugin.json").resolve()),
            skills_roots=["skills"] if (base / "skills").is_dir() else [],
        )

    # 3. Cursor bundle marker
    if (base / ".cursor-plugin" / "plugin.json").is_file():
        return BundleDetectionResult(
            format_type="bundle",
            bundle_format="cursor",
            manifest_path=str((base / ".cursor-plugin" / "plugin.json").resolve()),
            skills_roots=[p for p in [".cursor/commands", "skills"] if (base / p).is_dir()],
        )

    # 4. Claude bundle marker
    if (base / ".claude-plugin" / "plugin.json").is_file():
        return BundleDetectionResult(
            format_type="bundle",
            bundle_format="claude",
            manifest_path=str((base / ".claude-plugin" / "plugin.json").resolve()),
            skills_roots=[p for p in ["commands", "skills"] if (base / p).is_dir()],
        )

    # 5. Agent Plugins root plugin.json
    if (base / "plugin.json").is_file():
        return BundleDetectionResult(
            format_type="bundle",
            bundle_format="agent",
            manifest_path=str((base / "plugin.json").resolve()),
            skills_roots=["skills"] if (base / "skills").is_dir() else [],
        )

    # 6. Manifestless Claude layout
    if (base / "skills").is_dir() or (base / "commands").is_dir() or (base / ".mcp.json").is_file():
        return BundleDetectionResult(
            format_type="bundle",
            bundle_format="claude",
            skills_roots=[p for p in ["commands", "skills"] if (base / p).is_dir()],
        )

    return BundleDetectionResult(format_type="native", bundle_format="unknown")


def sanitize_tool_fragment(raw: str, fallback: str = "mcp", max_chars: int | None = None) -> str:
    """Sanitize a tool/server name fragment to be provider-safe."""
    cleaned = TOOL_NAME_SAFE_RE.sub("-", raw.strip())
    normalized = cleaned if cleaned else fallback
    provider_safe = normalized if re.match(r"^[A-Za-z]", normalized) else f"{fallback}-{normalized}"

    if max_chars and len(provider_safe) > max_chars:
        return provider_safe[:max_chars]
    return provider_safe


def sanitize_server_name(raw: str, used_names: Set[str]) -> str:
    """Sanitize an MCP server name and disambiguate collisions with numeric suffixes."""
    base = sanitize_tool_fragment(raw, fallback="mcp", max_chars=TOOL_NAME_MAX_PREFIX)
    candidate = base
    n = 2

    while candidate.lower() in used_names:
        suffix = f"-{n}"
        avail_len = max(1, TOOL_NAME_MAX_PREFIX - len(suffix))
        candidate = f"{base[:avail_len]}{suffix}"
        n += 1

    used_names.add(candidate.lower())
    return candidate


def build_safe_tool_name(server_name: str, tool_name: str, used_names: Set[str] | None = None) -> str:
    """Build model-facing provider-safe tool name: ``serverName__toolName``."""
    used = used_names if used_names is not None else set()
    safe_server = sanitize_server_name(server_name, set())
    safe_tool = sanitize_tool_fragment(tool_name, fallback="tool")

    full_name = f"{safe_server}{TOOL_NAME_SEPARATOR}{safe_tool}"
    if len(full_name) > TOOL_NAME_MAX_TOTAL:
        full_name = full_name[:TOOL_NAME_MAX_TOTAL]

    return full_name


__all__ = [
    "TOOL_NAME_MAX_PREFIX",
    "TOOL_NAME_MAX_TOTAL",
    "TOOL_NAME_SEPARATOR",
    "BundleDetectionResult",
    "BundleFormat",
    "PluginFormat",
    "build_safe_tool_name",
    "detect_plugin_bundle_format",
    "sanitize_server_name",
    "sanitize_tool_fragment",
]
