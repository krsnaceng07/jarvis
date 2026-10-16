"""Bundle MCP server configuration loading and tool-name sanitization.

Exact Python port of the relevant parts of OpenClaw's
``src/plugins/bundle-mcp.ts``.

This module handles:
- Reading MCP server configs from bundle manifests (``mcp.json`` for Agent
  format; ``.mcp.json`` for others).
- Validating Agent-format MCP configs strictly (schema, allowed keys, command
  boundary, cwd boundary).
- Expanding ``${PLUGIN_ROOT}``, ``${PLUGIN_DATA}``, and
  ``${CLAUDE_PLUGIN_ROOT}`` placeholders in a single pass.
- Absolutizing ``command``, ``cwd``, ``args``, and ``env`` values.
- Providing :func:`sanitize_mcp_tool_name` for provider-safe tool names.

MCP server *launching* (subprocess management, HTTP connection) is **not**
handled here — that belongs in the gateway MCP subsystem (Phase 2).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .bundle_manifest import (
    AGENT_BUNDLE_MANIFEST_RELATIVE_PATH,
    CLAUDE_BUNDLE_MANIFEST_RELATIVE_PATH,
    CODEX_BUNDLE_MANIFEST_RELATIVE_PATH,
    CURSOR_BUNDLE_MANIFEST_RELATIVE_PATH,
    PluginBundleFormat,
    merge_bundle_path_lists,
    normalize_bundle_path_list,
)

_log = logging.getLogger("jarvis_sdk.bundle_mcp")

# ── Constants (mirrors OpenClaw) ──────────────────────────────────────────────

_CLAUDE_PLUGIN_ROOT_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
_AGENT_PLUGIN_ROOT_PLACEHOLDER = "${PLUGIN_ROOT}"
_AGENT_PLUGIN_DATA_PLACEHOLDER = "${PLUGIN_DATA}"
_AGENT_MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

_BUNDLE_PLACEHOLDER_RE = re.compile(r"\$\{(?:CLAUDE_PLUGIN_ROOT|PLUGIN_ROOT|PLUGIN_DATA)\}")

# Agent-format allowed top-level keys
_AGENT_MCP_TOP_LEVEL_KEYS = frozenset(["$schema", "mcpServers"])
# Agent-format allowed stdio server keys
_AGENT_STDIO_KEYS = frozenset(["type", "command", "args", "env", "cwd"])
# Agent-format allowed HTTP server keys
_AGENT_HTTP_KEYS = frozenset(["type", "url", "headers"])

# Tool name caps (mirrors OpenClaw)
_MAX_SERVER_PREFIX_LEN = 30
_MAX_TOOL_NAME_LEN = 64

# ── Types ─────────────────────────────────────────────────────────────────────

BundleMcpServerConfig = dict[str, Any]


@dataclass(frozen=True, slots=True)
class BundleMcpConfig:
    """Resolved MCP server configuration for one bundle.

    ``mcp_servers`` maps server key → raw (but absolutized) server config dict.
    The gateway is responsible for launching stdio servers or connecting to
    HTTP servers.
    """

    plugin_id: str
    root_dir: Path
    mcp_servers: dict[str, BundleMcpServerConfig] = field(default_factory=dict)
    #: Non-fatal warnings encountered while loading the config.
    diagnostics: tuple[str, ...] = field(default_factory=tuple)


# ── Placeholder expansion (single-pass, mirrors OpenClaw) ─────────────────────


def _expand_placeholders(value: str, *, root_dir: str, plugin_data_dir: str | None = None) -> str:
    """Replace ``${PLUGIN_ROOT}``, ``${PLUGIN_DATA}``, ``${CLAUDE_PLUGIN_ROOT}``.

    One replacement pass only — substituted paths are not re-scanned.  This
    matches OpenClaw's ``expandBundleRootPlaceholders`` contract.
    """

    def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
        ph = m.group(0)
        if ph in (_CLAUDE_PLUGIN_ROOT_PLACEHOLDER, _AGENT_PLUGIN_ROOT_PLACEHOLDER):
            return root_dir
        # ${PLUGIN_DATA}
        return plugin_data_dir if plugin_data_dir is not None else ph

    return _BUNDLE_PLACEHOLDER_RE.sub(_replace, value)


# ── Path helpers ──────────────────────────────────────────────────────────────


def _is_explicit_relative(value: str) -> bool:
    return value in (".", "..") or value.startswith("./") or value.startswith("../")


def _is_path_inside(base_dir: str, target: str) -> bool:
    """Return True if ``target`` is inside ``base_dir`` (no symlink traversal)."""
    try:
        Path(target).resolve().relative_to(Path(base_dir).resolve())
        return True
    except ValueError:
        return False


# ── Agent MCP validation (strict) ────────────────────────────────────────────


def _is_valid_agent_command(command: object, root_dir: str) -> bool:
    if not isinstance(command, str) or not command:
        return False
    if command.startswith("./"):
        # Must stay inside root_dir
        return len(command) > 2 and _is_path_inside(root_dir, str(Path(root_dir) / command))
    # Bare executable — no spaces, no path separators
    return not re.search(r"[\s/\\]", command)


def _is_valid_agent_cwd(cwd: object, root_dir: str, plugin_data_dir: str) -> bool:
    if not isinstance(cwd, str):
        return False
    if cwd.startswith("./"):
        base = root_dir
    elif cwd in (
        _AGENT_PLUGIN_ROOT_PLACEHOLDER,
        f"{_AGENT_PLUGIN_ROOT_PLACEHOLDER}/",
    ) or cwd.startswith(f"{_AGENT_PLUGIN_ROOT_PLACEHOLDER}/"):
        base = root_dir
    elif cwd in (
        _AGENT_PLUGIN_DATA_PLACEHOLDER,
        f"{_AGENT_PLUGIN_DATA_PLACEHOLDER}/",
    ) or cwd.startswith(f"{_AGENT_PLUGIN_DATA_PLACEHOLDER}/"):
        base = plugin_data_dir
    else:
        return False
    expanded = _expand_placeholders(cwd, root_dir=root_dir, plugin_data_dir=plugin_data_dir)
    return _is_path_inside(base, str(Path(base) / expanded))


def _validate_agent_mcp_server(
    raw: object, root_dir: str, plugin_data_dir: str
) -> tuple[BundleMcpServerConfig, None] | tuple[None, str]:
    """Validate one Agent-format MCP server entry.

    Returns ``(server_dict, None)`` on success, ``(None, error_msg)`` on failure.
    Mirrors OpenClaw's ``validateAgentMcpServer``.
    """
    if not isinstance(raw, dict):
        return None, "server config must be an object"

    has_command = isinstance(raw.get("command"), str)
    has_url = isinstance(raw.get("url"), str)

    if has_command and has_url:
        return None, "server cannot have both 'command' and 'url'"

    if has_url:
        # HTTP server
        if not all(k in _AGENT_HTTP_KEYS for k in raw):
            bad = sorted(set(raw) - _AGENT_HTTP_KEYS)
            return None, f"HTTP server has disallowed keys: {bad}"
        url = raw["url"]
        if not isinstance(url, str) or not re.match(r"^https?://", url):
            return None, "HTTP server 'url' must start with http:// or https://"
        return dict(raw), None

    # Stdio server
    if not all(k in _AGENT_STDIO_KEYS for k in raw):
        bad = sorted(set(raw) - _AGENT_STDIO_KEYS)
        return None, f"stdio server has disallowed keys: {bad}"

    command = raw.get("command")
    if not _is_valid_agent_command(command, root_dir):
        return None, (
            f"stdio server 'command' must be a bare executable or ./path "
            f"inside plugin root; got {command!r}"
        )

    cwd = raw.get("cwd")
    if cwd is not None and not _is_valid_agent_cwd(cwd, root_dir, plugin_data_dir):
        return None, (
            f"stdio server 'cwd' must stay inside PLUGIN_ROOT or PLUGIN_DATA; got {cwd!r}"
        )

    return dict(raw), None


# ── Server absolutization (mirrors OpenClaw ``absolutizeBundleMcpServer``) ────


def _absolutize_server(
    server: BundleMcpServerConfig,
    *,
    root_dir: str,
    base_dir: str,
    plugin_data_dir: str | None = None,
    agent_format: bool = False,
) -> BundleMcpServerConfig:
    """Expand placeholders and absolutize paths in one server config dict."""
    next_server: BundleMcpServerConfig = dict(server)

    # Default cwd to base_dir when not explicitly set (non-agent, or agent with command)
    if (
        not isinstance(next_server.get("cwd"), str)
        and not isinstance(next_server.get("workingDirectory"), str)
        and (not agent_format or isinstance(next_server.get("command"), str))
    ):
        next_server["cwd"] = base_dir

    # command
    command = next_server.get("command")
    if isinstance(command, str):
        expanded = _expand_placeholders(command, root_dir=root_dir, plugin_data_dir=plugin_data_dir)
        if _is_explicit_relative(expanded):
            next_server["command"] = str(Path(base_dir) / expanded)
        elif Path(expanded).is_absolute():
            next_server["command"] = str(Path(expanded))
        else:
            next_server["command"] = expanded

    # cwd
    cwd = next_server.get("cwd")
    if isinstance(cwd, str):
        expanded = _expand_placeholders(cwd, root_dir=root_dir, plugin_data_dir=plugin_data_dir)
        if Path(expanded).is_absolute():
            next_server["cwd"] = expanded
        else:
            next_server["cwd"] = str(Path(base_dir) / expanded)

    # args
    if isinstance(next_server.get("args"), list):
        new_args = []
        for entry in next_server["args"]:
            if not isinstance(entry, str):
                new_args.append(entry)
                continue
            expanded = _expand_placeholders(
                entry, root_dir=root_dir, plugin_data_dir=plugin_data_dir
            )
            if _is_explicit_relative(expanded):
                new_args.append(str(Path(base_dir) / expanded))
            elif Path(expanded).is_absolute():
                new_args.append(str(Path(expanded)))
            else:
                new_args.append(expanded)
        next_server["args"] = new_args

    # env
    if isinstance(next_server.get("env"), dict):
        new_env: dict[str, Any] = {}
        for k, v in next_server["env"].items():
            if isinstance(v, str):
                expanded = _expand_placeholders(
                    v, root_dir=root_dir, plugin_data_dir=plugin_data_dir
                )
                new_env[k] = str(Path(expanded)) if Path(expanded).is_absolute() else expanded
            else:
                new_env[k] = v
        next_server["env"] = new_env

    # Inject PLUGIN_ROOT / PLUGIN_DATA env vars for Agent format stdio servers
    if plugin_data_dir and isinstance(next_server.get("command"), str):
        env = dict(next_server.get("env") or {})
        env["PLUGIN_ROOT"] = root_dir
        env["PLUGIN_DATA"] = plugin_data_dir
        next_server["env"] = env

    return next_server


# ── MCP config path resolution ────────────────────────────────────────────────


def _resolve_mcp_config_paths(
    raw: dict, root_dir: Path, bundle_format: PluginBundleFormat
) -> list[str]:
    """Return relative paths to MCP config files for this format."""
    if bundle_format == "agent":
        return ["mcp.json"] if (root_dir / "mcp.json").exists() else []
    declared = normalize_bundle_path_list(raw.get("mcpServers"))
    defaults = [".mcp.json"] if (root_dir / ".mcp.json").exists() else []
    return merge_bundle_path_lists(defaults, declared)


# ── Raw MCP server map extraction ─────────────────────────────────────────────


def _extract_mcp_server_map(raw: object) -> dict[str, BundleMcpServerConfig]:
    """Extract the ``mcpServers`` map from a raw MCP config object.

    Handles ``{mcpServers: {…}}``, ``{servers: {…}}``, or flat ``{key: …}``.
    Mirrors OpenClaw's ``extractMcpServerMap``.
    """
    if not isinstance(raw, dict):
        return {}
    nested = raw.get("mcpServers") or raw.get("servers") or raw
    if not isinstance(nested, dict):
        return {}
    return {k: dict(v) for k, v in nested.items() if isinstance(v, dict)}


# ── Public API ────────────────────────────────────────────────────────────────


def load_bundle_mcp_config(
    root_dir: Path,
    bundle_format: PluginBundleFormat,
    plugin_id: str,
    *,
    plugin_data_dir: Path | None = None,
) -> BundleMcpConfig | None:
    """Load and normalize the MCP server configuration for a bundle.

    Returns ``None`` if the bundle has no MCP config at all (not an error).
    Returns a :class:`BundleMcpConfig` (possibly with empty ``mcp_servers``)
    on partial failure — individual bad server entries are skipped and
    logged via ``diagnostics``.

    Mirrors OpenClaw's bundle MCP loading pipeline.
    """
    root_str = str(root_dir.resolve())
    data_str = str(plugin_data_dir.resolve()) if plugin_data_dir else None

    # Determine which manifest file to read for Codex/Claude/Cursor
    manifest_paths = {
        "agent": AGENT_BUNDLE_MANIFEST_RELATIVE_PATH,
        "codex": CODEX_BUNDLE_MANIFEST_RELATIVE_PATH,
        "claude": CLAUDE_BUNDLE_MANIFEST_RELATIVE_PATH,
        "cursor": CURSOR_BUNDLE_MANIFEST_RELATIVE_PATH,
    }
    manifest_rel = manifest_paths[bundle_format]
    manifest_path = root_dir / manifest_rel
    raw_manifest: dict = {}
    if manifest_path.exists():
        try:
            raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(raw_manifest, dict):
                raw_manifest = {}
        except (OSError, json.JSONDecodeError):
            raw_manifest = {}

    mcp_paths = _resolve_mcp_config_paths(raw_manifest, root_dir, bundle_format)
    if not mcp_paths:
        return None  # No MCP config — not an error.

    diagnostics: list[str] = []
    merged_servers: dict[str, BundleMcpServerConfig] = {}

    for mcp_rel in mcp_paths:
        mcp_path = root_dir / mcp_rel
        if not mcp_path.exists():
            continue
        try:
            raw_mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            diagnostics.append(f"failed to read {mcp_rel}: {exc}")
            continue
        if not isinstance(raw_mcp, dict):
            diagnostics.append(f"{mcp_rel}: top-level value must be an object")
            continue

        # Agent format: strict schema + key validation
        if bundle_format == "agent":
            if raw_mcp.get("$schema") != _AGENT_MCP_SCHEMA:
                diagnostics.append(
                    f"{mcp_rel}: missing or wrong $schema; expected {_AGENT_MCP_SCHEMA}"
                )
                continue
            extra_keys = set(raw_mcp) - _AGENT_MCP_TOP_LEVEL_KEYS
            if extra_keys:
                diagnostics.append(f"{mcp_rel}: disallowed top-level keys {sorted(extra_keys)}")
                continue

        server_map = _extract_mcp_server_map(raw_mcp)
        base_dir = str(mcp_path.parent.resolve())

        for server_name, server_raw in server_map.items():
            if bundle_format == "agent":
                pdd = data_str or str(Path.home() / ".jarvis" / "plugins" / plugin_id / "data")
                validated, err = _validate_agent_mcp_server(server_raw, root_str, pdd)
                if validated is None:
                    diagnostics.append(f"skipping server {server_name!r}: {err}")
                    continue
                server_raw = validated
                pdd_used: str | None = pdd
            else:
                pdd_used = data_str

            absolutized = _absolutize_server(
                server_raw,
                root_dir=root_str,
                base_dir=base_dir,
                plugin_data_dir=pdd_used,
                agent_format=(bundle_format == "agent"),
            )
            merged_servers[server_name] = absolutized

    return BundleMcpConfig(
        plugin_id=plugin_id,
        root_dir=root_dir,
        mcp_servers=merged_servers,
        diagnostics=tuple(diagnostics),
    )


def sanitize_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Return a provider-safe ``<server>__<tool>`` tool name.

    Mirrors OpenClaw's bundle MCP tool naming contract:
    - Characters outside ``A-Za-z0-9_-`` are replaced with ``-``.
    - Server prefixes are capped at 30 characters.
    - Full names are capped at 64 characters.
    - Numeric-start server keys get a letter prefix (``s-``).
    - Empty server name falls back to ``mcp``.
    """

    def _sanitize(s: str, max_len: int, prefix_fix: bool = False) -> str:
        clean = re.sub(r"[^A-Za-z0-9_\-]", "-", s)
        if prefix_fix and clean and not clean[0].isalpha():
            clean = "s-" + clean
        return clean[:max_len]

    safe_server = _sanitize(server_name or "mcp", _MAX_SERVER_PREFIX_LEN, prefix_fix=True)
    safe_tool = _sanitize(tool_name, _MAX_TOOL_NAME_LEN - len(safe_server) - 2)
    return f"{safe_server}__{safe_tool}"


__all__ = [
    "BundleMcpConfig",
    "BundleMcpServerConfig",
    "load_bundle_mcp_config",
    "sanitize_mcp_tool_name",
]
