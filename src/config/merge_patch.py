"""jarvis.config.merge_patch — RFC 7396 merge-patch with config safeguards.

OpenClaw parity: mirrors
``openclaw-main/src/config/merge-patch.ts``.
"""
from __future__ import annotations

from typing import Any, Optional, Set

_BLOCKED_KEYS = frozenset({"__proto__", "prototype", "constructor"})


def _is_blocked_object_key(key: str) -> bool:
    return key in _BLOCKED_KEYS


def _is_plain_object(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes, set))


def _is_object_with_string_id(value) -> bool:
    return _is_plain_object(value) and isinstance(value.get("id"), str) and bool(value.get("id"))


def is_merge_patch_object_key_allowed(key: str, parent_path: Optional[str] = None) -> bool:
    """Return whether ``key`` is safe at the given config path.

    Mirrors :func:`isMergePatchObjectKeyAllowed`
    (``shared/config/merge-patch.ts`).
    """
    if not _is_blocked_object_key(key):
        return True
    return parent_path == "browser.profiles" and key in ("constructor", "prototype")


def apply_merge_patch(
    base: Any,
    patch: Any,
    options: Optional[dict] = None,
) -> Any:
    """Apply an RFC 7396-style object merge patch with OpenClaw safeguards.

    Mirrors :func:`applyMergePatch`
    (``shared/config/merge-patch.ts`).
    """
    options = options or {}
    if not _is_plain_object(patch):
        return patch
    result: dict = dict(base) if _is_plain_object(base) else {}
    replace_array_paths: Set[str] = set(options.get("replaceArrayPaths") or set())
    for key, value in patch.items():
        path = f"{options['path']}.{key}" if options.get("path") else key
        if not is_merge_patch_object_key_allowed(key, options.get("path")):
            continue
        if value is None:
            result.pop(key, None)
            continue
        if options.get("mergeObjectArraysById") and isinstance(result.get(key), list) and isinstance(value, list):
            if path in replace_array_paths:
                result[key] = value
                continue
            base_arr = result[key]
            if not all(_is_object_with_string_id(item) for item in base_arr):
                # Not id-keyed: RFC replacement.
                result[key] = value
                continue
            merged = list(base_arr)
            index_by_id: dict = {}
            for idx, item in enumerate(merged):
                if _is_object_with_string_id(item):
                    index_by_id[item["id"]] = idx
            for patch_entry in value:
                if not _is_object_with_string_id(patch_entry):
                    import copy
                    merged.append(copy.deepcopy(patch_entry))
                    continue
                existing_index = index_by_id.get(patch_entry["id"])
                if existing_index is None:
                    import copy
                    merged.append(copy.deepcopy(patch_entry))
                    index_by_id[patch_entry["id"]] = len(merged) - 1
                    continue
                merged[existing_index] = apply_merge_patch(
                    merged[existing_index],
                    patch_entry,
                    {**options, "path": f"{path}[]"},
                )
            result[key] = merged
            continue
        if _is_plain_object(value):
            base_value = result.get(key)
            result[key] = apply_merge_patch(
                base_value if _is_plain_object(base_value) else {},
                value,
                {**options, "path": path},
            )
            continue
        result[key] = value
    return result


__all__ = ["is_merge_patch_object_key_allowed", "apply_merge_patch"]
