"""Registry state for plugin memory runtimes, prompt supplements, and flush planning.

OpenClaw parity: ``src/plugins/memory-state.ts``. The TS module keeps one
module-level state record plus an ``AsyncLocalStorage`` slot for the
run-scoped prepared prompt section; the Python port uses a module-level
dict and a ``contextvars.ContextVar`` (the asyncio analogue of ALS).
Only the prompt-section surface is exercised by the context-engine slice;
the runtime/flush-plan/public-artifact registries are ported alongside so
the module matches the host file one-to-one.
"""
from __future__ import annotations

import contextvars
import weakref
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Sequence

__all__ = [
    "MemoryPromptSectionParams",
    "PreparedMemoryPromptSection",
    "build_memory_prompt_section",
    "clear_memory_plugin_state",
    "get_active_prepared_memory_prompt_section",
    "get_memory_capability_registration",
    "get_memory_runtime",
    "has_memory_runtime",
    "list_memory_corpus_supplements",
    "list_memory_prompt_preparations",
    "list_memory_prompt_supplements",
    "prepare_memory_prompt_section",
    "register_memory_capability",
    "register_memory_corpus_supplement",
    "register_memory_flush_plan_resolver_for_plugin",
    "register_memory_prompt_preparation",
    "register_memory_prompt_section_for_plugin",
    "register_memory_prompt_supplement",
    "register_memory_runtime_for_plugin",
    "resolve_memory_flush_plan",
    "restore_memory_plugin_state",
    "run_with_prepared_memory_prompt_section",
]


@dataclass(frozen=True)
class MemoryPromptSectionParams:
    """Parameters handed to prompt-section builders for one run."""

    available_tools: frozenset[str] = frozenset()
    citations_mode: str | None = None
    agent_id: str | None = None
    agent_session_key: str | None = None
    sandboxed: bool | None = None


MemoryPromptSectionBuilder = Callable[[MemoryPromptSectionParams], Sequence[str]]
MemoryPromptSectionPreparer = Callable[
    [MemoryPromptSectionParams], Awaitable[Sequence[str]]
]


@dataclass(frozen=True, eq=False)
class PreparedMemoryPromptSection:
    """Immutable snapshot of prompt lines bound to one run's context.

    ``eq=False`` keeps hashing identity-based so the prepared-section
    registry below matches the TS ``WeakSet`` semantics exactly (two
    equal-valued snapshots are still distinct runs).
    """

    context: tuple  # (available_tools sorted tuple, citations, agent, key, sandboxed)
    lines: tuple[str, ...]


@dataclass
class _MemoryPluginState:
    capability: tuple[str, dict[str, Any]] | None = None
    corpus_supplements: list[tuple[str, Any]] = field(default_factory=list)
    prompt_preparations: list[tuple[str, MemoryPromptSectionPreparer]] = field(
        default_factory=list
    )
    prompt_supplements: list[tuple[str, MemoryPromptSectionBuilder]] = field(
        default_factory=list
    )


_state = _MemoryPluginState()

# Identity registry matching the TS WeakSet: prepared sections minted by
# prepare_memory_prompt_section, held weakly so runs cannot leak.
_prepared_sections: weakref.WeakSet = weakref.WeakSet()

_active_prepared: contextvars.ContextVar[PreparedMemoryPromptSection | None] = (
    contextvars.ContextVar("active_prepared_memory_prompt_section", default=None)
)


def register_memory_corpus_supplement(plugin_id: str, supplement: Any) -> None:
    _state.corpus_supplements = [
        entry for entry in _state.corpus_supplements if entry[0] != plugin_id
    ]
    _state.corpus_supplements.append((plugin_id, supplement))


def register_memory_capability(plugin_id: str, capability: dict[str, Any]) -> None:
    existing = _state.capability[1] if _state.capability else None
    # A selected memory plugin can add bridge artifacts while memory-core
    # owns sidecar runtime hooks.
    should_preserve_existing = (
        existing is not None
        and bool(capability.get("publicArtifacts"))
        and not capability.get("promptBuilder")
        and not capability.get("flushPlanResolver")
        and not capability.get("runtime")
    )
    merged: dict[str, Any] = {}
    if should_preserve_existing and existing:
        merged.update(existing)
    merged.update(capability)
    _state.capability = (plugin_id, merged)


def _patch_memory_capability(plugin_id: str, patch: dict[str, Any]) -> None:
    current = (
        dict(_state.capability[1])
        if _state.capability and _state.capability[0] == plugin_id
        else {}
    )
    current.update(patch)
    register_memory_capability(plugin_id, current)


def get_memory_capability_registration() -> tuple[str, dict[str, Any]] | None:
    if _state.capability is None:
        return None
    plugin_id, capability = _state.capability
    return (plugin_id, dict(capability))


def list_memory_corpus_supplements() -> list[tuple[str, Any]]:
    return list(_state.corpus_supplements)


def register_memory_prompt_section_for_plugin(
    plugin_id: str, builder: MemoryPromptSectionBuilder
) -> None:
    _patch_memory_capability(plugin_id, {"promptBuilder": builder})


def register_memory_prompt_supplement(
    plugin_id: str, builder: MemoryPromptSectionBuilder
) -> None:
    _state.prompt_supplements = [
        entry for entry in _state.prompt_supplements if entry[0] != plugin_id
    ]
    _state.prompt_supplements.append((plugin_id, builder))


