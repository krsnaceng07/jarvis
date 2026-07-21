"""prompt_section — Memory Wiki prompt section builders.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/prompt-section.ts``.

This module provides two factories that the
host calls when assembling the per-run
system-prompt section for a memory extension:

- :func:`create_wiki_prompt_section_builder`
  returns a **synchronous** builder that
  emits a tool-aware "## Compiled Wiki"
  guidance block. It does no filesystem or
  network I/O so the host can call it inline
  during prompt assembly without an async
  hop.

- :func:`create_wiki_prompt_section_preparer`
  returns an **asynchronous** preparer that
  loads the compiled cache snapshot and
  renders the per-vault "## Compiled Wiki
  Snapshot" digest block. It is run once
  per run during prompt preparation and
  caches the result for the run.

Both factories are bound to a base
``ResolvedMemoryWikiConfig``; the preparer
additionally takes a 2-arg
``MemoryWikiConfigResolver`` (matching
OpenClaw's contract) so the per-agent
config can be re-resolved for each
invocation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .compiled_cache import load_memory_wiki_compiled_cache

if TYPE_CHECKING:
    from .compiled_cache import MemoryWikiCompiledCacheSnapshot
    from .config import MemoryWikiConfigResolver, ResolvedMemoryWikiConfig


# ── Constants ────────────────────────────────────────────────

# Mirrors the OpenClaw
# ``DIGEST_MAX_PAGES = 4`` constant.
DIGEST_MAX_PAGES = 4

# Mirrors the OpenClaw
# ``DIGEST_MAX_CLAIMS_PER_PAGE = 2``
# constant.
DIGEST_MAX_CLAIMS_PER_PAGE = 2

# The set of tools the wiki prompt section
# knows about. Mirrors the OpenClaw
# ``buildWikiToolGuidance`` tool-name
# strings.
_WIKI_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "memory_search",
        "memory_get",
        "wiki_search",
        "wiki_get",
        "wiki_apply",
        "wiki_lint",
    }
)


# ── Public types ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MemoryPromptSectionParams:
    """The params shape for the prompt-section builder / preparer.

    Mirrors the OpenClaw
    ``MemoryPromptSectionParams = { availableTools: Set<string>,
    citationsMode?, agentId?, agentSessionKey?, sandboxed? }``
    type.
    """

    available_tools: set[str]
    citations_mode: str | None = None
    agent_id: str | None = None
    agent_session_key: str | None = None
    sandboxed: bool = False


# Mirrors the OpenClaw
# ``MemoryPromptSectionBuilder = (params) => string[]`` type.
MemoryPromptSectionBuilder = Callable[[MemoryPromptSectionParams], list[str]]

# Mirrors the OpenClaw
# ``MemoryPromptSectionPreparer = (params) => Promise<readonly string[]>`` type.
# The Python port wraps the sync cache loader in an async
# coroutine so the host can ``await`` it.
MemoryPromptSectionPreparer = Callable[[MemoryPromptSectionParams], Awaitable[list[str]]]


# ── Digest ranking + formatting helpers ─────────────────────


def _get_attr(value: Any, *names: str) -> Any:
    """Read the first present attribute/key from ``value``.

    Accepts both dataclass-style attribute
    access (``hasattr``) and ``dict``-style
    key access. Returns ``None`` when
    nothing matches.
    """
    if isinstance(value, dict):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _claim_count_of(page: Any) -> int:
    """Return the page's ``claimCount`` (snake / camel tolerant, dict or obj)."""
    for attr in ("claim_count", "claimCount"):
        value = _get_attr(page, attr)
        if isinstance(value, int | float):
            return int(value)
    return 0


def _questions_of(page: Any) -> list[Any]:
    """Return the page's questions list (snake / camel tolerant, dict or obj)."""
    value = _get_attr(page, "questions")
    if isinstance(value, list):
        return value
    return []


def _contradictions_of(page: Any) -> list[Any]:
    """Return the page's contradictions list (snake / camel tolerant, dict or obj)."""
    value = _get_attr(page, "contradictions")
    if isinstance(value, list):
        return value
    return []


def _top_claims_of(page: Any) -> list[Any]:
    """Return the page's ``topClaims`` list (snake / camel tolerant, dict or obj)."""
    for attr in ("top_claims", "topClaims"):
        value = _get_attr(page, attr)
        if isinstance(value, list):
            return value
    return []


