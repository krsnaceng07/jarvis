"""jarvis_config_core — typed JARVIS config loader.

Mirrors OpenClaw's ``packages/config-core/``.

Canonical config path: ``~/.jarvis/config.json``
Legacy compat path:    ``<app_dir>/config/api_keys.json`` (read-only)

Config shape (current canonical):
  {
    "gemini_api_key": "...",
    "model": "gemini-2.0-flash",
    "gateway_port": 7433,
    "log_level": "INFO",
    "extensions_dir": null,   // null = default ~/.jarvis/extensions
    "state_dir": null         // null = default ~/.jarvis/state
  }

Rules:
  - Runtime reads canonical config only (``~/.jarvis/config.json``).
  - Legacy paths are for migration/doctor use only.
  - No silent compat for old/malformed keys — ``JarvisConfig.validate()``
    surfaces issues; ``jarvis doctor --fix`` patches them.
  - Config is loaded once at startup; no hot-reload shims.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

_log = logging.getLogger("jarvis.config_core")

# ── Paths ──────────────────────────────────────────────────────────────

JARVIS_DIR = Path.home() / ".jarvis"
CONFIG_PATH = JARVIS_DIR / "config.json"

# Legacy path (app-local) — migration source only.
_LEGACY_API_KEYS_RELPATH = "config/api_keys.json"


# ── Typed config shape ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AgentConfig:
    id: str
    name: str = ""
    workspace: str = ""
    default: bool = False


@dataclass(frozen=True, slots=True)
class BindingMatch:
    channel: str | None = None
    account_id: str | None = None
    peer_kind: str | None = None
    peer_id: str | None = None
    guild_id: str | None = None
    team_id: str | None = None
    roles: list[str] | None = None


@dataclass(frozen=True, slots=True)
class BindingConfig:
    match: BindingMatch
    agent_id: str
    session_dm_scope: str | None = None


@dataclass(frozen=True, slots=True)
class SessionConfig:
    dm_scope: str = "main"
    identityLinks: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BroadcastConfig:
    strategy: str = "parallel"
    groups: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    """Agent identity persisted from bootstrap ritual."""

    name: str = "JARVIS"
    soul: str = ""  # voice/tone description
    workspace_configured: bool = False


@dataclass(frozen=True, slots=True)
class McpToolFilter:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    url: str | None = None
    transport: str = "stdio"
    enabled: bool = True
    command: str | None = None
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    connectionTimeoutMs: int = 5000
    requestTimeoutMs: int = 20000
    toolFilter: McpToolFilter = field(default_factory=McpToolFilter)
    auth: str | None = None
    oauth: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolSearchConfig:
    mode: str = "code"
    codeTimeoutMs: int = 10000
    searchDefaultLimit: int = 8
    maxSearchLimit: int = 20


@dataclass(frozen=True, slots=True)
class ToolsConfig:
    toolSearch: ToolSearchConfig | bool = False


@dataclass(frozen=True, slots=True)
class McpConfig:
    servers: dict[str, McpServerConfig] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JarvisConfig:
    """Typed representation of ``~/.jarvis/config.json``.

    All fields have safe defaults so the app can start even if the
    config file is empty or missing.
    """

    gemini_api_key: str = ""
    model: str = "gemini-2.0-flash"
    gateway_port: int = 7433
    log_level: str = "INFO"
    extensions_dir: Path | None = None
    state_dir: Path | None = None

    # Agent identity (from bootstrap ritual)
    agent: AgentIdentity = field(default_factory=AgentIdentity)

    # Routing extensions
    agents: dict[str, list[AgentConfig]] = field(default_factory=dict)
    bindings: list[BindingConfig] = field(default_factory=list)
    session: SessionConfig = field(default_factory=SessionConfig)
    broadcast: BroadcastConfig = field(default_factory=BroadcastConfig)

    # MCP
    mcp: McpConfig = field(default_factory=McpConfig)

    # Tools config (Tool Search, etc)
    tools: ToolsConfig = field(default_factory=ToolsConfig)

    # Internal hooks
    hooks: dict[str, Any] = field(default_factory=dict)

    # Messaging channels
    channels: dict[str, Any] = field(default_factory=dict)

    @property
    def is_configured(self) -> bool:
        """True if a non-empty API key is present."""
        return bool(self.gemini_api_key.strip())

    def validate(self) -> list[str]:
        """Return a list of validation issues (empty = ok).

        The caller (``jarvis doctor``) surfaces these to the user.
        """
        issues: list[str] = []
        if not self.gemini_api_key.strip():
            issues.append("gemini_api_key is missing or empty")
        if not (1 <= self.gateway_port <= 65535):
            issues.append(f"gateway_port {self.gateway_port!r} is out of range 1-65535")
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_levels:
            issues.append(f"log_level {self.log_level!r} is not a valid logging level")
        return issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "gemini_api_key": self.gemini_api_key,
            "model": self.model,
            "gateway_port": self.gateway_port,
            "log_level": self.log_level,
            "extensions_dir": str(self.extensions_dir) if self.extensions_dir else None,
            "state_dir": str(self.state_dir) if self.state_dir else None,
            "agent": {
                "name": self.agent.name,
                "soul": self.agent.soul,
                "workspace_configured": self.agent.workspace_configured,
            },
            "agents": {
                "list": [
                    {
                        "id": a.id,
                        "name": a.name,
                        "workspace": a.workspace,
                        "default": a.default,
                    }
                    for a in self.agents.get("list", [])
                ]
            },
            "bindings": [
                {
                    "match": {
                        "channel": b.match.channel,
                        "accountId": b.match.account_id,
                        "peer": {"kind": b.match.peer_kind, "id": b.match.peer_id}
                        if b.match.peer_kind
                        else None,
                        "guildId": b.match.guild_id,
                        "teamId": b.match.team_id,
                        "roles": b.match.roles,
                    },
                    "agentId": b.agent_id,
                    "session": {"dmScope": b.session_dm_scope} if b.session_dm_scope else None,
                }
                for b in self.bindings
            ],
            "session": {"dmScope": self.session.dm_scope},
            "broadcast": {
                "strategy": self.broadcast.strategy,
                **self.broadcast.groups,
            },
            "mcp": {
                "servers": {
                    name: {
                        "url": srv.url,
                        "transport": srv.transport,
                        "enabled": srv.enabled,
                        "command": srv.command,
                        "args": srv.args,
                        "cwd": srv.cwd,
                        "connectionTimeoutMs": srv.connectionTimeoutMs,
                        "requestTimeoutMs": srv.requestTimeoutMs,
                        "toolFilter": {
                            "include": srv.toolFilter.include,
                            "exclude": srv.toolFilter.exclude,
                        },
                        "auth": srv.auth,
                        "oauth": srv.oauth,
                        "headers": srv.headers,
                        "env": srv.env,
                    }
                    for name, srv in self.mcp.servers.items()
                }
            },
            "tools": {
                "toolSearch": (
                    self.tools.toolSearch
                    if isinstance(self.tools.toolSearch, bool)
                    else {
                        "mode": self.tools.toolSearch.mode,
                        "codeTimeoutMs": self.tools.toolSearch.codeTimeoutMs,
                        "searchDefaultLimit": self.tools.toolSearch.searchDefaultLimit,
                        "maxSearchLimit": self.tools.toolSearch.maxSearchLimit,
                    }
                )
            },
            "hooks": self.hooks,
            "channels": self.channels,
        }


# ── Loader ─────────────────────────────────────────────────────────────


def load_config(
    config_path: Path | None = None,
    *,
    legacy_app_dir: Path | None = None,
) -> JarvisConfig:
    """Load and return a ``JarvisConfig``.

    Resolution order:
    1. ``config_path`` (explicit override, used by tests/doctor).
    2. ``~/.jarvis/config.json`` (canonical).
    3. ``legacy_app_dir/config/api_keys.json`` (migration source, read-only).
    4. Empty defaults when nothing is found.

    Never raises; bad JSON is logged as a warning and defaults are used.
    """
    path = config_path or CONFIG_PATH
    raw: dict[str, Any] = {}

    if path.exists():
        raw = _read_json(path)
    elif legacy_app_dir is not None:
        legacy = legacy_app_dir / _LEGACY_API_KEYS_RELPATH
        if legacy.exists():
            _log.info("config_core: canonical config not found; reading legacy %s", legacy)
            raw = _read_json(legacy)
    else:
        _log.debug("config_core: no config at %s; using defaults", path)

    return _parse(raw)


def save_config(config: JarvisConfig, config_path: Path | None = None) -> None:
    """Persist a ``JarvisConfig`` to ``config_path`` (default: canonical path).

    Creates parent directories. Used by ``jarvis configure`` and
    ``jarvis doctor --fix``.
    """
    path = config_path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
    _log.info("config_core: saved config to %s", path)


def patch_config(
    patch: dict[str, Any],
    config_path: Path | None = None,
) -> JarvisConfig:
    """Apply a merge-patch to the config file and return the new config.

    Only keys present in ``patch`` are updated; others are preserved.
    Used by ``config.patch`` RPC and ``jarvis configure`` wizard.
    """
    current = load_config(config_path)
    merged: dict[str, Any] = current.to_dict()
    merged.update(patch)
    new_config = _parse(merged)
    save_config(new_config, config_path)
    return new_config


# ── Internal ───────────────────────────────────────────────────────────


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            _log.warning("config_core: %s is not a JSON object; ignoring", path)
            return {}
        return data
    except (json.JSONDecodeError, OSError) as e:
        _log.warning("config_core: failed to read %s: %s", path, e)
        return {}


def _parse(raw: dict[str, Any]) -> JarvisConfig:
    """Build a ``JarvisConfig`` from a raw dict, ignoring unknown keys."""
    known = {f.name for f in fields(JarvisConfig)}
    kwargs: dict[str, Any] = {}

    if "gemini_api_key" in raw:
        kwargs["gemini_api_key"] = str(raw["gemini_api_key"])
    if "model" in raw:
        kwargs["model"] = str(raw["model"])
    if "gateway_port" in raw:
        try:
            kwargs["gateway_port"] = int(raw["gateway_port"])
        except (TypeError, ValueError):
            _log.warning("config_core: invalid gateway_port %r; using default", raw["gateway_port"])
    if "log_level" in raw:
        kwargs["log_level"] = str(raw["log_level"]).upper()
    if "extensions_dir" in raw and raw["extensions_dir"] is not None:
        kwargs["extensions_dir"] = Path(str(raw["extensions_dir"]))
    if "state_dir" in raw and raw["state_dir"] is not None:
        kwargs["state_dir"] = Path(str(raw["state_dir"]))

    # Agent identity from bootstrap ritual
    if "agent" in raw and isinstance(raw["agent"], dict):
        agent_raw = raw["agent"]
        kwargs["agent"] = AgentIdentity(
            name=str(agent_raw.get("name", "JARVIS")),
            soul=str(agent_raw.get("soul", "")),
            workspace_configured=bool(agent_raw.get("workspace_configured", False)),
        )

    if "agents" in raw and isinstance(raw["agents"], dict):
        agent_list: list[AgentConfig] = []
        for a in raw["agents"].get("list", []):
            if isinstance(a, dict) and "id" in a:
                agent_list.append(
                    AgentConfig(
                        id=str(a["id"]),
                        name=str(a.get("name", "")),
                        workspace=str(a.get("workspace", "")),
                        default=bool(a.get("default", False)),
                    )
                )
        kwargs["agents"] = {"list": agent_list}

    if "bindings" in raw and isinstance(raw["bindings"], list):
        bindings_list: list[BindingConfig] = []
        for b in raw["bindings"]:
            if isinstance(b, dict) and "match" in b and "agentId" in b:
                match_raw = b["match"]
                if isinstance(match_raw, dict):
                    peer_raw = match_raw.get("peer")
                    peer_kind = peer_raw.get("kind") if isinstance(peer_raw, dict) else None
                    peer_id = peer_raw.get("id") if isinstance(peer_raw, dict) else None

                    bm = BindingMatch(
                        channel=match_raw.get("channel"),
                        account_id=match_raw.get("accountId"),
                        peer_kind=peer_kind,
                        peer_id=peer_id,
                        guild_id=match_raw.get("guildId"),
                        team_id=match_raw.get("teamId"),
                        roles=match_raw.get("roles"),
                    )

                    session_raw = b.get("session")
                    session_dm_scope = (
                        session_raw.get("dmScope") if isinstance(session_raw, dict) else None
                    )

                    bindings_list.append(
                        BindingConfig(
                            match=bm,
                            agent_id=str(b["agentId"]),
                            session_dm_scope=session_dm_scope,
                        )
                    )
        kwargs["bindings"] = bindings_list

    if "session" in raw and isinstance(raw["session"], dict):
        dm_scope = raw["session"].get("dmScope", "main")
        identity_links = raw["session"].get("identityLinks", {})
        kwargs["session"] = SessionConfig(dm_scope=str(dm_scope), identityLinks=identity_links)

    if "broadcast" in raw and isinstance(raw["broadcast"], dict):
        b_raw = raw["broadcast"]
        strategy = b_raw.get("strategy", "parallel")
        groups: dict[str, list[str]] = {}
        for k, v in b_raw.items():
            if k != "strategy" and isinstance(v, list):
                groups[k] = [str(x) for x in v]
        kwargs["broadcast"] = BroadcastConfig(strategy=str(strategy), groups=groups)

    if "mcp" in raw and isinstance(raw["mcp"], dict):
        mcp_raw = raw["mcp"]
        servers_dict = {}
        if "servers" in mcp_raw and isinstance(mcp_raw["servers"], dict):
            for name, s_raw in mcp_raw["servers"].items():
                if isinstance(s_raw, dict):
                    tf_raw = s_raw.get("toolFilter", {})
                    tf = McpToolFilter(
                        include=tf_raw.get("include", []),
                        exclude=tf_raw.get("exclude", []),
                    )
                    servers_dict[name] = McpServerConfig(
                        url=s_raw.get("url"),
                        transport=s_raw.get("transport", "stdio"),
                        enabled=bool(s_raw.get("enabled", True)),
                        command=s_raw.get("command"),
                        args=s_raw.get("args", []),
                        cwd=s_raw.get("cwd"),
                        connectionTimeoutMs=int(s_raw.get("connectionTimeoutMs", 5000)),
                        requestTimeoutMs=int(s_raw.get("requestTimeoutMs", 20000)),
                        toolFilter=tf,
                        auth=s_raw.get("auth"),
                        oauth=s_raw.get("oauth", {}),
                        headers=s_raw.get("headers", {}),
                        env=s_raw.get("env", {}),
                    )
        kwargs["mcp"] = McpConfig(servers=servers_dict)

    if "tools" in raw and isinstance(raw["tools"], dict):
        tools_raw = raw["tools"]
        ts_val = tools_raw.get("toolSearch", False)
        if isinstance(ts_val, bool):
            kwargs["tools"] = ToolsConfig(toolSearch=ts_val)
        elif isinstance(ts_val, dict):
            kwargs["tools"] = ToolsConfig(
                toolSearch=ToolSearchConfig(
                    mode=str(ts_val.get("mode", "code")),
                    codeTimeoutMs=int(ts_val.get("codeTimeoutMs", 10000)),
                    searchDefaultLimit=int(ts_val.get("searchDefaultLimit", 8)),
                    maxSearchLimit=int(ts_val.get("maxSearchLimit", 20)),
                )
            )

    if "hooks" in raw and isinstance(raw["hooks"], dict):
        kwargs["hooks"] = raw["hooks"]

    if "channels" in raw and isinstance(raw["channels"], dict):
        kwargs["channels"] = raw["channels"]

    unknown = set(raw) - known
    if unknown:
        _log.debug("config_core: ignoring unknown keys: %s", sorted(unknown))

    return JarvisConfig(**kwargs)


__all__ = [
    "CONFIG_PATH",
    "JARVIS_DIR",
    "AgentConfig",
    "AgentIdentity",
    "BindingMatch",
    "BindingConfig",
    "SessionConfig",
    "BroadcastConfig",
    "McpToolFilter",
    "McpServerConfig",
    "McpConfig",
    "ToolSearchConfig",
    "ToolsConfig",
    "JarvisConfig",
    "load_config",
    "patch_config",
    "save_config",
]
