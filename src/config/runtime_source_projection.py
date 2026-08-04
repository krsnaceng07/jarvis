"""jarvis.config.runtime_source_projection — runtime→source config projection.

OpenClaw parity: mirrors
``openclaw-main/src/config/runtime-source-projection.ts``.

Focused minimal port: thin facade that delegates to ``merge-patch`` for
the actual patch application. The runtime-snapshot getters are
caller-provided.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from src.config.merge_patch import apply_merge_patch


def _is_compatible_top_level_runtime_projection_shape(params: dict) -> bool:
    runtime = params.get("runtimeSnapshot") or {}
    candidate = params.get("candidate") or {}
    if not isinstance(runtime, dict) or not isinstance(candidate, dict):
        return False
    for key in runtime.keys():
        if key not in candidate:
            return False
        rv = runtime[key]
        cv = candidate[key]
        rtype = "array" if isinstance(rv, list) else "null" if rv is None else type(rv).__name__
        ctype = "array" if isinstance(cv, list) else "null" if cv is None else type(cv).__name__
        if rtype != ctype:
            return False
    return True


def project_config_onto_runtime_source_snapshot(
    config: Any,
    *,
    get_runtime_config_snapshot_fn: Optional[Callable] = None,
    get_runtime_config_source_snapshot_fn: Optional[Callable] = None,
    project_source_onto_runtime_shape_fn: Optional[Callable] = None,
    create_merge_patch_fn: Optional[Callable] = None,
) -> Any:
    """Project a runtime-derived config back onto the active authored source snapshot.

    Mirrors :func:`projectConfigOntoRuntimeSourceSnapshot`
    (``shared/config/runtime-source-projection.ts`).
    """
    if not callable(get_runtime_config_snapshot_fn) or not callable(get_runtime_config_source_snapshot_fn):
        return config
    runtime_config_snapshot = get_runtime_config_snapshot_fn()
    runtime_config_source_snapshot = get_runtime_config_source_snapshot_fn()
    if not runtime_config_snapshot or not runtime_config_source_snapshot:
        return config
    if config is runtime_config_snapshot:
        return runtime_config_source_snapshot
    if not _is_compatible_top_level_runtime_projection_shape({
        "runtimeSnapshot": runtime_config_snapshot,
        "candidate": config,
    }):
        return config
    if callable(project_source_onto_runtime_shape_fn):
        projected_source = project_source_onto_runtime_shape_fn(
            runtime_config_source_snapshot, runtime_config_snapshot,
        )
    else:
        projected_source = runtime_config_source_snapshot
    if callable(create_merge_patch_fn):
        runtime_patch = create_merge_patch_fn(runtime_config_snapshot, config)
    else:
        runtime_patch = config
    return apply_merge_patch(projected_source, runtime_patch)


__all__ = ["project_config_onto_runtime_source_snapshot"]
