"""jarvis.agents.embedded_agent_runner.model_discovery_cache — cache auth/model discovery.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/model-discovery-cache.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`discover_cached_agent_stores` — return auth + model
  registry, reusing a file-backed snapshot when the agent
  directory's inputs have not changed.
- :func:`reset_model_discovery_cache_for_test` — clear the
  process-local cache (mirrors the OpenClaw test hook).
- :data:`MAX_DISCOVERY_STORE_CACHE_ENTRIES` — the LRU cap.

Phase 7.3b — focused minimal port.

The OpenClaw source is tightly coupled to the agent-model
discovery, plugin-metadata snapshot, and runtime-config-cache
layers. The Python port keeps the public surface but delegates
all heavy operations to installable hooks so the host can plug
in the real discovery layers as they land.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


#: Maximum number of discovery cache entries.
MAX_DISCOVERY_STORE_CACHE_ENTRIES: int = 64


#: Process-local cache. Mirrors ``DISCOVERY_STORE_CACHE``
#: (``model-discovery-cache.ts:44``).
_DISCOVERY_STORE_CACHE: Dict[str, Dict[str, Any]] = {}
_DISCOVERY_CACHE_LOCK = threading.Lock()


#: File-fingerprint hook. The OpenClaw source uses
#: :func:`statSync` to read ``mtimeMs`` + ``size``. The Python port
#: delegates to an installable hook so the host can use ``os.stat``
#: or a real provider-catalog layer.
_FILE_FINGERPRINT: Callable[[str], Optional[Dict[str, Any]]] = (
    lambda pathname: _default_file_fingerprint(pathname)
)


def _default_file_fingerprint(pathname: str) -> Optional[Dict[str, Any]]:
    try:
        stat = os.stat(pathname)
    except OSError:
        return None
    mtime = getattr(stat, "st_mtime_ns", None)
    if mtime is None:
        mtime = int(stat.st_mtime * 1_000_000_000)
    mtime_ms = mtime / 1_000_000
    if not _is_finite(mtime_ms):
        return None
    return {"mtimeMs": mtime_ms, "size": stat.st_size}


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def set_file_fingerprint_hook(
    hook: Callable[[str], Optional[Dict[str, Any]]],
) -> None:
    """Install a custom file-fingerprint hook."""
    global _FILE_FINGERPRINT
    _FILE_FINGERPRINT = hook


#: Runtime-config cache-key hook. The OpenClaw source uses
#: :func:`resolveRuntimeConfigCacheKey` from
#: ``config/runtime-snapshot.js``. The Python port delegates to
#: an installable hook that defaults to ``None`` (no generation
#: signal).
_RUNTIME_CONFIG_CACHE_KEY: Callable[[Any], Any] = lambda _config: None


def set_runtime_config_cache_key_hook(
    hook: Callable[[Any], Any],
) -> None:
    """Install a custom runtime-config cache-key hook."""
    global _RUNTIME_CONFIG_CACHE_KEY
    _RUNTIME_CONFIG_CACHE_KEY = hook


#: Fresh-discovery hook. The host installs the real
#: :func:`discoverAuthStorage` + :func:`discoverModels``
#: implementation when the agent-model-discovery layer lands.
#: The default returns ``None`` placeholders so the cache flow
#: still works.
_FRESH_DISCOVERY: Callable[[str, Dict[str, Any], Any], Dict[str, Any]] = (
    lambda _agent_dir, _options, _snapshot: {
        "authStorage": None,
        "modelRegistry": None,
    }
)


def set_fresh_discovery_hook(
    hook: Callable[[str, Dict[str, Any], Any], Dict[str, Any]],
) -> None:
    """Install a custom fresh-discovery hook."""
    global _FRESH_DISCOVERY
    _FRESH_DISCOVERY = hook


#: Plugin-metadata-snapshot resolver. The host installs the real
#: implementation when the plugin-metadata layer lands. The
#: default returns ``None``.
_RESOLVE_PLUGIN_METADATA_SNAPSHOT: Callable[[Dict[str, Any]], Any] = (
    lambda _options: None
)


def set_resolve_plugin_metadata_snapshot_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom plugin-metadata-snapshot resolver hook."""
    global _RESOLVE_PLUGIN_METADATA_SNAPSHOT
    _RESOLVE_PLUGIN_METADATA_SNAPSHOT = hook


#: Plugin model catalog file lister. The host installs the real
#: implementation when the plugin-model-catalog layer lands.
#: The default returns an empty list.
_LIST_PLUGIN_MODEL_CATALOG_FILES: Callable[[str], List[Any]] = (
    lambda _agent_dir: []
)


def set_list_plugin_model_catalog_files_hook(
    hook: Callable[[str], List[Any]],
) -> None:
    """Install a custom plugin-model-catalog file lister."""
    global _LIST_PLUGIN_MODEL_CATALOG_FILES
    _LIST_PLUGIN_MODEL_CATALOG_FILES = hook


#: Runtime-auth profile source check. The host installs the real
#: implementation when the auth-profiles layer lands. The
#: default returns ``False``.
_HAS_RUNTIME_AUTH_PROFILE_SOURCE: Callable[[str], bool] = lambda _agent_dir: False


