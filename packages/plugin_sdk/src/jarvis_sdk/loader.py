"""Canonical plugin discovery and loading engine.

Mirrors OpenClaw's ``src/plugins/discovery.ts`` (~1.7K LOC) and the
host bootstrap pattern. This is the **single source of truth** for how
JARVIS finds and activates plugins — both the desktop and CLI apps call
this instead of maintaining their own hand-rolled loaders.

Discovery order (mirrors OpenClaw's priority):
  1. Scan ``extensions/*/openclaw.plugin.json`` (bundled plugins).
  2. Validate manifest JSON shape.
    3. Import the manifest ``entrypoint`` and read its exported entry attr.
  4. Build a ``PluginApi`` per plugin and call ``entry.register(api)``.
  5. Collect all registrations into a ``LoadResult``.
  6. Return ``LoadResult`` — the host wires it into its subsystems.

The host is responsible for:
  - Creating a ``HookBus`` and calling ``bus.register_all(result.hooks)``.
  - Routing tool calls through ``result.plugin_dispatch``.
  - Wiring ``result.channel`` into the channel router.
  - Registering ``result.http_handlers`` with the gateway.

Invariants (mirrors OpenClaw's AGENTS.md rules):
  - One ``PluginApi`` per plugin; call ``register`` exactly once.
  - Plugin exceptions are isolated — one bad plugin never stops others.
  - Manifest validation failures emit warnings; the plugin is skipped.
  - The channel slot is single-active (last ``on_startup`` channel wins).
"""

from __future__ import annotations

import importlib
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ManifestDict = dict[str, Any]

_log = logging.getLogger("jarvis_sdk.loader")

# Manifest filename — canonical across the codebase.
# OpenClaw uses ``openclaw.plugin.json``; we preserve the same name so
# the vendored tree and live extensions share the same convention.
MANIFEST_FILENAME = "openclaw.plugin.json"

# Activation values that cause a plugin to load at host startup.
_STARTUP_ACTIVATIONS = {"always", "on_startup"}


# ── Load result ────────────────────────────────────────────────────────


@dataclass
class LoadResult:
    """All registrations gathered from a full plugin discovery pass.

    Mirrors the tuple returned by the legacy ``_load_plugins()`` helper in
    ``apps/desktop/src/jarvis_desktop/app.py``, but as a named dataclass
    so callers can add fields without breaking the call-sites.

    Attributes
    ----------
    tool_decls : list[dict]
        Gemini-formatted tool declaration dicts (``{name, description,
        parameters}``), ready to pass to the LLM client.
    plugin_dispatch : dict[str, tuple]
        Maps ``tool_name -> (tool_instance, tool_name)`` for call routing.
    commands : list
        ``CommandDecl`` objects from every plugin.
    cli_handlers : list[tuple]
        ``(name, handler)`` CLI sub-command registrations.
    skills : list
        ``SkillDecl`` objects from every plugin.
    hooks : list[HookRegistration]
        Hook registrations to feed into ``HookBus.register_all()``.
    cron_jobs : list[CronDecl]
        Scheduled job declarations.
    doctor_contracts : list[dict]
        Raw doctor contract dicts for ``jarvis doctor``.
    http_handlers : list[dict]
        HTTP route registrations for the gateway.
    channel : dict | None
        Single-active channel plugin registration (last writer wins).
    plugin_count : int
        Number of successfully loaded plugins.
    skipped : list[str]
        Extension ids that failed to load (for diagnostic output).
    """

    tool_decls: list[dict[str, Any]] = field(default_factory=list)
    plugin_dispatch: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    commands: list[Any] = field(default_factory=list)
    cli_handlers: list[tuple[Any, Any, Any, Any]] = field(default_factory=list)
    skills: list[Any] = field(default_factory=list)
    hooks: list[Any] = field(default_factory=list)
    cron_jobs: list[Any] = field(default_factory=list)
    doctor_contracts: list[dict[str, Any]] = field(default_factory=list)
    http_handlers: list[dict[str, Any]] = field(default_factory=list)
    gateway_methods: list[dict[str, Any]] = field(default_factory=list)
    channel: dict[str, Any] | None = None
    plugin_count: int = 0
    skipped: list[str] = field(default_factory=list)


# ── Manifest validation ────────────────────────────────────────────────


def _read_manifest(manifest_path: Path) -> ManifestDict | None:
    """Read and minimally validate ``openclaw.plugin.json``.

    Returns the parsed dict on success, ``None`` on failure (which causes
    the extension to be skipped with a warning).
    """
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as e:
        _log.warning("loader: cannot read %s: %s", manifest_path, e)
        return None

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        _log.warning("loader: invalid JSON in %s: %s", manifest_path, e)
        return None

    if not isinstance(obj, dict):
        _log.warning("loader: manifest %s is not a JSON object", manifest_path)
        return None

    if "id" not in obj:
        _log.warning("loader: manifest %s missing required field 'id'", manifest_path)
        return None

    return obj


