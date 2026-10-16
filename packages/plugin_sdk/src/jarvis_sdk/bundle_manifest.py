"""Bundle manifest detection and loading.

Exact Python port of OpenClaw's ``src/plugins/bundle-manifest.ts``.

Bundles are content packs (Agent Plugins, Codex, Claude, Cursor format)
that JARVIS maps into native features (skills, hooks, MCP tools) without
requiring the author to rewrite the plugin as a native JARVIS extension.

Detection precedence (mirrors OpenClaw ``detectBundleManifestFormat``):
  1. ``.codex-plugin/plugin.json``     → format ``codex``
  2. ``.cursor-plugin/plugin.json``    → format ``cursor``
  3. ``.claude-plugin/plugin.json``    → format ``claude``
  4. ``openclaw.plugin.json`` present  → ``None`` (native wins)
  5. ``plugin.json`` with Agent schema → format ``agent``
  6. Any native entry candidate        → ``None``
  7. Manifestless Claude markers       → format ``claude``
  8. Otherwise                         → ``None``

Supported capabilities per format:

  +-----------+---------+-------+-------+--------+-----+------+---------+------+
  | cap       | agent   | codex | claude| cursor | sup |      |         |      |
  +-----------+---------+-------+-------+--------+-----+      |         |      |
  | skills    |  yes    | yes   | yes   | yes    | all |      |         |      |
  | mcpServers|  yes    | yes   | yes   | yes    | all |      |         |      |
  | settings  |  no     | no    | yes   | no     |clau |      |         |      |
  | commands  |  no     | no    | yes   | yes    |cl/cu|      |         |      |
  | outputSt. |  no     | no    | yes   | yes    |cl/cu|      |         |      |
  | lspServers|  no     | no    | yes   | yes    |cl/cu|      |         |      |
  | agents    |  no     | no    | yes   | no     |clau |      |         |      |
  | hooks     |  no     | yes   | yes   | no     |co/cl|      |         |      |
  | rules     |  no     | no    | no    | yes    | det |      |         |      |
  | apps      |  no     | yes   | no    | no     | det |      |         |      |
  +-----------+---------+-------+-------+--------+-----+------+---------+------+

``sup`` = "fully supported and wired".  ``det`` = "detected only, not wired".
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

_log = logging.getLogger("jarvis_sdk.bundle_manifest")

# ── Format literals ───────────────────────────────────────────────────────────

PluginFormat = Literal["openclaw", "bundle"]
PluginBundleFormat = Literal["agent", "codex", "claude", "cursor"]

# ── Marker paths (mirrors OpenClaw constants) ─────────────────────────────────

CODEX_BUNDLE_MANIFEST_RELATIVE_PATH = ".codex-plugin/plugin.json"
CURSOR_BUNDLE_MANIFEST_RELATIVE_PATH = ".cursor-plugin/plugin.json"
CLAUDE_BUNDLE_MANIFEST_RELATIVE_PATH = ".claude-plugin/plugin.json"
AGENT_BUNDLE_MANIFEST_RELATIVE_PATH = "plugin.json"

NATIVE_MANIFEST_FILENAME = "openclaw.plugin.json"
# Default native entry candidates (mirrors OpenClaw's DEFAULT_PLUGIN_ENTRY_CANDIDATES)
_NATIVE_ENTRY_CANDIDATES = (
    "openclaw.plugin.json",
    "jarvis.plugin.json",
    "package.json",
)

_AGENT_BUNDLE_MANIFEST_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
_AGENT_BUNDLE_EXTENSION_NAMESPACE = "ai.openclaw"
_MAX_AGENT_BUNDLE_MANIFEST_BYTES = 256 * 1024

# Manifestless Claude layout markers (at least one must exist)
_MANIFESTLESS_CLAUDE_MARKERS = (
    "skills",
    "commands",
    "agents",
    "hooks/hooks.json",
    ".mcp.json",
    ".lsp.json",
    "settings.json",
)

# ── Result types ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BundleManifest:
    """Normalized bundle manifest consumed by the loader.

    Mirrors the internal ``BundlePluginManifest`` type in OpenClaw's
    ``bundle-manifest.ts``.
    """

    id: str
    bundle_format: PluginBundleFormat
    name: str | None = None
    description: str | None = None
    version: str | None = None
    #: Relative paths to skill root directories inside ``root_dir``.
    skills: tuple[str, ...] = field(default_factory=tuple)
    #: Relative paths to hook roots (Codex/Claude HOOK.md layout only).
    hooks: tuple[str, ...] = field(default_factory=tuple)
    #: Relative paths to settings files (Claude only).
    settings_files: tuple[str, ...] = field(default_factory=tuple)
    #: Detected capability names (see module docstring).
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    #: OpenClaw-compatible activation value if declared.
    activation: str | None = None


# ── Slugification (mirrors OpenClaw ``slugifyPluginId``) ──────────────────────


def _slugify_plugin_id(raw: str | None, root_dir: Path) -> str:
    fallback = root_dir.name
    source = (raw or "").strip().lower() or fallback.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", source)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "bundle-plugin"


# ── Path helpers ──────────────────────────────────────────────────────────────


def _exists(root_dir: Path, relative: str) -> bool:
    return (root_dir / relative).exists()


def _is_dir(root_dir: Path, relative: str) -> bool:
    return (root_dir / relative).is_dir()


def _normalize_path_list(value: object) -> list[str]:
    """Normalize a string-or-list manifest field to a unique list of paths."""
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, list):
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                v = item.strip()
                if v and v not in seen:
                    seen.add(v)
                    result.append(v)
        return result
    return []


def _merge_path_lists(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        for entry in group:
            if entry not in seen:
                seen.add(entry)
                result.append(entry)
    return result


def _has_inline_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    return value is True


# ── Capability detection ──────────────────────────────────────────────────────


def is_bundle_capability_supported(bundle_format: PluginBundleFormat, capability: str) -> bool:
    """Return whether a capability is fully wired for ``bundle_format``.

    Mirrors OpenClaw's ``isBundleCapabilitySupported`` in
    ``bundle-capability-support.ts``.
    """
    if capability in ("skills", "mcpServers", "settings"):
        return True
    if capability in ("commands", "outputStyles", "lspServers"):
        return bundle_format in ("claude", "cursor")
    if capability == "agents":
        return bundle_format == "claude"
    if capability == "hooks":
        return bundle_format in ("codex", "claude")
    return False


# ── Per-format path resolution (mirrors bundle-manifest.ts) ──────────────────

# --- Codex ---


def _codex_skill_dirs(raw: dict, root_dir: Path) -> list[str]:
    declared = _normalize_path_list(raw.get("skills"))
    if declared:
        return declared
    return ["skills"] if _is_dir(root_dir, "skills") else []


def _codex_hook_dirs(raw: dict, root_dir: Path) -> list[str]:
    declared = _normalize_path_list(raw.get("hooks"))
    if declared:
        return declared
    return ["hooks"] if _is_dir(root_dir, "hooks") else []


def _build_codex_capabilities(raw: dict, root_dir: Path) -> list[str]:
    caps: list[str] = []
    if _codex_skill_dirs(raw, root_dir):
        caps.append("skills")
    if _codex_hook_dirs(raw, root_dir):
        caps.append("hooks")
    if _has_inline_value(raw.get("mcpServers")) or _exists(root_dir, ".mcp.json"):
        caps.append("mcpServers")
    if _has_inline_value(raw.get("apps")) or _exists(root_dir, ".app.json"):
        caps.append("apps")
    return caps


# --- Claude ---


def _claude_component_paths(raw: dict, key: str, root_dir: Path, defaults: list[str]) -> list[str]:
    declared = _normalize_path_list(raw.get(key))
    existing_defaults = [d for d in defaults if _exists(root_dir, d)]
    return _merge_path_lists(existing_defaults, declared)


def _claude_skills_root_dirs(raw: dict, root_dir: Path) -> list[str]:
    return _claude_component_paths(raw, "skills", root_dir, ["skills"])


def _claude_command_root_dirs(raw: dict, root_dir: Path) -> list[str]:
    return _claude_component_paths(raw, "commands", root_dir, ["commands"])


def _claude_agent_dirs(raw: dict, root_dir: Path) -> list[str]:
    return _claude_component_paths(raw, "agents", root_dir, ["agents"])


def _claude_hook_paths(raw: dict, root_dir: Path) -> list[str]:
    return _claude_component_paths(raw, "hooks", root_dir, ["hooks/hooks.json"])


def _claude_mcp_paths(raw: dict, root_dir: Path) -> list[str]:
    return _claude_component_paths(raw, "mcpServers", root_dir, [".mcp.json"])


def _claude_lsp_paths(raw: dict, root_dir: Path) -> list[str]:
    return _claude_component_paths(raw, "lspServers", root_dir, [".lsp.json"])


def _claude_output_style_paths(raw: dict, root_dir: Path) -> list[str]:
    return _claude_component_paths(raw, "outputStyles", root_dir, ["output-styles"])


def _claude_settings_files(root_dir: Path) -> list[str]:
    return ["settings.json"] if _exists(root_dir, "settings.json") else []


def _claude_skill_dirs(raw: dict, root_dir: Path) -> list[str]:
    return _merge_path_lists(
        _claude_skills_root_dirs(raw, root_dir),
        _claude_command_root_dirs(raw, root_dir),
        _claude_agent_dirs(raw, root_dir),
        _claude_output_style_paths(raw, root_dir),
    )


def _build_claude_capabilities(raw: dict, root_dir: Path) -> list[str]:
    caps: list[str] = []
    if _claude_skill_dirs(raw, root_dir):
        caps.append("skills")
    if _claude_command_root_dirs(raw, root_dir):
        caps.append("commands")
    if _claude_agent_dirs(raw, root_dir):
        caps.append("agents")
    if _has_inline_value(raw.get("hooks")) or _claude_hook_paths(raw, root_dir):
        caps.append("hooks")
    if _has_inline_value(raw.get("mcpServers")) or _claude_mcp_paths(raw, root_dir):
        caps.append("mcpServers")
    if _has_inline_value(raw.get("lspServers")) or _claude_lsp_paths(raw, root_dir):
        caps.append("lspServers")
    if _has_inline_value(raw.get("outputStyles")) or _claude_output_style_paths(raw, root_dir):
        caps.append("outputStyles")
    if _claude_settings_files(root_dir):
        caps.append("settings")
    return caps


# --- Cursor ---


def _cursor_skills_root_dirs(raw: dict, root_dir: Path) -> list[str]:
    declared = _normalize_path_list(raw.get("skills"))
    defaults = ["skills"] if _is_dir(root_dir, "skills") else []
    return _merge_path_lists(defaults, declared)


def _cursor_command_root_dirs(raw: dict, root_dir: Path) -> list[str]:
    declared = _normalize_path_list(raw.get("commands"))
    defaults = [".cursor/commands"] if _is_dir(root_dir, ".cursor/commands") else []
    return _merge_path_lists(defaults, declared)


def _cursor_skill_dirs(raw: dict, root_dir: Path) -> list[str]:
    return _merge_path_lists(
        _cursor_skills_root_dirs(raw, root_dir),
        _cursor_command_root_dirs(raw, root_dir),
    )


def _cursor_agent_dirs(raw: dict, root_dir: Path) -> list[str]:
    declared = _normalize_path_list(raw.get("subagents") or raw.get("agents"))
    defaults = [".cursor/agents"] if _is_dir(root_dir, ".cursor/agents") else []
    return _merge_path_lists(defaults, declared)


def _has_cursor_hook_capability(raw: dict, root_dir: Path) -> bool:
    return _has_inline_value(raw.get("hooks")) or _exists(root_dir, ".cursor/hooks.json")


def _has_cursor_rules_capability(raw: dict, root_dir: Path) -> bool:
    return _has_inline_value(raw.get("rules")) or _exists(root_dir, ".cursor/rules")


def _has_cursor_mcp_capability(raw: dict, root_dir: Path) -> bool:
    return _has_inline_value(raw.get("mcpServers")) or _exists(root_dir, ".mcp.json")


def _build_cursor_capabilities(raw: dict, root_dir: Path) -> list[str]:
    caps: list[str] = []
    if _cursor_skill_dirs(raw, root_dir):
        caps.append("skills")
    if _cursor_command_root_dirs(raw, root_dir):
        caps.append("commands")
    if _cursor_agent_dirs(raw, root_dir):
        caps.append("agents")
    if _has_cursor_hook_capability(raw, root_dir):
        caps.append("hooks")
    if _has_cursor_rules_capability(raw, root_dir):
        caps.append("rules")
    if _has_cursor_mcp_capability(raw, root_dir):
        caps.append("mcpServers")
    return caps


# --- Agent ---


def _agent_skill_dirs(root_dir: Path) -> list[str]:
    return ["skills"] if _is_dir(root_dir, "skills") else []


def _resolve_agent_activation(raw: dict) -> str | None:
    extensions = raw.get("extensions")
    if not isinstance(extensions, dict):
        return None
    oc_ext = extensions.get(_AGENT_BUNDLE_EXTENSION_NAMESPACE)
    if not isinstance(oc_ext, dict):
        return None
    act = oc_ext.get("activation")
    if not isinstance(act, dict):
        return None
    if act.get("always") is True:
        return "always"
    if act.get("onStartup") is True or act.get("on_startup") is True:
        return "on_startup"
    return "on_demand"


def _build_agent_capabilities(root_dir: Path) -> list[str]:
    caps: list[str] = []
    if _agent_skill_dirs(root_dir):
        caps.append("skills")
    if _exists(root_dir, "mcp.json"):
        caps.append("mcpServers")
    return caps


# ── Manifest file readers ─────────────────────────────────────────────────────


def _read_json_file(
    path: Path,
    *,
    max_bytes: int | None = None,
    strict: bool = False,
) -> dict | None:
    """Read and JSON-parse a file; return ``None`` on any error."""
    try:
        stat = path.stat()
    except OSError:
        return None
    if max_bytes is not None and stat.st_size > max_bytes:
        _log.warning("bundle_manifest: %s exceeds max size (%d bytes)", path, max_bytes)
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _log.debug("bundle_manifest: cannot read %s: %s", path, exc)
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        if strict:
            _log.warning("bundle_manifest: invalid JSON in %s: %s", path, exc)
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _normalize_activation(raw: dict) -> str | None:
    act = raw.get("activation")
    if act is None:
        return None
    if isinstance(act, str):
        return act.strip() or None
    if isinstance(act, dict):
        if act.get("always") is True:
            return "always"
        if act.get("onStartup") is True or act.get("on_startup") is True:
            return "on_startup"
        return "on_demand"
    return None


# ── Public API ────────────────────────────────────────────────────────────────


def detect_bundle_format(root_dir: Path) -> PluginBundleFormat | None:
    """Detect the bundle format for a plugin directory.

    Returns a :class:`PluginBundleFormat` literal if the directory looks like
    a bundle, or ``None`` if it is a native JARVIS plugin (or not a bundle at
    all).

    Mirrors OpenClaw's ``detectBundleManifestFormat`` exactly.
    """
    # 1. Client-specific markers take precedence over native manifests.
    if _exists(root_dir, CODEX_BUNDLE_MANIFEST_RELATIVE_PATH):
        return "codex"
    if _exists(root_dir, CURSOR_BUNDLE_MANIFEST_RELATIVE_PATH):
        return "cursor"
    if _exists(root_dir, CLAUDE_BUNDLE_MANIFEST_RELATIVE_PATH):
        return "claude"

    # 2. Native JARVIS manifest — stop; this is a native plugin.
    if _exists(root_dir, NATIVE_MANIFEST_FILENAME):
        return None

    # 3. Root plugin.json — only if it declares the Agent Plugins schema.
    if _exists(root_dir, AGENT_BUNDLE_MANIFEST_RELATIVE_PATH):
        raw = _read_json_file(
            root_dir / AGENT_BUNDLE_MANIFEST_RELATIVE_PATH,
            max_bytes=_MAX_AGENT_BUNDLE_MANIFEST_BYTES,
            strict=True,
        )
        if raw is not None and raw.get("$schema") == _AGENT_BUNDLE_MANIFEST_SCHEMA:
            return "agent"

    # 4. Any remaining native entry candidates — stop.
    for candidate in _NATIVE_ENTRY_CANDIDATES:
        if _exists(root_dir, candidate):
            return None

    # 5. Manifestless Claude layout — any marker present.
    for marker in _MANIFESTLESS_CLAUDE_MARKERS:
        if _exists(root_dir, marker):
            return "claude"

    return None


def load_bundle_manifest(
    root_dir: Path,
    bundle_format: PluginBundleFormat,
) -> BundleManifest | None:
    """Load and normalize a bundle manifest for ``root_dir``.

    Returns a :class:`BundleManifest` on success, or ``None`` with a warning
    logged on failure.  Never raises.

    Mirrors OpenClaw's ``loadBundleManifest`` exactly.
    """
    # ── Resolve manifest path per format ──────────────────────────────────────
    relative_path = {
        "codex": CODEX_BUNDLE_MANIFEST_RELATIVE_PATH,
        "cursor": CURSOR_BUNDLE_MANIFEST_RELATIVE_PATH,
        "claude": CLAUDE_BUNDLE_MANIFEST_RELATIVE_PATH,
        "agent": AGENT_BUNDLE_MANIFEST_RELATIVE_PATH,
    }[bundle_format]

    allow_missing = bundle_format == "claude"
    strict_json = bundle_format == "agent"
    max_bytes = _MAX_AGENT_BUNDLE_MANIFEST_BYTES if bundle_format == "agent" else None

    manifest_path = root_dir / relative_path
    if manifest_path.exists():
        raw = _read_json_file(manifest_path, max_bytes=max_bytes, strict=strict_json)
        if raw is None:
            if not allow_missing:
                _log.warning("bundle_manifest: failed to read manifest at %s", manifest_path)
                return None
            raw = {}
    elif allow_missing:
        raw = {}
    else:
        _log.warning("bundle_manifest: manifest not found: %s", manifest_path)
        return None

    # ── Common fields ─────────────────────────────────────────────────────────
    iface = raw.get("interface")
    iface_record = iface if isinstance(iface, dict) else {}
    raw_name = (raw.get("name") or "").strip() or None
    description = (
        (raw.get("description") or "").strip()
        or (raw.get("shortDescription") or "").strip()
        or (iface_record.get("shortDescription") or "").strip()
        or None
    )
    version = (raw.get("version") or "").strip() or None

    # ── Agent ─────────────────────────────────────────────────────────────────
    if bundle_format == "agent":
        if raw.get("$schema") != _AGENT_BUNDLE_MANIFEST_SCHEMA:
            _log.warning(
                "bundle_manifest: %s is not an Agent Plugins manifest (wrong $schema)",
                manifest_path,
            )
            return None
        if not raw_name:
            _log.warning(
                "bundle_manifest: Agent Plugins manifest at %s missing required 'name'",
                manifest_path,
            )
            return None
        return BundleManifest(
            id=_slugify_plugin_id(raw_name, root_dir),
            name=raw_name,
            description=description,
            version=version,
            bundle_format="agent",
            skills=tuple(_agent_skill_dirs(root_dir)),
            hooks=(),
            settings_files=(),
            activation=_resolve_agent_activation(raw),
            capabilities=tuple(_build_agent_capabilities(root_dir)),
        )

    # ── Codex ─────────────────────────────────────────────────────────────────
    if bundle_format == "codex":
        return BundleManifest(
            id=_slugify_plugin_id(raw_name, root_dir),
            name=raw_name,
            description=description,
            version=version,
            bundle_format="codex",
            skills=tuple(_codex_skill_dirs(raw, root_dir)),
            hooks=tuple(_codex_hook_dirs(raw, root_dir)),
            settings_files=(),
            activation=_normalize_activation(raw),
            capabilities=tuple(_build_codex_capabilities(raw, root_dir)),
        )

    # ── Cursor ────────────────────────────────────────────────────────────────
    if bundle_format == "cursor":
        return BundleManifest(
            id=_slugify_plugin_id(raw_name, root_dir),
            name=raw_name,
            description=description,
            version=version,
            bundle_format="cursor",
            skills=tuple(_cursor_skill_dirs(raw, root_dir)),
            hooks=(),
            settings_files=(),
            activation=_normalize_activation(raw),
            capabilities=tuple(_build_cursor_capabilities(raw, root_dir)),
        )

    # ── Claude (manifest-based or manifestless) ───────────────────────────────
    return BundleManifest(
        id=_slugify_plugin_id(raw_name, root_dir),
        name=raw_name,
        description=description,
        version=version,
        bundle_format="claude",
        skills=tuple(_claude_skill_dirs(raw, root_dir)),
        hooks=tuple(_claude_hook_paths(raw, root_dir)),
        settings_files=tuple(_claude_settings_files(root_dir)),
        activation=_normalize_activation(raw),
        capabilities=tuple(_build_claude_capabilities(raw, root_dir)),
    )


# ── Re-export helpers needed by bundle_mcp / bundle_commands ─────────────────


def normalize_bundle_path_list(value: object) -> list[str]:
    """Public helper: normalize a string-or-list path field from a bundle manifest."""
    return _normalize_path_list(value)


def merge_bundle_path_lists(*groups: list[str]) -> list[str]:
    """Public helper: merge unique path lists preserving insertion order."""
    return _merge_path_lists(*groups)


__all__ = [
    "BundleManifest",
    "AGENT_BUNDLE_MANIFEST_RELATIVE_PATH",
    "CLAUDE_BUNDLE_MANIFEST_RELATIVE_PATH",
    "CODEX_BUNDLE_MANIFEST_RELATIVE_PATH",
    "CURSOR_BUNDLE_MANIFEST_RELATIVE_PATH",
    "NATIVE_MANIFEST_FILENAME",
    "PluginBundleFormat",
    "PluginFormat",
    "detect_bundle_format",
    "is_bundle_capability_supported",
    "load_bundle_manifest",
    "merge_bundle_path_lists",
    "normalize_bundle_path_list",
]