def set_has_runtime_auth_profile_source_hook(
    hook: Callable[[str], bool],
) -> None:
    """Install a custom runtime-auth-profile-source check hook."""
    global _HAS_RUNTIME_AUTH_PROFILE_SOURCE
    _HAS_RUNTIME_AUTH_PROFILE_SOURCE = hook


#: Synthetic-auth provider refs. The host installs the real
#: implementation when the synthetic-auth layer lands. The
#: default returns an empty list.
_RUNTIME_SYNTHETIC_AUTH_PROVIDER_REFS: Callable[[], List[Any]] = list


def set_runtime_synthetic_auth_provider_refs_hook(
    hook: Callable[[], List[Any]],
) -> None:
    """Install a custom runtime-synthetic-auth provider-refs hook."""
    global _RUNTIME_SYNTHETIC_AUTH_PROVIDER_REFS
    _RUNTIME_SYNTHETIC_AUTH_PROVIDER_REFS = hook


#: External-auth provider refs. The host installs the real
#: implementation when the synthetic-auth layer lands. The
#: default returns an empty list.
_RUNTIME_EXTERNAL_AUTH_PROVIDER_REFS: Callable[[], List[Any]] = list


def set_runtime_external_auth_provider_refs_hook(
    hook: Callable[[], List[Any]],
) -> None:
    """Install a custom runtime-external-auth provider-refs hook."""
    global _RUNTIME_EXTERNAL_AUTH_PROVIDER_REFS
    _RUNTIME_EXTERNAL_AUTH_PROVIDER_REFS = hook


def _normalize_cache_dir(dirname: Optional[str]) -> Optional[str]:
    """Resolve ``dirname`` to an absolute path.

    Mirrors :func:`normalizeCacheDir``
    (``model-discovery-cache.ts:56-58``).
    """
    if not dirname:
        return None
    return os.path.abspath(dirname)


def _auth_fingerprint(agent_dir: str) -> Dict[str, Any]:
    """Return the auth-file fingerprint for ``agent_dir``.

    Mirrors :func:`authFingerprint``
    (``model-discovery-cache.ts:60-65``).
    """
    return {
        "authProfilesSqlite": _FILE_FINGERPRINT(
            os.path.join(agent_dir, "openclaw-agent.sqlite")
        ),
        "authProfilesSqliteWal": _FILE_FINGERPRINT(
            os.path.join(agent_dir, "openclaw-agent.sqlite-wal")
        ),
    }


def _plugin_model_catalog_fingerprint(
    agent_dir: str,
) -> List[Tuple[str, Optional[Dict[str, Any]]]]:
    """Return the plugin-model-catalog file fingerprint list.

    Mirrors :func:`pluginModelCatalogFingerprint``
    (``model-discovery-cache.ts:67-74``).
    """
    return [
        (
            getattr(catalog_file, "relativePath", str(catalog_file)),
            _FILE_FINGERPRINT(getattr(catalog_file, "path", str(catalog_file))),
        )
        for catalog_file in _LIST_PLUGIN_MODEL_CATALOG_FILES(agent_dir)
    ]


def _plugin_metadata_fingerprint(snapshot: Any) -> Dict[str, Any]:
    """Return the plugin-metadata fingerprint.

    Mirrors :func:`pluginMetadataFingerprint``
    (``model-discovery-cache.ts:132-138``).
    """
    if snapshot is None:
        return {
            "configFingerprint": None,
            "policyHash": None,
            "workspaceDir": None,
        }
    if isinstance(snapshot, dict):
        return {
            "configFingerprint": snapshot.get("configFingerprint"),
            "policyHash": snapshot.get("policyHash"),
            "workspaceDir": snapshot.get("workspaceDir"),
        }
    return {
        "configFingerprint": getattr(snapshot, "configFingerprint", None),
        "policyHash": getattr(snapshot, "policyHash", None),
        "workspaceDir": getattr(snapshot, "workspaceDir", None),
    }


def _has_runtime_plugin_auth_sources() -> bool:
    """Return True if any runtime plugin auth sources are present.

    Mirrors :func:`hasRuntimePluginAuthSources``
    (``model-discovery-cache.ts:101-106``).
    """
    return (
        len(_RUNTIME_SYNTHETIC_AUTH_PROVIDER_REFS()) > 0
        or len(_RUNTIME_EXTERNAL_AUTH_PROVIDER_REFS()) > 0
    )


def _prune_discovery_store_cache() -> None:
    """Evict the oldest entries past the cap.

    Mirrors :func:`pruneDiscoveryStoreCache``
    (``model-discovery-cache.ts:108-120``).
    """
    if len(_DISCOVERY_STORE_CACHE) <= MAX_DISCOVERY_STORE_CACHE_ENTRIES:
        return
    overflow = len(_DISCOVERY_STORE_CACHE) - MAX_DISCOVERY_STORE_CACHE_ENTRIES
    sorted_entries = sorted(
        _DISCOVERY_STORE_CACHE.items(),
        key=lambda kv: kv[1].get("lastUsedAt", 0),
    )
    for key, _ in sorted_entries[:overflow]:
        _DISCOVERY_STORE_CACHE.pop(key, None)


