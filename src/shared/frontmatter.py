"""jarvis.shared.frontmatter — frontmatter parsing helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/frontmatter.ts``.

Public surface:

- :func:`normalize_string_list`
- :func:`get_frontmatter_string`
- :func:`parse_frontmatter_bool`
- :func:`resolve_openclaw_manifest_block`
- :func:`resolve_openclaw_manifest_requires`
- :func:`resolve_openclaw_manifest_install`
- :func:`resolve_openclaw_manifest_os`
- :func:`parse_openclaw_manifest_install_base`
- :func:`apply_openclaw_manifest_install_common_fields`
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, TypeVar


T = TypeVar("T")


#: Canonical OpenClaw manifest key inside the frontmatter metadata block.
MANIFEST_KEY = "openclaw"

#: Legacy manifest keys still accepted for older skill/hook files.
LEGACY_MANIFEST_KEYS = ["jarvis", "agent"]


def normalize_string_list(value: Any) -> List[str]:
    """Normalize a comma-delimited or list-shaped metadata field into a string list.

    Mirrors :func:`normalizeStringList` (``shared/frontmatter.ts``).
    """
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
        return [p for p in parts if p]
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for item in value:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    out.append(cleaned)
            elif item is not None:
                out.append(str(item))
        return out
    return [str(value)] if value else []


def get_frontmatter_string(frontmatter: Dict[str, Any], key: str) -> Optional[str]:
    """Read ``frontmatter[key]`` only when it is a non-empty string.

    Mirrors :func:`getFrontmatterString` (``shared/frontmatter.ts``).
    """
    if not isinstance(frontmatter, dict):
        return None
    value = frontmatter.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def parse_frontmatter_bool(value: Optional[str], fallback: bool) -> bool:
    """Parse a frontmatter boolean, preserving the caller's default on missing.

    Mirrors :func:`parseFrontmatterBool` (``shared/frontmatter.ts``).
    """
    if not isinstance(value, str):
        return fallback
    cleaned = value.strip().lower()
    if cleaned in ("true", "1", "yes", "on"):
        return True
    if cleaned in ("false", "0", "no", "off"):
        return False
    return fallback


def resolve_openclaw_manifest_block(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse the JSON5 manifest block embedded inside a string frontmatter field.

    Mirrors :func:`resolveOpenClawManifestBlock` (``shared/frontmatter.ts``).
    """
    if not isinstance(params, dict):
        return None
    frontmatter = params.get("frontmatter")
    if not isinstance(frontmatter, dict):
        return None
    key = params.get("key", "metadata")
    raw = get_frontmatter_string(frontmatter, key)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not parsed or not isinstance(parsed, dict):
        return None
    for manifest_key in [MANIFEST_KEY, *LEGACY_MANIFEST_KEYS]:
        candidate = parsed.get(manifest_key)
        if isinstance(candidate, dict):
            return candidate
    return None


def resolve_openclaw_manifest_requires(metadata_obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract normalized runtime requirement lists from a manifest block.

    Mirrors :func:`resolveOpenClawManifestRequires` (``shared/frontmatter.ts``).
    """
    if not isinstance(metadata_obj, dict):
        return None
    requires_raw = metadata_obj.get("requires")
    if not isinstance(requires_raw, dict):
        return None
    return {
        "bins": normalize_string_list(requires_raw.get("bins")),
        "anyBins": normalize_string_list(requires_raw.get("anyBins")),
        "env": normalize_string_list(requires_raw.get("env")),
        "config": normalize_string_list(requires_raw.get("config")),
    }


def resolve_openclaw_manifest_install(
    metadata_obj: Dict[str, Any],
    parse_install_spec: Callable[[Any], Optional[T]],
) -> List[T]:
    """Parse manifest install entries, dropping unsupported specs.

    Mirrors :func:`resolveOpenClawManifestInstall` (``shared/frontmatter.ts``).
    """
    if not isinstance(metadata_obj, dict):
        return []
    install_raw = metadata_obj.get("install")
    if not isinstance(install_raw, list):
        return []
    out: List[T] = []
    for entry in install_raw:
        parsed = parse_install_spec(entry)
        if parsed is not None:
            out.append(parsed)
    return out


def resolve_openclaw_manifest_os(metadata_obj: Dict[str, Any]) -> List[str]:
    """Extract the OS allowlist from a manifest block.

    Mirrors :func:`resolveOpenClawManifestOs` (``shared/frontmatter.ts``).
    """
    if not isinstance(metadata_obj, dict):
        return []
    return normalize_string_list(metadata_obj.get("os"))


def parse_openclaw_manifest_install_base(
    value: Any, allowed_kinds: List[str]
) -> Optional[Dict[str, Any]]:
    """Parse kind/type plus common install fields.

    Mirrors :func:`parseOpenClawManifestInstallBase` (``shared/frontmatter.ts``).
    """
    if not isinstance(value, dict):
        return None
    kind_raw = value.get("kind") if isinstance(value.get("kind"), str) else value.get("type")
    kind = (kind_raw or "").strip().lower() if isinstance(kind_raw, str) else ""
    if not kind or kind not in allowed_kinds:
        return None
    spec: Dict[str, Any] = {"raw": value, "kind": kind}
    if isinstance(value.get("id"), str):
        spec["id"] = value["id"]
    if isinstance(value.get("label"), str):
        spec["label"] = value["label"]
    bins = normalize_string_list(value.get("bins"))
    if bins:
        spec["bins"] = bins
    return spec


def apply_openclaw_manifest_install_common_fields(
    spec: Dict[str, Any],
    parsed: Dict[str, Any],
) -> Dict[str, Any]:
    """Copy optional common install fields onto a caller-specific install spec.

    Mirrors :func:`applyOpenClawManifestInstallCommonFields` (``shared/frontmatter.ts``).
    """
    if not isinstance(spec, dict) or not isinstance(parsed, dict):
        return spec
    if "id" in parsed:
        spec["id"] = parsed["id"]
    if "label" in parsed:
        spec["label"] = parsed["label"]
    if "bins" in parsed:
        spec["bins"] = parsed["bins"]
    return spec


__all__ = [
    "MANIFEST_KEY",
    "LEGACY_MANIFEST_KEYS",
    "normalize_string_list",
    "get_frontmatter_string",
    "parse_frontmatter_bool",
    "resolve_openclaw_manifest_block",
    "resolve_openclaw_manifest_requires",
    "resolve_openclaw_manifest_install",
    "resolve_openclaw_manifest_os",
    "parse_openclaw_manifest_install_base",
    "apply_openclaw_manifest_install_common_fields",
]
