"""Tests for extensions/memory_wiki/prompt_section.py.

Phase 4.3f-mr6: ports the OpenClaw
``prompt-section.ts`` test surface. The
tests focus on:

- ``build_wiki_tool_guidance`` returns
  ``[]`` when no relevant tools are
  registered; otherwise emits a
  "## Compiled Wiki" block whose workflow
  lines depend on which tools are present.
- ``create_wiki_prompt_section_builder``
  returns a sync callable that wraps
  ``build_wiki_tool_guidance`` (no
  filesystem I/O during the sync phase).
- ``create_wiki_prompt_section_preparer``
  is async; returns ``[]`` for
  ``vault.scope="agent"`` with no
  ``agent_id``; respects
  ``context.includeCompiledDigestPrompt``;
  renders the digest section from a
  seeded compiled cache snapshot.
- The digest ordering is stable regardless
  of input order (prompt-cache-friendly).
- The preparer only renders the invoking
  agent's digest (multi-agent context).
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

import asyncio
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

from extensions.memory_wiki import prompt_section as ps  # noqa: E402
from extensions.memory_wiki.compiled_cache import (  # noqa: E402
    MemoryWikiCompiledCacheSnapshot,
    MemoryWikiCompiledClaim,
    activate_memory_wiki_compiled_cache_owner,
    configure_memory_wiki_compiled_cache_store,
    create_memory_wiki_compiled_cache_publication_id,
    create_memory_wiki_compiled_cache_store,
    reset_memory_wiki_compiled_cache_for_tests,
    resolve_memory_wiki_compiled_cache_generation,
    write_memory_wiki_compiled_cache,
)
from extensions.memory_wiki.config import (  # noqa: E402
    resolve_memory_wiki_agent_config,
    resolve_memory_wiki_config,
)
from extensions.memory_wiki.prompt_section import (  # noqa: E402
    DIGEST_MAX_CLAIMS_PER_PAGE,
    DIGEST_MAX_PAGES,
    MemoryPromptSectionParams,
    build_digest_prompt_section,
    build_wiki_tool_guidance,
    create_wiki_prompt_section_builder,
    create_wiki_prompt_section_preparer,
    format_prompt_claim,
    rank_prompt_claim_freshness,
    rank_prompt_digest_page,
    reset_memory_wiki_prompt_section_state_for_tests,
    sort_prompt_claims,
)


def _config(
    *,
    vault_path: str | None = None,
    scope: str = "global",
    include_digest: bool = False,
) -> SimpleNamespace:
    """Build a minimal ``ResolvedMemoryWikiConfig`` shape for tests."""
    if vault_path is None:
        import tempfile

        vault_path = tempfile.mkdtemp(prefix="memory-wiki-prompt-test-")
    return SimpleNamespace(
        vault=SimpleNamespace(scope=scope, path=vault_path),
        agent_id=None,
        context=SimpleNamespace(includeCompiledDigestPrompt=include_digest),
    )


def _digest_with_page(
    *,
    page_title: str = "Alpha",
    page_kind: str = "entity",
    claim_count: int = 1,
    questions: list[str] | None = None,
    contradictions: list[str] | None = None,
    top_claims: list[dict] | None = None,
    digest_claim_count: int = 1,
    digest_contradiction_count: int = 0,
) -> dict:
    """Build a digest dict for tests (matches the
    ``MemoryWikiCompiledCacheSnapshot.digest`` shape)."""
    return {
        "claimCount": digest_claim_count,
        "contradictionCount": digest_contradiction_count,
        "pages": [
            {
                "title": page_title,
                "kind": page_kind,
                "path": f"entities/{page_title.lower()}.md",
                "claimCount": claim_count,
                "questions": list(questions or []),
                "contradictions": list(contradictions or []),
                "topClaims": list(top_claims or []),
            }
        ],
    }


def _seed_snapshot(
    config: SimpleNamespace,
    snapshot: MemoryWikiCompiledCacheSnapshot,
    *,
    vault_generation: str = "gen-1",
) -> None:
    """Seed a compiled-cache snapshot for ``config`` (test helper).

    Creates a fresh store + configures it.
    For multi-agent tests, use
    :func:`_seed_snapshot_with_existing_store`
    so the writes share a single blob store.
    """
    configure_memory_wiki_compiled_cache_store(create_memory_wiki_compiled_cache_store())
    _seed_snapshot_with_existing_store(config, snapshot, vault_generation=vault_generation)


def _seed_snapshot_with_existing_store(
    config: SimpleNamespace,
    snapshot: MemoryWikiCompiledCacheSnapshot,
    *,
    vault_generation: str = "gen-1",
) -> None:
    """Seed a compiled-cache snapshot using the currently-configured store.

    The caller is responsible for
    configuring the store exactly once
    before the loop so the writes share a
    single in-memory blob store.
    """
    activate_memory_wiki_compiled_cache_owner(config, vault_generation)
    generation = resolve_memory_wiki_compiled_cache_generation(snapshot)
    publication_id = create_memory_wiki_compiled_cache_publication_id()

    def _load_durable_identity() -> dict[str, str | None]:
        # Match the publish-then-validate-then-commit
        # contract: the post-commit identity must
        # carry the new ``vaultGeneration`` and the
        # just-written ``compiledCachePublicationId``.
        return {
            "vaultGeneration": vault_generation,
            "compiledCachePublicationId": publication_id,
        }

    # The validate_publication /
    # commit_publication hooks are sync
    # ``Callable[[], None]`` (not async) in
    # the Python port — pass a no-op lambda.
    write_memory_wiki_compiled_cache(
        config,
        snapshot,
        generation,
        publication_id,
        None,
        lambda: None,
        lambda: None,
        _load_durable_identity,
    )


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level state before and after each test."""
    reset_memory_wiki_compiled_cache_for_tests()
    reset_memory_wiki_prompt_section_state_for_tests()
    yield
    reset_memory_wiki_compiled_cache_for_tests()
    reset_memory_wiki_prompt_section_state_for_tests()