def register_memory_prompt_preparation(
    plugin_id: str, prepare: MemoryPromptSectionPreparer
) -> None:
    _state.prompt_preparations = [
        entry for entry in _state.prompt_preparations if entry[0] != plugin_id
    ]
    _state.prompt_preparations.append((plugin_id, prepare))


def _normalize_memory_prompt_lines(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [line for line in value if isinstance(line, str)]


def _build_synchronous_memory_prompt_section(
    params: MemoryPromptSectionParams,
) -> tuple[list[str], list[tuple[str, list[str]]]]:
    builder = _state.capability[1].get("promptBuilder") if _state.capability else None
    primary = _normalize_memory_prompt_lines(builder(params) if builder else [])
    # Keep supplement order stable even if plugin registration order changes.
    supplements = [
        (plugin_id, _normalize_memory_prompt_lines(entry_builder(params)))
        for plugin_id, entry_builder in sorted(
            _state.prompt_supplements, key=lambda entry: entry[0]
        )
    ]
    return primary, supplements


def _snapshot_memory_prompt_context(params: MemoryPromptSectionParams) -> tuple:
    return (
        tuple(sorted(params.available_tools)),
        params.citations_mode,
        params.agent_id,
        params.agent_session_key,
        params.sandboxed is True,
    )


def _prepared_context_matches(
    prepared: PreparedMemoryPromptSection, params: MemoryPromptSectionParams
) -> bool:
    return prepared.context == _snapshot_memory_prompt_context(params)


async def prepare_memory_prompt_section(
    params: MemoryPromptSectionParams,
) -> PreparedMemoryPromptSection:
    """Prepare one immutable memory prompt snapshot for a run."""
    context = _snapshot_memory_prompt_context(params)
    primary, supplements = _build_synchronous_memory_prompt_section(params)
    prepared_supplements: list[tuple[str, list[str]]] = []
    for plugin_id, prepare in list(_state.prompt_preparations):
        lines = _normalize_memory_prompt_lines(await prepare(params))
        prepared_supplements.append((plugin_id, lines))
    combined = sorted(
        [*supplements, *prepared_supplements], key=lambda entry: entry[0]
    )
    lines = tuple(
        primary + [line for _, entry_lines in combined for line in entry_lines]
    )
    prepared = PreparedMemoryPromptSection(context=context, lines=lines)
    _prepared_sections.add(prepared)
    return prepared


async def run_with_prepared_memory_prompt_section(
    params: MemoryPromptSectionParams, run: Callable[[], Awaitable[Any]]
) -> Any:
    """Keep async preparation run-scoped while a context engine assembles."""
    prepared = await prepare_memory_prompt_section(params)
    token = _active_prepared.set(prepared)
    try:
        return await run()
    finally:
        _active_prepared.reset(token)


def get_active_prepared_memory_prompt_section() -> PreparedMemoryPromptSection | None:
    return _active_prepared.get()


def build_memory_prompt_section(
    params: MemoryPromptSectionParams,
    prepared: PreparedMemoryPromptSection | None = None,
) -> list[str]:
    if prepared is not None:
        # Run-scoped prompt state must never cross agent/session/tool boundaries.
        if prepared not in _prepared_sections or not _prepared_context_matches(
            prepared, params
        ):
            raise ValueError(
                "prepared memory prompt section does not match the current run"
            )
        return list(prepared.lines)
    primary, supplements = _build_synchronous_memory_prompt_section(params)
    return primary + [line for _, lines in supplements for line in lines]


def list_memory_prompt_supplements() -> list[tuple[str, MemoryPromptSectionBuilder]]:
    return list(_state.prompt_supplements)


def list_memory_prompt_preparations() -> list[tuple[str, MemoryPromptSectionPreparer]]:
    return list(_state.prompt_preparations)


def register_memory_flush_plan_resolver_for_plugin(
    plugin_id: str, resolver: Callable[..., Any]
) -> None:
    _patch_memory_capability(plugin_id, {"flushPlanResolver": resolver})


def resolve_memory_flush_plan(params: dict[str, Any] | None = None) -> Any:
    resolver = (
        _state.capability[1].get("flushPlanResolver") if _state.capability else None
    )
    if resolver is None:
        return None
    return resolver(params or {})


def register_memory_runtime_for_plugin(plugin_id: str, runtime: Any) -> None:
    _patch_memory_capability(plugin_id, {"runtime": runtime})


def get_memory_runtime() -> Any:
    return _state.capability[1].get("runtime") if _state.capability else None


def has_memory_runtime() -> bool:
    return get_memory_runtime() is not None


def restore_memory_plugin_state(state: dict[str, Any]) -> None:
    capability = state.get("capability")
    _state.capability = (
        (capability[0], dict(capability[1])) if capability else None
    )
    _state.corpus_supplements = list(state.get("corpus_supplements", []))
    _state.prompt_preparations = list(state.get("prompt_preparations", []))
    _state.prompt_supplements = list(state.get("prompt_supplements", []))


def clear_memory_plugin_state() -> None:
    _state.capability = None
    _state.corpus_supplements = []
    _state.prompt_preparations = []
    _state.prompt_supplements = []