def _claim_text_of(claim: Any) -> str:
    """Return the claim's text (snake / camel tolerant, dict or obj)."""
    value = _get_attr(claim, "text")
    if isinstance(value, str):
        return value
    return ""


def _claim_confidence_of(claim: Any) -> float | None:
    """Return the claim's confidence (snake / camel tolerant, dict or obj)."""
    for attr in ("confidence", "confidenceValue"):
        value = _get_attr(claim, attr)
        if isinstance(value, int | float):
            return float(value)
    return None


def _claim_freshness_of(claim: Any) -> str | None:
    """Return the claim's ``freshnessLevel`` (snake / camel tolerant, dict or obj)."""
    for attr in ("freshness_level", "freshnessLevel"):
        value = _get_attr(claim, attr)
        if isinstance(value, str):
            return value
    return None


def _claim_status_of(claim: Any) -> str | None:
    """Return the claim's ``status`` (snake / camel tolerant, dict or obj)."""
    value = _get_attr(claim, "status")
    if isinstance(value, str):
        return value
    return None


def _page_title_of(page: Any) -> str:
    """Return the page's title (snake / camel tolerant, dict or obj)."""
    for attr in ("title", "pageTitle"):
        value = _get_attr(page, attr)
        if isinstance(value, str):
            return value
    return ""


def _page_kind_of(page: Any) -> str:
    """Return the page's kind (snake / camel tolerant, dict or obj)."""
    for attr in ("kind", "pageKind"):
        value = _get_attr(page, attr)
        if isinstance(value, str):
            return value
    return ""


def _digest_pages_of(digest: Any) -> list[Any]:
    """Return the digest's ``pages`` list (dataclass or dict)."""
    if isinstance(digest, dict):
        value = digest.get("pages")
        if isinstance(value, list):
            return value
        return []
    value = getattr(digest, "pages", None)
    if isinstance(value, list):
        return value
    return []


def _digest_claim_count_of(digest: Any) -> int:
    """Return the digest's ``claimCount`` (dataclass or dict)."""
    if isinstance(digest, dict):
        value = digest.get("claimCount", 0)
        if isinstance(value, int | float):
            return int(value)
        return 0
    for attr in ("claim_count", "claimCount"):
        if hasattr(digest, attr):
            value = getattr(digest, attr)
            if isinstance(value, int | float):
                return int(value)
    return 0


def _digest_contradiction_count_of(digest: Any) -> int:
    """Return the digest's ``contradictionCount`` (dataclass or dict)."""
    if isinstance(digest, dict):
        value = digest.get("contradictionCount", 0)
        if isinstance(value, int | float):
            return int(value)
        return 0
    for attr in ("contradiction_count", "contradictionCount"):
        if hasattr(digest, attr):
            value = getattr(digest, attr)
            if isinstance(value, int | float):
                return int(value)
    return 0


def rank_prompt_digest_page(page: Any) -> int:
    """Return the digest ranking score for a page.

    Mirrors the OpenClaw ``rankPromptDigestPage``:

    - 6 points per contradiction cluster
    - 4 points per open question
    - 2 points per claim (capped at 6)
    - 1 point per top-claim (capped at 3)
    """
    contradictions = len(_contradictions_of(page))
    questions = len(_questions_of(page))
    claim_count = _claim_count_of(page)
    top_claims = len(_top_claims_of(page))
    return contradictions * 6 + questions * 4 + min(claim_count, 6) * 2 + min(top_claims, 3)


def rank_prompt_claim_freshness(level: str | None) -> int:
    """Return the freshness rank for ``level``.

    Mirrors the OpenClaw
    ``rankPromptClaimFreshness``:

    - ``fresh`` → 3
    - ``aging`` → 2
    - ``stale`` → 1
    - anything else → 0
    """
    if not isinstance(level, str):
        return 0
    normalized = level.strip().lower()
    if normalized == "fresh":
        return 3
    if normalized == "aging":
        return 2
    if normalized == "stale":
        return 1
    return 0


def sort_prompt_claims(claims: list[Any]) -> list[Any]:
    """Return a new list of ``claims`` sorted by digest priority.

    Mirrors the OpenClaw
    ``sortPromptClaims``: confidence
    descending, then freshness descending,
    then text ascending.
    """

    def _key(claim: Any) -> tuple[float, int, str]:
        confidence = _claim_confidence_of(claim)
        confidence_key = confidence if isinstance(confidence, int | float) else -1.0
        freshness_key = rank_prompt_claim_freshness(_claim_freshness_of(claim))
        text_key = _claim_text_of(claim)
        return (-float(confidence_key), -freshness_key, text_key)

    return sorted(claims, key=_key)


