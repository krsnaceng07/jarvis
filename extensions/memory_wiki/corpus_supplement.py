"""corpus_supplement — Memory Wiki per-vault corpus supplement.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/corpus-supplement.ts``.

A small factory that returns a
``{search, get}`` interface. Other parts of
the host (notably the memory-core dreaming
subsystem) consume this interface to add
wiki content as a *supplement* to the
memory search corpus.

The ``search`` and ``get`` wrappers
delegate to the in-memory wiki query
layer (``query.search_memory_wiki`` /
``query.get_memory_wiki_page``) with
``searchBackend="local"`` /
``searchCorpus="wiki"`` hard-coded so the
memory-core path is always looking at the
wiki side of the corpus (the host then
merges the results with the memory side).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .query import (
    WikiGetResult,
    WikiSearchResult,
    get_memory_wiki_page,
    search_memory_wiki,
)

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# Mirrors the OpenClaw ``MemoryWikiConfigResolver``
# type: ``(agentId?: string, appConfig?: OpenClawConfig)
# => ResolvedMemoryWikiConfig``. The consumer
# passes a closure that has already bound the
# base ``config`` (typically wrapping
# ``resolve_memory_wiki_agent_config``).
MemoryWikiConfigResolver = Callable[[str | None, Any], "ResolvedMemoryWikiConfig"]


@dataclass(frozen=True, slots=True)
class WikiCorpusSupplementSearchInput:
    """The input shape for ``WikiCorpusSupplement.search``.

    Mirrors the OpenClaw
    ``{ query, maxResults, agentId,
    agentSessionKey, sandboxed }`` input
    shape.
    """

    query: str
    max_results: int | None = None
    agent_id: str | None = None
    agent_session_key: str | None = None
    sandboxed: bool = False


@dataclass(frozen=True, slots=True)
class WikiCorpusSupplementGetInput:
    """The input shape for ``WikiCorpusSupplement.get``.

    Mirrors the OpenClaw
    ``{ lookup, fromLine, lineCount, agentId,
    agentSessionKey, sandboxed }`` input
    shape.
    """

    lookup: str
    from_line: int | None = None
    line_count: int | None = None
    agent_id: str | None = None
    agent_session_key: str | None = None
    sandboxed: bool = False


@dataclass(frozen=True, slots=True)
class WikiCorpusSupplement:
    """The corpus supplement interface.

    Mirrors the OpenClaw return shape of
    ``createWikiCorpusSupplement``. The
    ``search`` + ``get`` methods take an
    input dataclass and return the
    matching OpenClaw result shape
    (:class:`WikiSearchResult` /
    :class:`WikiGetResult`).
    """

    search: Callable[[WikiCorpusSupplementSearchInput], list[WikiSearchResult]]
    get: Callable[[WikiCorpusSupplementGetInput], WikiGetResult | None]
    resolve_config: MemoryWikiConfigResolver
    get_app_config: Callable[[], Any] = field(default=lambda: lambda: None)

    def search_results(self, input: WikiCorpusSupplementSearchInput) -> list[WikiSearchResult]:
        """Wrap the bound :attr:`search` callable."""
        return self.search(input)

    def get_result(self, input: WikiCorpusSupplementGetInput) -> WikiGetResult | None:
        """Wrap the bound :attr:`get` callable."""
        return self.get(input)


def create_wiki_corpus_supplement(
    *,
    resolve_config: MemoryWikiConfigResolver,
    get_app_config: Callable[[], Any] | None = None,
) -> WikiCorpusSupplement:
    """Build a wiki corpus-supplement interface.

    Mirrors the OpenClaw
    :func:`createWikiCorpusSupplement`.
    Returns a :class:`WikiCorpusSupplement`
    whose ``search`` + ``get`` methods
    resolve the per-agent config + delegate
    to the in-memory wiki query layer with
    ``searchBackend="local"`` /
    ``searchCorpus="wiki"`` so the
    memory-core path is always looking at
    the wiki side of the corpus.

    The ``resolve_config`` callable is
    called as ``resolve_config(agent_id,
    app_config)`` — matching the OpenClaw
    ``MemoryWikiConfigResolver`` type. The
    caller is expected to bind the base
    ``config`` (typically by wrapping
    ``resolve_memory_wiki_agent_config``
    with the pre-resolved base config).
    """
    effective_get_app_config = get_app_config or (lambda: None)

    def _search(
        input: WikiCorpusSupplementSearchInput,
    ) -> list[WikiSearchResult]:
        app_config = effective_get_app_config()
        config = resolve_config(input.agent_id, app_config)
        return search_memory_wiki(
            config=config,
            app_config=app_config,
            agent_id=getattr(config, "agent_id", None) or input.agent_id,
            agent_session_key=input.agent_session_key,
            sandboxed=input.sandboxed,
            query=input.query,
            max_results=input.max_results,
            search_backend="local",
            search_corpus="wiki",
        )

    def _get(
        input: WikiCorpusSupplementGetInput,
    ) -> WikiGetResult | None:
        app_config = effective_get_app_config()
        config = resolve_config(input.agent_id, app_config)
        return get_memory_wiki_page(
            config=config,
            app_config=app_config,
            agent_id=getattr(config, "agent_id", None) or input.agent_id,
            agent_session_key=input.agent_session_key,
            sandboxed=input.sandboxed,
            lookup=input.lookup,
            from_line=input.from_line,
            line_count=input.line_count,
            search_backend="local",
            search_corpus="wiki",
        )

    return WikiCorpusSupplement(
        search=_search,
        get=_get,
        resolve_config=resolve_config,
        get_app_config=effective_get_app_config,
    )


def reset_memory_wiki_corpus_supplement_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
    "MemoryWikiConfigResolver",
    "WikiCorpusSupplement",
    "WikiCorpusSupplementGetInput",
    "WikiCorpusSupplementSearchInput",
    "create_wiki_corpus_supplement",
    "reset_memory_wiki_corpus_supplement_state_for_tests",
]
