"""jarvis.config.io — stable public facade for config loading/snapshots/writes.

OpenClaw parity: mirrors ``openclaw-main/src/config/io.ts``.

Focused minimal port: re-exports the public config-IO surface. Heavy
runtime/snapshot work is delegated to caller-provided callables until
the corresponding subsystems land.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable

from src.config.env_substitution import MissingEnvVarError  # noqa: F401
from src.config.io_recovery import (
    recover_config_from_json_root_suffix_with_context as _recover_config_from_json_root_suffix_with_context,
)
from src.config.runtime_source_projection import (
    project_config_onto_runtime_source_snapshot as _project_config_onto_runtime_source_snapshot,
)
from src.config.shell_env_expected_keys import (
    resolve_shell_env_expected_keys as _resolve_shell_env_expected_keys,
)

# Runtime-installable hook map. Host runtime can call
# ``install_runtime_hooks({'get_runtime_config': fn, 'load_config': fn, ...})``
# to provide full runtime behavior without patching callers.
_RUNTIME_HOOKS: dict[str, Any] = {}


def install_runtime_hooks(hooks: dict[str, Any]) -> None:
    """Install runtime hook implementations into the config IO facade.

    The host runtime should call this during startup to provide
    authoritative implementations for functions such as
    ``get_runtime_config`` and ``load_config``.
    """
    if not isinstance(hooks, dict):
        return
    _RUNTIME_HOOKS.update(hooks)


def get_installed_runtime_hook(name: str):
    return _RUNTIME_HOOKS.get(name)


# CircularIncludeError + ConfigIncludeError live in src.config.includes
# (a future port). For now we provide lightweight placeholders so the
# ``io`` facade can be imported without breaking.
class CircularIncludeError(Exception):
    """Raised when a config include cycle is detected (placeholder)."""


class ConfigIncludeError(Exception):
    """Raised when a config include fails to load (placeholder)."""


def _strip_js_comments_and_trailing_commas(src: str) -> str:
    # Match either a quoted string or a comment to avoid stripping '//' inside URLs/strings
    pattern = r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|(/\*[\s\S]*?\*/|//[^\r\n]*)'

    def replacer(match: re.Match) -> str:
        if match.group(1) is not None:
            return match.group(1)
        return ""

    src = re.sub(pattern, replacer, src)
    # Heuristic: remove trailing commas before closing ] or }
    src = re.sub(r",\s*(\]|\})", r"\1", src)
    return src


def parse_config_json5(raw: str) -> dict[str, Any]:
    """Parse a JSON5-like string into a Python dict.

    Attempts to use the `json5` package if available; otherwise falls
    back to a conservative sanitizer that strips JS-style comments and
    trailing commas and then parses with the stdlib `json`.
    """
    if raw is None:
        return {}
    try:
        import json5  # type: ignore

        return json5.loads(raw)
    except Exception:
        sanitized = _strip_js_comments_and_trailing_commas(raw)
        return json.loads(sanitized)


_CONFIG_WRITE_LISTENERS: list[Callable[[dict[str, Any]], None]] = []


def _notify_config_write_listeners(config: dict[str, Any]) -> None:
    for listener in list(_CONFIG_WRITE_LISTENERS):
        try:
            listener(config)
        except Exception:
            pass


def resolve_canonical_config_path(config_path: str | Path | None = None) -> Path:
    """Resolve the canonical JSON config file path."""
    if config_path:
        return Path(config_path)
    env_path = os.environ.get("JARVIS_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    env_data = os.environ.get("JARVIS_DATA_DIR")
    if env_data:
        return Path(env_data) / "config" / "jarvis.json"
    return Path(__file__).resolve().parents[2] / "config" / "jarvis.json"


def create_config_io(
    *, config_path: str | Path | None = None, env: dict[str, Any] | None = None
) -> Any:
    """Create a minimal config-IO facade suitable for lightweight use.

    This is a conservative, safe implementation that supports basic
    read/write of a JSON/JSON5-like `jarvis.json` config file. It is
    intentionally small so other subsystems can import `src.config.io`
    without runtime errors; it is not a full OpenClaw parity port yet.
    """

    class _ConfigIO:
        def __init__(self, config_path: Path | None, env: dict | None):
            self.configPath = str(config_path) if config_path is not None else ""
            self.env = env if env is not None else os.environ

        def _get_path(self) -> Path:
            return resolve_canonical_config_path(self.configPath)

        def loadConfig(self, loadOptions: dict | None = None) -> dict[str, Any]:
            path = self._get_path()
            if not path.exists():
                return {}
            text = path.read_text(encoding="utf-8")
            try:
                return parse_config_json5(text)
            except Exception:
                # Fallback: return empty on parse failure to avoid large breakage.
                return {}

        def readBestEffortConfig(self) -> dict[str, Any]:
            return self.loadConfig()

        def readSourceConfigBestEffort(self) -> dict[str, Any]:
            return self.loadConfig()

        def readConfigFileSnapshot(self) -> dict[str, Any]:
            path = self._get_path()
            return _build_config_file_snapshot(path)

        def writeConfigFile(self, config: dict[str, Any], *, indent: int = 2) -> None:
            path = self._get_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(config, indent=indent, sort_keys=True), encoding="utf-8")
            _notify_config_write_listeners(config)

    return _ConfigIO(Path(config_path) if config_path is not None else None, env)


def resolve_config_snapshot_hash(snapshot: dict | None) -> str | None:
    """Resolve a stable hash for a config snapshot dict with optional 'hash' or 'raw'."""
    if not snapshot:
        return None
    if isinstance(snapshot.get("hash"), str):
        trimmed = snapshot["hash"].strip()
        if trimmed:
            return trimmed
    raw = snapshot.get("raw")
    if not isinstance(raw, str):
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def restore_env_changes_if_unchanged(env: dict, before: dict, after: dict) -> None:
    """Restore environment `env` to `before` values for keys that were unchanged by external actors.

    The function updates `env` in-place.
    """
    keys = set(list(before.keys()) + list(after.keys()))
    for key in keys:
        if before.get(key) == after.get(key) or env.get(key) != after.get(key):
            continue
        prev = before.get(key)
        if prev is None:
            if key in env:
                del env[key]
        else:
            env[key] = prev


def _normalize_config_path(config_path: str | Path | None) -> str | None:
    if config_path is None:
        return None
    return str(config_path)


def _resolve_config_io_args(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[str | None, dict[str, Any] | None]:
    config_path: str | Path | None = None
    if args:
        first = args[0]
        if isinstance(first, (str, Path)):
            config_path = first
    config_path = kwargs.get("config_path", kwargs.get("configPath", config_path))
    env = kwargs.get("env")
    return _normalize_config_path(config_path), env


def _create_config_io_for_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    config_path, env = _resolve_config_io_args(args, kwargs)
    return create_config_io(config_path=config_path, env=env)


def read_best_effort_config(*args: Any, **kwargs: Any) -> Any:
    io = _create_config_io_for_args(args, kwargs)
    return io.readBestEffortConfig()


def read_best_effort_config_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    io = _create_config_io_for_args(args, kwargs)
    try:
        cfg = io.readBestEffortConfig()
        return {"config": cfg, "sourceConfig": cfg, "raw": None}
    except Exception:
        return {"config": {}, "sourceConfig": {}, "raw": None}


def _build_config_file_snapshot(path: Path) -> dict[str, Any]:
    raw = None
    if path.exists():
        raw = path.read_text(encoding="utf-8")
    try:
        parsed = parse_config_json5(raw) if raw is not None else {}
        valid = True
    except Exception:
        parsed = {}
        valid = False
    config = parsed if isinstance(parsed, dict) else {}
    return {
        "path": str(path),
        "exists": path.exists(),
        "raw": raw,
        "hash": resolve_config_snapshot_hash({"raw": raw}),
        "config": config,
        "sourceConfig": config,
        "valid": valid,
        "issues": [],
        "warnings": [],
    }


def read_config_file_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    io = _create_config_io_for_args(args, kwargs)
    path = (
        Path(io.configPath)
        if io.configPath
        else Path(__file__).resolve().parents[2] / "config" / "jarvis.json"
    )
    return _build_config_file_snapshot(path)


def read_config_file_snapshot_for_write(*args: Any, **kwargs: Any) -> dict[str, Any]:
    snapshot = read_config_file_snapshot(*args, **kwargs)
    return {
        "config": snapshot["config"],
        "snapshot": snapshot,
        "writeOptions": {
            "assertConfigPathForWrite": lambda: None,
            "expectedConfigPath": snapshot["path"],
            "ownedConfigPathForWrite": snapshot["path"],
        },
    }


def read_config_file_snapshot_with_plugin_metadata(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {
        "snapshot": read_config_file_snapshot(*args, **kwargs),
        "pluginMetadataSnapshot": {},
    }


def read_source_config_best_effort(*args: Any, **kwargs: Any) -> dict[str, Any]:
    io = _create_config_io_for_args(args, kwargs)
    try:
        return io.readSourceConfigBestEffort()
    except Exception:
        return {}


def read_source_config_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return read_config_file_snapshot(*args, **kwargs)


def read_source_config_snapshot_for_write(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return read_config_file_snapshot_for_write(*args, **kwargs)


def read_config_file_snapshot_for_runtime_transaction(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return read_config_file_snapshot(*args, **kwargs)


_CACHED_RUNTIME_CONFIG: dict[str, Any] | None = None
_RUNTIME_CONFIG_SNAPSHOT: dict[str, Any] | None = None
_APPLIED_RUNTIME_CONFIG_SNAPSHOT: dict[str, Any] | None = None
_MANAGED_WRITE_OWNER: Any = None
_REFRESH_HANDLER: Callable | None = None


def write_config_file(config: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
    global _CACHED_RUNTIME_CONFIG
    _CACHED_RUNTIME_CONFIG = dict(config)
    io = _create_config_io_for_args(args, kwargs)
    return io.writeConfigFile(config)


def clear_config_cache(*args: Any, **kwargs: Any) -> None:
    global _CACHED_RUNTIME_CONFIG
    _CACHED_RUNTIME_CONFIG = None


def preserve_config_snapshot_as_clobbered(*args: Any, **kwargs: Any) -> str | None:
    """Save a timestamped backup copy before config overwrite or repair."""
    hook = get_installed_runtime_hook(
        "preserve_config_snapshot_as_clobbered"
    ) or get_installed_runtime_hook("preserveConfigSnapshotAsClobbered")
    if callable(hook):
        return hook(*args, **kwargs)

    import datetime
    import shutil

    config_path, _ = _resolve_config_io_args(args, kwargs)
    path = resolve_canonical_config_path(config_path)
    if not path.exists():
        return None

    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    clobbered_path = path.parent / f"{path.stem}.clobbered.{timestamp}{path.suffix}.bak"
    clobbered_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, clobbered_path)
    return str(clobbered_path)


def promote_config_snapshot_to_last_known_good(*args: Any, **kwargs: Any) -> str | None:
    """Atomically promote validated config snapshot to last_known_good.json."""
    hook = get_installed_runtime_hook(
        "promote_config_snapshot_to_last_known_good"
    ) or get_installed_runtime_hook("promoteConfigSnapshotToLastKnownGood")
    if callable(hook):
        return hook(*args, **kwargs)

    import shutil

    config_path, _ = _resolve_config_io_args(args, kwargs)
    path = resolve_canonical_config_path(config_path)
    lkg_path = path.parent / f"{path.stem}.last_known_good{path.suffix}"
    lkg_path.parent.mkdir(parents=True, exist_ok=True)

    config_dict = None
    for a in args:
        if isinstance(a, dict):
            config_dict = a.get("config", a)
            break
    if "config" in kwargs and isinstance(kwargs["config"], dict):
        config_dict = kwargs["config"]

    if config_dict is not None and isinstance(config_dict, dict):
        lkg_path.write_text(json.dumps(config_dict, indent=2, sort_keys=True), encoding="utf-8")
        return str(lkg_path)

    if path.exists():
        shutil.copy2(path, lkg_path)
        return str(lkg_path)

    return None


async def recover_config_from_json_root_suffix(*args: Any, **kwargs: Any) -> Any:
    return await _recover_config_from_json_root_suffix_with_context(*args, **kwargs)


def recover_config_from_last_known_good(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Recover and restore config from last_known_good backup."""
    hook = get_installed_runtime_hook(
        "recover_config_from_last_known_good"
    ) or get_installed_runtime_hook("recoverConfigFromLastKnownGood")
    if callable(hook):
        return hook(*args, **kwargs)

    import shutil

    config_path, _ = _resolve_config_io_args(args, kwargs)
    path = resolve_canonical_config_path(config_path)
    lkg_path = path.parent / f"{path.stem}.last_known_good{path.suffix}"
    if not lkg_path.exists():
        return {}

    raw = lkg_path.read_text(encoding="utf-8")
    recovered = parse_config_json5(raw)
    if recovered:
        shutil.copy2(lkg_path, path)
        global _CACHED_RUNTIME_CONFIG
        _CACHED_RUNTIME_CONFIG = dict(recovered)
    return recovered if isinstance(recovered, dict) else {}


