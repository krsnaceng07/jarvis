"""Manifest types — declarative shape of an extension's tools and config.

Mirrors parts of OpenClaw's `openclaw.plugin.json` schema. These are plain
dataclasses for now; Phase 1C may move to pydantic for full JSON-Schema
emission (mirroring OpenClaw's use of TypeBox).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# Re-export bundle format types from bundle_manifest so callers can import
# everything manifest-related from one place (mirrors OpenClaw's manifest-types.ts).
from .bundle_manifest import PluginBundleFormat, PluginFormat

# ── Plugin kinds ─────────────────────────────────────────────────────
PluginKind = Literal[
    "channel",  # messaging surface (Telegram, Discord, ...)
    "provider",  # LLM / model provider (openai, anthropic, ...)
    "tool",  # exposes one or more tools to the LLM
    "memory",  # memory host (single-active-slot pattern)
    "skill",  # declarative skill (markdown only, not code)
    "infra",  # infrastructure (cron, webhooks, ...)
    "migration",  # one-shot legacy-data migrator (doctor contract)
]

#: When the host should activate the plugin.
#: - ``"always"`` — loaded at every host start.
#: - ``"on_startup"`` — loaded if the manifest's dependencies are satisfied.
#: - ``"on_demand"`` — loaded only when something explicitly requests it.
PluginActivation = Literal["always", "on_startup", "on_demand"]


# ── Tool declaration ─────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ToolParam:
    """A single tool parameter declaration (subset of JSON Schema)."""

    name: str
    type: Literal["string", "integer", "number", "boolean", "array", "object"]
    description: str
    required: bool = False
    enum: list[str] | None = None
    items: list[ToolParam] | None = None
    properties: list[ToolParam] | None = None


@dataclass(frozen=True, slots=True)
class ToolDecl:
    """A tool that a plugin exposes to the LLM.

    Mirrors the ``tools[]`` array inside each ``openclaw.plugin.json``.
    The host converts this to the LLM provider's tool-call format at
    session start.
    """

    name: str
    description: str
    parameters: list[ToolParam] = field(default_factory=list)
    returns: str = "string"
    category: str = "general"
    requires: list[str] = field(default_factory=list)
    replay_safe: bool = False

    def required_params(self) -> list[str]:
        """Names of parameters marked required."""
        return [p.name for p in self.parameters if p.required]


# ── Plugin manifest (subset; full shape lives in openclaw.plugin.json) ──
@dataclass(frozen=True, slots=True)
class PluginManifestSummary:
    """The minimum manifest fields the SDK understands in code.

    The full manifest lives in ``extensions/<id>/openclaw.plugin.json``;
    the host reads it directly. This dataclass is for typed code that
    needs a manifest-shaped value (e.g. tests, documentation generators).
    """

    id: str
    kind: PluginKind
    version: str
    description: str
    tools: list[ToolDecl] = field(default_factory=list)
    activation: PluginActivation = "on_demand"
    requires: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    icon: str | None = None
    # Generic OpenClaw manifest passthrough (read-only; the manifest file
    # stays the source of truth, the host reads these without per-id branches).
    channels: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    cli_commands: list[str] = field(default_factory=list)


__all__ = [
    "PluginActivation",
    "PluginBundleFormat",
    "PluginFormat",
    "PluginKind",
    "PluginManifestSummary",
    "ToolDecl",
    "ToolParam",
]
