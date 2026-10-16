"""jarvis.plugins.plugin_manifest — plugin manifest parser and validator.

OpenClaw parity: mirrors
``openclaw-main/src/plugins/manifest.ts`` and
``openclaw-main/src/plugins/manifest-types.ts``.

Features:
- `JARVIS_PLUGIN_MANIFEST_FILENAMES`: `["jarvis.plugin.json", "openclaw.plugin.json"]`
- `PluginManifest` dataclass: `id`, `name`, `version`, `description`, `kind`, `format`, `contracts`, `config_schema`.
- `load_plugin_manifest()`: Reads, parses, and normalizes a plugin manifest from a plugin directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

PluginFormat = Literal["openclaw", "bundle", "jarvis"]
PluginKind = Literal[
    "channel",
    "provider",
    "media",
    "memory",
    "tools",
    "productivity",
    "voice",
    "infrastructure",
]

JARVIS_PLUGIN_MANIFEST_FILENAMES = ["jarvis.plugin.json", "openclaw.plugin.json"]


@dataclass
class PluginContracts:
    tools: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)


@dataclass
class PluginManifest:
    id: str
    name: str = ""
    version: str = "0.0.0"
    description: str = ""
    format: PluginFormat = "jarvis"
    kind: PluginKind = "tools"
    dir_path: str = ""
    contracts: PluginContracts = field(default_factory=PluginContracts)
    config_schema: dict[str, Any] = field(default_factory=dict)


def load_plugin_manifest(dir_path: str | Path) -> PluginManifest | None:
    """Load and normalize a plugin manifest from *dir_path*."""
    base_dir = Path(dir_path)
    if not base_dir.is_dir():
        return None

    manifest_file: Path | None = None
    for fname in JARVIS_PLUGIN_MANIFEST_FILENAMES:
        candidate = base_dir / fname
        if candidate.is_file():
            manifest_file = candidate
            break

    if not manifest_file:
        return None

    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    raw_id = data.get("id") or base_dir.name
    plugin_id = str(raw_id).strip().lower()

    name = str(data.get("name") or plugin_id)
    version = str(data.get("version") or "0.0.0")
    description = str(data.get("description") or "")
    fmt = data.get("format") or "jarvis"
    kind = data.get("kind") or "tools"

    # Normalize contracts
    raw_contracts = data.get("contracts") if isinstance(data.get("contracts"), dict) else {}
    tools = [str(x) for x in raw_contracts.get("tools", []) if str(x)]
    providers = [str(x) for x in raw_contracts.get("providers", []) if str(x)]
    channels = [str(x) for x in raw_contracts.get("channels", []) if str(x)]
    hooks = [str(x) for x in raw_contracts.get("hooks", []) if str(x)]

    contracts = PluginContracts(
        tools=tools,
        providers=providers,
        channels=channels,
        hooks=hooks,
    )

    config_schema = data.get("config_schema") if isinstance(data.get("config_schema"), dict) else {}

    return PluginManifest(
        id=plugin_id,
        name=name,
        version=version,
        description=description,
        format=fmt,
        kind=kind,
        dir_path=str(base_dir.resolve()),
        contracts=contracts,
        config_schema=config_schema,
    )


__all__ = [
    "JARVIS_PLUGIN_MANIFEST_FILENAMES",
    "PluginContracts",
    "PluginFormat",
    "PluginKind",
    "PluginManifest",
    "load_plugin_manifest",
]