class TestConstants:
    def test_digest_max_pages(self) -> None:
        assert DIGEST_MAX_PAGES == 4

    def test_digest_max_claims_per_page(self) -> None:
        assert DIGEST_MAX_CLAIMS_PER_PAGE == 2


class TestRankPromptClaimFreshness:
    def test_fresh_ranks_highest(self) -> None:
        assert rank_prompt_claim_freshness("fresh") == 3

    def test_aging(self) -> None:
        assert rank_prompt_claim_freshness("aging") == 2

    def test_stale(self) -> None:
        assert rank_prompt_claim_freshness("stale") == 1

    def test_unknown_ranks_zero(self) -> None:
        assert rank_prompt_claim_freshness("unknown") == 0

    def test_none_ranks_zero(self) -> None:
        assert rank_prompt_claim_freshness(None) == 0

    def test_normalizes_case(self) -> None:
        assert rank_prompt_claim_freshness("FRESH") == 3


class TestRankPromptDigestPage:
    def test_empty_page_ranks_zero(self) -> None:
        page = SimpleNamespace(claimCount=0, questions=[], contradictions=[], topClaims=[])
        assert rank_prompt_digest_page(page) == 0

    def test_contradictions_dominate(self) -> None:
        page = SimpleNamespace(
            claimCount=0,
            questions=[],
            contradictions=["c1", "c2"],
            topClaims=[],
        )
        # 2 contradictions * 6 = 12
        assert rank_prompt_digest_page(page) == 12

    def test_caps_claim_count_at_six(self) -> None:
        page = SimpleNamespace(
            claimCount=20,
            questions=[],
            contradictions=[],
            topClaims=[],
        )
        # min(20, 6) * 2 = 12
        assert rank_prompt_digest_page(page) == 12

    def test_caps_top_claims_at_three(self) -> None:
        page = SimpleNamespace(
            claimCount=0,
            questions=[],
            contradictions=[],
            topClaims=["c1", "c2", "c3", "c4", "c5"],
        )
        # min(5, 3) = 3
        assert rank_prompt_digest_page(page) == 3

    def test_combined_score(self) -> None:
        page = SimpleNamespace(
            claimCount=3,
            questions=["q1"],
            contradictions=["c1"],
            topClaims=["c1", "c2"],
        )
        # 1 contradiction * 6 + 1 question * 4 + 3 claims * 2 + 2 top = 6 + 4 + 6 + 2 = 18
        assert rank_prompt_digest_page(page) == 18


