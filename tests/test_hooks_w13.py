"""Tests for Wave 13 — Hooks Runtime (policy, loader, plugin_hooks, types)."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.hooks.types import (
    Hook,
    HookEntry,
    HookMetadata,
    InternalHookEvent,
    is_known_hook_event_key,
)
from src.hooks.policy import (
    HookEnableState,
    resolve_hook_enable_state,
    resolve_hook_entries,
)
from src.hooks.plugin_hooks import resolve_plugin_hook_dirs
from src.hooks.loader import load_hooks, load_hook_handler


def test_is_known_hook_event_key():
    assert is_known_hook_event_key("session:start") or is_known_hook_event_key("session")
    assert is_known_hook_event_key("message:received")
    assert is_known_hook_event_key("agent:bootstrap")
    assert not is_known_hook_event_key("unknown:xyz")


def test_hook_policy_precedence():
    entry_bundled = HookEntry(
        hook=Hook("h1", "desc", "jarvis-bundled", "/b/1", "/b", "/b/h.py"),
        frontmatter={"name": "h1"},
        metadata=HookMetadata(events=("session:start",)),
    )
    entry_workspace = HookEntry(
        hook=Hook("h1", "desc", "jarvis-workspace", "/w/1", "/w", "/w/h.py"),
        frontmatter={"name": "h1"},
        metadata=HookMetadata(events=("session:start",)),
    )

    # Workspace requires explicit opt-in
    state_ws = resolve_hook_enable_state(entry_workspace, config={})
    assert not state_ws.enabled
    assert state_ws.reason == "workspace hook (disabled by default)"

    state_ws_opt = resolve_hook_enable_state(
        entry_workspace, config={"hooks": {"internal": {"entries": {"h1": {"enabled": True}}}}}
    )
    assert state_ws_opt.enabled


def test_resolve_hook_entries_override():
    entry_bundled = HookEntry(
        hook=Hook("h1", "desc", "jarvis-bundled", "/b/1", "/b", "/b/h.py"),
        frontmatter={"name": "h1"},
        metadata=HookMetadata(events=("session:start",)),
    )
    entry_plugin = HookEntry(
        hook=Hook("h1", "desc", "jarvis-plugin", "/p/1", "/p", "/p/h.py", plugin_id="p1"),
        frontmatter={"name": "h1"},
        metadata=HookMetadata(events=("session:start",)),
    )

    # Plugin can override bundled
    resolved = resolve_hook_entries([entry_bundled, entry_plugin])
    assert len(resolved) == 1
    assert resolved[0].hook.source == "jarvis-plugin"


def test_resolve_plugin_hook_dirs_security(tmp_path: Path):
    plugin_root = tmp_path / "my_plugin"
    plugin_root.mkdir()
    hook_dir = plugin_root / "hooks" / "h1"
    hook_dir.mkdir(parents=True)

    records = [
        {
            "id": "my_plugin",
            "root_dir": str(plugin_root),
            "hooks": ["hooks/h1"],
            "enabled": True,
        }
    ]

    res = resolve_plugin_hook_dirs(records)
    assert len(res) == 1
    assert res[0].plugin_id == "my_plugin"

    # Escaping attempt
    bad_records = [
        {
            "id": "bad_plugin",
            "root_dir": str(plugin_root),
            "hooks": ["../../outside"],
            "enabled": True,
        }
    ]
    res_bad = resolve_plugin_hook_dirs(bad_records)
    assert len(res_bad) == 0


def test_load_hooks_bundled():
    hooks = load_hooks()
    # Bundled hooks (session-memory, compaction-notifier) should load
    names = [h.hook.name for h in hooks]
    assert "session-memory" in names
    assert "compaction-notifier" in names
