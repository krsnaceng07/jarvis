"""Tests for extensions/memory_wiki/corpus_supplement.py.

Phase 4.3f-mr5: ports the OpenClaw
``corpus-supplement.ts`` test surface. The
tests focus on:

- ``create_wiki_corpus_supplement`` returns
  a ``WikiCorpusSupplement`` whose
  ``search`` + ``get`` methods delegate to
  the in-memory query layer with the
  correct ``searchBackend="local"`` /
  ``searchCorpus="wiki"`` overrides.
- The ``resolve_config`` callable is
  invoked as ``(agent_id, app_config)`` —
  matching the OpenClaw
  ``MemoryWikiConfigResolver`` contract.
- The per-call config is resolved for each
  invocation's agent context (no leakage
  between successive calls).
- The call fails closed before querying
  when the multi-agent context is missing
  (i.e. the resolver raises).
"""

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportReturnType=false

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.memory_wiki import corpus_supplement as cs  # noqa: E402
from extensions.memory_wiki.config import (  # noqa: E402
    resolve_memory_wiki_agent_config,
    resolve_memory_wiki_config,
)
from extensions.memory_wiki.query import WikiGetResult, WikiSearchResult  # noqa: E402


@pytest.fixture
def app_config() -> dict:
    return {
        "agents": {
            "list": [
                {"id": "support", "default": True},
                {"id": "marketing"},
            ]
        }
    }


@pytest.fixture
def base_config(tmp_path: Path) -> SimpleNamespace:
    return resolve_memory_wiki_config(
        {"vault": {"scope": "agent", "path": str(tmp_path / "memory-wiki-agents")}}
    )


class TestInputDataclasses:
    def test_search_input_default_sandboxed_false(self) -> None:
        inp = cs.WikiCorpusSupplementSearchInput(query="x")
        assert inp.query == "x"
        assert inp.max_results is None
        assert inp.agent_id is None
        assert inp.agent_session_key is None
        assert inp.sandboxed is False

    def test_search_input_all_fields(self) -> None:
        inp = cs.WikiCorpusSupplementSearchInput(
            query="support handbook",
            max_results=4,
            agent_id="support",
            agent_session_key="agent:support:main",
            sandboxed=True,
        )
        assert inp.query == "support handbook"
        assert inp.max_results == 4
        assert inp.agent_id == "support"
        assert inp.agent_session_key == "agent:support:main"
        assert inp.sandboxed is True

    def test_get_input_default_sandboxed_false(self) -> None:
        inp = cs.WikiCorpusSupplementGetInput(lookup="x")
        assert inp.lookup == "x"
        assert inp.from_line is None
        assert inp.line_count is None
        assert inp.agent_id is None
        assert inp.agent_session_key is None
        assert inp.sandboxed is False

    def test_get_input_all_fields(self) -> None:
        inp = cs.WikiCorpusSupplementGetInput(
            lookup="marketing-plan",
            from_line=3,
            line_count=8,
            agent_id="marketing",
            agent_session_key="agent:marketing:main",
            sandboxed=False,
        )
        assert inp.lookup == "marketing-plan"
        assert inp.from_line == 3
        assert inp.line_count == 8
        assert inp.agent_id == "marketing"
        assert inp.agent_session_key == "agent:marketing:main"
        assert inp.sandboxed is False


class TestFactoryShape:
    def test_returns_supplement_dataclass(self, tmp_path: Path) -> None:
        supplement = cs.create_wiki_corpus_supplement(
            resolve_config=lambda _a, _b: SimpleNamespace(
                agent_id="x",
                vault=SimpleNamespace(path=str(tmp_path / "x"), scope="agent"),
                search=SimpleNamespace(corpus="wiki"),
            ),
        )
        assert isinstance(supplement, cs.WikiCorpusSupplement)
        assert callable(supplement.search)
        assert callable(supplement.get)

    def test_search_results_wrapper(self, tmp_path: Path) -> None:
        supplement = cs.create_wiki_corpus_supplement(
            resolve_config=lambda _a, _b: SimpleNamespace(
                agent_id="x",
                vault=SimpleNamespace(path=str(tmp_path / "x"), scope="global"),
                search=SimpleNamespace(corpus="wiki"),
            ),
        )
        # Use a real query against a non-existent path; the
        # factory should still return an empty list (no pages).
        out = supplement.search_results(
            cs.WikiCorpusSupplementSearchInput(
                query="hello",
                agent_id="x",
            )
        )
        assert isinstance(out, list)

    def test_get_result_wrapper(self, tmp_path: Path) -> None:
        config = resolve_memory_wiki_config({"vault": {"scope": "global", "path": str(tmp_path)}})
        supplement = cs.create_wiki_corpus_supplement(
            resolve_config=lambda _a, _b: config,
        )
        # Lookup will resolve to ``None`` (vault is empty).
        out = supplement.get_result(
            cs.WikiCorpusSupplementGetInput(
                lookup="missing",
                agent_id="x",
            )
        )
        assert out is None


