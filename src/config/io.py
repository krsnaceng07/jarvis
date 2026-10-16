"""jarvis.config.io — stable public facade for config loading/snapshots/writes.

OpenClaw parity: mirrors ``openclaw-main/src/config/io.ts``.

Focused minimal port: re-exports the public config-IO surface. Heavy
runtime/snapshot work is delegated to caller-provided callables until
the corresponding subsystems land.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import hashlib
import os
from typing import Any


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

# Re-export selected surface items from the underlying config modules.
from src.config.env_substitution import MissingEnvVarError  # noqa: F401

# CircularIncludeError + ConfigIncludeError live in src.config.includes
# (a future port). For now we provide lightweight placeholders so the
# ``io`` facade can be imported without breaking.
class CircularIncludeError(Exception):
    """Raised when a config include cycle is detected (placeholder)."""


class ConfigIncludeError(Exception):
    """Raised when a config include fails to load (placeholder)."""

# Facade placeholders. The full set of exports lands incrementally as the
# corresponding io.* modules are ported.
from src.config.runtime_source_projection import (
    project_config_onto_runtime_source_snapshot as _project_config_onto_runtime_source_snapshot,
)
from src.config.shell_env_expected_keys import (
    resolve_shell_env_expected_keys as _resolve_shell_env_expected_keys,
)
from src.config.io_recovery import (
    recover_config_from_json_root_suffix_with_context as _recover_config_from_json_root_suffix_with_context,
)

def _strip_js_comments_and_trailing_commas(src: str) -> str:
    # Remove /* ... */ comments
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    # Remove // comments
    src = re.sub(r"//.*?$", "", src, flags=re.MULTILINE)
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


def create_config_io(*, config_path: str | Path | None = None, env: dict[str, Any] | None = None) -> Any:
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

        def loadConfig(self, loadOptions: dict | None = None) -> dict[str, Any]:
            path = Path(self.configPath) if self.configPath else Path(__file__).resolve().parents[2] / "config" / "jarvis.json"
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
            path = Path(self.configPath) if self.configPath else Path(__file__).resolve().parents[2] / "config" / "jarvis.json"
            return _build_config_file_snapshot(path)

        def writeConfigFile(self, config: dict[str, Any], *, indent: int = 2) -> None:
            path = Path(self.configPath) if self.configPath else Path(__file__).resolve().parents[2] / "config" / "jarvis.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(config, indent=indent, sort_keys=True), encoding="utf-8")

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


def _resolve_config_io_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
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
    path = Path(io.configPath) if io.configPath else Path(__file__).resolve().parents[2] / "config" / "jarvis.json"
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


def write_config_file(config: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
    io = _create_config_io_for_args(args, kwargs)
    return io.writeConfigFile(config)


def clear_config_cache(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
    return None


def preserve_config_snapshot_as_clobbered(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
    raise NotImplementedError("preserveConfigSnapshotAsClobbered facade")


def promote_config_snapshot_to_last_known_good(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("promoteConfigSnapshotToLastKnownGood facade")


async def recover_config_from_json_root_suffix(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover
    return await _recover_config_from_json_root_suffix_with_context(*args, **kwargs)


def recover_config_from_last_known_good(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover
    raise NotImplementedError("recoverConfigFromLastKnownGood facade")


def register_config_write_listener(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover
    raise NotImplementedError("registerConfigWriteListener facade")


def get_runtime_config(*args: Any, **kwargs: Any) -> dict[str, Any]:
    # Prefer an installed runtime hook if present.
    hook = get_installed_runtime_hook("get_runtime_config")
    if callable(hook):
        return hook(*args, **kwargs)

    # Preserve the original contract: when called with no explicit
    # arguments, indicate the runtime hook is required. If callers pass
    # explicit args/kwargs (e.g. a config_path), provide a conservative
    # fallback to read the runtime snapshot.
    if not args and not kwargs:
        raise NotImplementedError("getRuntimeConfig facade — install via runtime hooks")
    try:
        return get_runtime_config_snapshot(*args, **kwargs)
    except Exception:
        raise NotImplementedError("getRuntimeConfig facade — install via runtime hooks")


def load_config(*args, **kwargs) -> dict[str, Any]:
    # Prefer an installed runtime hook if present.
    hook = get_installed_runtime_hook("load_config")
    if callable(hook):
        return hook(*args, **kwargs)

    # Preserve original behavior for no-arg calls (runtime hook required).
    if not args and not kwargs:
        raise NotImplementedError("loadConfig facade — install via runtime hooks")
    try:
        io = _create_config_io_for_args(args, kwargs)
        return io.loadConfig()
    except Exception:
        raise NotImplementedError("loadConfig facade — install via runtime hooks")





def project_config_onto_runtime_source_snapshot(*args, **kwargs):  # pragma: no cover
    return _project_config_onto_runtime_source_snapshot(*args, **kwargs)


def clear_runtime_config_snapshot(*args, **kwargs):  # pragma: no cover
    return None


def _read_runtime_config_file() -> dict[str, Any]:
    config_path = Path(__file__).resolve().parents[2] / "config" / "jarvis.json"
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        parsed = json.load(handle)
        return parsed if isinstance(parsed, dict) else {}


def get_runtime_config_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:  # pragma: no cover
    snapshot = read_config_file_snapshot(*args, **kwargs)
    return snapshot.get("config", {}) if isinstance(snapshot, dict) else {}


def get_runtime_config_snapshot_metadata(*args, **kwargs):  # pragma: no cover
    config_path, _ = _resolve_config_io_args(args, kwargs)
    if config_path is None:
        config_path = Path(__file__).resolve().parents[2] / "config" / "jarvis.json"
    path = Path(config_path)
    return {
        "path": str(path),
        "exists": path.exists(),
    }


def get_runtime_config_source_snapshot(*args, **kwargs):  # pragma: no cover
    return get_runtime_config_snapshot(*args, **kwargs)


def register_managed_runtime_config_write_owner(*args, **kwargs):  # pragma: no cover
    hook = get_installed_runtime_hook("register_managed_runtime_config_write_owner") or get_installed_runtime_hook("registerManagedRuntimeConfigWriteOwner")
    if callable(hook):
        return hook(*args, **kwargs)
    raise NotImplementedError("registerManagedRuntimeConfigWriteOwner facade")


def reset_config_runtime_state(*args, **kwargs):  # pragma: no cover
    hook = get_installed_runtime_hook("reset_config_runtime_state") or get_installed_runtime_hook("resetConfigRuntimeState")
    if callable(hook):
        return hook(*args, **kwargs)
    raise NotImplementedError("resetConfigRuntimeState facade")


def resolve_runtime_config_cache_key(*args, **kwargs):  # pragma: no cover
    hook = get_installed_runtime_hook("resolve_runtime_config_cache_key") or get_installed_runtime_hook("resolveRuntimeConfigCacheKey")
    if callable(hook):
        return hook(*args, **kwargs)
    raise NotImplementedError("resolveRuntimeConfigCacheKey facade")


def select_applicable_runtime_config(*args, **kwargs):  # pragma: no cover
    hook = get_installed_runtime_hook("select_applicable_runtime_config") or get_installed_runtime_hook("selectApplicableRuntimeConfig")
    if callable(hook):
        return hook(*args, **kwargs)
    raise NotImplementedError("selectApplicableRuntimeConfig facade")


def set_applied_runtime_config_snapshot(*args, **kwargs):  # pragma: no cover
    hook = get_installed_runtime_hook("set_applied_runtime_config_snapshot") or get_installed_runtime_hook("setAppliedRuntimeConfigSnapshot")
    if callable(hook):
        return hook(*args, **kwargs)
    raise NotImplementedError("setAppliedRuntimeConfigSnapshot facade")


def set_runtime_config_snapshot(*args, **kwargs):  # pragma: no cover
    hook = get_installed_runtime_hook("set_runtime_config_snapshot") or get_installed_runtime_hook("setRuntimeConfigSnapshot")
    if callable(hook):
        return hook(*args, **kwargs)
    raise NotImplementedError("setRuntimeConfigSnapshot facade")


def set_runtime_config_snapshot_refresh_handler(*args, **kwargs):  # pragma: no cover
    hook = get_installed_runtime_hook("set_runtime_config_snapshot_refresh_handler") or get_installed_runtime_hook("setRuntimeConfigSnapshotRefreshHandler")
    if callable(hook):
        return hook(*args, **kwargs)
    raise NotImplementedError("setRuntimeConfigSnapshotRefreshHandler facade")


def resolve_shell_env_expected_keys(*args, **kwargs):  # pragma: no cover
    return _resolve_shell_env_expected_keys(*args, **kwargs)


__all__ = [
    "MissingEnvVarError",
    "CircularIncludeError",
    "ConfigIncludeError",
    "create_config_io",
    "parse_config_json5",
    "resolve_config_snapshot_hash",
    "restore_env_changes_if_unchanged",
    "clear_config_cache",
    "get_runtime_config",
    "load_config",
    "preserve_config_snapshot_as_clobbered",
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
    "recover_config_from_json_root_suffix",
    "recover_config_from_last_known_good",
    "register_config_write_listener",
    "write_config_file",
    "project_config_onto_runtime_source_snapshot",
    "clear_runtime_config_snapshot",
    "get_runtime_config_snapshot",
    "get_runtime_config_snapshot_metadata",
    "get_runtime_config_source_snapshot",
    "register_managed_runtime_config_write_owner",
    "reset_config_runtime_state",
    "resolve_runtime_config_cache_key",
    "select_applicable_runtime_config",
    "set_applied_runtime_config_snapshot",
    "set_runtime_config_snapshot",
    "set_runtime_config_snapshot_refresh_handler",
    "resolve_shell_env_expected_keys",
]