class TestSortPromptClaims:
    def test_sorts_by_confidence_desc(self) -> None:
        c1 = SimpleNamespace(text="low", confidence=0.3, freshnessLevel="fresh", status="supported")
        c2 = SimpleNamespace(
            text="high", confidence=0.9, freshnessLevel="fresh", status="supported"
        )
        out = sort_prompt_claims([c1, c2])
        assert [c.text for c in out] == ["high", "low"]

    def test_breaks_ties_by_freshness(self) -> None:
        c1 = SimpleNamespace(text="a", confidence=0.5, freshnessLevel="aging", status="supported")
        c2 = SimpleNamespace(text="b", confidence=0.5, freshnessLevel="fresh", status="supported")
        out = sort_prompt_claims([c1, c2])
        assert [c.text for c in out] == ["b", "a"]

    def test_breaks_ties_by_text(self) -> None:
        c1 = SimpleNamespace(text="b", confidence=0.5, freshnessLevel="fresh", status="supported")
        c2 = SimpleNamespace(text="a", confidence=0.5, freshnessLevel="fresh", status="supported")
        out = sort_prompt_claims([c1, c2])
        assert [c.text for c in out] == ["a", "b"]


class TestFormatPromptClaim:
    def test_no_qualifiers(self) -> None:
        claim = SimpleNamespace(text="x", confidence=None, freshnessLevel=None, status=None)
        assert format_prompt_claim(claim) == "x"

    def test_with_all_qualifiers(self) -> None:
        claim = SimpleNamespace(
            text="x",
            confidence=0.91,
            freshnessLevel="fresh",
            status="supported",
        )
        out = format_prompt_claim(claim)
        assert out == "x (status supported, confidence 0.91, freshness fresh)"

    def test_confidence_only(self) -> None:
        claim = SimpleNamespace(text="x", confidence=0.5, freshnessLevel=None, status=None)
        assert format_prompt_claim(claim) == "x (confidence 0.50)"


class TestBuildWikiToolGuidance:
    def test_empty_for_no_relevant_tools(self) -> None:
        assert build_wiki_tool_guidance({"web_search"}) == []
        assert build_wiki_tool_guidance(set()) == []

    def test_memory_search_guidance(self) -> None:
        lines = build_wiki_tool_guidance({"memory_search"})
        text = "\n".join(lines)
        assert "## Compiled Wiki" in text
        assert "`memory_search` with `corpus=all`" in text

    def test_memory_get_guidance(self) -> None:
        lines = build_wiki_tool_guidance({"memory_get"})
        text = "\n".join(lines)
        assert "`memory_get` with `corpus=wiki` or `corpus=all`" in text

    def test_wiki_search_and_get_pair(self) -> None:
        lines = build_wiki_tool_guidance({"wiki_search", "wiki_get"})
        text = "\n".join(lines)
        assert "wiki-specific ranking or provenance details" in text
        assert "wiki_search" in text
        assert "wiki_get" in text

    def test_wiki_search_only(self) -> None:
        lines = build_wiki_tool_guidance({"wiki_search"})
        text = "\n".join(lines)
        assert "Use `wiki_search`" in text
        assert "wiki_get" not in text

    def test_wiki_get_only(self) -> None:
        lines = build_wiki_tool_guidance({"wiki_get"})
        text = "\n".join(lines)
        assert "Use `wiki_get`" in text
        assert "wiki_search" not in text

    def test_wiki_apply_guidance(self) -> None:
        lines = build_wiki_tool_guidance({"wiki_apply"})
        text = "\n".join(lines)
        assert "`wiki_apply`" in text

    def test_wiki_lint_guidance(self) -> None:
        lines = build_wiki_tool_guidance({"wiki_lint"})
        text = "\n".join(lines)
        assert "`wiki_lint`" in text


class TestCreateWikiPromptSectionBuilder:
    def test_builder_uses_available_tools(self) -> None:
        builder = create_wiki_prompt_section_builder()
        params = MemoryPromptSectionParams(
            available_tools={"memory_search", "memory_get", "wiki_search", "wiki_get"}
        )
        lines = builder(params)
        text = "\n".join(lines)
        assert "`memory_search` with `corpus=all`" in text
        assert "`memory_get` with `corpus=wiki` or `corpus=all`" in text
        assert "wiki-specific ranking or provenance details" in text

    def test_builder_empty_for_no_tools(self) -> None:
        builder = create_wiki_prompt_section_builder()
        params = MemoryPromptSectionParams(available_tools={"web_search"})
        assert builder(params) == []

    def test_builder_does_no_file_io(self) -> None:
        """The sync builder must not touch the filesystem.
        Mirrors the OpenClaw ``vi.spyOn(fsSync,
        "readFileSync")`` assertion."""
        # The builder takes only the params
        # and delegates to ``build_wiki_tool_guidance``
        # which is a pure function. The
        # ``load_memory_wiki_compiled_cache`` is
        # NEVER called in the sync path — it is
        # only called by the preparer.
        builder = create_wiki_prompt_section_builder()
        # We can prove this by patching the
        # loader to raise; the builder must
        # still return its tool-guidance lines.
        import extensions.memory_wiki.prompt_section as ps_mod

        original_loader = ps_mod.load_memory_wiki_compiled_cache

        def raising_loader(*_args, **_kwargs):
            raise RuntimeError("sync builder must not call the compiled-cache loader")

        ps_mod.load_memory_wiki_compiled_cache = raising_loader  # type: ignore[assignment]
        try:
            lines = builder(MemoryPromptSectionParams(available_tools={"wiki_lint"}))
        finally:
            ps_mod.load_memory_wiki_compiled_cache = original_loader  # type: ignore[assignment]
        text = "\n".join(lines)
        assert "`wiki_lint`" in text