class TestSearchDelegation:
    def test_search_forwards_to_query_layer(
        self, app_config: dict, base_config: SimpleNamespace
    ) -> None:
        """The search wrapper should call the in-memory query
        layer with the resolved per-agent config + the
        ``searchBackend="local"`` / ``searchCorpus="wiki"``
        overrides."""
        resolved_configs: list[SimpleNamespace] = []
        received_calls: list[dict] = []

        def fake_resolve_config(agent_id, current_app_config):
            resolved = resolve_memory_wiki_agent_config(
                config=base_config,  # type: ignore[arg-type]
                app_config=current_app_config,
                agent_id=agent_id,
            )
            resolved_configs.append(resolved)
            return resolved

        def fake_get_app_config() -> dict:
            return app_config

        # Monkey-patch the in-memory query functions.
        original_search = cs.search_memory_wiki

        def fake_search(**kwargs):
            received_calls.append(kwargs)
            return [
                WikiSearchResult(
                    corpus="wiki",
                    path="entities/support.md",
                    title="Support Handbook",
                    kind="entity",
                    score=1.0,
                    snippet="support snippet",
                )
            ]

        cs.search_memory_wiki = fake_search  # type: ignore[assignment]
        try:
            supplement = cs.create_wiki_corpus_supplement(
                resolve_config=fake_resolve_config,
                get_app_config=fake_get_app_config,
            )
            out = supplement.search(
                cs.WikiCorpusSupplementSearchInput(
                    query="support handbook",
                    max_results=4,
                    agent_id="support",
                    agent_session_key="agent:support:main",
                    sandboxed=True,
                )
            )
        finally:
            cs.search_memory_wiki = original_search  # type: ignore[assignment]

        # ``resolve_config`` is called with the agent id + app
        # config (positional, matching OpenClaw).
        assert len(resolved_configs) == 1
        # ``search_memory_wiki`` was called once with the wiki
        # overrides + per-agent config.
        assert len(received_calls) == 1
        call = received_calls[0]
        assert call["query"] == "support handbook"
        assert call["max_results"] == 4
        assert call["agent_id"] == "support"
        assert call["agent_session_key"] == "agent:support:main"
        assert call["sandboxed"] is True
        assert call["search_backend"] == "local"
        assert call["search_corpus"] == "wiki"
        assert call["app_config"] is app_config
        # The ``config`` passed to the query layer has the
        # per-agent vault path resolved.
        cfg = call["config"]
        # ``ResolvedMemoryWikiConfig`` stores its
        # fields as camelCase attributes (matching
        # the OpenClaw layout). Use the
        # ``_read_attr`` helper to read either
        # ``agentId`` or ``agent_id``.
        from extensions.memory_wiki.claim_health import _read_attr

        assert _read_attr(cfg, "agent_id", "agentId") == "support"
        # The returned list is the wrapped one.
        assert out == [
            WikiSearchResult(
                corpus="wiki",
                path="entities/support.md",
                title="Support Handbook",
                kind="entity",
                score=1.0,
                snippet="support snippet",
            )
        ]

    def test_search_resolves_per_call_config(
        self, app_config: dict, base_config: SimpleNamespace
    ) -> None:
        """Each call should resolve its own per-agent config
        (no leakage between calls)."""
        seen_calls: list[dict] = []

        def fake_search(**kwargs):
            seen_calls.append(kwargs)
            return []

        original = cs.search_memory_wiki
        cs.search_memory_wiki = fake_search  # type: ignore[assignment]
        try:
            supplement = cs.create_wiki_corpus_supplement(
                resolve_config=lambda agent_id, current_app_config: (
                    resolve_memory_wiki_agent_config(
                        config=base_config,  # type: ignore[arg-type]
                        app_config=current_app_config,
                        agent_id=agent_id,
                    )
                ),
                get_app_config=lambda: app_config,
            )
            supplement.search(cs.WikiCorpusSupplementSearchInput(query="x", agent_id="support"))
            supplement.search(cs.WikiCorpusSupplementSearchInput(query="y", agent_id="marketing"))
        finally:
            cs.search_memory_wiki = original  # type: ignore[assignment]

        assert len(seen_calls) == 2
        assert seen_calls[0]["agent_id"] == "support"
        assert seen_calls[1]["agent_id"] == "marketing"
        # Both should carry the wiki overrides.
        for c in seen_calls:
            assert c["search_backend"] == "local"
            assert c["search_corpus"] == "wiki"
            assert c["app_config"] is app_config


