"""lancedb_schema — table name + agent predicate helpers.

OpenClaw parity: mirrors ``extensions/memory-lancedb/lancedb-schema.ts``.

Single source of truth for the LanceDB table name and the
``agentId`` predicate used by every store operation. Keeping
these in one file guarantees the in-memory fallback and the
real LanceDB backend never drift on schema shape.
"""

from __future__ import annotations

import re

# Mirrors ``MEMORY_TABLE_NAME`` in OpenClaw.
MEMORY_TABLE_NAME = "memories"

# Mirrors ``MEMORY_AGENT_ID_COLUMN`` in OpenClaw.
MEMORY_AGENT_ID_COLUMN = "agentId"

# UUID v1/v4/v5 pattern — used by ``MemoryDB.delete`` to validate
# incoming memory ids before they hit the SQL predicate. Mirrors
# OpenClaw's ``UUID_PATTERN``.
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def quote_lance_sql_string(value: str) -> str:
    """Quote a string for inclusion in a LanceDB SQL predicate.

    Mirrors OpenClaw's ``quoteLanceSqlString``. The naive
    single-quote escape (``'value'`` with doubled internal ``'``)
    is the LanceDB convention.
    """
    return f"'{value.replace(chr(39), chr(39) * 2)}'"


def memory_agent_predicate(agent_id: str) -> str:
    """Return a LanceDB SQL predicate that scopes to one agent.

    Mirrors OpenClaw's ``memoryAgentPredicate``. Foreign rows
    must never enter this agent's candidate set or top-K.
    """
    return f"{MEMORY_AGENT_ID_COLUMN} = {quote_lance_sql_string(agent_id)}"


def has_agent_scope_column(schema: object) -> bool:
    """Return True if the given table schema has an ``agentId`` column.

    Mirrors OpenClaw's ``hasAgentScopeColumn``. Used by the
    doctor migration to detect pre-isolation legacy tables.

    Robust to multiple schema shapes: LanceDB's
    ``table.schema()`` returns a ``pyarrow.Schema`` (which
    exposes ``.names`` but no ``.fields`` iterator), but
    some LanceDB versions return a dataclass-like object
    with ``.fields``. We try the cheapest path first
    (``schema.names``) and fall back to the iterator.
    """
    # Cheap path: pyarrow exposes a ``names`` tuple.
    names = getattr(schema, "names", None)
    if names is not None:
        return MEMORY_AGENT_ID_COLUMN in names
    # Fallback: iterate fields (older LanceDB or duck-typed
    # schema providers).
    fields = getattr(schema, "fields", None)
    if not fields:
        return False
    return any(getattr(field, "name", None) == MEMORY_AGENT_ID_COLUMN for field in fields)


def is_valid_memory_id(memory_id: str) -> bool:
    """Return True if ``memory_id`` is a well-formed UUID.

    Mirrors OpenClaw's ``UUID_PATTERN.test(id)`` guard in
    ``MemoryDB.delete``. The check prevents accidental SQL
    predicate injection through crafted ids.
    """
    return bool(_UUID_PATTERN.match(memory_id))


def legacy_memory_schema_error() -> Exception:
    """Error returned when a pre-isolation memory table is found.

    Mirrors OpenClaw's ``legacyMemorySchemaError``.
    """
    return RuntimeError(
        "memory-lancedb: the existing memory table predates per-agent "
        "isolation. Run `jarvis doctor --fix` to assign legacy rows to "
        "the default agent, then restart JARVIS."
    )


__all__ = [
    "MEMORY_AGENT_ID_COLUMN",
    "MEMORY_TABLE_NAME",
    "has_agent_scope_column",
    "is_valid_memory_id",
    "legacy_memory_schema_error",
    "memory_agent_predicate",
    "quote_lance_sql_string",
]
