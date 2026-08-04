"""jarvis.config.schema_shared — shared JSON-schema helpers.

OpenClaw parity: mirrors ``openclaw-main/src/config/schema.shared.ts``.
"""
from __future__ import annotations

import copy
from typing import Any, Optional


def clone_schema(value):
    """Deep-clone a schema payload before callers mutate it.

    Mirrors :func:`cloneSchema`
    (``shared/config/schema.shared.ts`).
    """
    return copy.deepcopy(value)


def as_schema_object(value) -> Optional[dict]:
    """Narrow unknown JSON-schema fragments to non-array objects.

    Mirrors :func:`asSchemaObject`
    (``shared/config/schema.shared.ts`).
    """
    if not value or not isinstance(value, dict):
        return None
    return value


def schema_has_children(schema: dict) -> bool:
    """Return whether a schema node exposes nested fields.

    Mirrors :func:`schemaHasChildren`
    (``shared/config/schema.shared.ts`).
    """
    if not isinstance(schema, dict):
        return False
    properties = schema.get("properties")
    if isinstance(properties, dict) and properties:
        return True
    addl = schema.get("additionalProperties")
    if isinstance(addl, dict):
        return True
    items = schema.get("items")
    if isinstance(items, list):
        return any(isinstance(entry, dict) and entry for entry in items)
    for branch in (schema.get("oneOf"), schema.get("anyOf"), schema.get("allOf")):
        if isinstance(branch, list):
            if any(isinstance(entry, dict) and schema_has_children(entry) for entry in branch):
                return True
    return isinstance(items, dict)


def find_wildcard_hint_match(params: dict):
    """Find the most specific wildcard UI hint that matches a config path.

    Mirrors :func:`findWildcardHintMatch`
    (``shared/config/schema.shared.ts`).
    """
    ui_hints = params.get("uiHints") or {}
    path = params.get("path") or ""
    split_path = params.get("splitPath") or (lambda p: [s for s in p.split(".") if s])
    target_parts = list(split_path(path))
    best: Optional[dict] = None
    for hint_path, hint in ui_hints.items():
        hint_parts = list(split_path(hint_path))
        if len(hint_parts) != len(target_parts):
            continue
        wildcard_count = 0
        matches = True
        for i, h in enumerate(hint_parts):
            t = target_parts[i]
            if h == t:
                continue
            if h == "*":
                wildcard_count += 1
                continue
            matches = False
            break
        if not matches:
            continue
        # Fewer wildcards = more specific = wins ties.
        if best is None or wildcard_count < best["wildcard_count"]:
            best = {
                "path": hint_path,
                "hint": hint,
                "wildcard_count": wildcard_count,
            }
    if best is None:
        return None
    return {"path": best["path"], "hint": best["hint"]}


__all__ = [
    "clone_schema",
    "as_schema_object",
    "schema_has_children",
    "find_wildcard_hint_match",
]
