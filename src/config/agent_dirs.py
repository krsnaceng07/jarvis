"""jarvis.config.agent_dirs — agent directory resolution and duplicate detection.

OpenClaw parity: mirrors ``openclaw-main/src/config/agent-dirs.ts``.
"""
from __future__ import annotations

import os
import sys
from typing import Callable, List, Optional, TypedDict


DEFAULT_AGENT_ID = "main"


def _expand_tilde(path: str) -> str:
    """Expand leading ``~`` to the OS home dir (focused minimal port)."""
    if not isinstance(path, str) or not path.startswith("~"):
        return path
    home = os.path.expanduser("~")
    if path == "~":
        return home
    if path.startswith("~/"):
        return os.path.join(home, path[2:])
    return os.path.join(home, path[1:])


def normalize_agent_id(value: str) -> str:
    """Normalize agent id; Python port treats any non-empty string as-is."""
    if not isinstance(value, str):
        return DEFAULT_AGENT_ID
    trimmed = value.strip().lower()
    return trimmed or DEFAULT_AGENT_ID


class DuplicateAgentDir(TypedDict):
    agentDir: str
    agentIds: List[str]


class DuplicateAgentDirError(Exception):
    def __init__(self, duplicates: List[DuplicateAgentDir]) -> None:
        self.duplicates = duplicates
        super().__init__(format_duplicate_agent_dir_error(duplicates))


def _canonicalize_agent_dir(agent_dir: str) -> str:
    resolved = os.path.abspath(agent_dir)
    if sys.platform in ("darwin", "win32"):
        # Agent dirs collide case-insensitively on macOS/Windows.
        return resolved.lower()
    return resolved


def _collect_referenced_agent_ids(cfg: dict) -> List[str]:
    ids: set = set()
    agents = cfg.get("agents", {}).get("list") if isinstance(cfg, dict) else None
    agents = agents if isinstance(agents, list) else []
    default_id = DEFAULT_AGENT_ID
    for agent in agents:
        if isinstance(agent, dict) and agent.get("default"):
            default_id = agent.get("id") or default_id
            break
    if agents:
        first = agents[0]
        if isinstance(first, dict) and first.get("default") is not True:
            default_id = first.get("id") or default_id
    ids.add(normalize_agent_id(default_id))
    for entry in agents:
        if isinstance(entry, dict) and entry.get("id"):
            ids.add(normalize_agent_id(entry["id"]))
    bindings = cfg.get("bindings") if isinstance(cfg, dict) else None
    if isinstance(bindings, list):
        for b in bindings:
            if isinstance(b, dict):
                bid = b.get("agentId")
                if isinstance(bid, str) and bid.strip():
                    ids.add(normalize_agent_id(bid))
    return sorted(ids)


def _resolve_state_dir(env: dict, homedir: Callable[[], str]) -> str:
    state = env.get("JARVIS_STATE_DIR") or env.get("OPENCLAW_STATE_DIR")
    if state:
        return _expand_tilde(state)
    return os.path.join(homedir(), ".jarvis")


def resolve_effective_agent_dir(
    cfg: dict,
    agent_id: str,
    *,
    env: Optional[dict] = None,
    homedir: Optional[Callable[[], str]] = None,
) -> str:
    """Resolve the effective agent dir for ``agent_id``.

    Mirrors :func:`resolveEffectiveAgentDir` (``shared/config/agent-dirs.ts``).
    """
    env = env if env is not None else dict(os.environ)
    homedir = homedir or os.path.expanduser
    aid = normalize_agent_id(agent_id)
    agents = cfg.get("agents", {}).get("list") if isinstance(cfg, dict) else None
    agents = agents if isinstance(agents, list) else []
    configured = None
    for agent in agents:
        if isinstance(agent, dict) and normalize_agent_id(agent.get("id") or "") == aid:
            configured = agent.get("agentDir")
            break
    if isinstance(configured, str) and configured.strip():
        return _expand_tilde(configured.strip())
    root = _resolve_state_dir(env, homedir)
    return os.path.join(root, "agents", aid, "agent")


def find_duplicate_agent_dirs(
    cfg: dict,
    *,
    env: Optional[dict] = None,
    homedir: Optional[Callable[[], str]] = None,
) -> List[DuplicateAgentDir]:
    """Find agent ids whose effective agentDir would share auth/session state.

    Mirrors :func:`findDuplicateAgentDirs` (``shared/config/agent-dirs.ts``).
    """
    by_dir: dict = {}
    for aid in _collect_referenced_agent_ids(cfg):
        agent_dir = resolve_effective_agent_dir(cfg, aid, env=env, homedir=homedir)
        key = _canonicalize_agent_dir(agent_dir)
        entry = by_dir.get(key)
        if entry:
            entry["agentIds"].append(aid)
        else:
            by_dir[key] = {"agentDir": agent_dir, "agentIds": [aid]}
    return [v for v in by_dir.values() if len(v["agentIds"]) > 1]


def format_duplicate_agent_dir_error(dups: List[DuplicateAgentDir]) -> str:
    """Format duplicate agentDir conflicts with the remediation operators should take.

    Mirrors :func:`formatDuplicateAgentDirError`
    (``shared/config/agent-dirs.ts``).
    """
    lines = [
        "Duplicate agentDir detected (multi-agent config).",
        "Each agent must have a unique agentDir; sharing it causes auth/session state collisions and token invalidation.",
        "",
        "Conflicts:",
        *[
            f'- {d["agentDir"]}: {", ".join(f"\"" + a + "\"" for a in d["agentIds"])}'
            for d in dups
        ],
        "",
        "Fix: remove the shared agents.list[].agentDir override (or give each agent its own directory).",
        "If you want to share credentials, copy auth-profiles.json instead of sharing the entire agentDir.",
    ]
    return "\n".join(lines)


__all__ = [
    "DEFAULT_AGENT_ID",
    "DuplicateAgentDir",
    "DuplicateAgentDirError",
    "normalize_agent_id",
    "resolve_effective_agent_dir",
    "find_duplicate_agent_dirs",
    "format_duplicate_agent_dir_error",
]
