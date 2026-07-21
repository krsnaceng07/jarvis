"""Tests for extensions/memory_wiki/tool.py.

Phase 4.3f-mr3: ports the OpenClaw
``tool.ts`` (the 5 wiki tools). The tests
focus on:

- Each of the 5 tools builds a
  :class:`WikiTool` dict with the expected
  ``name`` / ``label`` / ``description``
  / ``parameters`` shape.
- ``wiki_status`` returns a text block +
  status details.
- ``wiki_search`` returns a text block +
  the matched results (empty / non-empty
  / mode passed through).
- ``wiki_lint`` returns a text block +
  the issues (no issues today; the stub
  reports no issues).
- ``wiki_apply`` applies a mutation and
  reports the page path + the compile
  summary.
- ``wiki_get`` returns the page body +
  the line-range metadata; returns
  ``"Wiki page not found: ..."`` when the
  page doesn't exist.
- ``create_wiki_tools`` returns the 5
  tools in OpenClaw's order.
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

from extensions.memory_wiki.markdown_pages import render_wiki_markdown  # noqa: E402
from extensions.memory_wiki.tool import (  # noqa: E402
    WikiTool,
    WikiToolMemoryContext,
    WikiToolResult,
    create_wiki_apply_tool,
    create_wiki_get_tool,
    create_wiki_lint_tool,
    create_wiki_search_tool,
    create_wiki_status_tool,
    create_wiki_tools,
    format_wiki_tool_report_path,
)


def _config(vault_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        vaultMode="single",
        vault=SimpleNamespace(path=str(vault_path), scope="global", renderMode="native"),
        search=SimpleNamespace(
            corpus="wiki",
            backend="auto",
        ),
        bridge=SimpleNamespace(enabled=False, indexMemoryRoot=False),
    )


def _seed_vault(vault: Path) -> None:
    for sub in ("entities", "concepts", "sources", "syntheses", "reports"):
        (vault / sub).mkdir(parents=True, exist_ok=True)
    (vault / "entities" / "alpha.md").write_text(
        render_wiki_markdown(
            frontmatter={"pageType": "entity", "id": "entity.alpha"},
            body="# Alpha\n\nFirst line about Alpha.\nSecond line.\n",
        ),
        encoding="utf-8",
    )
    (vault / "entities" / "beta.md").write_text(
        render_wiki_markdown(
            frontmatter={"pageType": "entity", "id": "entity.beta"},
            body="# Beta\n\nBeta-only content.\n",
        ),
        encoding="utf-8",
    )


async def _run(tool: WikiTool, **params: object) -> WikiToolResult:
    """Invoke a tool's ``execute`` coroutine and return the result."""
    execute = tool["execute"]
    return await execute("call-id", params)


