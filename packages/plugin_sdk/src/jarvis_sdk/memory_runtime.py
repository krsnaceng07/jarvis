"""jarvis_sdk.memory_runtime — host-side memory runtime facade.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/openclaw-runtime-memory.ts``'s
``MemoryPluginRuntime``, ``MemoryFlushPlan``, ``MemoryFlushPlanResolver``,
``MemoryPromptSectionBuilder``, ``MemoryPluginPublicArtifact``,
``MemoryPluginPublicArtifactsProvider``, ``MemoryPluginCapability``.

This is the single contract every memory extension talks to.
The host hands each extension a ``MemoryPluginRuntime`` and the
extension returns a ``MemoryPluginCapability`` (a bundle of
prompt-builder + flush-plan + public-artifacts + runtime
handle).

Architecture
============
In OpenClaw the host's `registerMemoryCapability` call receives
this bundle. The host then:
  - calls ``prompt_builder(build_options)`` to inject the
    memory section into the system prompt
  - calls ``flush_plan_resolver(build_options)`` before a
    compaction to decide what to flush
  - exposes ``public_artifacts`` to other extensions
    (``list_artifacts``) for the doctor/UI surface
  - calls ``runtime.get_memory_search_manager(params)`` on
    demand

The Python port mirrors the same shape.

Parity
======
- ``MemoryPluginRuntime`` is a small wrapper over the
  host's search-manager pool.
- ``MemoryFlushPlan`` is a frozen dataclass with
  ``should_flush`` and a free-form ``reason``.
- ``MemoryPluginCapability`` is the bundle a memory extension
  returns from ``register(api)``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .memory_storage import MemorySearchManager


@dataclass(frozen=True, slots=True)
class MemoryFlushPlan:
    """Decides whether the agent should flush before compaction.

    Mirrors OpenClaw's ``MemoryFlushPlan``.
    """

    should_flush: bool = False
    reason: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MemoryPluginPublicArtifact:
    """An artifact published by a memory extension.

    Mirrors OpenClaw's ``MemoryPluginPublicArtifact``.
    """

    id: str
    kind: str
    path: str
    description: str = ""


class MemoryFlushPlanResolver(ABC):
    """Decides whether to flush before compaction."""

    @abstractmethod
    def resolve(self, build_options: dict[str, Any]) -> MemoryFlushPlan: ...


class MemoryPromptSectionBuilder(ABC):
    """Builds the system-prompt section for a memory plugin."""

    @abstractmethod
    def build(self, build_options: dict[str, Any]) -> str: ...


class MemoryPluginPublicArtifactsProvider(ABC):
    """Lists public artifacts exposed by a memory plugin."""

    @abstractmethod
    async def list_artifacts(
        self, params: dict[str, Any] | None = None
    ) -> list[MemoryPluginPublicArtifact]: ...


class MemoryPluginRuntime(ABC):
    """Runtime handle handed to a memory extension.

    Mirrors OpenClaw's ``MemoryPluginRuntime``.
    """

    @abstractmethod
    async def get_memory_search_manager(
        self,
        params: dict[str, Any] | None = None,
    ) -> MemorySearchManager: ...

    @abstractmethod
    async def close_all_memory_search_managers(self) -> None: ...


@dataclass(frozen=True, slots=True)
class MemoryPluginCapability:
    """The bundle a memory extension returns at register time.

    Mirrors OpenClaw's ``MemoryPluginCapability``.
    """

    prompt_builder: MemoryPromptSectionBuilder
    flush_plan_resolver: MemoryFlushPlanResolver
    runtime: MemoryPluginRuntime
    public_artifacts: MemoryPluginPublicArtifactsProvider | None = None


__all__ = [
    "MemoryFlushPlan",
    "MemoryFlushPlanResolver",
    "MemoryPluginCapability",
    "MemoryPluginPublicArtifact",
    "MemoryPluginPublicArtifactsProvider",
    "MemoryPluginPromptSectionBuilder" if False else "MemoryPromptSectionBuilder",
    "MemoryPluginRuntime",
    "MemoryPromptSectionBuilder",
]