def _normalize_activation(manifest: ManifestDict) -> str:
    """Normalize OpenClaw-style plugin activation values."""
    activation = manifest.get("activation", "on_demand")
    if isinstance(activation, str):
        return activation
    if isinstance(activation, dict):
        if activation.get("always") is True:
            return "always"
        if activation.get("onStartup") is True or activation.get("on_startup") is True:
            return "on_startup"
        return "on_demand"
    return "on_demand"


# ── Tool declaration builder ───────────────────────────────────────────


def _build_tool_decl(tool_decl: Any) -> dict | None:
    """Convert a ``ToolDecl`` (or duck-typed object) to a Gemini tool dict.

    Returns ``None`` if the object doesn't have the required shape.
    This mirrors the conversion in the legacy ``_load_plugins()`` helper
    so the LLM receives the same format as before.
    """
    if not (hasattr(tool_decl, "name") and hasattr(tool_decl, "parameters")):
        return None

    params: dict[str, Any] = {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    }
    for p in getattr(tool_decl, "parameters", []):
        params["properties"][p.name] = {
            "type": getattr(p, "type", "string").upper(),
            "description": getattr(p, "description", ""),
        }
        if getattr(p, "required", False):
            params["required"].append(p.name)

    return {
        "name": tool_decl.name,
        "description": getattr(tool_decl, "description", ""),
        "parameters": params,
    }


# ── Per-extension loading ──────────────────────────────────────────────


def _load_one_extension(
    ext_name: str,
    manifest: ManifestDict,
    workspace: Path,
    result: LoadResult,
) -> bool:
    """Import one extension and merge its registrations into ``result``.

    Returns ``True`` on success, ``False`` if the extension should be skipped.
    Mirrors OpenClaw's per-plugin load sequence in ``discovery.ts``.
    """
    from .api import PluginApi
    from .context import PluginContext

    # Step 1 — import the extension module.
    try:
        module = importlib.import_module(f"extensions.{ext_name}")
    except ImportError as e:
        _log.warning("loader: cannot import extensions.%s: %s", ext_name, e)
        return False

    # Step 2 — resolve the manifest entrypoint when present. Bundled
    # extensions may keep a package-level ``entry`` alias, while OpenClaw-
    # shaped manifests point directly at ``module:attribute``.
    entry = None
    entrypoint: Any = manifest.get("entrypoint")
    if isinstance(entrypoint, str) and ":" in entrypoint:
        module_name, attribute_name = entrypoint.split(":", 1)
        if module_name.startswith("src."):
            module_name = f"extensions.{ext_name}.{module_name}"
        try:
            entry = getattr(importlib.import_module(module_name), attribute_name)
        except (ImportError, AttributeError) as e:
            _log.warning("loader: cannot resolve %s entrypoint %r: %s", ext_name, entrypoint, e)
            return False
    if entry is None:
        entry = getattr(module, "entry", None)
    if entry is None:
        _log.warning(
            "loader: extensions.%s has no 'entry' attribute; skipping",
            ext_name,
        )
        return False

    # Step 3 — build context + api.
    ctx = PluginContext(
        plugin_id=str(getattr(entry, "id", manifest.get("id", ext_name))),
        plugin_kind=str(getattr(entry, "kind", manifest.get("kind", "unknown"))),
        data_dir=Path.home() / ".jarvis" / "extensions" / ext_name,
        workspace=workspace,
    )
    api = PluginApi(ctx)

    # Validate contracts.tools against manifest (mirrors OpenClaw's
    # ``PluginContext.set_manifest`` contract from Phase 4.3h).
    try:
        api.set_manifest(manifest)
    except Exception as e:  # noqa: BLE001
        _log.warning("loader: %s set_manifest() error: %s", ext_name, e)

    # Step 4 — call register(api).
    try:
        entry.register(api)
    except Exception as e:  # noqa: BLE001
        _log.warning("loader: %s.register() raised: %s", ext_name, e)
        return False

    # Step 5 — collect registrations.

    # Tools: convert ToolDecl instances to Gemini-format dicts.
    for tool_inst in api.tool_instances:
        # tool_inst may be a ToolDecl directly or an object with a .tools list.
        decls = getattr(tool_inst, "tools", None)
        if decls is None:
            # Duck-typed single tool.
            decl_dict = _build_tool_decl(tool_inst)
            if decl_dict:
                result.tool_decls.append(decl_dict)
                result.plugin_dispatch[decl_dict["name"]] = (tool_inst, decl_dict["name"])
        else:
            for td in decls:
                decl_dict = _build_tool_decl(td)
                if decl_dict:
                    result.tool_decls.append(decl_dict)
                    result.plugin_dispatch[decl_dict["name"]] = (tool_inst, decl_dict["name"])

    result.commands.extend(api.commands)
    result.cli_handlers.extend(api.cli_handlers)
    result.skills.extend(api.skills)
    result.hooks.extend(api.hooks)
    result.cron_jobs.extend(api.cron_jobs)
    result.doctor_contracts.extend(api.doctor_contracts)
    result.http_handlers.extend(api.http_handlers)
    result.gateway_methods.extend(api.gateway_methods)

    # Channel is single-active-slot (last on_startup channel wins).
    # Mirrors OpenClaw's bundled channel precedence: the last registered
    # channel that has ``activation == "on_startup"`` becomes active.
    if api.channel is not None:
        result.channel = api.channel

    return True


