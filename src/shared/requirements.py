"""jarvis.shared.requirements — runtime requirement evaluation.

OpenClaw parity: mirrors ``openclaw-main/src/shared/requirements.ts``.
"""
from __future__ import annotations

import sys
from typing import Any, Callable, List, Optional, TypedDict


class Requirements(TypedDict, total=False):
    bins: List[str]
    anyBins: List[str]
    env: List[str]
    config: List[str]
    os: List[str]


class RequirementConfigCheck(TypedDict):
    path: str
    satisfied: bool


class RequirementsMetadata(TypedDict, total=False):
    requires: dict
    os: List[str]


class RequirementRemote(TypedDict, total=False):
    hasBin: Callable[[str], bool]
    hasAnyBin: Callable[[List[str]], bool]
    platforms: List[str]


def _normalize_os_requirement_platform(platform: str) -> str:
    normalized = platform.strip().lower() if isinstance(platform, str) else ""
    return "darwin" if normalized == "macos" else normalized


def _resolve_missing_bins(params: dict) -> List[str]:
    required = params.get("required") or []
    has_local = params.get("hasLocalBin")
    has_remote = params.get("hasRemoteBin")
    missing: List[str] = []
    for bin_name in required:
        if has_local and has_local(bin_name):
            continue
        if has_remote and has_remote(bin_name):
            continue
        missing.append(bin_name)
    return missing


def _resolve_missing_any_bins(params: dict) -> List[str]:
    required = params.get("required") or []
    if not required:
        return []
    has_local = params.get("hasLocalBin")
    has_remote_any = params.get("hasRemoteAnyBin")
    if has_local and any(has_local(b) for b in required):
        return []
    if has_remote_any and has_remote_any(required):
        return []
    return list(required)


def _resolve_missing_os(params: dict) -> List[str]:
    required = params.get("required") or []
    if not required:
        return []
    local_platform = _normalize_os_requirement_platform(params.get("localPlatform") or "")
    required_set = {_normalize_os_requirement_platform(p) for p in required}
    if local_platform in required_set:
        return []
    remote_platforms = params.get("remotePlatforms") or []
    if any(_normalize_os_requirement_platform(p) in required_set for p in remote_platforms):
        return []
    return list(required)


def _resolve_missing_env(params: dict) -> List[str]:
    required = params.get("required") or []
    is_satisfied = params.get("isSatisfied")
    if not is_satisfied:
        return list(required)
    return [e for e in required if not is_satisfied(e)]


def _build_config_checks(params: dict) -> List[RequirementConfigCheck]:
    required = params.get("required") or []
    is_satisfied = params.get("isSatisfied")
    out: List[RequirementConfigCheck] = []
    for p in required:
        satisfied = bool(is_satisfied(p)) if is_satisfied else False
        out.append({"path": p, "satisfied": satisfied})
    return out


def evaluate_requirements(
    *,
    always: bool,
    required: Requirements,
    has_local_bin: Callable[[str], bool],
    is_env_satisfied: Callable[[str], bool],
    is_config_satisfied: Callable[[str], bool],
    local_platform: Optional[str] = None,
    remote_platforms: Optional[List[str]] = None,
    has_remote_bin: Optional[Callable[[str], bool]] = None,
    has_remote_any_bin: Optional[Callable[[List[str]], bool]] = None,
) -> dict:
    """Evaluate normalized requirements.

    Mirrors :func:`evaluateRequirements` (internal; exposed for tests).
    """
    missing_bins = _resolve_missing_bins({
        "required": required.get("bins") or [],
        "hasLocalBin": has_local_bin,
        "hasRemoteBin": has_remote_bin,
    })
    missing_any_bins = _resolve_missing_any_bins({
        "required": required.get("anyBins") or [],
        "hasLocalBin": has_local_bin,
        "hasRemoteAnyBin": has_remote_any_bin,
    })
    missing_os = _resolve_missing_os({
        "required": required.get("os") or [],
        "localPlatform": local_platform if local_platform is not None else sys.platform,
        "remotePlatforms": remote_platforms,
    })
    missing_env = _resolve_missing_env({
        "required": required.get("env") or [],
        "isSatisfied": is_env_satisfied,
    })
    config_checks = _build_config_checks({
        "required": required.get("config") or [],
        "isSatisfied": is_config_satisfied,
    })
    missing_config = [c["path"] for c in config_checks if not c["satisfied"]]
    if always:
        missing = {"bins": [], "anyBins": [], "env": [], "config": [], "os": []}
    else:
        missing = {
            "bins": missing_bins,
            "anyBins": missing_any_bins,
            "env": missing_env,
            "config": missing_config,
            "os": missing_os,
        }
    eligible = always or all(
        len(missing[k]) == 0 for k in ("bins", "anyBins", "env", "config", "os")
    )
    return {"missing": missing, "eligible": eligible, "configChecks": config_checks}


def evaluate_requirements_from_metadata_with_remote(
    *,
    always: bool,
    metadata: Optional[RequirementsMetadata] = None,
    has_local_bin: Callable[[str], bool],
    is_env_satisfied: Callable[[str], bool],
    is_config_satisfied: Callable[[str], bool],
    local_platform: Optional[str] = None,
    remote: Optional[RequirementRemote] = None,
) -> dict:
    """Convenience wrapper that receives remote capability checks as one object.

    Mirrors :func:`evaluateRequirementsFromMetadataWithRemote`
    (``shared/requirements.ts``).
    """
    requires = (metadata or {}).get("requires") or {}
    required: Requirements = {
        "bins": list(requires.get("bins") or []),
        "anyBins": list(requires.get("anyBins") or []),
        "env": list(requires.get("env") or []),
        "config": list(requires.get("config") or []),
        "os": list((metadata or {}).get("os") or []),
    }
    return evaluate_requirements(
        always=always,
        required=required,
        has_local_bin=has_local_bin,
        is_env_satisfied=is_env_satisfied,
        is_config_satisfied=is_config_satisfied,
        local_platform=local_platform,
        remote_platforms=(remote or {}).get("platforms") if remote else None,
        has_remote_bin=(remote or {}).get("hasBin") if remote else None,
        has_remote_any_bin=(remote or {}).get("hasAnyBin") if remote else None,
    )


__all__ = [
    "Requirements",
    "RequirementConfigCheck",
    "RequirementsMetadata",
    "RequirementRemote",
    "evaluate_requirements",
    "evaluate_requirements_from_metadata_with_remote",
]
