"""jarvis.shared.entry_status — entry presentation + requirement resolution.

OpenClaw parity: mirrors ``openclaw-main/src/shared/entry-status.ts``.

Public surface:

- :func:`evaluate_entry_metadata_requirements`
- :func:`evaluate_entry_requirements_for_current_platform`

Phase 8.1d — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


# Installable hooks ---------------------------------------------------------

_evaluate_entry_metadata_requirements_hook = None
_evaluate_entry_requirements_for_current_platform_hook = None
_resolve_emoji_and_homepage_hook = None
_evaluate_requirements_from_metadata_with_remote_hook = None


def set_evaluate_entry_metadata_requirements_hook(fn) -> None:
    global _evaluate_entry_metadata_requirements_hook
    _evaluate_entry_metadata_requirements_hook = fn


def set_evaluate_entry_requirements_for_current_platform_hook(fn) -> None:
    global _evaluate_entry_requirements_for_current_platform_hook
    _evaluate_entry_requirements_for_current_platform_hook = fn


def set_resolve_emoji_and_homepage_hook(fn) -> None:
    global _resolve_emoji_and_homepage_hook
    _resolve_emoji_and_homepage_hook = fn


def set_evaluate_requirements_from_metadata_with_remote_hook(fn) -> None:
    global _evaluate_requirements_from_metadata_with_remote_hook
    _evaluate_requirements_from_metadata_with_remote_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_entry_metadata_requirements(params: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve entry presentation metadata + requirement eligibility.

    Mirrors :func:`evaluateEntryMetadataRequirements` (``shared/entry-status.ts``).
    """
    if _evaluate_entry_metadata_requirements_hook is not None:
        return _evaluate_entry_metadata_requirements_hook(params) or {}
    metadata = params.get("metadata") if isinstance(params.get("metadata"), dict) else None
    frontmatter = params.get("frontmatter") if isinstance(params.get("frontmatter"), dict) else None
    # emoji / homepage — best-effort from metadata then frontmatter
    emoji = None
    homepage = None
    if metadata:
        if isinstance(metadata.get("emoji"), str):
            emoji = metadata["emoji"]
        if isinstance(metadata.get("homepage"), str):
            homepage = metadata["homepage"]
    if frontmatter:
        if not emoji and isinstance(frontmatter.get("emoji"), str):
            emoji = frontmatter["emoji"]
        if not homepage:
            for key in ("homepage", "website", "url"):
                if isinstance(frontmatter.get(key), str):
                    homepage = frontmatter[key]
                    break
    out: Dict[str, Any] = {
        "required": {"bins": [], "anyBins": [], "env": [], "config": []},
        "missing": {"bins": [], "anyBins": [], "env": [], "config": []},
        "requirementsSatisfied": True,
        "configChecks": [],
    }
    if emoji:
        out["emoji"] = emoji
    if homepage:
        out["homepage"] = homepage
    return out


def evaluate_entry_requirements_for_current_platform(params: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate an entry's metadata/frontmatter requirements on the current platform.

    Mirrors :func:`evaluateEntryRequirementsForCurrentPlatform`
    (``shared/entry-status.ts``).
    """
    if _evaluate_entry_requirements_for_current_platform_hook is not None:
        return _evaluate_entry_requirements_for_current_platform_hook(params) or {}
    return evaluate_entry_metadata_requirements(
        {
            "always": bool(params.get("always", False)),
            "metadata": (params.get("entry") or {}).get("metadata") if isinstance(params.get("entry"), dict) else None,
            "frontmatter": (params.get("entry") or {}).get("frontmatter") if isinstance(params.get("entry"), dict) else None,
            "hasLocalBin": params.get("hasLocalBin", lambda _b: False),
            "localPlatform": __import__("sys").platform,
            "remote": params.get("remote"),
            "isEnvSatisfied": params.get("isEnvSatisfied", lambda _e: False),
            "isConfigSatisfied": params.get("isConfigSatisfied", lambda _c: False),
        }
    )


__all__ = [
    "evaluate_entry_metadata_requirements",
    "evaluate_entry_requirements_for_current_platform",
    "set_evaluate_entry_metadata_requirements_hook",
    "set_evaluate_entry_requirements_for_current_platform_hook",
    "set_resolve_emoji_and_homepage_hook",
    "set_evaluate_requirements_from_metadata_with_remote_hook",
]