class TestGetDelegation:
    def test_get_forwards_to_query_layer(
        self, app_config: dict, base_config: SimpleNamespace
    ) -> None:
        """The ``get`` wrapper should call the in-memory query
        layer with the per-agent config + line range."""
        received_calls: list[dict] = []
        get_result = WikiGetResult(
            corpus="wiki",
            path="entities/marketing-plan.md",
            title="Marketing Plan",
            kind="entity",
            content="line 3\nline 4",
            from_line=3,
            line_count=8,
            total_lines=10,
            truncated=True,
        )

        def fake_get(**kwargs):
            received_calls.append(kwargs)
            return get_result

        original = cs.get_memory_wiki_page
        cs.get_memory_wiki_page = fake_get  # type: ignore[assignment]
        try:
            supplement = cs.create_wiki_corpus_supplement(
                resolve_config=lambda agent_id, current_app_config: (
                    resolve_memory_wiki_agent_config(
                        config=base_config,  # type: ignore[arg-type]
                        app_config=current_app_config,
                        agent_id=agent_id,
                    )
                ),
                get_app_config=lambda: app_config,
            )
            out = supplement.get(
                cs.WikiCorpusSupplementGetInput(
                    lookup="marketing-plan",
                    from_line=3,
                    line_count=8,
                    agent_id="marketing",
                    agent_session_key="agent:marketing:main",
                    sandboxed=False,
                )
            )
        finally:
            cs.get_memory_wiki_page = original  # type: ignore[assignment]

        assert len(received_calls) == 1
        call = received_calls[0]
        assert call["lookup"] == "marketing-plan"
        assert call["from_line"] == 3
        assert call["line_count"] == 8
        assert call["agent_id"] == "marketing"
        assert call["agent_session_key"] == "agent:marketing:main"
        assert call["sandboxed"] is False
        assert call["search_backend"] == "local"
        assert call["search_corpus"] == "wiki"
        assert call["app_config"] is app_config
        cfg = call["config"]
        from extensions.memory_wiki.claim_health import _read_attr

        assert _read_attr(cfg, "agent_id", "agentId") == "marketing"
        assert out is get_result

    def test_get_propagates_none_for_missing_page(
        self, app_config: dict, base_config: SimpleNamespace
    ) -> None:
        original = cs.get_memory_wiki_page
        cs.get_memory_wiki_page = lambda **_k: None  # type: ignore[assignment]
        try:
            supplement = cs.create_wiki_corpus_supplement(
                resolve_config=lambda agent_id, current_app_config: (
                    resolve_memory_wiki_agent_config(
                        config=base_config,  # type: ignore[arg-type]
                        app_config=current_app_config,
                        agent_id=agent_id,
                    )
                ),
                get_app_config=lambda: app_config,
            )
            assert (
                supplement.get(
                    cs.WikiCorpusSupplementGetInput(
                        lookup="missing",
                        agent_id="support",
                    )
                )
                is None
            )
        finally:
            cs.get_memory_wiki_page = original  # type: ignore[assignment]


class TestFailClosed:
    def test_search_fails_closed_when_resolver_raises(self, app_config: dict) -> None:
        """When ``resolve_config`` raises (e.g. multi-agent
        context missing), the wrapper must fail closed
        BEFORE the query layer is invoked."""

        def raising_resolver(_a, _b):
            raise ValueError("agentId is required for memory-wiki")

        supplement = cs.create_wiki_corpus_supplement(
            resolve_config=raising_resolver,
            get_app_config=lambda: app_config,
        )
        with pytest.raises(ValueError, match="agentId is required"):
            supplement.search(
                cs.WikiCorpusSupplementSearchInput(
                    query="shared data",
                )
            )

    def test_get_fails_closed_when_resolver_raises(self, app_config: dict) -> None:
        def raising_resolver(_a, _b):
            raise ValueError("agentId is required for memory-wiki")

        supplement = cs.create_wiki_corpus_supplement(
            resolve_config=raising_resolver,
            get_app_config=lambda: app_config,
        )
        with pytest.raises(ValueError, match="agentId is required"):
            supplement.get(cs.WikiCorpusSupplementGetInput(lookup="x"))


class TestReset:
    def test_reset_returns_none(self) -> None:
        assert cs.reset_memory_wiki_corpus_supplement_state_for_tests() is None


class TestExports:
    def test_all_exports(self) -> None:
        for name in (
            "MemoryWikiConfigResolver",
            "WikiCorpusSupplement",
            "WikiCorpusSupplementGetInput",
            "WikiCorpusSupplementSearchInput",
            "create_wiki_corpus_supplement",
            "reset_memory_wiki_corpus_supplement_state_for_tests",
        ):
            assert hasattr(cs, name), f"missing export: {name}"