class TestBuildDigestPromptSection:
    def test_empty_when_no_digest(self) -> None:
        assert build_digest_prompt_section(None) == []

    def test_empty_when_pages_field_is_empty_list(self) -> None:
        digest = {
            "claimCount": 0,
            "contradictionCount": 0,
            "pages": [],
        }
        assert build_digest_prompt_section(digest) == []

    def test_empty_when_no_eligible_pages(self) -> None:
        # All pages have claimCount=0, no questions, no contradictions.
        digest = {
            "claimCount": 0,
            "contradictionCount": 0,
            "pages": [
                {
                    "title": "Empty",
                    "kind": "entity",
                    "path": "entities/empty.md",
                    "claimCount": 0,
                    "questions": [],
                    "contradictions": [],
                    "topClaims": [],
                }
            ],
        }
        assert build_digest_prompt_section(digest) == []

    def test_renders_basic_digest(self) -> None:
        digest = _digest_with_page(
            page_title="Alpha",
            claim_count=3,
            questions=["Still active?"],
            contradictions=["Conflicts with source.beta"],
            top_claims=[
                {
                    "text": "Alpha uses PostgreSQL for production writes.",
                    "confidence": 0.91,
                    "freshnessLevel": "fresh",
                    "status": "supported",
                }
            ],
            digest_claim_count=8,
            digest_contradiction_count=1,
        )
        lines = build_digest_prompt_section(digest)
        text = "\n".join(lines)
        assert "## Compiled Wiki Snapshot" in text
        assert "Compiled wiki currently tracks 8 claims" in text
        assert "Contradiction clusters: 1." in text
        assert "Alpha: entity, 3 claims, 1 open questions, 1 contradiction notes" in text
        assert "Alpha uses PostgreSQL for production writes." in text
        assert "(status supported, confidence 0.91, freshness fresh)" in text

    def test_caps_pages_at_digest_max(self) -> None:
        # 6 pages, all eligible → only top 4 should appear.
        pages = [
            {
                "title": f"Page{i}",
                "kind": "entity",
                "path": f"entities/page{i}.md",
                "claimCount": i + 1,
                "questions": [],
                "contradictions": [],
                "topClaims": [],
            }
            for i in range(6)
        ]
        digest = {
            "claimCount": 21,
            "contradictionCount": 0,
            "pages": pages,
        }
        lines = build_digest_prompt_section(digest)
        text = "\n".join(lines)
        # Top 4 by score (highest claimCount): Page5, Page4, Page3, Page2
        assert "Page5" in text
        assert "Page4" in text
        assert "Page3" in text
        assert "Page2" in text
        assert "Page1" not in text
        assert "Page0" not in text

    def test_caps_claims_per_page(self) -> None:
        digest = _digest_with_page(
            claim_count=5,
            top_claims=[
                {"text": "c1", "confidence": 0.9, "freshnessLevel": "fresh", "status": "supported"},
                {"text": "c2", "confidence": 0.8, "freshnessLevel": "fresh", "status": "supported"},
                {"text": "c3", "confidence": 0.7, "freshnessLevel": "fresh", "status": "supported"},
            ],
        )
        lines = build_digest_prompt_section(digest)
        text = "\n".join(lines)
        # Top 2 by confidence.
        assert "c1" in text
        assert "c2" in text
        assert "c3" not in text


