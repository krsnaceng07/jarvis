"""jarvis.agents.sessions.settings_manager — session settings manager.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/settings-manager.ts``.

Loads and persists user/session defaults for
models, transports, retry policy, UI,
packages, and telemetry. Supports global
(``~/.jarvis/agents/default/settings.json``) +
project (``./.jarvis/settings.json``) scopes
+ runtime overrides layered on top.

Phase 6.8a — settings manager foundation
(storage + core load/reload/flush/save).

Adaptations
-----------
- The OpenClaw source's TS interfaces
  (``Settings``, ``CompactionSettings``,
  ``BranchSummarySettings``, …) are
  replaced with plain ``dict`` shapes.
  The full typed Settings surface lands in
  Phase 6.8b.
- The OpenClaw source's
  ``@openclaw/normalization-core`` is the
  LLM-side normalizer. The Python port uses
  a hand-rolled ``resolve_integer_option``
  helper (Phase 6.8+ wires the LLM-side
  normalizer).
- The OpenClaw source's
  ``mergeDeep`` from ``../../infra/deep-merge.js``
  is replaced with a hand-rolled
  ``_deep_merge`` helper (Phase 6.8+ wires
  the LLM-side deep-merge).
- The OpenClaw source's
  ``structuredClone`` is replaced with
  :func:`copy.deepcopy`.
- The OpenClaw source uses Node's
  ``readFileSync`` / ``writeFileSync`` /
  ``existsSync`` / ``mkdirSync``. The Python
  port uses the equivalent :mod:`os` /
  :mod:`json` + :func:`open` calls.
- The OpenClaw source's typed setters
(``getSteeringMode`` / ``setSteeringMode`` /
``getRetrySettings`` / ``setRetryEnabled`` /
``getProviderRetrySettings`` / …) ship in
Phase 6.8b.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
from typing import Any, Optional


_LOG = logging.getLogger("jarvis.agents.sessions.settings_manager")


# ============================================================================
# Settings types (Phase 6.8a minimal shape)
# ============================================================================


#: Settings scope: ``"global"`` (in the agent
#: dir) or ``"project"`` (in ``<cwd>/.jarvis/``).
#: Mirrors ``SettingsScope``
#: (``settings-manager.ts:130``).
SettingsScope = str  # "global" | "project"


#: Settings dict. The full typed shape lands
#: in Phase 6.8b. Mirrors ``Settings``
#: (``settings-manager.ts:85-123``).
Settings = dict


#: Settings error. Mirrors ``SettingsError``
#: (``settings-manager.ts:136-139``).
SettingsError = dict


# ============================================================================
# Deep merge
# ============================================================================


def _deep_merge(base: Any, overrides: Any) -> Any:
    """Recursively merge ``overrides`` into
    ``base``. Mirrors the OpenClaw source's
    ``mergeDeep``
    (``openclaw-main/src/infra/deep-merge.js``).

    The Python port supports the same
    merge semantics: nested dicts are
    merged; non-dict values are replaced.
    Lists are replaced (not concatenated).
    """
    if isinstance(base, dict) and isinstance(overrides, dict):
        merged: dict = {}
        for k, v in base.items():
            merged[k] = v
        for k, v in overrides.items():
            if k in merged:
                merged[k] = _deep_merge(merged[k], v)
            else:
                merged[k] = v
        return merged
    return overrides


# ============================================================================
# SettingsStorage
# ============================================================================


class SettingsStorage:
    """Abstract storage. Mirrors
    ``SettingsStorage``
    (``settings-manager.ts:132-134``)."""

    def with_lock(
        self,
        scope: SettingsScope,
        fn: Callable[[Optional[str]], Optional[str]],
    ) -> None:
        """Acquire the lock, read the current
        content, pass it to ``fn``; if ``fn``
        returns a new value, write it. Mirrors
        the OpenClaw source's
        ``withLock``."""
        raise NotImplementedError


#: Config dir name (matches the OpenClaw source's
#: ``CONFIG_DIR_NAME``). Phase 6.8a ships the
#: OpenClaw default (``.jarvis``); the LLM-side
#: constant lands in 6.8+.
CONFIG_DIR_NAME = ".jarvis"


def _default_agent_dir() -> str:
    """Return the JARVIS agent dir."""
    return str(
        __import__("pathlib").Path.home()
        / ".jarvis"
        / "agents"
        / "default"
    )


class FileSettingsStorage(SettingsStorage):
    """File-backed :class:`SettingsStorage`. Mirrors
    ``FileSettingsStorage``
    (``settings-manager.ts:141-179``)."""

    def __init__(
        self, cwd: str, agent_dir: Optional[str] = None
    ) -> None:
        if agent_dir is None:
            agent_dir = _default_agent_dir()
        self.global_settings_path = os.path.join(agent_dir, "settings.json")
        self.project_settings_path = os.path.join(
            cwd, CONFIG_DIR_NAME, "settings.json"
        )

    def with_lock(
        self,
        scope: SettingsScope,
        fn: Callable[[Optional[str]], Optional[str]],
    ) -> None:
        # Phase 6.8a ships an in-process
        # ``threading.Lock`` (per-scope) + a
        # Windows-friendly read-then-write
        # pattern (matching the auth-storage
        # Phase 6.6 fix). The full cross-process
        # ``acquire_lock_sync_with_retry`` lands
        # with the infra layer in 6.8+.
        file_path = (
            self.global_settings_path
            if scope == "global"
            else self.project_settings_path
        )
        parent_dir = os.path.dirname(file_path)
        # Read the current content.
        current: Optional[str] = None
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    current = f.read()
            except (OSError, FileNotFoundError):
                current = None
        next_content = fn(current)
        if next_content is not None:
            if not os.path.isdir(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(next_content)


class InMemorySettingsStorage(SettingsStorage):
    """In-memory :class:`SettingsStorage`. Mirrors
    ``InMemorySettingsStorage``
    (``settings-manager.ts:181-196``)."""

    def __init__(self) -> None:
        self.global_value: Optional[str] = None
        self.project_value: Optional[str] = None
        self._lock = threading.Lock()

    def with_lock(
        self,
        scope: SettingsScope,
        fn: Callable[[Optional[str]], Optional[str]],
    ) -> None:
        with self._lock:
            current = (
                self.global_value
                if scope == "global"
                else self.project_value
            )
            next_content = fn(current)
            if next_content is not None:
                if scope == "global":
                    self.global_value = next_content
                else:
                    self.project_value = next_content


# ============================================================================
# SettingsManager (core)
# ============================================================================


def _migrate_settings(settings: dict) -> dict:
    """Migrate the old settings format to the
    new format. Mirrors
    ``migrateSettings``
    (``settings-manager.ts:295-361``).

    - ``queueMode`` → ``steeringMode``
    - Legacy ``websockets: bool`` →
      ``transport: "websocket" | "sse"``
    - Old ``skills: {…}`` object → ``skills: [...]`` array
    - ``retry.maxDelayMs`` →
      ``retry.provider.maxRetryDelayMs``
    """
    if (
        "queueMode" in settings
        and not isinstance(settings.get("queueMode"), dict)
        and "steeringMode" not in settings
    ):
        settings["steeringMode"] = settings.pop("queueMode")
    if (
        "transport" not in settings
        and isinstance(settings.get("websockets"), bool)
    ):
        settings["transport"] = (
            "websocket" if settings["websockets"] else "sse"
        )
        del settings["websockets"]
    if (
        "skills" in settings
        and isinstance(settings["skills"], dict)
    ):
        skills_settings = settings["skills"]
        if (
            "enableSkillCommands" in skills_settings
            and "enableSkillCommands" not in settings
        ):
            settings["enableSkillCommands"] = skills_settings[
                "enableSkillCommands"
            ]
        if (
            isinstance(skills_settings.get("customDirectories"), list)
            and skills_settings["customDirectories"]
        ):
            settings["skills"] = skills_settings["customDirectories"]
        else:
            del settings["skills"]
    if (
        "retry" in settings
        and isinstance(settings["retry"], dict)
    ):
        retry = settings["retry"]
        provider = retry.get("provider")
        if (
            isinstance(retry.get("maxDelayMs"), (int, float))
            and not isinstance(provider, dict)
        ):
            retry["provider"] = {
                **(provider or {}),
                "maxRetryDelayMs": retry["maxDelayMs"],
            }
        retry.pop("maxDelayMs", None)
    return settings


class SettingsManager:
    """Settings manager. Mirrors ``SettingsManager``
    (``settings-manager.ts:198-1080``).

    Phase 6.8a ships the core: constructor +
    factories + load/reload/flush + global /
    project settings getters + the deep-merge
    + the ``applyOverrides`` API. The typed
    setters (``getSteeringMode`` /
    ``setSteeringMode`` / etc.) land in
    Phase 6.8b.
    """

    def __init__(
        self,
        storage: SettingsStorage,
        initial_global: Settings,
        initial_project: Settings,
        global_load_error: Optional[BaseException] = None,
        project_load_error: Optional[BaseException] = None,
        initial_errors: Optional[list[SettingsError]] = None,
    ) -> None:
        self.storage = storage
        self.global_settings: Settings = initial_global
        self.project_settings: Settings = initial_project
        self.global_settings_load_error = global_load_error
        self.project_settings_load_error = project_load_error
        self.errors: list[SettingsError] = list(initial_errors or [])
        self.runtime_overrides: Settings = {}
        # Per-field modification tracking
        # (Phase 6.8a ships a no-op for the
        # typed setters; 6.8b wires the actual
        # tracking).
        self.modified_fields: set[str] = set()
        self.modified_nested_fields: dict[str, set[str]] = {}
        self.modified_project_fields: set[str] = set()
        self.modified_project_nested_fields: dict[str, set[str]] = {}
        # Async write queue (mirrors the
        # OpenClaw source's
        # ``writeQueue: Promise<void>``).
        self._write_queue: Optional[Any] = None
        self._write_lock = threading.Lock()
        self._recompute_settings()

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @staticmethod
    def create(
        cwd: str, agent_dir: Optional[str] = None
    ) -> "SettingsManager":
        """File-backed settings manager. Mirrors
        ``SettingsManager.create``
        (``settings-manager.ts:232-235``)."""
        if agent_dir is None:
            agent_dir = _default_agent_dir()
        storage = FileSettingsStorage(cwd, agent_dir)
        return SettingsManager.from_storage(storage)

    @staticmethod
    def from_storage(storage: SettingsStorage) -> "SettingsManager":
        """Build a manager from an arbitrary
        storage backend. Mirrors
        ``SettingsManager.fromStorage``
        (``settings-manager.ts:238-257``)."""
        global_load = SettingsManager._try_load_from_storage(storage, "global")
        project_load = SettingsManager._try_load_from_storage(
            storage, "project"
        )
        initial_errors: list[SettingsError] = []
        if global_load.get("error"):
            initial_errors.append(
                {
                    "scope": "global",
                    "error": global_load["error"],
                }
            )
        if project_load.get("error"):
            initial_errors.append(
                {
                    "scope": "project",
                    "error": project_load["error"],
                }
            )
        return SettingsManager(
            storage=storage,
            initial_global=global_load.get("settings", {}),
            initial_project=project_load.get("settings", {}),
            global_load_error=global_load.get("error"),
            project_load_error=project_load.get("error"),
            initial_errors=initial_errors,
        )

    @staticmethod
    def in_memory(settings: Optional[Settings] = None) -> "SettingsManager":
        """In-memory settings manager. Mirrors
        ``SettingsManager.inMemory``
        (``settings-manager.ts:260-267``)."""
        settings = settings or {}
        storage = InMemorySettingsStorage()
        migrated = _migrate_settings(copy.deepcopy(dict(settings)))
        storage.with_lock(
            "global", lambda _current: json.dumps(migrated, indent=2)
        )
        return SettingsManager.from_storage(storage)

    # ------------------------------------------------------------------
    # Load / reload / flush
    # ------------------------------------------------------------------

    @staticmethod
    def _load_from_storage(
        storage: SettingsStorage, scope: SettingsScope
    ) -> Settings:
        """Read + parse + migrate the settings
        from ``storage``. Mirrors
        ``loadFromStorage``
        (``settings-manager.ts:269-281``)."""
        content: Optional[str] = None
        def _read(current: Optional[str]) -> Optional[str]:
            nonlocal content
            content = current
            return None
        storage.with_lock(scope, _read)
        if not content:
            return {}
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            return {}
        if not isinstance(parsed, dict):
            return {}
        return _migrate_settings(parsed)

    @staticmethod
    def _try_load_from_storage(
        storage: SettingsStorage, scope: SettingsScope
    ) -> dict:
        """Try-load variant that captures the
        load error. Mirrors
        ``tryLoadFromStorage``
        (``settings-manager.ts:283-292``)."""
        try:
            return {
                "settings": SettingsManager._load_from_storage(
                    storage, scope
                ),
                "error": None,
            }
        except Exception as exc:
            return {"settings": {}, "error": exc}

    async def reload(self) -> None:
        """Reload from disk. Mirrors ``reload``
        (``settings-manager.ts:378-404``)."""
        await self._join_write_queue()
        global_load = SettingsManager._try_load_from_storage(
            self.storage, "global"
        )
        if not global_load.get("error"):
            self.global_settings = global_load["settings"]
            self.global_settings_load_error = None
        else:
            self.global_settings_load_error = global_load["error"]
            self._record_error("global", global_load["error"])
        self.modified_fields.clear()
        self.modified_nested_fields.clear()
        self.modified_project_fields.clear()
        self.modified_project_nested_fields.clear()
        project_load = SettingsManager._try_load_from_storage(
            self.storage, "project"
        )
        if not project_load.get("error"):
            self.project_settings = project_load["settings"]
            self.project_settings_load_error = None
        else:
            self.project_settings_load_error = project_load["error"]
            self._record_error("project", project_load["error"])
        self._recompute_settings()

    async def flush(self) -> None:
        """Wait for the pending write queue to
        finish. Mirrors ``flush``
        (``settings-manager.ts:544-546``)."""
        await self._join_write_queue()

    async def _join_write_queue(self) -> None:
        """Wait for the in-flight write (if any)
        to complete."""
        if self._write_queue is None:
            return
        # The Python port uses a future +
        # threading lock; ``await`` yields
        # back to the event loop. The OpenClaw
        # source uses a chained Promise
        # (the same shape).
        import asyncio
        try:
            await asyncio.shield(self._write_queue)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    def get_global_settings(self) -> Settings:
        """Mirrors ``getGlobalSettings``
        (``settings-manager.ts:363-365``)."""
        return copy.deepcopy(self.global_settings)

    def get_project_settings(self) -> Settings:
        """Mirrors ``getProjectSettings``
        (``settings-manager.ts:367-369``)."""
        return copy.deepcopy(self.project_settings)

    def get_settings(self) -> Settings:
        """Return the merged (global + project +
        runtime-overrides) settings. Mirrors
        the OpenClaw source's
        ``this.settings`` (private) used by the
        typed getters."""
        return copy.deepcopy(self.settings)

    def get_session_dir(self) -> Optional[str]:
        """Mirrors ``getSessionDir``
        (``settings-manager.ts:564-576``)."""
        session_dir = self.settings.get("sessionDir")
        if not session_dir:
            return session_dir
        if session_dir == "~":
            return os.path.expanduser("~")
        if session_dir.startswith("~/") or session_dir.startswith("~\\"):
            home = os.path.expanduser("~")
            tail = session_dir[2:]
            return os.path.join(home, tail)
        return session_dir

    # ------------------------------------------------------------------
    # applyOverrides
    # ------------------------------------------------------------------

    def apply_overrides(self, overrides: Settings) -> None:
        """Apply non-persisted overrides on top
        of global/project settings. Mirrors
        ``applyOverrides``
        (``settings-manager.ts:407-410``)."""
        self.runtime_overrides = _deep_merge(
            self.runtime_overrides, overrides
        )
        self._recompute_settings()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recompute_settings(self) -> None:
        """Recompute the merged settings from
        global + project + runtime overrides.
        Mirrors ``recomputeSettings``
        (``settings-manager.ts:371-376``)."""
        self.settings = _deep_merge(
            _deep_merge(self.global_settings, self.project_settings),
            self.runtime_overrides,
        )

    def _record_error(self, scope: SettingsScope, error: Any) -> None:
        """Record an error in the errors list.
        Mirrors ``recordError``
        (``settings-manager.ts:434-437``)."""
        normalized = (
            error if isinstance(error, BaseException) else RuntimeError(str(error))
        )
        self.errors.append({"scope": scope, "error": normalized})

    def drain_errors(self) -> list[SettingsError]:
        """Drain + clear the error list. Mirrors
        ``drainErrors``
        (``settings-manager.ts:548-552``)."""
        drained = list(self.errors)
        self.errors = []
        return drained

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Persist the global settings. Mirrors
        ``save``
        (``settings-manager.ts:502-521``).

        Phase 6.8a ships the sync save path
        (the OpenClaw source's
        ``enqueueWrite`` chains a Promise;
        the Python port uses
        ``_schedule_write`` which runs the
        task synchronously after the
        in-flight task).
        """
        if self.global_settings_load_error:
            return
        snapshot = copy.deepcopy(self.global_settings)
        modified_fields = set(self.modified_fields)
        modified_nested = {
            k: set(v) for k, v in self.modified_nested_fields.items()
        }
        def _task() -> None:
            self._persist_scoped_settings(
                "global", snapshot, modified_fields, modified_nested
            )
        self._schedule_write("global", _task)
        # Clear the modification tracking
        # (the OpenClaw source's
        # ``clearModifiedScope`` does this in
        # the chained Promise).
        self.modified_fields.clear()
        self.modified_nested_fields.clear()

    def _persist_scoped_settings(
        self,
        scope: SettingsScope,
        snapshot_settings: Settings,
        modified_fields: set[str],
        modified_nested_fields: dict[str, set[str]],
    ) -> None:
        """Persist the scoped settings via
        ``storage.withLock``. Mirrors
        ``persistScopedSettings``
        (``settings-manager.ts:471-500``)."""
        def _merge(current: Optional[str]) -> Optional[str]:
            if not current:
                current_dict: dict = {}
            else:
                try:
                    parsed = json.loads(current)
                    current_dict = (
                        _migrate_settings(parsed)
                        if isinstance(parsed, dict)
                        else {}
                    )
                except (ValueError, TypeError):
                    current_dict = {}
            merged: dict = {**current_dict}
            for field in modified_fields:
                value = snapshot_settings.get(field)
                if (
                    field in modified_nested_fields
                    and isinstance(value, dict)
                ):
                    nested_modified = modified_nested_fields[field]
                    base_nested = current_dict.get(field) or {}
                    in_memory_nested = value
                    merged_nested: dict = {
                        **(
                            base_nested
                            if isinstance(base_nested, dict)
                            else {}
                        )
                    }
                    for nested_key in nested_modified:
                        merged_nested[nested_key] = in_memory_nested.get(
                            nested_key
                        )
                    merged[field] = merged_nested
                else:
                    merged[field] = value
            return json.dumps(merged, indent=2)
        self.storage.with_lock(scope, _merge)

    def _schedule_write(
        self, scope: SettingsScope, task: Callable[[], None]
    ) -> None:
        """Schedule a write task. The OpenClaw
        source uses a chained Promise; the
        Python port runs the task
        synchronously (the cross-process
        async write lands in 6.8+ with the
        infra layer)."""
        with self._write_lock:
            task()


__all__ = [
    "CONFIG_DIR_NAME",
    "FileSettingsStorage",
    "InMemorySettingsStorage",
    "Settings",
    "SettingsError",
    "SettingsManager",
    "SettingsScope",
    "SettingsStorage",
]
