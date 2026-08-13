"""Hooks type contracts — mirrors OpenClaw ``src/hooks/internal-hook-types.ts``
and ``src/hooks/types.ts``.

HookSource precedence (lowest → highest, same as OpenClaw HOOK_SOURCE_POLICIES):
  jarvis-bundled  (10) → jarvis-plugin (20) → jarvis-managed (30) → jarvis-workspace (40)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

# ── Source literals (mirrors HookSource in OpenClaw types.ts) ────────────────

HookSource = Literal[
    "jarvis-bundled",
    "jarvis-plugin",
    "jarvis-managed",
    "jarvis-workspace",
]

# ── Internal hook event family + action keys ─────────────────────────────────

InternalHookEventType = Literal["command", "session", "agent", "gateway", "message"]

KNOWN_INTERNAL_HOOK_EVENT_KEYS: frozenset[str] = frozenset({
    "agent:bootstrap",
    "command:new",
    "command:reset",
    "command:stop",
    "gateway:pre-restart",
    "gateway:shutdown",
    "gateway:startup",
    "message:preprocessed",
    "message:received",
    "message:sent",
    "message:transcribed",
    "session:compact:after",
    "session:compact:before",
    "session:patch",
})

KNOWN_INTERNAL_HOOK_EVENT_FAMILIES: frozenset[str] = frozenset({
    "command", "session", "agent", "gateway", "message",
})


def is_known_hook_event_key(key: str) -> bool:
    """Return True if key is a known event key or bare family name."""
    return key in KNOWN_INTERNAL_HOOK_EVENT_KEYS or key in KNOWN_INTERNAL_HOOK_EVENT_FAMILIES


# ── Hook data types ──────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Hook:
    """Runtime hook descriptor — mirrors OpenClaw Hook interface."""

    name: str
    description: str
    source: HookSource
    file_path: str          # Path to HOOK.md
    base_dir: str           # Directory containing hook
    handler_path: str       # Path to handler module (handler.py)
    plugin_id: str | None = None


@dataclass(frozen=True, slots=True)
class HookInstallSpec:
    kind: Literal["bundled", "uv", "pip", "git"]
    label: str | None = None
    package: str | None = None
    repository: str | None = None
    bins: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class HookMetadata:
    """Frontmatter-resolved hook metadata — mirrors OpenClawHookMetadata."""

    events: tuple[str, ...]
    always: bool = False
    hook_key: str | None = None
    emoji: str | None = None
    homepage: str | None = None
    os: tuple[str, ...] = field(default_factory=tuple)
    requires_bins: tuple[str, ...] = field(default_factory=tuple)
    requires_any_bins: tuple[str, ...] = field(default_factory=tuple)
    requires_env: tuple[str, ...] = field(default_factory=tuple)
    install: tuple[HookInstallSpec, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class HookInvocationPolicy:
    enabled: bool


@dataclass
class HookEntry:
    """A resolved, loaded hook ready for dispatch — mirrors OpenClaw HookEntry."""

    hook: Hook
    frontmatter: dict[str, str]
    metadata: HookMetadata | None = None
    invocation: HookInvocationPolicy | None = None


# ── Internal hook event (runtime payload) ───────────────────────────────────

@dataclass
class InternalHookEvent:
    """Runtime hook event payload — mirrors OpenClaw InternalHookEvent."""

    type: InternalHookEventType
    action: str
    session_key: str
    context: dict[str, Any]
    timestamp: float          # Unix timestamp
    messages: list[str] = field(default_factory=list)

    @property
    def event_key(self) -> str:
        return f"{self.type}:{self.action}"


InternalHookHandler = Callable[[InternalHookEvent], Any]

# ── Eligibility context (mirrors HookEligibilityContext) ────────────────────

@dataclass
class HookEligibilityContext:
    platform: str = "windows"     # sys.platform value
    has_bins: frozenset[str] = field(default_factory=frozenset)

    def has_bin(self, bin_name: str) -> bool:
        return bin_name in self.has_bins

    def has_any_bin(self, bins: list[str]) -> bool:
        return any(b in self.has_bins for b in bins)


__all__ = [
    "Hook",
    "HookEligibilityContext",
    "HookEntry",
    "HookInstallSpec",
    "HookInvocationPolicy",
    "HookMetadata",
    "HookSource",
    "InternalHookEvent",
    "InternalHookEventType",
    "InternalHookHandler",
    "KNOWN_INTERNAL_HOOK_EVENT_KEYS",
    "KNOWN_INTERNAL_HOOK_EVENT_FAMILIES",
    "is_known_hook_event_key",
]