class TestPreparerDisabled:
    def test_returns_empty_when_digest_disabled(self) -> None:
        config = _config(include_digest=False)
        preparer = create_wiki_prompt_section_preparer(
            config=config,
            resolve_config=lambda _a, _b: config,
        )
        out = asyncio.run(preparer(MemoryPromptSectionParams(available_tools=set())))
        assert out == []

    def test_returns_empty_for_agent_vault_without_agent_id(self) -> None:
        # ``vault.scope == "agent"`` with no
        # ``agent_id`` in the params must
        # return ``[]`` (context-free
        # preparation must not choose or
        # disclose another agent's vault).
        config = _config(scope="agent", include_digest=True)
        preparer = create_wiki_prompt_section_preparer(
            config=config,
            resolve_config=lambda _a, _b: config,
        )
        out = asyncio.run(preparer(MemoryPromptSectionParams(available_tools=set())))
        assert out == []


class TestPreparerEnabled:
    def test_renders_digest_from_seeded_snapshot(self) -> None:
        config = _config(include_digest=True)
        snapshot = MemoryWikiCompiledCacheSnapshot(
            digest=_digest_with_page(
                page_title="Alpha",
                claim_count=3,
                questions=["Still active?"],
                contradictions=["Conflicts with source.beta"],
                top_claims=[
                    {
                        "text": "Alpha uses PostgreSQL for production writes.",
                        "confidence": 0.91,
                        "freshnessLevel": "fresh",
                        "status": "supported",
                    }
                ],
                digest_claim_count=8,
                digest_contradiction_count=1,
            ),
            claims=[
                MemoryWikiCompiledClaim(
                    page_title="Alpha",
                    page_kind="entity",
                    page_path="entities/alpha.md",
                    text="Alpha uses PostgreSQL for production writes.",
                )
            ],
        )
        _seed_snapshot(config, snapshot)
        preparer = create_wiki_prompt_section_preparer(
            config=config,
            resolve_config=lambda _a, _b: config,
        )
        out = asyncio.run(preparer(MemoryPromptSectionParams(available_tools=set())))
        text = "\n".join(out)
        assert "## Compiled Wiki Snapshot" in text
        assert "Alpha: entity, 3 claims, 1 open questions, 1 contradiction notes" in text
        assert "Alpha uses PostgreSQL for production writes." in text


class TestPreparerStableOrdering:
    def test_stable_digest_output_for_reversed_input(self) -> None:
        """Mirrors the OpenClaw
        ``stabilizes digest ordering for
        prompt-cache-friendly output`` test.
        Reversing the top-claim list of a
        page must NOT change the rendered
        digest (the sort is by confidence
        desc, then freshness desc, then
        text asc)."""
        config = _config(include_digest=True)
        # Two pages with claimCount=4 and 2 (Alpha
        # has higher score because of
        # contradictions + questions + more
        # claims). With both pages eligible,
        # the ranking puts Alpha first
        # regardless of input order.
        page_alpha = {
            "title": "Alpha",
            "kind": "entity",
            "path": "entities/alpha.md",
            "claimCount": 4,
            "questions": ["Still active?"],
            "contradictions": ["Conflicts with source.beta"],
            "topClaims": [
                {
                    "text": "Alpha was renamed in 2026.",
                    "confidence": 0.42,
                    "freshnessLevel": "aging",
                    "status": "supported",
                },
                {
                    "text": "Alpha uses PostgreSQL for production writes.",
                    "confidence": 0.91,
                    "freshnessLevel": "fresh",
                    "status": "supported",
                },
            ],
        }
        page_zulu = {
            "title": "Zulu",
            "kind": "concept",
            "path": "concepts/zulu.md",
            "claimCount": 2,
            "questions": [],
            "contradictions": [],
            "topClaims": [
                {
                    "text": "Zulu fallback note.",
                    "confidence": 0.3,
                    "freshnessLevel": "stale",
                    "status": "supported",
                }
            ],
        }

        snapshot_first = MemoryWikiCompiledCacheSnapshot(
            digest={
                "claimCount": 6,
                "contradictionCount": 1,
                "pages": [page_zulu, page_alpha],
            }
        )
        _seed_snapshot(config, snapshot_first)
        preparer = create_wiki_prompt_section_preparer(
            config=config,
            resolve_config=lambda _a, _b: config,
        )
        first = asyncio.run(preparer(MemoryPromptSectionParams(available_tools=set())))

        # Now re-seed with reversed top-claim order
        # on the Alpha page (and the same pages in
        # the same order).
        page_alpha_reversed = {
            **page_alpha,
            "topClaims": list(reversed(page_alpha["topClaims"])),
        }
        snapshot_second = MemoryWikiCompiledCacheSnapshot(
            digest={
                "claimCount": 6,
                "contradictionCount": 1,
                "pages": [page_zulu, page_alpha_reversed],
            }
        )
        _seed_snapshot(config, snapshot_second)
        second = asyncio.run(preparer(MemoryPromptSectionParams(available_tools=set())))

        assert first == second
        text = "\n".join(first)
        # Highest-confidence claim is rendered
        # first regardless of input order.
        assert (
            "Alpha uses PostgreSQL for production writes. "
            "(status supported, confidence 0.91, freshness fresh)"
        ) in text


