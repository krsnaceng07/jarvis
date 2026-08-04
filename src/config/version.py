"""jarvis.config.version — config version metadata + compatibility helpers.

OpenClaw parity: mirrors ``openclaw-main/src/config/version.ts``.

Focused minimal port: exposes the public version helpers. The semver
implementation is delegated to caller-provided callables until the
``infra/semver`` module lands.
"""
from __future__ import annotations

import re
from typing import Optional

_LEGACY_DOT_BETA_RE = re.compile(r"^(\d+)\.(\d+)\.b(\d+)$")


def _parse_openclaw_version(
    raw: Optional[str],
    *,
    parse_semver_fn=None,
    normalize_legacy_dot_beta_version_fn=None,
):
    if not raw:
        return None
    normalized = (
        normalize_legacy_dot_beta_version_fn(raw.strip())
        if callable(normalize_legacy_dot_beta_version_fn)
        else raw.strip()
    )
    if callable(parse_semver_fn):
        return parse_semver_fn(normalized)
    return None


def normalize_openclaw_version_base(
    raw: Optional[str],
    *,
    parse_semver_fn=None,
    normalize_legacy_dot_beta_version_fn=None,
) -> Optional[str]:
    """Return the major.minor.patch base of a parsed version, or None.

    Mirrors :func:`normalizeOpenClawVersionBase`
    (``shared/config/version.ts`).
    """
    parsed = _parse_openclaw_version(
        raw,
        parse_semver_fn=parse_semver_fn,
        normalize_legacy_dot_beta_version_fn=normalize_legacy_dot_beta_version_fn,
    )
    if not parsed:
        return None
    if isinstance(parsed, dict):
        return f"{parsed['major']}.{parsed['minor']}.{parsed['patch']}"
    major, minor, patch = getattr(parsed, "major", 0), getattr(parsed, "minor", 0), getattr(parsed, "patch", 0)
    return f"{major}.{minor}.{patch}"


def compare_openclaw_versions(
    a: Optional[str],
    b: Optional[str],
    *,
    parse_semver_fn=None,
    normalize_legacy_dot_beta_version_fn=None,
    compare_openclaw_semver_fn=None,
) -> Optional[int]:
    """Compare two OpenClaw version strings, returning -1/0/1 or None on parse failure.

    Mirrors :func:`compareOpenClawVersions`
    (``shared/config/version.ts`).
    """
    parsed_a = _parse_openclaw_version(
        a,
        parse_semver_fn=parse_semver_fn,
        normalize_legacy_dot_beta_version_fn=normalize_legacy_dot_beta_version_fn,
    )
    parsed_b = _parse_openclaw_version(
        b,
        parse_semver_fn=parse_semver_fn,
        normalize_legacy_dot_beta_version_fn=normalize_legacy_dot_beta_version_fn,
    )
    if not parsed_a or not parsed_b:
        return None
    if callable(compare_openclaw_semver_fn):
        return compare_openclaw_semver_fn(parsed_a, parsed_b)
    return 0


def should_warn_on_touched_version(
    current: Optional[str],
    touched: Optional[str],
    *,
    parse_semver_fn=None,
    normalize_legacy_dot_beta_version_fn=None,
    compare_openclaw_semver_fn=None,
    is_openclaw_correction_semver_fn=None,
) -> bool:
    """Return whether touching ``touched`` from ``current`` should warn.

    Mirrors :func:`shouldWarnOnTouchedVersion`
    (``shared/config/version.ts`).
    """
    parsed_current = _parse_openclaw_version(
        current,
        parse_semver_fn=parse_semver_fn,
        normalize_legacy_dot_beta_version_fn=normalize_legacy_dot_beta_version_fn,
    )
    parsed_touched = _parse_openclaw_version(
        touched,
        parse_semver_fn=parse_semver_fn,
        normalize_legacy_dot_beta_version_fn=normalize_legacy_dot_beta_version_fn,
    )
    if parsed_current and parsed_touched:
        cm = getattr(parsed_current, "compare_main", None)
        if callable(cm) and cm(parsed_touched) == 0:
            pre = getattr(parsed_touched, "prerelease", None) or []
            if not pre or (callable(is_openclaw_correction_semver_fn) and is_openclaw_correction_semver_fn(parsed_touched)):
                return False
    if parsed_current is None or parsed_touched is None:
        return False
    if callable(compare_openclaw_semver_fn):
        return compare_openclaw_semver_fn(parsed_current, parsed_touched) < 0
    return False


__all__ = [
    "normalize_openclaw_version_base",
    "compare_openclaw_versions",
    "should_warn_on_touched_version",
]