def _discovery_fingerprint(
    agent_dir: str,
    inherited_auth_dir: Optional[str],
    config: Any,
    plugin_metadata_snapshot: Any,
) -> str:
    """Compute the discovery fingerprint.

    Mirrors :func:`discoveryFingerprint``
    (``model-discovery-cache.ts:76-99``).
    """
    return str(
        {
            "agentDir": agent_dir,
            "inheritedAuthDir": inherited_auth_dir,
            "localAuth": _auth_fingerprint(agent_dir),
            "inheritedAuth": _auth_fingerprint(inherited_auth_dir) if inherited_auth_dir else None,
            "modelsJson": _FILE_FINGERPRINT(
                os.path.join(agent_dir, "models.json")
            ),
            "runtimeConfig": (
                _RUNTIME_CONFIG_CACHE_KEY(config) if config is not None else None
            ),
            "pluginMetadata": _plugin_metadata_fingerprint(plugin_metadata_snapshot),
            "pluginModelCatalogs": _plugin_model_catalog_fingerprint(agent_dir),
        }
    )


def _resolve_plugin_metadata_snapshot_for_discovery(
    options: Dict[str, Any],
) -> Any:
    """Resolve the plugin-metadata snapshot for discovery.

    Mirrors :func:`resolvePluginMetadataSnapshotForDiscovery``
    (``model-discovery-cache.ts:122-130``).
    """
    return _RESOLVE_PLUGIN_METADATA_SNAPSHOT(options)


def _discover_fresh_agent_stores(
    agent_dir: str,
    options: Dict[str, Any],
    plugin_metadata_snapshot: Any,
) -> Dict[str, Any]:
    """Discover auth/model stores from scratch.

    Mirrors :func:`discoverFreshAgentStores``
    (``model-discovery-cache.ts:140-155``).
    """
    return _FRESH_DISCOVERY(agent_dir, options, plugin_metadata_snapshot)


def discover_cached_agent_stores(
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """Discover auth/model stores, reusing file-backed snapshots.

    Mirrors :func:`discoverCachedAgentStores``
    (``model-discovery-cache.ts:158-201``).
    """
    agent_dir_raw = options.get("agentDir", "")
    agent_dir = _normalize_cache_dir(agent_dir_raw) or agent_dir_raw
    inherited_auth_dir = _normalize_cache_dir(options.get("inheritedAuthDir"))
    if (
        _HAS_RUNTIME_AUTH_PROFILE_SOURCE(agent_dir)
        or _has_runtime_plugin_auth_sources()
    ):
        # Runtime profile sources are process-owned state — fresh
        # discovery preserves provider/auth changes made during the
        # same long-lived process.
        return _discover_fresh_agent_stores(
            agent_dir,
            options,
            _resolve_plugin_metadata_snapshot_for_discovery(options),
        )
    plugin_metadata_snapshot = _resolve_plugin_metadata_snapshot_for_discovery(
        options
    )
    cache_key = str({"agentDir": agent_dir, "inheritedAuthDir": inherited_auth_dir})
    fingerprint = _discovery_fingerprint(
        agent_dir,
        inherited_auth_dir,
        options.get("config"),
        plugin_metadata_snapshot,
    )
    with _DISCOVERY_CACHE_LOCK:
        cached = _DISCOVERY_STORE_CACHE.get(cache_key)
        if cached and cached.get("fingerprint") == fingerprint:
            cached["lastUsedAt"] = int(time.time() * 1000)
            return {
                "authStorage": cached.get("authStorage"),
                "modelRegistry": cached.get("modelRegistry"),
            }
        stores = _discover_fresh_agent_stores(
            agent_dir, options, plugin_metadata_snapshot
        )
        _DISCOVERY_STORE_CACHE[cache_key] = {
            "authStorage": stores.get("authStorage"),
            "fingerprint": fingerprint,
            "lastUsedAt": int(time.time() * 1000),
            "modelRegistry": stores.get("modelRegistry"),
        }
        _prune_discovery_store_cache()
    return stores


def reset_model_discovery_cache_for_test() -> None:
    """Clear the process-local discovery cache.

    Mirrors :func:`resetModelDiscoveryCacheForTest``
    (``model-discovery-cache.ts:204-206``).
    """
    with _DISCOVERY_CACHE_LOCK:
        _DISCOVERY_STORE_CACHE.clear()


__all__ = [
    "MAX_DISCOVERY_STORE_CACHE_ENTRIES",
    "discover_cached_agent_stores",
    "reset_model_discovery_cache_for_test",
    "set_file_fingerprint_hook",
    "set_fresh_discovery_hook",
    "set_has_runtime_auth_profile_source_hook",
    "set_list_plugin_model_catalog_files_hook",
    "set_resolve_plugin_metadata_snapshot_hook",
    "set_runtime_config_cache_key_hook",
    "set_runtime_external_auth_provider_refs_hook",
    "set_runtime_synthetic_auth_provider_refs_hook",
]