class TestPreparerPerAgentDigest:
    def test_only_invoke_agent_digest_is_rendered(self) -> None:
        """Mirrors the OpenClaw ``prepares only
        the invoking agent's compiled digest``
        test. The preparer must re-resolve
        the config for each call's
        ``agent_id`` and only show the
        matching vault's digest."""
        app_config = {"agents": {"list": [{"id": "support", "default": True}, {"id": "marketing"}]}}
        import tempfile

        tmp_root = tempfile.mkdtemp(prefix="memory-wiki-prompt-test-")
        # Build the base config with the digest
        # flag ON — the per-agent resolve
        # propagates the same context (matching
        # the OpenClaw semantics where
        # ``context.includeCompiledDigestPrompt``
        # is a base-config knob, not a
        # per-agent override).
        base_config = resolve_memory_wiki_config(
            {
                "vault": {"scope": "agent", "path": tmp_root},
                "context": {"includeCompiledDigestPrompt": True},
            }
        )

        # Configure the store ONCE so writes
        # for both agents land in the same
        # blob store. (Calling
        # ``create_memory_wiki_compiled_cache_store``
        # inside the loop would orphan the
        # first agent's snapshot.)
        configure_memory_wiki_compiled_cache_store(create_memory_wiki_compiled_cache_store())

        for agent_id, marker in [
            ("support", "SUPPORT_SENTINEL"),
            ("marketing", "MARKETING_SENTINEL"),
        ]:
            agent_config = resolve_memory_wiki_agent_config(
                config=base_config,
                app_config=app_config,
                agent_id=agent_id,
            )
            snapshot = MemoryWikiCompiledCacheSnapshot(
                digest=_digest_with_page(
                    page_title=agent_id,
                    claim_count=1,
                    top_claims=[
                        {
                            "text": marker,
                            "confidence": 0.5,
                            "freshnessLevel": "fresh",
                            "status": "supported",
                        }
                    ],
                )
            )
            try:
                _seed_snapshot_with_existing_store(agent_config, snapshot)
            except Exception as exc:
                pytest.fail(f"failed to seed {agent_id}: {exc}")

        def resolve(agent_id, _app_config):
            if not agent_id:
                return base_config
            return resolve_memory_wiki_agent_config(
                config=base_config, app_config=app_config, agent_id=agent_id
            )

        preparer = create_wiki_prompt_section_preparer(
            config=base_config,
            resolve_config=resolve,
        )

        support = asyncio.run(
            preparer(MemoryPromptSectionParams(available_tools=set(), agent_id="support"))
        )
        marketing = asyncio.run(
            preparer(MemoryPromptSectionParams(available_tools=set(), agent_id="marketing"))
        )
        support_text = "\n".join(support)
        marketing_text = "\n".join(marketing)
        assert "SUPPORT_SENTINEL" in support_text
        assert "MARKETING_SENTINEL" not in support_text
        assert "MARKETING_SENTINEL" in marketing_text
        assert "SUPPORT_SENTINEL" not in marketing_text

        # No agent_id → returns [] (agent vault
        # context-free).
        empty = asyncio.run(preparer(MemoryPromptSectionParams(available_tools=set())))
        assert empty == []


class TestReset:
    def test_reset_returns_none(self) -> None:
        assert reset_memory_wiki_prompt_section_state_for_tests() is None


class TestExports:
    def test_all_exports(self) -> None:
        for name in (
            "DIGEST_MAX_CLAIMS_PER_PAGE",
            "DIGEST_MAX_PAGES",
            "MemoryPromptSectionBuilder",
            "MemoryPromptSectionParams",
            "MemoryPromptSectionPreparer",
            "build_digest_prompt_section",
            "build_wiki_tool_guidance",
            "create_wiki_prompt_section_builder",
            "create_wiki_prompt_section_preparer",
            "format_prompt_claim",
            "rank_prompt_claim_freshness",
            "rank_prompt_digest_page",
            "reset_memory_wiki_prompt_section_state_for_tests",
            "sort_prompt_claims",
        ):
            assert hasattr(ps, name), f"missing export: {name}"