def register_config_write_listener(
    listener: Callable[[dict[str, Any]], None], *args: Any, **kwargs: Any
) -> Callable[[], None]:
    """Register a listener invoked whenever a config is written."""
    hook = get_installed_runtime_hook(
        "register_config_write_listener"
    ) or get_installed_runtime_hook("registerConfigWriteListener")
    if callable(hook):
        return hook(listener, *args, **kwargs)

    if callable(listener) and listener not in _CONFIG_WRITE_LISTENERS:
        _CONFIG_WRITE_LISTENERS.append(listener)

    def _unregister() -> None:
        if listener in _CONFIG_WRITE_LISTENERS:
            _CONFIG_WRITE_LISTENERS.remove(listener)

    return _unregister


def get_runtime_config(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Return active validated runtime config dictionary, caching in-memory."""
    hook = get_installed_runtime_hook("get_runtime_config") or get_installed_runtime_hook(
        "getRuntimeConfig"
    )
    if callable(hook):
        return hook(*args, **kwargs)

    global _CACHED_RUNTIME_CONFIG
    if _CACHED_RUNTIME_CONFIG is not None and not args and not kwargs:
        return _CACHED_RUNTIME_CONFIG

    config_path, _ = _resolve_config_io_args(args, kwargs)
    path = resolve_canonical_config_path(config_path)
    if path.exists():
        try:
            raw = path.read_text(encoding="utf-8")
            parsed = parse_config_json5(raw)
        except Exception:
            parsed = {}
    else:
        parsed = {}

    cfg = parsed if isinstance(parsed, dict) else {}
    if not args and not kwargs:
        _CACHED_RUNTIME_CONFIG = cfg
    return cfg


def load_config(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Load config from source or path."""
    hook = get_installed_runtime_hook("load_config") or get_installed_runtime_hook("loadConfig")
    if callable(hook):
        return hook(*args, **kwargs)

    config_path, env = _resolve_config_io_args(args, kwargs)
    path = resolve_canonical_config_path(config_path)
    io = create_config_io(config_path=path, env=env)
    return io.loadConfig()


def project_config_onto_runtime_source_snapshot(*args: Any, **kwargs: Any) -> Any:
    return _project_config_onto_runtime_source_snapshot(*args, **kwargs)


def clear_runtime_config_snapshot(*args: Any, **kwargs: Any) -> None:
    global _RUNTIME_CONFIG_SNAPSHOT, _CACHED_RUNTIME_CONFIG
    _RUNTIME_CONFIG_SNAPSHOT = None
    _CACHED_RUNTIME_CONFIG = None


def _read_runtime_config_file() -> dict[str, Any]:
    path = resolve_canonical_config_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        parsed = json.load(handle)
        return parsed if isinstance(parsed, dict) else {}


def get_runtime_config_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    global _RUNTIME_CONFIG_SNAPSHOT
    if _RUNTIME_CONFIG_SNAPSHOT is not None and not args and not kwargs:
        return _RUNTIME_CONFIG_SNAPSHOT
    snapshot = read_config_file_snapshot(*args, **kwargs)
    return snapshot.get("config", {}) if isinstance(snapshot, dict) else {}


def get_runtime_config_snapshot_metadata(*args: Any, **kwargs: Any) -> dict[str, Any]:
    config_path, _ = _resolve_config_io_args(args, kwargs)
    path = resolve_canonical_config_path(config_path)
    return {
        "path": str(path),
        "exists": path.exists(),
    }


def get_runtime_config_source_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return get_runtime_config_snapshot(*args, **kwargs)


def register_managed_runtime_config_write_owner(*args: Any, **kwargs: Any) -> Any:
    hook = get_installed_runtime_hook(
        "register_managed_runtime_config_write_owner"
    ) or get_installed_runtime_hook("registerManagedRuntimeConfigWriteOwner")
    if callable(hook):
        return hook(*args, **kwargs)
    global _MANAGED_WRITE_OWNER
    _MANAGED_WRITE_OWNER = args[0] if args else kwargs.get("owner")
    return lambda: None


def reset_config_runtime_state(*args: Any, **kwargs: Any) -> None:
    hook = get_installed_runtime_hook("reset_config_runtime_state") or get_installed_runtime_hook(
        "resetConfigRuntimeState"
    )
    if callable(hook):
        return hook(*args, **kwargs)
    global \
        _CACHED_RUNTIME_CONFIG, \
        _RUNTIME_CONFIG_SNAPSHOT, \
        _APPLIED_RUNTIME_CONFIG_SNAPSHOT, \
        _MANAGED_WRITE_OWNER
    _CACHED_RUNTIME_CONFIG = None
    _RUNTIME_CONFIG_SNAPSHOT = None
    _APPLIED_RUNTIME_CONFIG_SNAPSHOT = None
    _MANAGED_WRITE_OWNER = None


def resolve_runtime_config_cache_key(*args: Any, **kwargs: Any) -> str:
    hook = get_installed_runtime_hook(
        "resolve_runtime_config_cache_key"
    ) or get_installed_runtime_hook("resolveRuntimeConfigCacheKey")
    if callable(hook):
        return hook(*args, **kwargs)
    config_path, _ = _resolve_config_io_args(args, kwargs)
    path = resolve_canonical_config_path(config_path)
    if path.exists():
        try:
            return f"{path}:{path.stat().st_mtime_ns}"
        except Exception:
            return f"{path}:present"
    return f"{path}:missing"


def select_applicable_runtime_config(*args: Any, **kwargs: Any) -> dict[str, Any]:
    hook = get_installed_runtime_hook(
        "select_applicable_runtime_config"
    ) or get_installed_runtime_hook("selectApplicableRuntimeConfig")
    if callable(hook):
        return hook(*args, **kwargs)
    if args and isinstance(args[0], dict):
        if "config" in args[0]:
            return args[0]["config"]
        return args[0]
    return get_runtime_config()


def set_applied_runtime_config_snapshot(*args: Any, **kwargs: Any) -> None:
    hook = get_installed_runtime_hook(
        "set_applied_runtime_config_snapshot"
    ) or get_installed_runtime_hook("setAppliedRuntimeConfigSnapshot")
    if callable(hook):
        return hook(*args, **kwargs)
    global _APPLIED_RUNTIME_CONFIG_SNAPSHOT
    _APPLIED_RUNTIME_CONFIG_SNAPSHOT = args[0] if args else kwargs.get("snapshot")


def set_runtime_config_snapshot(*args: Any, **kwargs: Any) -> None:
    hook = get_installed_runtime_hook("set_runtime_config_snapshot") or get_installed_runtime_hook(
        "setRuntimeConfigSnapshot"
    )
    if callable(hook):
        return hook(*args, **kwargs)
    global _RUNTIME_CONFIG_SNAPSHOT
    _RUNTIME_CONFIG_SNAPSHOT = args[0] if args else kwargs.get("snapshot")


def set_runtime_config_snapshot_refresh_handler(*args: Any, **kwargs: Any) -> None:
    hook = get_installed_runtime_hook(
        "set_runtime_config_snapshot_refresh_handler"
    ) or get_installed_runtime_hook("setRuntimeConfigSnapshotRefreshHandler")
    if callable(hook):
        return hook(*args, **kwargs)
    global _REFRESH_HANDLER
    _REFRESH_HANDLER = args[0] if args else kwargs.get("handler")


# CamelCase aliases for OpenClaw parity
getRuntimeConfig = get_runtime_config
loadConfig = load_config
preserveConfigSnapshotAsClobbered = preserve_config_snapshot_as_clobbered
promoteConfigSnapshotToLastKnownGood = promote_config_snapshot_to_last_known_good
recoverConfigFromLastKnownGood = recover_config_from_last_known_good
registerConfigWriteListener = register_config_write_listener


def resolve_shell_env_expected_keys(*args: Any, **kwargs: Any) -> Any:
    return _resolve_shell_env_expected_keys(*args, **kwargs)


__all__ = [
    "CircularIncludeError",
    "ConfigIncludeError",
    "MissingEnvVarError",
    "clear_config_cache",
    "clear_runtime_config_snapshot",
    "create_config_io",
    "getRuntimeConfig",
    "get_runtime_config",
    "get_runtime_config_snapshot",
    "get_runtime_config_snapshot_metadata",
    "get_runtime_config_source_snapshot",
    "loadConfig",
    "load_config",
    "parse_config_json5",
    "preserveConfigSnapshotAsClobbered",
    "preserve_config_snapshot_as_clobbered",
    "project_config_onto_runtime_source_snapshot",
    "promoteConfigSnapshotToLastKnownGood",
    "promote_config_snapshot_to_last_known_good",
    "read_best_effort_config",
    "read_best_effort_config_snapshot",
    "read_config_file_snapshot",
    "read_config_file_snapshot_for_runtime_transaction",
    "read_config_file_snapshot_for_write",
    "read_config_file_snapshot_with_plugin_metadata",
    "read_source_config_best_effort",
    "read_source_config_snapshot",
    "read_source_config_snapshot_for_write",
    "recoverConfigFromLastKnownGood",
    "recover_config_from_json_root_suffix",
    "recover_config_from_last_known_good",
    "registerConfigWriteListener",
    "register_config_write_listener",
    "register_managed_runtime_config_write_owner",
    "reset_config_runtime_state",
    "resolve_config_snapshot_hash",
    "resolve_runtime_config_cache_key",
    "resolve_shell_env_expected_keys",
    "restore_env_changes_if_unchanged",
    "select_applicable_runtime_config",
    "set_applied_runtime_config_snapshot",
    "set_runtime_config_snapshot",
    "set_runtime_config_snapshot_refresh_handler",
    "write_config_file",
]