class TestToolShape:
    def test_create_wiki_tools_returns_five(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        tools = create_wiki_tools(config)
        assert len(tools) == 5
        names = [tool["name"] for tool in tools]
        assert names == [
            "wiki_status",
            "wiki_search",
            "wiki_lint",
            "wiki_apply",
            "wiki_get",
        ]

    def test_each_tool_has_required_keys(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        for tool in create_wiki_tools(config):
            for key in ("name", "label", "description", "parameters", "execute"):
                assert key in tool, f"tool {tool['name']} missing {key!r}"


class TestWikiStatus:
    @pytest.mark.asyncio
    async def test_returns_status_text(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        tool = create_wiki_status_tool(
            config, memory_context=WikiToolMemoryContext(agent_id="alpha")
        )
        result = await _run(tool)
        assert isinstance(result, WikiToolResult)
        assert result.content
        text = result.content[0].text
        assert "Vault mode: single" in text
        assert "Render mode: native" in text
        # ``agentIds`` is propagated to the
        # details payload.
        assert "alpha" in result.details.get("agentIds", [])


class TestWikiSearch:
    @pytest.mark.asyncio
    async def test_empty_query_returns_required_message(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        tool = create_wiki_search_tool(config)
        result = await _run(tool, query="")
        assert "query is required" in result.content[0].text

    @pytest.mark.asyncio
    async def test_no_results_returns_no_results_message(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        tool = create_wiki_search_tool(config)
        result = await _run(tool, query="nothing-matches-this")
        assert "No wiki or memory results." in result.content[0].text
        assert result.details.get("results") == []

    @pytest.mark.asyncio
    async def test_title_match(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        tool = create_wiki_search_tool(config)
        result = await _run(tool, query="Alpha")
        text = result.content[0].text
        assert "Alpha" in text
        assert "entities/alpha.md" in text

    @pytest.mark.asyncio
    async def test_body_match(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        tool = create_wiki_search_tool(config)
        # ``Beta-only content.`` is in beta.md.
        result = await _run(tool, query="Beta-only")
        text = result.content[0].text
        assert "Beta" in text
        assert "entities/beta.md" in text

    @pytest.mark.asyncio
    async def test_max_results_truncates(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        tool = create_wiki_search_tool(config)
        result = await _run(tool, query="line", maxResults=1)
        results = result.details.get("results") or []
        assert len(results) <= 1


class TestWikiLint:
    @pytest.mark.asyncio
    async def test_no_issues_returns_summary(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        tool = create_wiki_lint_tool(config)
        result = await _run(tool)
        text = result.content[0].text
        # The stub reports no issues today.
        assert "No wiki lint issues." in text or "Issues: 0" in text
        assert result.details.get("issueCount") == 0


class TestWikiApply:
    @pytest.mark.asyncio
    async def test_create_synthesis(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        tool = create_wiki_apply_tool(config)
        result = await _run(
            tool,
            op="create_synthesis",
            title="My synthesis",
            body="Summary body.",
            sourceIds=["s1"],
        )
        text = result.content[0].text
        assert "syntheses/" in text
        assert "via create_synthesis" in text
        # The new page is on disk.
        assert any(tmp_path.glob("syntheses/*.md"))

    @pytest.mark.asyncio
    async def test_update_metadata(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        tool = create_wiki_apply_tool(config)
        result = await _run(
            tool,
            op="update_metadata",
            lookup="entities/alpha",
            status="draft",
        )
        text = result.content[0].text
        assert "entities/alpha.md" in text
        assert "via update_metadata" in text
        page = (tmp_path / "entities" / "alpha.md").read_text(encoding="utf-8")
        assert "status: draft" in page


class TestWikiGet:
    @pytest.mark.asyncio
    async def test_returns_page_body(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        tool = create_wiki_get_tool(config)
        result = await _run(tool, lookup="entities/alpha.md")
        assert "# Alpha" in result.content[0].text
        assert result.details.get("found") is True
        assert result.details.get("path") == "entities/alpha.md"

    @pytest.mark.asyncio
    async def test_respects_line_range(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        tool = create_wiki_get_tool(config)
        result = await _run(
            tool,
            lookup="entities/alpha.md",
            fromLine=2,
            lineCount=1,
        )
        # The body lines are:
        # 1: # Alpha
        # 2: (empty)
        # 3: First line about Alpha.
        # 4: Second line.
        # ``fromLine=2, lineCount=1`` returns
        # the single line at 1-indexed
        # position 2 (the empty line).
        content = result.content[0].text
        assert content == ""

    @pytest.mark.asyncio
    async def test_missing_page_returns_not_found(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        tool = create_wiki_get_tool(config)
        result = await _run(tool, lookup="entities/missing.md")
        text = result.content[0].text
        assert "Wiki page not found" in text
        assert result.details.get("found") is False

    @pytest.mark.asyncio
    async def test_empty_lookup_returns_required(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        tool = create_wiki_get_tool(config)
        result = await _run(tool, lookup="")
        text = result.content[0].text
        assert "lookup is required" in text


class TestFormatWikiToolReportPath:
    def test_relative_when_inside_vault(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        report = str(tmp_path / ".openclaw-wiki" / "lint.md")
        out = format_wiki_tool_report_path(config, report)
        assert not out.startswith(tmp_path.drive + "\\")
        assert out.endswith("lint.md")
        assert ".openclaw-wiki" in out

    def test_absolute_when_outside_vault(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        # Path on a different root → return
        # the input unchanged.
        out = format_wiki_tool_report_path(config, "/tmp/elsewhere/lint.md")
        # On Windows the ``/tmp`` path can't
        # be resolved relative to ``tmp_path``;
        # the helper returns it unchanged.
        assert out == "/tmp/elsewhere/lint.md"


class TestMemoryContext:
    def test_default_context(self) -> None:
        ctx = WikiToolMemoryContext()
        assert ctx.agent_id is None
        assert ctx.agent_session_key is None
        assert ctx.sandboxed is False

    def test_custom_context(self) -> None:
        ctx = WikiToolMemoryContext(
            agent_id="alpha",
            agent_session_key="sess-1",
            sandboxed=True,
        )
        assert ctx.agent_id == "alpha"
        assert ctx.agent_session_key == "sess-1"
        assert ctx.sandboxed is True
