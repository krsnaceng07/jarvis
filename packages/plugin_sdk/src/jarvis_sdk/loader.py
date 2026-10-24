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
import importlib.util
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .api import PluginApi
from .context import PluginContext
from .host import skills_to_prompt_section

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
    manifest_metadata : list[dict]
        Per-plugin manifest ownership facts (``id``/``kind``/``channels``/
        ``providers``/``cli_commands``/``has_doctor_contract``) so the host
        reads OpenClaw manifest metadata without per-id branches.
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
    manifest_metadata: list[dict[str, Any]] = field(default_factory=list)
    channels: dict[str, Any] = field(default_factory=dict)
    channel: dict[str, Any] | None = None
    plugin_count: int = 0
    skipped: list[str] = field(default_factory=list)
    # Bundle discovery results (OpenClaw parity: bundles run alongside natives)
    bundles: list[Any] = field(default_factory=list)  # list[BundleManifest]
    bundle_mcp_configs: list[Any] = field(default_factory=list)  # list[BundleMcpConfig]
    bundle_count: int = 0

    @property
    def plugins(self) -> list[dict[str, Any]]:
        """List of discovered plugin manifest metadata records."""
        return self.manifest_metadata

    @property
    def manifests(self) -> list[dict[str, Any]]:
        """List of discovered plugin manifest metadata records."""
        return self.manifest_metadata

    @property
    def tool_declarations(self) -> list[dict[str, Any]]:
        """Alias to tool_decls for OpenClaw parity."""
        return self.tool_decls

    @property
    def dispatch_table(self) -> dict[str, Any]:
        """Alias to plugin_dispatch for OpenClaw parity."""
        return self.plugin_dispatch


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
    if not hasattr(tool_decl, "name"):
        return None

    has_params = hasattr(tool_decl, "parameters")
    has_schema = hasattr(tool_decl, "schema")

    if not (has_params or has_schema):
        return None

    params: dict[str, Any] = {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    }

    schema_cls = getattr(tool_decl, "schema", None)
    raw_params = getattr(tool_decl, "parameters", None)

    if schema_cls and hasattr(schema_cls, "model_json_schema"):
        schema_dict = schema_cls.model_json_schema()
        for prop_name, prop_info in schema_dict.get("properties", {}).items():
            t = prop_info.get("type", "string").upper()
            # pydantic uses 'number' for float, but Gemini uses 'NUMBER'
            # pydantic uses 'integer' for int, Gemini uses 'INTEGER'
            params["properties"][prop_name] = {
                "type": t,
                "description": prop_info.get("description", ""),
            }
        params["required"] = schema_dict.get("required", [])
    elif isinstance(schema_cls, dict) and schema_cls:
        params = dict(schema_cls)
        if "type" in params and isinstance(params["type"], str):
            params["type"] = params["type"].upper()
        params.setdefault("type", "OBJECT")
        params.setdefault("properties", {})
        params.setdefault("required", [])
    elif raw_params is not None:
        if isinstance(raw_params, dict):
            params = dict(raw_params)
            if "type" in params and isinstance(params["type"], str):
                params["type"] = params["type"].upper()
            params.setdefault("type", "OBJECT")
            params.setdefault("properties", {})
            params.setdefault("required", [])
        elif isinstance(raw_params, (list, tuple)):
            for p in raw_params:
                if hasattr(p, "name"):
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
    registration_mode: str = "full",
) -> bool:
    """Import one extension and merge its registrations into ``result``.

    Returns ``True`` on success, ``False`` if the extension should be skipped.
    Mirrors OpenClaw's per-plugin load sequence in ``discovery.ts``.

    Parameters
    ----------
    registration_mode : str
        The OpenClaw-style registration scope to pass to ``PluginApi``.
        ``"full"`` (default) registers everything; other values gate
        what the plugin registers (see ``RegistrationMode``).
    """

    # Step 1 — import the extension module.
    module = None
    import_names = [f"extensions.{ext_name}"]
    if "-" in ext_name:
        import_names.append(f"extensions.{ext_name.replace('-', '_')}")
    last_err = None
    for name in import_names:
        try:
            module = importlib.import_module(name)
            break
        except ImportError as e:
            last_err = e

    if module is None:
        ext_dir = workspace / "extensions" / ext_name if workspace else None
        if ext_dir and ext_dir.exists():
            entry_file = (
                ext_dir / "plugin.py"
                if (ext_dir / "plugin.py").exists()
                else ext_dir / "__init__.py"
            )
            if entry_file.exists():
                try:
                    spec = importlib.util.spec_from_file_location(
                        f"extensions_{ext_name.replace('-', '_')}", entry_file
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[f"extensions.{ext_name.replace('-', '_')}"] = module
                        spec.loader.exec_module(module)
                except Exception as e:
                    last_err = e

    if module is None:
        _log.warning("loader: cannot import extensions.%s: %s", ext_name, last_err)
        return False

    # Step 2 — resolve the manifest entrypoint when present. Bundled
    # extensions may keep a package-level ``entry`` alias, while OpenClaw-
    # shaped manifests point directly at ``module:attribute``.
    entry = None
    entrypoint: Any = manifest.get("entrypoint")
    if isinstance(entrypoint, str) and ":" in entrypoint:
        module_name, attribute_name = entrypoint.split(":", 1)
        if module_name.startswith("src."):
            module_name = f"extensions.{ext_name.replace('-', '_')}.{module_name}"
            try:
                entry = getattr(importlib.import_module(module_name), attribute_name)
            except (ImportError, AttributeError) as e:
                _log.warning("loader: cannot resolve %s entrypoint %r: %s", ext_name, entrypoint, e)
                return False
        elif module_name in ("plugin", "plugin.py"):
            entry = getattr(module, attribute_name, None)
        else:
            try:
                entry = getattr(importlib.import_module(module_name), attribute_name)
            except (ImportError, AttributeError) as e:
                _log.warning("loader: cannot resolve %s entrypoint %r: %s", ext_name, entrypoint, e)
                return False
    if entry is None:
        entry = getattr(module, "entry", None) or getattr(module, "plugin", None)
    if entry is None and hasattr(module, "__path__"):
        try:
            plugin_submod = importlib.import_module(f"{module.__name__}.plugin")
            entry = getattr(plugin_submod, "entry", None) or getattr(plugin_submod, "plugin", None)
        except Exception:
            pass
    if entry is None:
        _log.warning(
            "loader: extensions.%s has no 'entry' or 'plugin' attribute; skipping",
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
    from ._plugin_api_init import RegistrationMode as _RM  # noqa: PLC0415

    # Cast to the Literal type — loader already validates caller-supplied values.
    _mode: _RM = (
        registration_mode
        if registration_mode in ("full", "cli-metadata", "discovery", "tool-discovery")
        else "full"
    )  # type: ignore[assignment]
    api = PluginApi(ctx, registration_mode=_mode)

    # Validate contracts.tools against manifest (mirrors OpenClaw's
    # ``PluginContext.set_manifest`` contract from Phase 4.3h).
    try:
        api.set_manifest(manifest)
    except Exception as e:  # noqa: BLE001
        _log.warning("loader: %s set_manifest() error: %s", ext_name, e)

    # Step 3.5 — evaluate Capability Ladder Contract.
    from .capability_ladder import CapabilityLadderContract, CapabilityTier  # noqa: PLC0415

    ladder_contract = CapabilityLadderContract.from_manifest(manifest)
    setattr(ctx, "capability_contract", ladder_contract)
    setattr(api, "capability_contract", ladder_contract)

    if ladder_contract.quarantined:
        _log.warning(
            "loader: %s quarantined by Capability Ladder: %s",
            ext_name,
            ladder_contract.quarantine_reason,
        )
        return False

    # Step 4 — call register(api).
    from .contract import ChannelPlugin, Plugin  # noqa: PLC0415

    target_register = None
    if isinstance(entry, dict):
        if "plugin" in entry and hasattr(entry["plugin"], "register"):
            target_register = entry["plugin"].register
        elif "register" in entry and callable(entry["register"]):
            target_register = entry["register"]
    elif hasattr(entry, "register") and callable(entry.register):
        if getattr(entry.register, "__func__", None) is Plugin.register:
            # Entry inherits base Plugin.register without overriding it.
            # Check if it is a ChannelPlugin or other declarative component first.
            target_register = None
        else:
            target_register = entry.register
    elif callable(entry):
        target_register = entry

    if target_register is None:
        # Check if entry is a ChannelPlugin or channel descriptor
        is_channel = (
            isinstance(entry, ChannelPlugin)
            or getattr(entry, "kind", None) == "channel"
            or manifest.get("kind") == "channel"
            or bool(manifest.get("channels"))
            or hasattr(entry, "send")
            or (isinstance(entry, dict) and "channel" in entry)
        )
        if is_channel:
            channel_obj = (
                entry.get("channel") if isinstance(entry, dict) and "channel" in entry else entry
            )

            def _reg_channel(a: Any, c: Any = channel_obj) -> None:
                a.register_channel(c)

            target_register = _reg_channel
        elif isinstance(entry, dict) and "speechProviders" in entry:

            def _reg_speech(a: Any, ent: dict[str, Any] = entry) -> None:
                for sp in ent.get("speechProviders", []):
                    if hasattr(a, "register_speech_provider"):
                        a.register_speech_provider(sp)

            target_register = _reg_speech
        else:
            fallback_reg = getattr(entry, "register", None)
            if callable(fallback_reg):
                target_register = fallback_reg
            elif (
                ladder_contract.granted_tier == CapabilityTier.TIER_0_METADATA_ONLY
                or manifest.get("kind") in ("skill", "migration")
                or not manifest.get("tools")
            ):
                # Declarative / metadata-only plugin: gracefully registered
                target_register = lambda _api: None

    if target_register is None:
        _log.debug("loader: %s has no callable register method; skipping", ext_name)
        return False

    try:
        target_register(api)
    except Exception as e:  # noqa: BLE001
        _log.debug("loader: %s.register() raised: %s", ext_name, e)
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

    result.manifest_metadata.append(
        {
            "id": manifest.get("id", ext_name),
            "kind": manifest.get("kind"),
            "channels": api.manifest_channels,
            "providers": api.manifest_providers,
            "cli_commands": api.manifest_cli_commands,
            "has_doctor_contract": api.manifest_doctor_contract is not None,
        }
    )
    result.commands.extend(api.commands)
    result.cli_handlers.extend(api.cli_handlers)
    result.skills.extend(api.skills)
    result.hooks.extend(api.hooks)
    result.cron_jobs.extend(api.cron_jobs)
    result.doctor_contracts.extend(api.doctor_contracts)
    result.http_handlers.extend(api.http_handlers)
    result.gateway_methods.extend(api.gateway_methods)

    # Channels: collect into channels dict for multi-channel concurrent execution.
    # Single-active `channel` property is preserved for backward compatibility.
    if api.channel is not None:
        result.channel = api.channel
        ch_id = str(api.channel.get("id") or manifest.get("id") or ext_name)
        result.channels[ch_id] = api.channel

    return True


# ── Bundle loading ────────────────────────────────────────────────────────


def _load_one_bundle(
    ext_dir: Path,
    bundle_format: Any,
    workspace: Path,
    result: "LoadResult",
) -> bool:
    """Load a single bundle directory and merge its content into ``result``.

    Mirrors the native ``_load_one_extension`` but for content-only bundles:
    no Python import, no ``entry.register()`` — just skills, commands, and
    MCP configs.

    Mirrors OpenClaw's bundle load path in ``discovery.ts``.
    """
    from .bundle_commands import load_bundle_command_skills
    from .bundle_manifest import load_bundle_manifest
    from .bundle_mcp import load_bundle_mcp_config

    bundle_manifest = load_bundle_manifest(ext_dir, bundle_format)
    if bundle_manifest is None:
        return False

    _log.debug(
        "loader: bundle %s (%s) — capabilities: %s",
        bundle_manifest.id,
        bundle_format,
        bundle_manifest.capabilities,
    )

    # Skills: walk each skill root for SKILL.md files *and* load command markdown.
    # load_bundle_command_skills covers all skill roots including commands/.
    bundle_skills = load_bundle_command_skills(ext_dir, bundle_manifest)
    result.skills.extend(bundle_skills)

    # MCP: collect server configs for gateway wiring (Phase 2).
    plugin_data_dir = Path.home() / ".jarvis" / "plugins" / bundle_manifest.id / "data"
    mcp_cfg = load_bundle_mcp_config(
        ext_dir,
        bundle_format,
        bundle_manifest.id,
        plugin_data_dir=plugin_data_dir,
    )
    if mcp_cfg is not None:
        if mcp_cfg.diagnostics:
            for diag in mcp_cfg.diagnostics:
                _log.warning("loader: bundle %s MCP: %s", bundle_manifest.id, diag)
        if mcp_cfg.mcp_servers:
            result.bundle_mcp_configs.append(mcp_cfg)

    result.bundles.append(bundle_manifest)
    return True


# ── Public API ─────────────────────────────────────────────────────────


def load_all_plugins(
    extensions_root: Path,
    *,
    workspace: Path | None = None,
    only_startup: bool = False,
    extra_sys_paths: list[Path] | None = None,
    registration_mode: str = "full",
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
    registration_mode : str
        OpenClaw-style scope forwarded to every ``PluginApi`` instance.
        ``"full"`` (default) = startup; ``"cli-metadata"`` = CLI scan;
        ``"discovery"`` = capability enumeration; ``"tool-discovery"`` =
        tool-name enumeration. Mirrors ``discovery.ts`` host call sites.

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

    # ── Native plugin scan (openclaw.plugin.json / jarvis.plugin.json) ──────
    # Collect native extension directories so the bundle scan below can skip
    # them (native manifest wins over any bundle markers in the same dir).
    native_ext_dirs: set[str] = set()
    manifest_paths: list[Path] = []
    if extensions_root.is_dir():
        for ext_dir in sorted(extensions_root.iterdir()):
            if not ext_dir.is_dir():
                continue
            oc_manifest = ext_dir / MANIFEST_FILENAME
            jv_manifest = ext_dir / "jarvis.plugin.json"
            if oc_manifest.is_file():
                manifest_paths.append(oc_manifest)
            elif jv_manifest.is_file():
                manifest_paths.append(jv_manifest)
    _log.debug("loader: found %d manifests under %s", len(manifest_paths), extensions_root)

    for manifest_path in manifest_paths:
        ext_name = manifest_path.parent.name
        native_ext_dirs.add(ext_name)

        manifest = _read_manifest(manifest_path)
        if manifest is None:
            result.skipped.append(ext_name)
            continue

        # Activation filter.
        activation = _normalize_activation(manifest)
        if only_startup and activation not in _STARTUP_ACTIVATIONS:
            _log.debug("loader: skipping %s (activation=%s)", ext_name, activation)
            continue

        ok = _load_one_extension(
            ext_name, manifest, ws, result, registration_mode=registration_mode
        )
        if ok:
            result.plugin_count += 1
        else:
            result.skipped.append(ext_name)

    # ── Bundle scan (Agent Plugins / Codex / Claude / Cursor) ─────────────
    # Run parallel to native scan — bundles are content-only packs.
    try:
        from .bundle_manifest import detect_bundle_format  # noqa: PLC0415

        bundle_skipped: list[str] = []
        for ext_dir in sorted(extensions_root.iterdir()):
            if not ext_dir.is_dir():
                continue
            # Directories with a native manifest were already loaded above.
            if ext_dir.name in native_ext_dirs:
                continue
            bundle_fmt = detect_bundle_format(ext_dir)
            if bundle_fmt is None:
                continue
            ok = _load_one_bundle(ext_dir, bundle_fmt, ws, result)
            if ok:
                result.bundle_count += 1
            else:
                bundle_skipped.append(ext_dir.name)

        if bundle_skipped:
            _log.debug("loader: skipped bundles: %s", ", ".join(bundle_skipped))

    except Exception as exc:  # noqa: BLE001
        # Bundle scan must never crash the native plugin load.
        _log.warning("loader: bundle scan raised unexpectedly: %s", exc)

    _log.info(
        "loader: loaded %d plugins + %d bundles (%d skipped) from %s",
        result.plugin_count,
        result.bundle_count,
        len(result.skipped),
        extensions_root,
    )
    if result.skipped:
        _log.debug("loader: skipped extensions: %s", ", ".join(result.skipped))

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


def discover_plugins(
    root_or_workspace: Path | str | None = None,
    *,
    workspace: Path | str | None = None,
    extensions_root: Path | str | None = None,
    only_startup: bool = False,
    extra_sys_paths: list[Path] | None = None,
    registration_mode: str = "full",
    **kwargs: Any,
) -> LoadResult:
    """Discover, validate, and activate plugins across workspace extensions.

    Mirrors OpenClaw's ``discoverPlugins`` (``src/plugins/discovery.ts``)
    and manifest registry. Canonical discovery entrypoint for scripts,
    agents, tests, and external callers expecting:
        ``from jarvis_sdk.loader import discover_plugins``
    or
        ``from jarvis_sdk import discover_plugins``

    Parameters
    ----------
    root_or_workspace : Path | str | None
        Optional path to workspace root or extensions directory.
    workspace : Path | str | None
        Explicit workspace directory root.
    extensions_root : Path | str | None
        Explicit extensions directory root.
    only_startup : bool
        If True, only load plugins marked for startup.
    extra_sys_paths : list[Path] | None
        Additional paths to prepend to sys.path.
    registration_mode : str
        OpenClaw registration mode ('full', 'cli-metadata', 'discovery', 'tool-discovery').
    **kwargs : Any
        Additional keyword arguments forwarded to ``load_all_plugins``.

    Returns
    -------
    LoadResult
        All gathered registrations and manifest metadata.
    """
    target_path = Path(root_or_workspace) if root_or_workspace is not None else None
    ws_path = Path(workspace) if workspace is not None else None
    ext_path = Path(extensions_root) if extensions_root is not None else None

    if ext_path is not None:
        resolved_ext = ext_path
        resolved_ws = ws_path or resolved_ext.parent
    elif target_path is not None:
        if (
            target_path.name == "extensions"
            or any(target_path.glob(f"*/{MANIFEST_FILENAME}"))
            or any(target_path.glob("*/jarvis.plugin.json"))
        ):
            resolved_ext = target_path
            resolved_ws = ws_path or target_path.parent
        elif (target_path / "extensions").is_dir():
            resolved_ws = target_path
            resolved_ext = target_path / "extensions"
        else:
            resolved_ws = target_path
            resolved_ext = target_path / "extensions"
    elif ws_path is not None:
        resolved_ws = ws_path
        resolved_ext = ws_path / "extensions"
    else:
        cwd = Path.cwd()
        if (cwd / "extensions").is_dir():
            resolved_ws = cwd
            resolved_ext = cwd / "extensions"
        else:
            candidate = cwd
            found_ws = None
            while True:
                if (candidate / "extensions").is_dir():
                    found_ws = candidate
                    break
                if candidate.parent == candidate:
                    break
                candidate = candidate.parent
            resolved_ws = found_ws or cwd
            resolved_ext = resolved_ws / "extensions"

    return load_all_plugins(
        resolved_ext,
        workspace=resolved_ws,
        only_startup=only_startup,
        extra_sys_paths=extra_sys_paths,
        registration_mode=registration_mode,
        **kwargs,
    )


load_plugins = discover_plugins


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
    "discover_plugins",
    "load_all_plugins",
    "load_all_plugins_from_workspace",
    "load_plugins",
    "skills_to_prompt_section",
]
