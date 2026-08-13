"""Hook policy — mirrors OpenClaw ``src/hooks/policy.ts``.

Implements source-precedence, default-enablement, and override rules
that determine which hook wins when multiple hooks share the same name.

Source precedence (lower number = lower precedence, gets overridden):
  jarvis-bundled  (10)
  jarvis-plugin   (20)
  jarvis-managed  (30)
  jarvis-workspace(40)

Override is asymmetric: both source policies must agree that candidate
may replace existing (``canOverride`` ∩ ``canBeOverriddenBy``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal

if TYPE_CHECKING:
    from .types import HookEntry, HookSource

_log = logging.getLogger("jarvis.hooks.policy")

HookEnableStateReason = Literal[
    "disabled in config",
    "workspace hook (disabled by default)",
]


@dataclass(frozen=True, slots=True)
class HookEnableState:
    enabled: bool
    reason: HookEnableStateReason | None = None


@dataclass(frozen=True, slots=True)
class _HookSourcePolicy:
    precedence: int
    trusted_local_code: bool
    default_enable_mode: Literal["default-on", "explicit-opt-in"]
    can_override: frozenset[str]           # HookSource values this source may override
    can_be_overridden_by: frozenset[str]   # HookSource values that may override this


# Mirrors HOOK_SOURCE_POLICIES in policy.ts
_HOOK_SOURCE_POLICIES: dict[str, _HookSourcePolicy] = {
    "jarvis-bundled": _HookSourcePolicy(
        precedence=10,
        trusted_local_code=True,
        default_enable_mode="default-on",
        can_override=frozenset({"jarvis-bundled"}),
        can_be_overridden_by=frozenset({"jarvis-managed", "jarvis-plugin"}),
    ),
    "jarvis-plugin": _HookSourcePolicy(
        precedence=20,
        trusted_local_code=True,
        default_enable_mode="default-on",
        can_override=frozenset({"jarvis-bundled", "jarvis-plugin"}),
        can_be_overridden_by=frozenset({"jarvis-managed"}),
    ),
    "jarvis-managed": _HookSourcePolicy(
        precedence=30,
        trusted_local_code=True,
        default_enable_mode="default-on",
        can_override=frozenset({"jarvis-bundled", "jarvis-managed", "jarvis-plugin"}),
        can_be_overridden_by=frozenset({"jarvis-managed"}),
    ),
    "jarvis-workspace": _HookSourcePolicy(
        precedence=40,
        trusted_local_code=True,
        default_enable_mode="explicit-opt-in",
        can_override=frozenset({"jarvis-workspace"}),
        can_be_overridden_by=frozenset({"jarvis-workspace"}),
    ),
}


def _get_policy(source: str) -> _HookSourcePolicy:
    return _HOOK_SOURCE_POLICIES[source]


def resolve_hook_config(config: dict | None, hook_key: str) -> dict | None:
    """Resolve explicit per-hook config by hook key — mirrors resolveHookConfig."""
    if not config:
        return None
    hooks = (config.get("hooks") or {}).get("internal", {}).get("entries", {})
    if not isinstance(hooks, dict):
        return None
    return hooks.get(hook_key)


def resolve_hook_enable_state(
    entry: "HookEntry",
    config: dict | None = None,
    hook_config: dict | None = None,
) -> HookEnableState:
    """Resolve whether a hook is enabled — mirrors resolveHookEnableState."""
    if hook_config is None:
        key = entry.metadata.hook_key if entry.metadata and entry.metadata.hook_key else entry.hook.name
        hook_config = resolve_hook_config(config, key)

    # Plugin hooks are always enabled (plugin activation already checked)
    if entry.hook.source == "jarvis-plugin":
        return HookEnableState(enabled=True)

    # Explicit disable wins
    if hook_config and hook_config.get("enabled") is False:
        return HookEnableState(enabled=False, reason="disabled in config")

    source_policy = _get_policy(entry.hook.source)
    if (
        source_policy.default_enable_mode == "explicit-opt-in"
        and not (hook_config and hook_config.get("enabled") is True)
    ):
        return HookEnableState(
            enabled=False, reason="workspace hook (disabled by default)"
        )

    return HookEnableState(enabled=True)


def _can_override(candidate: "HookEntry", existing: "HookEntry") -> bool:
    """True if candidate is allowed to replace existing — asymmetric check."""
    cp = _get_policy(candidate.hook.source)
    ep = _get_policy(existing.hook.source)
    return (
        existing.hook.source in cp.can_override
        and candidate.hook.source in ep.can_be_overridden_by
    )


@dataclass
class HookResolutionCollision:
    name: str
    kept: "HookEntry"
    ignored: "HookEntry"


def resolve_hook_entries(
    entries: list["HookEntry"],
    *,
    on_collision_ignored: Callable[[HookResolutionCollision], None] | None = None,
) -> list["HookEntry"]:
    """Merge hook entries by name using source precedence + override policy.

    Mirrors resolveHookEntries in policy.ts. Higher-precedence source wins
    only if both policies agree on the override direction.
    """
    # Sort by precedence asc (lower = lower precedence, processed first)
    ordered = sorted(
        enumerate(entries),
        key=lambda idx_e: (
            _get_policy(idx_e[1].hook.source).precedence,
            idx_e[0],   # stable original index as tiebreaker
        ),
    )

    merged: dict[str, "HookEntry"] = {}
    for _idx, entry in ordered:
        existing = merged.get(entry.hook.name)
        if existing is None:
            merged[entry.hook.name] = entry
            continue
        if _can_override(entry, existing):
            merged[entry.hook.name] = entry
            continue
        if on_collision_ignored:
            on_collision_ignored(HookResolutionCollision(
                name=entry.hook.name,
                kept=existing,
                ignored=entry,
            ))

    return list(merged.values())


__all__ = [
    "HookEnableState",
    "HookEnableStateReason",
    "HookResolutionCollision",
    "resolve_hook_config",
    "resolve_hook_enable_state",
    "resolve_hook_entries",
]
