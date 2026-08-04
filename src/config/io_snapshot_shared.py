"""jarvis.config.io_snapshot_shared — shared config-snapshot construction.

OpenClaw parity: mirrors ``openclaw-main/src/config/io.snapshot-shared.ts``.

Focused minimal port: ``createConfigFileSnapshot`` builds the public
``ConfigFileSnapshot`` shape. Observation + legacy-issue collection are
delegated to caller-provided callables.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


def create_config_file_snapshot(params: dict) -> dict:
    """Build the public ``ConfigFileSnapshot`` shape with ``source`` and ``runtime`` views.

    Mirrors :func:`createConfigFileSnapshot`
    (``shared/config/io.snapshot-shared.ts`).
    """
    source_config = params.get("sourceConfig") or {}
    runtime_config = params.get("runtimeConfig") or {}
    snapshot: dict = {
        "path": params.get("path"),
        "exists": params.get("exists", False),
        "raw": params.get("raw"),
        "parsed": params.get("parsed"),
        "sourceConfig": source_config,
        "resolved": source_config,
        "valid": params.get("valid", False),
        "runtimeConfig": runtime_config,
        "config": runtime_config,
        "issues": params.get("issues") or [],
        "warnings": params.get("warnings") or [],
        "legacyIssues": params.get("legacyIssues") or [],
    }
    if "hash" in params:
        snapshot["hash"] = params["hash"]
    if params.get("readError"):
        snapshot["readError"] = params["readError"]
    return snapshot


async def finalize_read_config_snapshot_internal_result(
    deps: dict,
    result: dict,
    options: Optional[dict] = None,
    *,
    observe_config_snapshot_fn: Optional[Callable] = None,
) -> dict:
    """Run the ``observe`` step on a read snapshot if enabled.

    Mirrors :func:`finalizeReadConfigSnapshotInternalResult`
    (``shared/config/io.snapshot-shared.ts`).
    """
    options = options or {}
    if deps.get("observe") and options.get("observe", True):
        if callable(observe_config_snapshot_fn):
            await observe_config_snapshot_fn(deps, result.get("snapshot"))
    return result


async def collect_invalid_config_legacy_issues(
    raw: Any,
    source_raw: Any,
    *,
    find_doctor_legacy_config_issues: Optional[Callable] = None,
) -> list:
    """Collect doctor-style legacy issues for an invalid config.

    Mirrors :func:`collectInvalidConfigLegacyIssues`
    (``shared/config/io.snapshot-shared.ts`).
    """
    if not raw or not isinstance(raw, dict):
        return []
    if not callable(find_doctor_legacy_config_issues):
        return []
    return await find_doctor_legacy_config_issues(raw, source_raw)


__all__ = [
    "create_config_file_snapshot",
    "finalize_read_config_snapshot_internal_result",
    "collect_invalid_config_legacy_issues",
]
