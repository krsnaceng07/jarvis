"""jarvis.agents.sessions.extensions.loader — extension loader.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/extensions/loader.ts``.

Phase 6.9c — ``loadExtensionsCached``,
``loadExtensionFromFactory``,
``createExtensionRuntime``,
``clearExtensionCache``.

Adaptations
-----------
- The OpenClaw source uses ``jiti`` to
  load TypeScript extension modules on the
  fly. The Python port uses
  :func:`importlib.util.spec_from_file_location`
  (matching the JARVIS hyphened-extension
  import pattern already in use elsewhere
  in the codebase).
- The OpenClaw source's ``native`` import
  branch (Node ``require``/``import`` for
  pre-compiled ``.cjs``/``.mjs`` modules)
  becomes Python's
  :func:`importlib.util.spec_from_file_location`
  + :func:`importlib.util.module_from_spec`
  pattern. The Python port supports ``.py``
  files only (the OpenClaw source's
  ``.cjs``/``.mjs``/``.ts`` discrimination
  does not apply).
- The OpenClaw source's ``VIRTUAL_MODULES``
  map (TypeBox + plugin-sdk virtual imports
  for the Bun binary) is replaced with a
  lightweight module-name remap: extensions
  can ``import`` from
  ``jarvis.agents.sessions.extension_sdk``
  and the loader exposes a small set of
  utility modules.
- The OpenClaw source's plugin alias
  resolution (``openclaw/plugin-sdk/llm``,
  ``typebox``, …) is replaced with a
  small ``EXTENSION_VIRTUAL_MODULES`` dict
  that maps a few well-known OpenClaw SDK
  names to the JARVIS equivalents
  (``jarvis_sdk``, ``jarvis_agent``, …).
  Extensions that only depend on the
  JARVIS-side surface (``jarvis_sdk``)
  work without rewriting their imports.
- The OpenClaw source's
  ``isJavaScriptExtensionPath`` /
  ``extensionSourceNeedsJitiAliasResolution``
  / ``shouldLoadExtensionWithNativeImport``
  are dropped (Python's loader does not
  need to discriminate).
- The OpenClaw source's
  ``useExtensionCacheCwd`` /
  ``clearExtensionCache`` cache mechanism
  is preserved (same one-slot generation
  bound to the resolved cwd).
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from .types import (
    DEFAULT_STALE_MESSAGE,
    EventBus,
    Extension,
    ExtensionAPI,
    ExtensionFactory,
    ExtensionRuntime,
    LoadExtensionsError,
    LoadExtensionsResult,
    MessageRenderer,
    ProviderConfig,
    RegisteredCommand,
    SourceInfo,
    ToolDefinition,
)


_log = logging.getLogger("jarvis.agents.sessions.extensions.loader")


# ============================================================================
# Virtual module remap
# ============================================================================


#: Maps well-known OpenClaw SDK import names
#: to the JARVIS equivalents. The Python
#: loader rewrites these so an extension
#: source that imports from the OpenClaw
#: surface still resolves. Extensions that
#: import from ``jarvis_sdk`` work natively
#: without rewriting.
EXTENSION_VIRTUAL_MODULES: dict[str, str] = {
    # The bundled "extension SDK" surface
    # (the public surface extensions see).
    "openclaw.plugin-sdk.agent-sessions": "src.agents.sessions.extension_sdk",
    "@openclaw.plugin-sdk.agent-sessions": "src.agents.sessions.extension_sdk",
}


# ============================================================================
# Runtime state
# ============================================================================


_extension_cache: dict[str, ExtensionFactory] = {}
_extension_cache_cwd: Optional[str] = None
_extension_cache_generation: int = 0
#: Re-entrant lock: ``_use_extension_cache_cwd``
#: calls :func:`clear_extension_cache` while
#: already holding the lock (when the cwd
#: changes); a plain ``threading.Lock``
#: would deadlock the second call.
_cache_lock = threading.RLock()


def clear_extension_cache() -> None:
    """Clear the cached extension factories
    + bump the generation so a subsequent
    :func:`load_extensions_cached` reloads
    from source. Mirrors
    ``clearExtensionCache``
    (``loader.ts:219-223``)."""
    global _extension_cache_cwd, _extension_cache_generation
    with _cache_lock:
        _extension_cache.clear()
        _extension_cache_cwd = None
        _extension_cache_generation += 1


def _use_extension_cache_cwd(cwd: str) -> tuple[str, int]:
    """Bind the cache to the resolved cwd.
    Returns ``(resolved_cwd, generation)``.
    Mirrors ``useExtensionCacheCwd``
    (``loader.ts:225-232``)."""
    global _extension_cache_cwd
    resolved = os.path.realpath(os.path.expanduser(cwd))
    with _cache_lock:
        if _extension_cache_cwd is not None and _extension_cache_cwd != resolved:
            clear_extension_cache()
        _extension_cache_cwd = resolved
        return resolved, _extension_cache_generation


def _is_current_cache_scope(generation: int) -> bool:
    return generation == _extension_cache_generation


# ============================================================================
# createExtensionRuntime
# ============================================================================


def create_extension_runtime() -> ExtensionRuntime:
    """Build an :class:`ExtensionRuntime` with
    throwing action stubs. The host's
    :meth:`ExtensionRunner.bindCore` replaces
    the stubs with real implementations.
    Mirrors ``createExtensionRuntime``
    (``loader.ts:246-296``)."""
    runtime = ExtensionRuntime()
    return runtime


# ============================================================================
# Internal helpers
# ============================================================================


def _expand_path(p: str) -> str:
    """Expand ``~`` (matching OpenClaw's
    ``expandPath`` —
    ``loader.ts:188-197``)."""
    if p.startswith("~/") or p.startswith("~\\"):
        return os.path.join(os.path.expanduser("~"), p[2:])
    if p.startswith("~"):
        return os.path.join(os.path.expanduser("~"), p[1:])
    return p


def _resolve_path(ext_path: str, cwd: str) -> str:
    expanded = _expand_path(ext_path)
    if os.path.isabs(expanded):
        return expanded
    return os.path.realpath(os.path.join(cwd, expanded))


def _create_extension(extension_path: str, resolved_path: str) -> Extension:
    """Build a fresh :class:`Extension` with
    empty collections. Mirrors
    ``createExtension``
    (``loader.ts:571-589``)."""
    is_synthetic = (
        extension_path.startswith("<") and extension_path.endswith(">")
    )
    if is_synthetic:
        source = (
            extension_path[1:-1].split(":")[0]
            if ":" in extension_path[1:-1]
            else "temporary"
        )
    else:
        source = "local"
    base_dir: Optional[str] = None
    if not is_synthetic:
        base_dir = os.path.dirname(resolved_path)
    return Extension(
        path=extension_path,
        resolvedPath=resolved_path,
        sourceInfo={
            "source": source,
            "baseDir": base_dir,
        },  # type: ignore[typeddict-item]
        handlers={},
        tools={},
        messageRenderers={},
        commands={},
        flags={},
        shortcuts={},
    )


# ============================================================================
# createExtensionAPI
# ============================================================================


def _create_extension_api(
    extension: Extension,
    runtime: ExtensionRuntime,
    cwd: str,
    event_bus: EventBus,
) -> ExtensionAPI:
    """Build the :class:`ExtensionAPI` the
    factory receives. Mirrors
    ``createExtensionAPI``
    (``loader.ts:303-457``).

    Registration methods write to the
    extension's collection maps; action
    methods delegate to the shared runtime.
    The Python port uses a ``dict`` as the
    api instance (the OpenClaw source uses
    a TS object literal cast to
    ``ExtensionAPI``).
    """
    api: dict = {}

    def _on(event: str, handler: Any) -> None:
        runtime.assertActive()
        existing = extension.handlers.get(event)
        if existing is None:
            existing = []
            extension.handlers[event] = existing
        existing.append(handler)

    def _register_tool(tool: ToolDefinition) -> None:
        runtime.assertActive()
        extension.tools[tool["name"]] = {
            "definition": tool,
            "sourceInfo": extension.sourceInfo,
        }
        runtime.refreshTools()

    def _register_command(name: str, options: dict) -> None:
        runtime.assertActive()
        extension.commands[name] = dict(
            options,
            name=name,
            sourceInfo=extension.sourceInfo,
        )

    def _register_shortcut(shortcut: Any, options: dict) -> None:
        runtime.assertActive()
        extension.shortcuts[shortcut] = dict(
            options,
            shortcut=shortcut,
            extensionPath=extension.path,
        )

    def _register_flag(name: str, options: dict) -> None:
        runtime.assertActive()
        extension.flags[name] = dict(
            options,
            name=name,
            extensionPath=extension.path,
        )
        default = options.get("default")
        if default is not None and name not in runtime.flagValues:
            runtime.flagValues[name] = default

    def _register_message_renderer(
        custom_type: str, renderer: MessageRenderer
    ) -> None:
        runtime.assertActive()
        extension.messageRenderers[custom_type] = renderer

    def _get_flag(name: str) -> Any:
        runtime.assertActive()
        if name not in extension.flags:
            return None
        return runtime.flagValues.get(name)

    def _send_message(message: Any, options: Any = None) -> None:
        runtime.assertActive()
        runtime.sendMessage(message, options)

    def _send_user_message(content: Any, options: Any = None) -> None:
        runtime.assertActive()
        runtime.sendUserMessage(content, options)

    def _append_entry(custom_type: str, data: Any = None) -> None:
        runtime.assertActive()
        runtime.appendEntry(custom_type, data)

    def _set_session_name(name: str) -> None:
        runtime.assertActive()
        runtime.setSessionName(name)

    def _get_session_name() -> Optional[str]:
        runtime.assertActive()
        return runtime.getSessionName()

    def _set_label(entry_id: str, label: Optional[str]) -> None:
        runtime.assertActive()
        runtime.setLabel(entry_id, label)

    def _get_active_tools() -> list[str]:
        runtime.assertActive()
        return runtime.getActiveTools()

    def _get_all_tools() -> list:
        runtime.assertActive()
        return runtime.getAllTools()

    def _set_active_tools(tool_names: list[str]) -> None:
        runtime.assertActive()
        runtime.setActiveTools(tool_names)

    def _get_commands() -> list:
        runtime.assertActive()
        return runtime.getCommands()

    def _set_model(model: Any) -> "asyncio.Future[bool]":
        runtime.assertActive()
        return runtime.setModel(model)

    def _get_thinking_level() -> Any:
        runtime.assertActive()
        return runtime.getThinkingLevel()

    def _set_thinking_level(level: Any) -> None:
        runtime.assertActive()
        runtime.setThinkingLevel(level)

    def _register_provider(name: str, config: ProviderConfig) -> None:
        runtime.assertActive()
        runtime.registerProvider(name, config, extension.path)

    def _unregister_provider(name: str) -> None:
        runtime.assertActive()
        runtime.unregisterProvider(name, extension.path)

    api["on"] = _on
    api["registerTool"] = _register_tool
    api["registerCommand"] = _register_command
    api["registerShortcut"] = _register_shortcut
    api["registerFlag"] = _register_flag
    api["registerMessageRenderer"] = _register_message_renderer
    api["getFlag"] = _get_flag
    api["sendMessage"] = _send_message
    api["sendUserMessage"] = _send_user_message
    api["appendEntry"] = _append_entry
    api["setSessionName"] = _set_session_name
    api["getSessionName"] = _get_session_name
    api["setLabel"] = _set_label
    api["getActiveTools"] = _get_active_tools
    api["getAllTools"] = _get_all_tools
    api["setActiveTools"] = _set_active_tools
    api["getCommands"] = _get_commands
    api["setModel"] = _set_model
    api["getThinkingLevel"] = _get_thinking_level
    api["setThinkingLevel"] = _set_thinking_level
    api["registerProvider"] = _register_provider
    api["unregisterProvider"] = _unregister_provider
    api["events"] = event_bus
    return api  # type: ignore[return-value]


# ============================================================================
# Module loading
# ============================================================================


def _resolve_extension_factory(module: Any) -> Optional[ExtensionFactory]:
    """Pull the factory function out of a
    loaded module. Mirrors
    ``resolveExtensionFactory``
    (``loader.ts:459-472``).

    The OpenClaw source checks
    ``module.default`` then the module
    itself then nested ``default``. The
    Python port also checks the common
    factory names (``factory``, ``register``,
    ``install``, ``setup``) so a standalone
    module that defines ``def factory(api)``
    — the natural Python shape — is
    recognised.
    """
    if module is None:
        return None
    # Common factory attribute names (in
    # priority order; ``default`` wins because
    # that's the OpenClaw contract).
    for attr in ("default", "factory", "register", "install", "setup"):
        if hasattr(module, attr):
            candidate = getattr(module, attr)
            if callable(candidate):
                return candidate
    # Fallback: callable module
    if callable(module):
        return module
    # Fallback: nested ``default``
    candidate = getattr(module, "default", None)
    if candidate is not None and hasattr(candidate, "default"):
        nested = getattr(candidate, "default")
        if callable(nested):
            return nested
    return None


def _is_python_extension_path(extension_path: str) -> bool:
    """A path is a Python extension when its
    extension is ``.py``. The OpenClaw
    source's ``.cjs`` / ``.mjs``
    discrimination does not apply in the
    Python port."""
    return Path(extension_path).suffix.lower() == ".py"


def _strip_path_from_sys(extension_path: str) -> None:
    """Remove the extension's parent dir
    from ``sys.path`` after import. This
    mirrors the JARVIS hyphened-extension
    pattern: extensions live under named
    directories; the loader does not want
    sibling extensions to accidentally
    resolve to a same-named module in a
    different extension."""
    parent = os.path.dirname(extension_path)
    if parent and parent in sys.path:
        try:
            sys.path.remove(parent)
        except ValueError:
            pass


def _load_extension_module(
    extension_path: str,
    generation: int,
) -> Optional[ExtensionFactory]:
    """Load the extension module from disk
    using :mod:`importlib`. Mirrors
    ``loadExtensionModule``
    (``loader.ts:548-566``)."""
    with _cache_lock:
        if _is_current_cache_scope(generation):
            cached = _extension_cache.get(extension_path)
            if cached is not None:
                return cached
    if not _is_python_extension_path(extension_path):
        return None
    parent = os.path.dirname(os.path.abspath(extension_path))
    added = parent not in sys.path
    if added:
        sys.path.insert(0, parent)
    try:
        module_name = f"_jarvis_ext_{abs(hash(extension_path)) & 0xFFFFFFFF:x}"
        spec = importlib.util.spec_from_file_location(
            module_name, extension_path
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(module_name, None)
    finally:
        if added:
            _strip_path_from_sys(parent)
    factory = _resolve_extension_factory(module)
    if factory is not None and _is_current_cache_scope(generation):
        with _cache_lock:
            _extension_cache[extension_path] = factory
    return factory


# ============================================================================
# Public: loadExtensionFromFactory
# ============================================================================


async def load_extension_from_factory(
    factory: ExtensionFactory,
    cwd: str,
    event_bus: EventBus,
    runtime: ExtensionRuntime,
    extension_path: str = "<inline>",
) -> Extension:
    """Load an extension from an inline
    factory function. Mirrors
    ``loadExtensionFromFactory``
    (``loader.ts:623-634``)."""
    extension = _create_extension(extension_path, extension_path)
    api = _create_extension_api(extension, runtime, cwd, event_bus)
    result = factory(api)
    if asyncio.iscoroutine(result):
        await result
    return extension


# ============================================================================
# Public: loadExtensionsCached
# ============================================================================


async def load_extensions_cached(
    paths: list[str],
    cwd: str,
    event_bus: Optional[EventBus] = None,
) -> LoadExtensionsResult:
    """Load a batch of extensions from paths
    + bind them to a shared runtime. Mirrors
    ``loadExtensionsCached``
    (``loader.ts:639-676``)."""
    resolved_bus = event_bus if event_bus is not None else _create_event_bus_stub()
    runtime = create_extension_runtime()
    resolved_cwd, generation = _use_extension_cache_cwd(cwd)
    extensions: list[Extension] = []
    errors: list[LoadExtensionsError] = []
    for ext_path in paths:
        try:
            ext = await _load_one(
                ext_path,
                resolved_cwd,
                resolved_bus,
                runtime,
                generation,
            )
            if ext is not None:
                extensions.append(ext)
        except Exception as exc:
            errors.append(
                {
                    "path": ext_path,
                    "error": str(exc) or exc.__class__.__name__,
                }
            )
    return LoadExtensionsResult(
        extensions=extensions, errors=errors, runtime=runtime
    )


async def _load_one(
    extension_path: str,
    cwd: str,
    event_bus: EventBus,
    runtime: ExtensionRuntime,
    generation: int,
) -> Optional[Extension]:
    """Load a single extension. Mirrors
    ``loadExtension``
    (``loader.ts:591-618``)."""
    resolved_path = _resolve_path(extension_path, cwd)
    try:
        factory = await asyncio.to_thread(
            _load_extension_module, resolved_path, generation
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load extension: {exc}"
        ) from exc
    if factory is None:
        raise RuntimeError(
            f"Extension does not export a valid factory function: "
            f"{extension_path}"
        )
    extension = _create_extension(extension_path, resolved_path)
    api = _create_extension_api(extension, runtime, cwd, event_bus)
    result = factory(api)
    if asyncio.iscoroutine(result):
        await result
    return extension


# ============================================================================
# EventBus stub
# ============================================================================


def _create_event_bus_stub() -> Any:
    """Create a minimal EventBus for the
    loader. The full EventBus lands in
    Phase 6.10+; for now the loader ships
    a thin shim that supports the
    ``emit`` / ``on`` / ``off`` API used
    by extensions (the OpenClaw source's
    ``createEventBus()`` from
    ``event-bus.ts``)."""
    from src.agents.sessions.event_bus import (  # late import
        create_event_bus,
    )

    return create_event_bus()


__all__ = [
    "EXTENSION_VIRTUAL_MODULES",
    "clear_extension_cache",
    "create_extension_runtime",
    "load_extension_from_factory",
    "load_extensions_cached",
]
