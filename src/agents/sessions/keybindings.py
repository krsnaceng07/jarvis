"""jarvis.agents.sessions.keybindings — application keybinding definitions.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/keybindings.ts``.

Application keybinding definitions and user-config
migration helpers. The OpenClaw source wraps
``@earendil-works/pi-tui`` keybindings with
OpenClaw-specific actions and per-agent overrides.

Parity
======
- ``KEYBINDINGS`` dict (``keybindings.ts:69-208``) —
  the canonical key-id → ``{default_keys,
  description}`` map. Every entry matches the
  OpenClaw source exactly (same key ids, same
  default bindings, same descriptions).
- ``KEYBINDING_NAME_MIGRATIONS`` dict
  (``keybindings.ts:210-270``) — the legacy key-name
  → new key-name map. Every entry matches.
- ``to_keybindings_config(value)`` — coerce a
  loaded JSON object into the typed keybindings
  config shape (``keybindings.ts:276-292``).
- ``migrate_keybindings_config(raw_config)`` — rename
  legacy keys to the new names; preserve order via
  :func:`_order_keybindings_config`
  (``keybindings.ts:295-316``).
- ``_order_keybindings_config(config)`` — push known
  key ids first, then alphabetize the unknown
  extras (``keybindings.ts:318-334``).
- ``load_raw_config(path)`` — read a JSON file and
  coerce to ``dict`` (``keybindings.ts:336-346``).
- ``KeybindingsManager`` class
  (``keybindings.ts:349-384``) — the user-override
  loader. Inherits the TUI manager from
  ``@earendil-works/pi-tui``; Phase 6.1 ships a
  protocol-shaped Python port that does not depend
  on any TUI library.
- ``KeybindingsConfig`` type alias
  (``keybindings.ts:386``) — the typed
  ``dict[str, str | list[str]]`` shape.

Phase 6.1 — storage primitives.

Adaptations
-----------
- The OpenClaw source imports the TUI manager
  from ``@earendil-works/pi-tui``. JARVIS does not
  have a TUI library (the desktop uses PyQt6, the
  CLI is read-only). The Python port declares a
  :class:`KeybindingsManager` class that exposes
  the same public surface but is backed by a plain
  ``dict`` instead of the TUI library. A future
  Phase 6.16 can wire it to PyQt6 shortcodes.
- ``isRecord`` (from ``@openclaw/normalization-core/record-coerce``)
  becomes :func:`_is_record` (local; the
  ``jarvis_normalization_core`` does not export a
  matching helper in Phase 6.1).
- The OpenClaw source's ``satisfies
  KeybindingDefinitions`` / ``satisfies
  Record<string, Keybinding>`` is a TS-only type
  assertion; the Python port uses the same shape
  via :class:`KeybindingDef` / ``dict`` typing.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union


#: A single key binding — string or list of strings.
KeyBindingValue = Union[str, list[str]]


#: Typed keybindings config. Mirrors
#: ``KeybindingsConfig`` (``keybindings.ts:386`` /
#: the type exported by ``@earendil-works/pi-tui``).
KeybindingsConfig = dict[str, KeyBindingValue]


@dataclass(frozen=True, slots=True)
class KeybindingDef:
    """Mirrors the ``{defaultKeys, description}`` shape
    used in ``KEYBINDINGS`` (keybindings.ts:71-207)."""

    default_keys: KeyBindingValue
    description: str

    def to_dict(self) -> dict:
        return {"defaultKeys": self.default_keys, "description": self.description}


# ============================================================================
# KEYBINDINGS — verbatim port of keybindings.ts:69-208
# ============================================================================
# The default-keys values are kept identical to the
# OpenClaw source so user overrides round-trip
# cleanly across a future port. Platform-specific
# defaults (``app.suspend``, ``app.clipboard.pasteImage``)
# match the OpenClaw ``process.platform === "win32"``
# checks; the Python port reads ``sys.platform`` at
# import time (same effect, since both run before
# any platform switch).


_is_windows = sys.platform == "win32"


#: Canonical keybinding table. Mirrors
#: ``KEYBINDINGS`` (``keybindings.ts:69-208``). The
#: order matches the OpenClaw source so the legacy
#: migration table + the order-by-known-names
#: function both work the same way.
KEYBINDINGS: dict[str, KeybindingDef] = {
    "app.interrupt": KeybindingDef(
        default_keys="escape", description="Cancel or abort"
    ),
    "app.clear": KeybindingDef(
        default_keys="ctrl+c", description="Clear editor"
    ),
    "app.exit": KeybindingDef(
        default_keys="ctrl+d", description="Exit when editor is empty"
    ),
    "app.suspend": KeybindingDef(
        default_keys=[] if _is_windows else "ctrl+z",
        description="Suspend to background",
    ),
    "app.thinking.cycle": KeybindingDef(
        default_keys="shift+tab", description="Cycle thinking level"
    ),
    "app.model.cycleForward": KeybindingDef(
        default_keys="ctrl+p", description="Cycle to next model"
    ),
    "app.model.cycleBackward": KeybindingDef(
        default_keys="shift+ctrl+p", description="Cycle to previous model"
    ),
    "app.model.select": KeybindingDef(
        default_keys="ctrl+l", description="Open model selector"
    ),
    "app.tools.expand": KeybindingDef(
        default_keys="ctrl+o", description="Toggle tool output"
    ),
    "app.thinking.toggle": KeybindingDef(
        default_keys="ctrl+t", description="Toggle thinking blocks"
    ),
    "app.session.toggleNamedFilter": KeybindingDef(
        default_keys="ctrl+n", description="Toggle named session filter"
    ),
    "app.editor.external": KeybindingDef(
        default_keys="ctrl+g", description="Open external editor"
    ),
    "app.message.followUp": KeybindingDef(
        default_keys="alt+enter", description="Queue follow-up message"
    ),
    "app.message.dequeue": KeybindingDef(
        default_keys="alt+up", description="Restore queued messages"
    ),
    "app.clipboard.pasteImage": KeybindingDef(
        default_keys="alt+v" if _is_windows else "ctrl+v",
        description="Paste image from clipboard",
    ),
    "app.session.new": KeybindingDef(
        default_keys=[], description="Start a new session"
    ),
    "app.session.tree": KeybindingDef(
        default_keys=[], description="Open session tree"
    ),
    "app.session.fork": KeybindingDef(
        default_keys=[], description="Fork current session"
    ),
    "app.session.resume": KeybindingDef(
        default_keys=[], description="Resume a session"
    ),
    "app.tree.foldOrUp": KeybindingDef(
        default_keys=["ctrl+left", "alt+left"],
        description="Fold tree branch or move up",
    ),
    "app.tree.unfoldOrDown": KeybindingDef(
        default_keys=["ctrl+right", "alt+right"],
        description="Unfold tree branch or move down",
    ),
    "app.tree.editLabel": KeybindingDef(
        default_keys="shift+l", description="Edit tree label"
    ),
    "app.tree.toggleLabelTimestamp": KeybindingDef(
        default_keys="shift+t", description="Toggle tree label timestamps"
    ),
    "app.session.togglePath": KeybindingDef(
        default_keys="ctrl+p", description="Toggle session path display"
    ),
    "app.session.toggleSort": KeybindingDef(
        default_keys="ctrl+s", description="Toggle session sort mode"
    ),
    "app.session.rename": KeybindingDef(
        default_keys="ctrl+r", description="Rename session"
    ),
    "app.session.delete": KeybindingDef(
        default_keys="ctrl+d", description="Delete session"
    ),
    "app.session.deleteNoninvasive": KeybindingDef(
        default_keys="ctrl+backspace",
        description="Delete session when query is empty",
    ),
    "app.models.save": KeybindingDef(
        default_keys="ctrl+s", description="Save model selection"
    ),
    "app.models.enableAll": KeybindingDef(
        default_keys="ctrl+a", description="Enable all models"
    ),
    "app.models.clearAll": KeybindingDef(
        default_keys="ctrl+x", description="Clear all models"
    ),
    "app.models.toggleProvider": KeybindingDef(
        default_keys="ctrl+p", description="Toggle all models for provider"
    ),
    "app.models.reorderUp": KeybindingDef(
        default_keys="alt+up", description="Move model up in order"
    ),
    "app.models.reorderDown": KeybindingDef(
        default_keys="alt+down", description="Move model down in order"
    ),
    "app.tree.filter.default": KeybindingDef(
        default_keys="ctrl+d", description="Tree filter: default view"
    ),
    "app.tree.filter.noTools": KeybindingDef(
        default_keys="ctrl+t", description="Tree filter: hide tool results"
    ),
    "app.tree.filter.userOnly": KeybindingDef(
        default_keys="ctrl+u", description="Tree filter: user messages only"
    ),
    "app.tree.filter.labeledOnly": KeybindingDef(
        default_keys="ctrl+l", description="Tree filter: labeled entries only"
    ),
    "app.tree.filter.all": KeybindingDef(
        default_keys="ctrl+a", description="Tree filter: show all entries"
    ),
    "app.tree.filter.cycleForward": KeybindingDef(
        default_keys="ctrl+o", description="Tree filter: cycle forward"
    ),
    "app.tree.filter.cycleBackward": KeybindingDef(
        default_keys="shift+ctrl+o", description="Tree filter: cycle backward"
    ),
}


# ============================================================================
# KEYBINDING_NAME_MIGRATIONS — verbatim port of keybindings.ts:210-270
# ============================================================================


KEYBINDING_NAME_MIGRATIONS: dict[str, str] = {
    "cursorUp": "tui.editor.cursorUp",
    "cursorDown": "tui.editor.cursorDown",
    "cursorLeft": "tui.editor.cursorLeft",
    "cursorRight": "tui.editor.cursorRight",
    "cursorWordLeft": "tui.editor.cursorWordLeft",
    "cursorWordRight": "tui.editor.cursorWordRight",
    "cursorLineStart": "tui.editor.cursorLineStart",
    "cursorLineEnd": "tui.editor.cursorLineEnd",
    "jumpForward": "tui.editor.jumpForward",
    "jumpBackward": "tui.editor.jumpBackward",
    "pageUp": "tui.editor.pageUp",
    "pageDown": "tui.editor.pageDown",
    "deleteCharBackward": "tui.editor.deleteCharBackward",
    "deleteCharForward": "tui.editor.deleteCharForward",
    "deleteWordBackward": "tui.editor.deleteWordBackward",
    "deleteWordForward": "tui.editor.deleteWordForward",
    "deleteToLineStart": "tui.editor.deleteToLineStart",
    "deleteToLineEnd": "tui.editor.deleteToLineEnd",
    "yank": "tui.editor.yank",
    "yankPop": "tui.editor.yankPop",
    "undo": "tui.editor.undo",
    "newLine": "tui.input.newLine",
    "submit": "tui.input.submit",
    "tab": "tui.input.tab",
    "copy": "tui.input.copy",
    "selectUp": "tui.select.up",
    "selectDown": "tui.select.down",
    "selectPageUp": "tui.select.pageUp",
    "selectPageDown": "tui.select.pageDown",
    "selectConfirm": "tui.select.confirm",
    "selectCancel": "tui.select.cancel",
    "interrupt": "app.interrupt",
    "clear": "app.clear",
    "exit": "app.exit",
    "suspend": "app.suspend",
    "cycleThinkingLevel": "app.thinking.cycle",
    "cycleModelForward": "app.model.cycleForward",
    "cycleModelBackward": "app.model.cycleBackward",
    "selectModel": "app.model.select",
    "expandTools": "app.tools.expand",
    "toggleThinking": "app.thinking.toggle",
    "toggleSessionNamedFilter": "app.session.toggleNamedFilter",
    "externalEditor": "app.editor.external",
    "followUp": "app.message.followUp",
    "dequeue": "app.message.dequeue",
    "pasteImage": "app.clipboard.pasteImage",
    "newSession": "app.session.new",
    "tree": "app.session.tree",
    "fork": "app.session.fork",
    "resume": "app.session.resume",
    "treeFoldOrUp": "app.tree.foldOrUp",
    "treeUnfoldOrDown": "app.tree.unfoldOrDown",
    "treeEditLabel": "app.tree.editLabel",
    "treeToggleLabelTimestamp": "app.tree.toggleLabelTimestamp",
    "toggleSessionPath": "app.session.togglePath",
    "toggleSessionSort": "app.session.toggleSort",
    "renameSession": "app.session.rename",
    "deleteSession": "app.session.delete",
    "deleteSessionNoninvasive": "app.session.deleteNoninvasive",
}


# ============================================================================
# Migration helpers
# ============================================================================


def _is_record(value: object) -> bool:
    """Local re-implementation of OpenClaw's
    ``isRecord`` (from
    ``@openclaw/normalization-core/record-coerce``).
    Returns True for non-array, non-null objects.
    """
    return isinstance(value, dict)


def is_legacy_keybinding_name(key: str) -> bool:
    """True iff ``key`` has a legacy-name migration.

    Mirrors ``isLegacyKeybindingName``
    (``keybindings.ts:272-274``).
    """
    return key in KEYBINDING_NAME_MIGRATIONS


def to_keybindings_config(value: object) -> KeybindingsConfig:
    """Coerce a JSON-decoded value to a typed
    keybindings config. Mirrors
    ``toKeybindingsConfig`` (``keybindings.ts:276-292``).

    Only string and array-of-string values are
    accepted; everything else is silently dropped
    (matches the OpenClaw source's behaviour).
    """
    if not _is_record(value):
        return {}

    config: KeybindingsConfig = {}
    for key, binding in value.items():
        if isinstance(binding, str):
            config[key] = binding
            continue
        if (
            isinstance(binding, list)
            and all(isinstance(item, str) for item in binding)
        ):
            config[key] = list(binding)  # type: ignore[arg-type]
    return config


def _order_keybindings_config(
    config: dict,
) -> dict:
    """Push known key ids first, then alphabetize
    unknown extras. Mirrors ``orderKeybindingsConfig``
    (``keybindings.ts:318-334``)."""
    ordered: dict = {}
    for keybinding in KEYBINDINGS:
        if keybinding in config:
            ordered[keybinding] = config[keybinding]

    extras = sorted(
        key for key in config if key not in ordered
    )
    for key in extras:
        ordered[key] = config[key]
    return ordered


def migrate_keybindings_config(
    raw_config: dict,
) -> tuple[dict, bool]:
    """Migrate legacy keybinding names + order
    known entries ahead of unknown extras.

    Mirrors ``migrateKeybindingsConfig``
    (``keybindings.ts:295-316``).

    Returns
    -------
    (config, migrated) : tuple[dict, bool]
        The migrated config + a flag indicating
        whether any rename happened.
    """
    config: dict = {}
    migrated = False

    for key, value in raw_config.items():
        next_key = (
            KEYBINDING_NAME_MIGRATIONS[key]
            if is_legacy_keybinding_name(key)
            else key
        )
        if next_key != key:
            migrated = True
        if key != next_key and next_key in raw_config:
            # New names win when both legacy and
            # migrated keys are present.
            migrated = True
            continue
        config[next_key] = value

    return _order_keybindings_config(config), migrated


def load_raw_config(path: str) -> Optional[dict]:
    """Read a JSON file and coerce to ``dict``.

    Mirrors ``loadRawConfig`` (``keybindings.ts:336-346``).
    Returns ``None`` if the file is missing, the
    content is not valid JSON, or the parsed value
    is not a dict.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not _is_record(parsed):
        return None
    return parsed  # type: ignore[return-value]


# ============================================================================
# KeybindingsManager
# ============================================================================


def _default_agent_dir() -> str:
    """Return the JARVIS agent directory.

    The OpenClaw source uses ``getAgentDir()`` from
    ``../config.js``; the Python port ships a local
    helper that returns the JARVIS convention
    (``~/.jarvis/agents/default``) until the full
    config surface lands in Phase 6.8.
    """
    home = Path.home()
    return str(home / ".jarvis" / "agents" / "default")


class KeybindingsManager:
    """User-override loader for keybindings. Mirrors
    ``KeybindingsManager`` (``keybindings.ts:349-384``).

    The OpenClaw source extends a TUI library's
    ``KeybindingsManager``; the Python port is a
    standalone class with the same public surface
    (the actual TUI binding can be wired in a future
    Phase 6.16 when a Python TUI library is chosen).
    """

    def __init__(
        self,
        user_bindings: Optional[KeybindingsConfig] = None,
        config_path: Optional[str] = None,
    ) -> None:
        self._user_bindings: KeybindingsConfig = dict(user_bindings or {})
        self._config_path = config_path

    @staticmethod
    def create(agent_dir: str = "") -> "KeybindingsManager":
        """Create a manager from the agent's
        ``keybindings.json``. Mirrors
        ``KeybindingsManager.create``
        (``keybindings.ts:358-362``)."""
        if not agent_dir:
            agent_dir = _default_agent_dir()
        config_path = str(Path(agent_dir) / "keybindings.json")
        user_bindings = KeybindingsManager.load_from_file(config_path)
        return KeybindingsManager(user_bindings=user_bindings, config_path=config_path)

    def reload(self) -> None:
        """Reload user overrides from disk when this
        manager was created with a config path.
        Mirrors ``KeybindingsManager.reload``
        (``keybindings.ts:365-370``)."""
        if not self._config_path:
            return
        self._user_bindings = KeybindingsManager.load_from_file(
            self._config_path
        )

    def get_effective_config(self) -> KeybindingsConfig:
        """Return the currently resolved keybinding
        map (defaults + user overrides). Mirrors
        ``KeybindingsManager.getEffectiveConfig``
        (``keybindings.ts:373-375``).

        User overrides win over the default table.
        """
        effective: KeybindingsConfig = {}
        for key, defn in KEYBINDINGS.items():
            effective[key] = defn.default_keys
        for key, value in self._user_bindings.items():
            effective[key] = value
        return effective

    def set_user_bindings(self, bindings: KeybindingsConfig) -> None:
        """Replace the in-memory user bindings (used
        by :meth:`reload`)."""
        self._user_bindings = dict(bindings)

    @staticmethod
    def load_from_file(path: str) -> KeybindingsConfig:
        """Read a ``keybindings.json`` file, migrate
        legacy names, and return a typed config.

        Mirrors the private
        ``KeybindingsManager.loadFromFile``
        (``keybindings.ts:377-383``).
        """
        raw = load_raw_config(path)
        if raw is None:
            return {}
        migrated, _ = migrate_keybindings_config(raw)
        return to_keybindings_config(migrated)


__all__ = [
    "KeyBindingValue",
    "KeybindingDef",
    "KeybindingsConfig",
    "KeybindingsManager",
    "KEYBINDINGS",
    "KEYBINDING_NAME_MIGRATIONS",
    "is_legacy_keybinding_name",
    "load_raw_config",
    "migrate_keybindings_config",
    "to_keybindings_config",
]