def format_prompt_claim(claim: Any) -> str:
    """Render ``claim`` as a single line.

    Mirrors the OpenClaw
    ``formatPromptClaim``: appends
    ``(status X, confidence Y, freshness Z)``
    when any qualifier is present.
    """
    text = _claim_text_of(claim)
    qualifiers: list[str] = []
    status = _claim_status_of(claim)
    if isinstance(status, str) and status.strip():
        qualifiers.append(f"status {status.strip()}")
    confidence = _claim_confidence_of(claim)
    if isinstance(confidence, int | float):
        qualifiers.append(f"confidence {float(confidence):.2f}")
    freshness = _claim_freshness_of(claim)
    if isinstance(freshness, str) and freshness.strip():
        qualifiers.append(f"freshness {freshness.strip()}")
    if not qualifiers:
        return text
    return f"{text} ({', '.join(qualifiers)})"


# ── Section builders ────────────────────────────────────────


def build_digest_prompt_section(
    digest: Any,
) -> list[str]:
    """Render the per-vault digest prompt section.

    Mirrors the OpenClaw
    ``buildDigestPromptSection``. Returns
    the lines as a list (the OpenClaw
    function returns ``string[]``; the host
    joins them with ``"\\n"``). Returns
    ``[]`` when no pages are eligible.

    The ``digest`` argument is tolerant of
    either a dataclass (with
    ``claimCount`` / ``contradictionCount``
    / ``pages`` attributes) or a plain
    ``dict`` (with the same camelCase keys)
    — matching how the Python port's
    ``MemoryWikiCompiledCacheSnapshot``
    currently stores the digest payload.
    """
    if digest is None:
        return []
    pages = _digest_pages_of(digest)
    if not isinstance(pages, list) or not pages:
        return []

    selected = [
        page
        for page in pages
        if _claim_count_of(page) > 0
        or len(_questions_of(page)) > 0
        or len(_contradictions_of(page)) > 0
    ]
    if not selected:
        return []

    selected_sorted = sorted(
        selected,
        key=lambda page: (
            -rank_prompt_digest_page(page),
            _page_title_of(page),
        ),
    )
    selected_top = selected_sorted[:DIGEST_MAX_PAGES]
    if not selected_top:
        return []

    claim_count_total = _digest_claim_count_of(digest)
    contradiction_count = _digest_contradiction_count_of(digest)

    lines: list[str] = [
        "## Compiled Wiki Snapshot",
        (
            f"Compiled wiki currently tracks {claim_count_total} claims across "
            f"{len(selected_top)} high-signal pages."
        ),
        f"Contradiction clusters: {contradiction_count}.",
    ]
    for page in selected_top:
        details: list[str] = []
        kind = _page_kind_of(page)
        if kind:
            details.append(kind)
        details.append(f"{_claim_count_of(page)} claims")
        if len(_questions_of(page)) > 0:
            details.append(f"{len(_questions_of(page))} open questions")
        if len(_contradictions_of(page)) > 0:
            details.append(f"{len(_contradictions_of(page))} contradiction notes")
        lines.append(f"- {_page_title_of(page)}: {', '.join(details)}")
        sorted_claims = sort_prompt_claims(_top_claims_of(page))[:DIGEST_MAX_CLAIMS_PER_PAGE]
        for claim in sorted_claims:
            lines.append(f"  - {format_prompt_claim(claim)}")
    lines.append("")
    return lines


