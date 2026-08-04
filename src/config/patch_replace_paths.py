"""jarvis.config.patch_replace_paths — config.patch replacePaths normalizer.

OpenClaw parity: mirrors
``openclaw-main/src/config/patch-replace-paths.ts``.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Set

#: Match numeric array indexes in dotted paths so we normalize to ``[]`` form.
_ARRAY_INDEX_RE = re.compile(r"\[\d+\](?=\.)")


def _normalize_config_patch_replace_path(value: str) -> str:
    if not isinstance(value, str):
        return ""
    trimmed = value.strip()
    if trimmed.endswith("[]"):
        return _ARRAY_INDEX_RE.sub("[]", trimmed[:-2])
    return _ARRAY_INDEX_RE.sub("[]", trimmed)


def normalize_config_patch_replace_paths(values: Optional[Iterable]) -> Set[str]:
    """Return the normalized set of replacePaths for config.patch.

    Mirrors :func:`normalizeConfigPatchReplacePaths`
    (``shared/config/patch-replace-paths.ts`).
    """
    if not values:
        return set()
    return {
        v
        for v in (_normalize_config_patch_replace_path(x) for x in values)
        if isinstance(v, str) and v
    }


__all__ = ["normalize_config_patch_replace_paths"]
