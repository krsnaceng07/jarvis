"""doctor — health checks + state migrations for memory_lancedb.

OpenClaw parity: mirrors
``extensions/memory-lancedb/doctor-contract-api.ts``.

Phase 4.1 ships the same surface as OpenClaw:

  - ``detect_legacy`` / ``apply_migration`` — the
    per-agent-isolation migration (assigns legacy rows to
    the default agent).

  - ``check_health`` — a structured health report for the
    CLI (`jarvis doctor`) and the runtime.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .lancedb_runtime import is_lancedb_available, load_lancedb_module
from .lancedb_schema import (
    MEMORY_AGENT_ID_COLUMN,
    MEMORY_TABLE_NAME,
    has_agent_scope_column,
    memory_agent_predicate,
    quote_lance_sql_string,
)

_log = logging.getLogger("extensions.memory_lancedb.doctor")


@dataclass(frozen=True, slots=True)
class MigrationFinding:
    """A single doctor finding (mirrors OpenClaw's preview shape)."""

    id: str
    label: str
    preview: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Result of a state migration. Mirrors OpenClaw's migrate return."""

    changes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _resolve_plugin_db_path(state_dir: Path, plugin_root: Path | None = None) -> Path:
    """Return the LanceDB path the plugin would use.

    Mirrors OpenClaw's ``resolveConfiguredDbPath``. The Phase
    4.1 port checks ``$JARVIS_DATA_DIR/memory/lancedb`` and
    falls back to ``~/.jarvis/memory/lancedb``.
    """
    env = os.environ
    env_data = env.get("JARVIS_DATA_DIR", "").strip()
    if env_data:
        return Path(env_data) / "memory" / "lancedb"
    home = env.get("HOME", "").strip() or str(Path.home())
    return Path(home) / ".jarvis" / "memory" / "lancedb"


# ruff: noqa: PLR0911  # migration is intentionally branchy (mirrors OpenClaw)
def detect_legacy(state_dir: Path, config: Mapping[str, Any]) -> list[MigrationFinding]:
    """Detect a pre-isolation memory table.

    Mirrors OpenClaw's ``detectLegacyState``. Returns an
    empty list if no migration is needed.
    """
    if not is_lancedb_available():
        return []
    db_path = _resolve_plugin_db_path(state_dir)
    if not db_path.exists():
        return []
    try:
        module = load_lancedb_module()
    except RuntimeError:
        return []
    try:
        conn = module.connect(str(db_path))
    except Exception as exc:
        _log.debug("doctor: lancedb connect failed: %s", exc)
        return []
    try:
        table_names = conn.table_names()
        if MEMORY_TABLE_NAME not in table_names:
            return []
        table = conn.open_table(MEMORY_TABLE_NAME)
        if has_agent_scope_column(table.schema()):
            return []
        default_agent = _resolve_default_agent(config)
        count = int(table.count_rows())
        return [
            MigrationFinding(
                id="memory-lancedb-agent-scope",
                label="Memory LanceDB per-agent isolation",
                preview=(
                    f"Memory LanceDB: assign {count} legacy "
                    f"{'row' if count == 1 else 'rows'} at {db_path} to "
                    f"default agent {default_agent}",
                ),
            )
        ]
    except Exception as exc:
        _log.debug("doctor: detect_legacy failed: %s", exc)
        return []
    finally:
        with contextlib.suppress(Exception):
            conn.close()


# ruff: noqa: PLR0911  # migration is intentionally branchy (mirrors OpenClaw)
def apply_migration(state_dir: Path, config: Mapping[str, Any]) -> MigrationResult:
    """Migrate a pre-isolation memory table to add ``agentId``.

    Mirrors OpenClaw's ``migrateLegacyState``.
    """
    if not is_lancedb_available():
        return MigrationResult(
            warnings=("LanceDB runtime is not available; skipping migration.",),
        )
    db_path = _resolve_plugin_db_path(state_dir)
    if not db_path.exists():
        return MigrationResult()
    try:
        module = load_lancedb_module()
    except RuntimeError as exc:
        return MigrationResult(warnings=(str(exc),))
    try:
        conn = module.connect(str(db_path))
    except Exception as exc:
        return MigrationResult(warnings=(f"connect failed: {exc}",))
    try:
        table_names = conn.table_names()
        if MEMORY_TABLE_NAME not in table_names:
            return MigrationResult()
        table = conn.open_table(MEMORY_TABLE_NAME)
        if has_agent_scope_column(table.schema()):
            return MigrationResult()
        default_agent = _resolve_default_agent(config)
        row_count = int(table.count_rows())
        try:
            table.add_columns(
                [
                    {
                        "name": MEMORY_AGENT_ID_COLUMN,
                        "valueSql": quote_lance_sql_string(default_agent),
                    }
                ]
            )
        except AttributeError:
            # Older LanceDB doesn't have add_columns. The schema
            # migration is non-trivial; surface a warning so the
            # operator can re-create the table.
            return MigrationResult(
                warnings=(
                    "LanceDB version too old to add columns; recreate the "
                    "memory table to apply per-agent isolation.",
                ),
            )
        if (
            not has_agent_scope_column(table.schema())
            or int(table.count_rows(memory_agent_predicate(default_agent))) != row_count
        ):
            return MigrationResult(
                warnings=("LanceDB agent-scope migration verification failed.",),
            )
        return MigrationResult(
            changes=(
                f"Assigned {row_count} legacy Memory LanceDB "
                f"{'row' if row_count == 1 else 'rows'} to default agent "
                f"{default_agent}",
            ),
        )
    except Exception as exc:
        return MigrationResult(warnings=(f"migrate failed: {exc}",))
    finally:
        with contextlib.suppress(Exception):
            conn.close()


def _resolve_default_agent(config: Mapping[str, Any]) -> str:
    """Return the configured default agent id, or ``"default"``.

    Mirrors OpenClaw's ``resolveDefaultAgentId``. Phase 4.1
    only consults the in-memory config; the host-owned
    default is wired in Phase 4.2.
    """
    agents = config.get("agents") if isinstance(config, Mapping) else None
    if isinstance(agents, Mapping):
        defaults = agents.get("defaults")
        if isinstance(defaults, Mapping):
            agent_id = defaults.get("id")
            if isinstance(agent_id, str) and agent_id.strip():
                return agent_id.strip()
    return "default"


def check_health(state_dir: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    """Build a structured health report.

    Mirrors OpenClaw's doctor contract return value. Used
    by ``jarvis doctor`` to surface plugin health.
    """
    db_path = _resolve_plugin_db_path(state_dir)
    available = is_lancedb_available()
    report: dict[str, Any] = {
        "id": "memory_lancedb",
        "label": "Memory LanceDB",
        "runtime_available": available,
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "legacy_table": False,
        "row_count": None,
    }
    if not available or not db_path.exists():
        return report
    try:
        module = load_lancedb_module()
        conn = module.connect(str(db_path))
        try:
            table_names = conn.table_names()
            if MEMORY_TABLE_NAME not in table_names:
                return report
            table = conn.open_table(MEMORY_TABLE_NAME)
            report["legacy_table"] = not has_agent_scope_column(table.schema())
            report["row_count"] = int(table.count_rows())
        finally:
            with contextlib.suppress(Exception):
                conn.close()
    except Exception as exc:
        report["error"] = str(exc)
    return report


__all__ = [
    "MigrationFinding",
    "MigrationResult",
    "apply_migration",
    "check_health",
    "detect_legacy",
]
