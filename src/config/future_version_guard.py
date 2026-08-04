"""jarvis.config.future_version_guard — future-version config guard.

OpenClaw parity: mirrors
``openclaw-main/src/config/future-version-guard.ts``.
"""
from __future__ import annotations

from typing import List, Optional, TypedDict


#: Env var that opts into destructive config actions on an older binary.
ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV = "OPENCLAW_ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS"


class FutureConfigActionBlock(TypedDict, total=False):
    """Block payload shown when an older binary would mutate newer-written config.

    Mirrors :type:`FutureConfigActionBlock`
    (``shared/config/future-version-guard.ts``).
    """
    action: str
    currentVersion: str
    touchedVersion: str
    message: str
    hints: List[str]


def _allow_older_binary_destructive_actions(env) -> bool:
    raw = ((env or {}).get(ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV) or "").strip().lower()
    return raw in ("1", "true", "yes")


def _should_warn_on_touched_version(current_version: str, touched_version: str) -> bool:
    """Compare two semantic version strings; return True when touched is newer.

    Focused minimal port: simple lexicographic comparison on dot-separated
    numeric parts. The OpenClaw source uses a more sophisticated semver
    comparator; the Python port defers to a dedicated version helper.
    """
    if not touched_version:
        return False
    if touched_version == current_version:
        return False
    try:
        cur = [int(x) for x in current_version.split(".")]
        tch = [int(x) for x in touched_version.split(".")]
    except ValueError:
        return touched_version > current_version
    return tch > cur


def _resolve_touched_version(params: dict) -> Optional[str]:
    snapshot = params.get("snapshot")
    config = params.get("config")
    candidates = [
        ((snapshot or {}).get("sourceConfig") or {}).get("meta", {}).get("lastTouchedVersion"),
        ((snapshot or {}).get("config") or {}).get("meta", {}).get("lastTouchedVersion"),
        ((config or {}).get("meta") or {}).get("lastTouchedVersion"),
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_future_config_action_block(params: dict) -> Optional[FutureConfigActionBlock]:
    """Resolve whether a destructive action should be blocked.

    Mirrors :func:`resolveFutureConfigActionBlock`
    (``shared/config/future-version-guard.ts``).
    """
    env = params.get("env") or {}
    if _allow_older_binary_destructive_actions(env):
        return None
    current_version = params.get("currentVersion") or "0.0.0"
    touched_version = _resolve_touched_version(params)
    if not touched_version or not _should_warn_on_touched_version(current_version, touched_version):
        return None
    return {
        "action": params.get("action") or "",
        "currentVersion": current_version,
        "touchedVersion": touched_version,
        "message": (
            f"Refusing to {params.get('action') or ''} because this OpenClaw binary "
            f"({current_version}) is older than the config last written by OpenClaw "
            f"{touched_version}."
        ),
        "hints": [
            "Run the newer openclaw binary on PATH, or reinstall the intended gateway service from the newer install.",
            f"Set {ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV}=1 only for an intentional downgrade or recovery action.",
        ],
    }


def format_future_config_action_block(block: FutureConfigActionBlock) -> str:
    """Format a future-config action block for CLI/service error output.

    Mirrors :func:`formatFutureConfigActionBlock`
    (``shared/config/future-version-guard.ts``).
    """
    return "\n".join([block.get("message") or "", *(block.get("hints") or [])])


__all__ = [
    "ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV",
    "FutureConfigActionBlock",
    "resolve_future_config_action_block",
    "format_future_config_action_block",
]