def build_wiki_tool_guidance(available_tools: set[str] | frozenset[str]) -> list[str]:
    """Render the synchronous "## Compiled Wiki" tool-guidance block.

    Mirrors the OpenClaw
    ``buildWikiToolGuidance``. Returns
    ``[]`` when no wiki- or memory-adjacent
    tools are registered. The host joins the
    lines with ``"\\n"`` to produce the
    final prompt section text.
    """
    has_memory_search = "memory_search" in available_tools
    has_memory_get = "memory_get" in available_tools
    has_wiki_search = "wiki_search" in available_tools
    has_wiki_get = "wiki_get" in available_tools
    has_wiki_apply = "wiki_apply" in available_tools
    has_wiki_lint = "wiki_lint" in available_tools

    if not (
        has_memory_search
        or has_memory_get
        or has_wiki_search
        or has_wiki_get
        or has_wiki_apply
        or has_wiki_lint
    ):
        return []

    lines: list[str] = [
        "## Compiled Wiki",
        (
            "Use the wiki when the answer depends on accumulated project knowledge, "
            "prior syntheses, entity pages, or source-backed notes that should survive "
            "beyond one conversation."
        ),
    ]
    if has_memory_search:
        lines.append(
            "Prefer `memory_search` with `corpus=all` for one recall pass across "
            "durable memory and the compiled wiki when both are relevant."
        )
    if has_memory_get:
        lines.append(
            "Use `memory_get` with `corpus=wiki` or `corpus=all` when you already "
            "know the page path and want a small excerpt without leaving the shared "
            "memory tool flow."
        )
    if has_wiki_search and has_wiki_get:
        lines.append(
            "Workflow: `wiki_search` first, then `wiki_get` for the exact page or "
            "imported memory file you need. Use this when you want wiki-specific "
            "ranking or provenance details instead of the broader shared memory flow."
        )
    elif has_wiki_search:
        lines.append(
            "Use `wiki_search` before answering from stored knowledge when you want "
            "wiki-specific ranking or provenance details."
        )
    elif has_wiki_get:
        lines.append(
            "Use `wiki_get` to inspect specific wiki pages or imported memory files " "by path/id."
        )
    if has_wiki_apply:
        lines.append(
            "Use `wiki_apply` for narrow synthesis filing and metadata repair instead "
            "of rewriting managed markdown blocks by hand."
        )
    if has_wiki_lint:
        lines.append("After meaningful wiki updates, run `wiki_lint` before trusting the vault.")
    lines.append("")
    return lines


# ── Factories ────────────────────────────────────────────────


def create_wiki_prompt_section_builder() -> MemoryPromptSectionBuilder:
    """Build the synchronous prompt-section builder for the memory wiki.

    Mirrors the OpenClaw
    :func:`createWikiPromptSectionBuilder`.
    Returns a callable that takes
    :class:`MemoryPromptSectionParams` and
    returns the tool-guidance lines (or
    ``[]`` when no relevant tools are
    registered).
    """

    def _builder(params: MemoryPromptSectionParams) -> list[str]:
        return build_wiki_tool_guidance(params.available_tools)

    return _builder


def create_wiki_prompt_section_preparer(
    *,
    config: ResolvedMemoryWikiConfig,
    resolve_config: MemoryWikiConfigResolver,
) -> MemoryPromptSectionPreparer:
    """Build the async prompt-section preparer for the memory wiki.

    Mirrors the OpenClaw
    :func:`createWikiPromptSectionPreparer`.
    Returns an async callable that loads
    the per-vault compiled cache snapshot
    and renders the digest prompt section.

    - When ``config.vault.scope == "agent"``
      and no ``agent_id`` is provided in the
      params, the preparer returns ``[]``
      (context-free preparation must not
      choose or disclose another agent's
      vault).
    - When the resolved config has
      ``context.includeCompiledDigestPrompt``
      ``False``, the preparer returns ``[]``.
    - Otherwise the preparer re-resolves the
      config for the params' ``agent_id``,
      loads the compiled cache snapshot, and
      returns the digest prompt section.
    """

    async def _prepare(params: MemoryPromptSectionParams) -> list[str]:
        # Context-free preparation must not choose or
        # disclose another agent's vault.
        if (
            getattr(getattr(config, "vault", None), "scope", None) == "agent"
            and not params.agent_id
        ):
            return []
        per_agent_config = resolve_config(params.agent_id, None)
        include_digest = bool(
            getattr(
                getattr(per_agent_config, "context", None),
                "includeCompiledDigestPrompt",
                False,
            )
        )
        if not include_digest:
            return []
        snapshot: MemoryWikiCompiledCacheSnapshot | None = load_memory_wiki_compiled_cache(
            per_agent_config
        )
        if snapshot is None:
            return []
        return build_digest_prompt_section(getattr(snapshot, "digest", None))

    return _prepare


def reset_memory_wiki_prompt_section_state_for_tests() -> None:
    """Reset module-level state (test-only helper).

    The prompt section helpers are
    stateless; this function exists so test
    code can call a known name (mirroring the
    OpenClaw
    ``resetMemoryWikiPromptSectionStateForTests``
    pattern used by other modules).
    """
    return


__all__ = [
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
]
