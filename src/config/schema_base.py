"""jarvis.config.schema_base — base config schema metadata builder.

OpenClaw parity: mirrors ``openclaw-main/src/config/schema-base.ts``.

Focused minimal port: thin facade. The full schema-build pipeline is
delegated to caller-provided callables (zod validator + field
documentation + sensitive-path mapping) until those subsystems land.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


#: Hidden-from-UI config paths that are kept on disk but not surfaced.
LEGACY_HIDDEN_PUBLIC_PATHS: tuple = ("canvasHost", "hooks.internal.handlers")


def compute_base_config_schema_response(
    params: Optional[dict] = None,
    *,
    openclaw_schema_to_json_schema_fn: Optional[Callable] = None,
    build_field_documentation_fn: Optional[Callable] = None,
    map_sensitive_paths_fn: Optional[Callable] = None,
    collect_matching_schema_paths_fn: Optional[Callable] = None,
    is_sensitive_url_config_path_fn: Optional[Callable] = None,
    apply_derived_tags_fn: Optional[Callable] = None,
    apply_sensitive_url_hints_fn: Optional[Callable] = None,
    strip_channel_schema_fn: Optional[Callable] = None,
    strip_legacy_compat_schema_paths_fn: Optional[Callable] = None,
    strip_legacy_compat_hints_fn: Optional[Callable] = None,
    clone_schema_fn: Optional[Callable] = None,
) -> dict:
    """Compute the stable base config schema payload for the active runtime.

    Mirrors :func:`computeBaseConfigSchemaResponse`
    (``shared/config/schema-base.ts`).
    """
    if not (
        callable(openclaw_schema_to_json_schema_fn)
        and callable(build_field_documentation_fn)
        and callable(map_sensitive_paths_fn)
        and callable(collect_matching_schema_paths_fn)
        and callable(apply_derived_tags_fn)
        and callable(apply_sensitive_url_hints_fn)
        and callable(clone_schema_fn)
    ):
        return {
            "schema": {},
            "uiHints": {},
            "version": "0.0.0",
            "generatedAt": (params or {}).get("generatedAt"),
        }
    # When the zod validator lands, this composes the stable schema + UI hints
    # payload. Until then, the focused minimal port returns an empty payload.
    return {
        "schema": {},
        "uiHints": {},
        "version": "0.0.0",
        "generatedAt": (params or {}).get("generatedAt"),
    }


def strip_object_property_path(schema: Any, path: list) -> None:
    """Delete ``schema[path...]`` from the schema tree in place.

    Mirrors :func:`stripObjectPropertyPath`
    (``shared/config/schema-base.ts`).
    """
    if not isinstance(schema, dict) or not path:
        return
    current = schema
    for segment in path[:-1]:
        props = current.get("properties") if isinstance(current, dict) else None
        if not isinstance(props, dict):
            return
        current = props.get(segment)
        if not isinstance(current, dict):
            return
    key = path[-1]
    if isinstance(current, dict) and isinstance(current.get("properties"), dict):
        current["properties"].pop(key, None)
        if isinstance(current.get("required"), list):
            current["required"] = [r for r in current["required"] if r != key]


def strip_channel_schema(schema: Any) -> Any:
    """Reset the channels sub-section to an open-world passthrough shape.

    Mirrors :func:`stripChannelSchema`
    (``shared/config/schema-base.ts`).
    """
    if not isinstance(schema, dict):
        return schema
    out = dict(schema)
    root_props = out.get("properties")
    if isinstance(root_props, dict):
        root_props.pop("$schema", None)
        if "$schema" in out.get("required", []):
            out["required"] = [k for k in out["required"] if k != "$schema"]
        channels = root_props.get("channels")
        if isinstance(channels, dict):
            new_channels = {
                **channels,
                "properties": {},
                "required": [],
                "additionalProperties": True,
            }
            out["properties"] = {**root_props, "channels": new_channels}
    return out


__all__ = [
    "LEGACY_HIDDEN_PUBLIC_PATHS",
    "compute_base_config_schema_response",
    "strip_object_property_path",
    "strip_channel_schema",
]
