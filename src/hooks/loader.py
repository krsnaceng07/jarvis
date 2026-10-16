"""Hook loader — mirrors OpenClaw ``src/hooks/loader.ts``.

Discovers, parses, and merges hooks from three tiers:
  1. Bundled  (``src/hooks/bundled/<name>/`` — shipped with JARVIS)
  2. Plugin   (dirs contributed by plugin manifests via register_hook)
  3. Workspace(``~/.jarvis/hooks/<name>/``  — operator-installed hooks)

Each hook directory must contain:
  - ``HOOK.md``    — YAML frontmatter (events, always, hookKey, emoji, …)
  - ``handler.py`` — Python callable ``handle(event: InternalHookEvent) -> None``

After scanning, ``load_hooks`` applies ``resolve_hook_entries`` so that
higher-precedence sources win over lower ones, following the same asymmetric
override rules as OpenClaw.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from .policy import resolve_hook_enable_state, resolve_hook_entries
from .types import (
    Hook,
    HookEntry,
    HookEligibilityContext,
    HookInvocationPolicy,
    HookMetadata,
    HookSource,
)

_log = logging.getLogger("jarvis.hooks.loader")

# Bundled hooks ship alongside this package
_BUNDLED_DIR = Path(__file__).parent / "bundled"

# Workspace hooks live in ~/.jarvis/hooks/
_WORKSPACE_HOOKS_DIR = Path.home() / ".jarvis" / "hooks"


def _parse_hook_md(hook_md_path: Path) -> dict[str, Any]:
    """Parse YAML frontmatter from HOOK.md.

    Format::
        ---
        events: ["message:received", "session:start"]
        emoji: "🪝"
        always: false
        ---
        Description text…
    """
    try:
        text = hook_md_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    if not text.startswith("---"):
        return {}

    end = text.find("---", 3)
    if end == -1:
        return {}

    frontmatter_text = text[3:end].strip()
    try:
        import yaml  # type: ignore[import-untyped]
        return yaml.safe_load(frontmatter_text) or {}
    except Exception:
        pass

    # Fallback: minimal key:value parser (no yaml dep required)
    result: dict[str, Any] = {}
    for line in frontmatter_text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # Inline list: ["a", "b"]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            result[key] = [v.strip().strip('"\'') for v in inner.split(",") if v.strip()]
        elif val.lower() in ("true", "yes"):
            result[key] = True
        elif val.lower() in ("false", "no"):
            result[key] = False
        else:
            result[key] = val
    return result


def _build_hook_metadata(fm: dict[str, Any]) -> HookMetadata | None:
    events = fm.get("events")
    if not events:
        return None
    if isinstance(events, str):
        events = [events]
    return HookMetadata(
        events=tuple(events),
        always=bool(fm.get("always", False)),
        hook_key=fm.get("hookKey") or fm.get("hook_key"),
        emoji=fm.get("emoji"),
        homepage=fm.get("homepage"),
        os=tuple(fm.get("os") or []),
        requires_bins=tuple((fm.get("requires") or {}).get("bins") or []),
        requires_any_bins=tuple((fm.get("requires") or {}).get("anyBins") or []),
        requires_env=tuple((fm.get("requires") or {}).get("env") or []),
    )


def _load_hook_from_dir(
    hook_dir: Path,
    source: HookSource,
    plugin_id: str | None = None,
) -> HookEntry | None:
    """Load a single hook from its directory. Returns None if invalid."""
    hook_md = hook_dir / "HOOK.md"
    handler_py = hook_dir / "handler.py"

    if not hook_md.exists() or not handler_py.exists():
        return None

    fm = _parse_hook_md(hook_md)
    name = fm.get("name") or hook_dir.name
    description = fm.get("description", "")
    metadata = _build_hook_metadata(fm)

    if metadata is None:
        _log.debug("hook %s has no events — skipping", hook_dir)
        return None

    hook = Hook(
        name=name,
        description=description,
        source=source,
        file_path=str(hook_md),
        base_dir=str(hook_dir),
        handler_path=str(handler_py),
        plugin_id=plugin_id,
    )
    return HookEntry(
        hook=hook,
        frontmatter={str(k): str(v) for k, v in fm.items()},
        metadata=metadata,
        invocation=None,
    )


def _scan_dir(
    root: Path,
    source: HookSource,
    plugin_id: str | None = None,
) -> list[HookEntry]:
    """Scan a directory of hook subdirs and load valid hooks."""
    if not root.exists() or not root.is_dir():
        return []
    entries: list[HookEntry] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        entry = _load_hook_from_dir(child, source, plugin_id)
        if entry:
            entries.append(entry)
    return entries


def load_hooks(
    plugin_hook_dirs: list[dict] | None = None,
    config: dict | None = None,
    eligibility: "HookEligibilityContext | None" = None,
    include_disabled: bool = False,
) -> list[HookEntry]:
    """Discover and merge all hooks from bundled + plugin + workspace sources.

    Args:
        plugin_hook_dirs: list of ``{"dir": str, "plugin_id": str}`` dicts
            from ``resolve_plugin_hook_dirs``.
        config: JARVIS config dict — used by enable-state resolution.
        eligibility: runtime eligibility context (bin availability, platform).
        include_disabled: if True, returns disabled hooks as well.

    Returns:
        Merged, policy-resolved list of enabled ``HookEntry`` objects.
    """
    all_entries: list[HookEntry] = []

    # 1. Bundled hooks (highest trust, lowest precedence = default-on)
    bundled = _scan_dir(_BUNDLED_DIR, "jarvis-bundled")
    all_entries.extend(bundled)
    _log.debug("loaded %d bundled hooks", len(bundled))

    # 2. Plugin-contributed hooks
    for entry_dict in (plugin_hook_dirs or []):
        hook_dir = Path(entry_dict.get("dir", ""))
        pid = entry_dict.get("plugin_id")
        plugin_entry = _load_hook_from_dir(hook_dir, "jarvis-plugin", plugin_id=pid)
        if plugin_entry:
            all_entries.append(plugin_entry)

    # 3. Workspace hooks (~/.jarvis/hooks/) — explicit opt-in required
    workspace = _scan_dir(_WORKSPACE_HOOKS_DIR, "jarvis-workspace")
    all_entries.extend(workspace)
    _log.debug("loaded %d workspace hooks", len(workspace))

    # Apply enable-state filtering
    filtered: list[HookEntry] = []
    for e in all_entries:
        state = resolve_hook_enable_state(e, config)
        if state.enabled:
            # Attach invocation policy
            e.invocation = HookInvocationPolicy(enabled=True)
            filtered.append(e)
        else:
            _log.debug("hook %s disabled: %s", e.hook.name, state.reason)
            if include_disabled:
                e.invocation = HookInvocationPolicy(enabled=False, reason=state.reason)
                filtered.append(e)

    # Merge by name using precedence + override policy
    merged = resolve_hook_entries(filtered)
    _log.info("hooks ready: %d active", len(merged))
    return merged


def load_hook_handler(entry: HookEntry):
    """Dynamically import and return the ``handle`` callable from handler.py."""
    spec = importlib.util.spec_from_file_location(
        f"jarvis_hook_{entry.hook.name}", entry.hook.handler_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load hook handler: {entry.hook.handler_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    handler = getattr(mod, "handle", None)
    if handler is None:
        raise AttributeError(
            f"hook handler {entry.hook.handler_path} has no 'handle' function"
        )
    return handler


__all__ = ["load_hook_handler", "load_hooks"]
