"""jarvis_sdk.memory_host_search — memory search manager lifecycle.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/memory-host-search``'s
``closeActiveMemorySearchManager``.

Used by ``active-memory`` to release per-agent memory-search
managers after a recall timeout. The OpenClaw shape is a
single async function that takes ``{cfg, agentId}`` and
closes any cached search manager for the agent. The Python
port is a sync function — the underlying ``MemorySearchManager``
is sync (Phase 4.0 SDK), and closing it is also sync.

Parity
======
- ``close_active_memory_search_manager(params)`` → ``None``.
  Best-effort: never raises on bad input or on the search
  manager being missing.
"""

from __future__ import annotations

import logging
from typing import Any

from .plugin_state import KeyedStore, open_keyed_store

_log = logging.getLogger("jarvis_sdk.memory_host_search")


def close_active_memory_search_manager(params: dict[str, Any] | None) -> None:
    """Close any cached memory search manager for ``agentId``.

    Mirrors ``openclaw/plugin-sdk/memory-host-search``'s
    ``closeActiveMemorySearchManager``. Best-effort: never
    raises on missing fields or missing manager.
    """
    if not isinstance(params, dict):
        return
    agent_id = params.get("agentId") or params.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        return
    canonical = agent_id.strip().lower()
    try:
        store = _get_manager_store(params.get("cfg"))
    except (OSError, ValueError) as exc:
        _log.debug("close_active_memory_search_manager: store init failed: %s", exc)
        return
    if store is None:
        return
    key = f"search-manager:{canonical}"
    try:
        store.delete(key)
    except (OSError, ValueError) as exc:
        _log.debug("close_active_memory_search_manager: delete failed: %s", exc)


def _get_manager_store(cfg: Any) -> KeyedStore | None:
    """Locate the host's per-agent manager store.

    Phase 4.2 ports only the search-manager *lifecycle*
    side; the actual store path comes from the host's
    state dir. We probe a small set of conventional
    locations so the helper is drop-in.
    """
    import os
    from pathlib import Path

    from .plugin_state import OpenKeyedStoreOptions

    data_dir = os.environ.get("JARVIS_DATA_DIR")
    root: Path
    if data_dir:
        root = Path(data_dir) / "plugins" / "active-memory"
    else:
        root = Path.home() / ".jarvis" / "plugins" / "active-memory"
    if not root.exists():
        return None
    try:
        return open_keyed_store(OpenKeyedStoreOptions(root=root, name="search-managers"))
    except (OSError, ValueError):
        return None


__all__ = ["close_active_memory_search_manager"]