# ── Public API ─────────────────────────────────────────────────────────


def load_all_plugins(
    extensions_root: Path,
    *,
    workspace: Path | None = None,
    only_startup: bool = False,
    extra_sys_paths: list[Path] | None = None,
) -> LoadResult:
    """Discover and activate every extension under ``extensions_root``.

    This is the canonical entry point. Both ``apps/desktop`` and
    ``apps/cli`` call this instead of their own hand-rolled loaders.

    Parameters
    ----------
    extensions_root : Path
        Absolute path to the ``extensions/`` directory.
    workspace : Path | None
        Workspace root (defaults to ``extensions_root.parent``).
    only_startup : bool
        If ``True``, only load plugins with ``activation == "always"``
        or ``activation == "on_startup"``. Mirrors OpenClaw's startup
        filter in ``discovery.ts``.
    extra_sys_paths : list[Path] | None
        Additional paths to prepend to ``sys.path`` before importing.
        Useful for headless CLI contexts where the workspace root is not
        already on the path.

    Returns
    -------
    LoadResult
        All collected registrations. The caller is responsible for wiring
        them into the appropriate host subsystems.
    """
    ws = workspace or extensions_root.parent

    # Ensure the workspace root and src/ are importable so
    # ``import extensions.X`` and ``import src.Y`` work regardless of
    # where the process was started. This mirrors the desktop host's
    # bootstrap path and the CLI ``sys.path.insert`` block.
    _ensure_sys_path(ws, extra_sys_paths)

    if not extensions_root.exists():
        _log.debug("loader: extensions_root %s does not exist; returning empty", extensions_root)
        return LoadResult()

    result = LoadResult()

    manifest_paths = sorted(extensions_root.glob(f"*/{MANIFEST_FILENAME}"))
    _log.debug("loader: found %d manifests under %s", len(manifest_paths), extensions_root)

    for manifest_path in manifest_paths:
        ext_name = manifest_path.parent.name

        manifest = _read_manifest(manifest_path)
        if manifest is None:
            result.skipped.append(ext_name)
            continue

        # Activation filter.
        activation = _normalize_activation(manifest)
        if only_startup and activation not in _STARTUP_ACTIVATIONS:
            _log.debug("loader: skipping %s (activation=%s)", ext_name, activation)
            continue

        ok = _load_one_extension(ext_name, manifest, ws, result)
        if ok:
            result.plugin_count += 1
        else:
            result.skipped.append(ext_name)

    _log.info(
        "loader: loaded %d plugins (%d skipped) from %s",
        result.plugin_count,
        len(result.skipped),
        extensions_root,
    )
    if result.skipped:
        _log.warning("loader: skipped extensions: %s", ", ".join(result.skipped))

    return result


def load_all_plugins_from_workspace(workspace: Path, **kwargs: Any) -> LoadResult:
    """Convenience wrapper: infer ``extensions_root`` from ``workspace``.

    Equivalent to ``load_all_plugins(workspace / "extensions", workspace=workspace)``.
    """
    return load_all_plugins(
        workspace / "extensions",
        workspace=workspace,
        **kwargs,
    )


# ── Internal helpers ───────────────────────────────────────────────────


def _ensure_sys_path(workspace: Path, extra: list[Path] | None) -> None:
    """Prepend workspace paths to ``sys.path`` if not already present.

    Order (highest priority first):
      1. ``extra_sys_paths`` (caller-supplied)
      2. workspace root (so ``import extensions.X`` works)
      3. workspace/src (appended so stdlib logging is not shadowed)
    """
    candidates: list[Path] = []
    if extra:
        candidates.extend(extra)
    candidates.append(workspace)

    for p in candidates:
        s = str(p)
        if s not in sys.path:
            sys.path.append(s)

    src_p = workspace / "src"
    if src_p.exists() and str(src_p) not in sys.path:
        sys.path.append(str(src_p))



__all__ = [
    "MANIFEST_FILENAME",
    "LoadResult",
    "load_all_plugins",
    "load_all_plugins_from_workspace",
]
