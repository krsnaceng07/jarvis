"""Tests for show_widget tool — OpenClaw parity.

Covers:
- wrap.build_widget_document output structure and bridge injection order
- documents.create_canvas_document on-disk lifecycle
- documents.resolve_retention_scope SHA-256 logic
- widget_tool.create_show_widget_tool validation, happy path, cap list
- canvas.__init__ public surface
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

import pytest

# ---------------------------------------------------------------------------
# wrap
# ---------------------------------------------------------------------------

from src.canvas.wrap import (
    WIDGET_THEME_TOKENS,
    build_widget_document,
)


class TestBuildWidgetDocument:
    def test_doctype_and_charset(self):
        html = build_widget_document("T", "<p>hi</p>")
        assert html.startswith("<!doctype html>")
        assert 'charset="utf-8"' in html

    def test_title_escaped(self):
        html = build_widget_document('<script>alert(1)</script>', "<p/>")
        assert "&lt;script&gt;" in html
        assert "<script>alert" not in html

    def test_csp_injected(self):
        html = build_widget_document("T", "<p/>")
        assert "Content-Security-Policy" in html
        assert "default-src 'none'" in html

    def test_base_styles_present(self):
        html = build_widget_document("T", "<p/>")
        # The baked palette root block must be present
        assert "--surface:" in html
        assert "--accent-fill:" in html

    def test_prompt_bridge_present(self):
        html = build_widget_document("T", "<p/>")
        assert "openclaw:widget-prompt-offer" in html
        assert "sendPrompt" in html

    def test_theme_bridge_present(self):
        html = build_widget_document("T", "<p/>")
        assert "openclaw:widget-theme" in html
        # All theme tokens must be embedded in the bridge
        for token in WIDGET_THEME_TOKENS:
            assert token in html

    def test_snapshot_bridge_present(self):
        html = build_widget_document("T", "<p/>")
        assert "openclaw:widget-snapshot-request" in html
        assert "openclaw:widget-snapshot" in html

    def test_size_reporter_present(self):
        html = build_widget_document("T", "<p/>")
        assert "openclaw:widget-size" in html
        assert "ResizeObserver" in html

    def test_widget_code_included(self):
        code = '<div id="unique-test-id">Hello</div>'
        html = build_widget_document("T", code)
        assert code in html

    def test_svg_gets_svg_widget_class(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
        html = build_widget_document("T", svg)
        assert 'class="svg-widget"' in html

    def test_html_no_svg_class(self):
        html = build_widget_document("T", "<div/>")
        assert 'class="svg-widget"' not in html

    def test_bridge_order_matches_openclaw(self):
        """Prompt → theme → snapshot → widget_code → size reporter."""
        html = build_widget_document("T", "<p id='wc'/>")
        pos_prompt = html.index("openclaw:widget-prompt-offer")
        pos_theme = html.index("openclaw:widget-theme")
        pos_snapshot = html.index("openclaw:widget-snapshot-request")
        pos_widget = html.index("<p id='wc'/>")
        pos_size = html.index("openclaw:widget-size")
        assert pos_prompt < pos_theme < pos_snapshot < pos_widget < pos_size

    def test_theme_tokens_list_completeness(self):
        required = {
            "surface", "card", "elevated", "text", "text-strong", "muted",
            "border", "border-strong", "accent", "accent-fill", "accent-fg",
            "ok", "warn", "danger", "info", "radius", "font-body", "font-mono",
        }
        assert required == set(WIDGET_THEME_TOKENS)


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------

from src.canvas.documents import (
    CanvasDocumentCreateInput,
    CanvasDocumentEntrypointHtml,
    create_canvas_document,
    resolve_retention_scope,
)


class TestResolveRetentionScope:
    def test_session_scope(self):
        scope = resolve_retention_scope("ses-123", None)
        expected = hashlib.sha256(b"session:ses-123").hexdigest()
        assert scope == expected

    def test_agent_scope(self):
        scope = resolve_retention_scope(None, "agt-456")
        expected = hashlib.sha256(b"agent:agt-456").hexdigest()
        assert scope == expected

    def test_default_agent_scope(self):
        scope = resolve_retention_scope(None, None)
        expected = hashlib.sha256(b"agent:default").hexdigest()
        assert scope == expected

    def test_session_wins_over_agent(self):
        scope = resolve_retention_scope("s", "a")
        expected = hashlib.sha256(b"session:s").hexdigest()
        assert scope == expected


class TestCreateCanvasDocument:
    def test_creates_manifest_and_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = CanvasDocumentCreateInput(
                kind="html_bundle",
                title="Test Widget",
                entrypoint=CanvasDocumentEntrypointHtml(type="html", value="<p>hi</p>"),
                surface="assistant_message",
                csp_sandbox="scripts",
            )
            manifest = create_canvas_document(inp, state_dir=tmpdir)
            assert manifest.id
            assert manifest.kind == "html_bundle"
            assert manifest.title == "Test Widget"
            assert manifest.surface == "assistant_message"
            assert manifest.csp_sandbox == "scripts"
            assert manifest.local_entrypoint == "index.html"
            assert manifest.entry_url.endswith("index.html")

    def test_index_html_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = CanvasDocumentCreateInput(
                kind="html_bundle",
                entrypoint=CanvasDocumentEntrypointHtml(type="html", value="<b>bold</b>"),
            )
            manifest = create_canvas_document(inp, state_dir=tmpdir)
            docs_dir = os.path.join(tmpdir, "canvas", "documents")
            index_path = os.path.join(docs_dir, manifest.id, "index.html")
            assert os.path.isfile(index_path)
            with open(index_path) as f:
                assert "<b>bold</b>" in f.read()

    def test_manifest_json_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = CanvasDocumentCreateInput(
                kind="html_bundle",
                title="M",
                entrypoint=CanvasDocumentEntrypointHtml(type="html", value="<p/>"),
            )
            manifest = create_canvas_document(inp, state_dir=tmpdir)
            docs_dir = os.path.join(tmpdir, "canvas", "documents")
            manifest_path = os.path.join(docs_dir, manifest.id, "manifest.json")
            assert os.path.isfile(manifest_path)
            with open(manifest_path) as f:
                data = json.load(f)
            assert data["id"] == manifest.id
            assert data["kind"] == "html_bundle"

    def test_pruning_removes_oldest_when_over_cap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scope = "test-scope-prune"
            # Create 3 docs with cap of 2
            for i in range(3):
                inp = CanvasDocumentCreateInput(
                    kind="html_bundle",
                    entrypoint=CanvasDocumentEntrypointHtml(type="html", value=f"<p>{i}</p>"),
                    retention_scope=scope,
                )
                create_canvas_document(inp, state_dir=tmpdir, max_documents_per_scope=2)
            docs_dir = os.path.join(tmpdir, "canvas", "documents")
            remaining = [
                d for d in os.listdir(docs_dir)
                if os.path.isdir(os.path.join(docs_dir, d))
            ]
            assert len(remaining) == 2

    def test_entry_url_contains_document_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = CanvasDocumentCreateInput(
                kind="html_bundle",
                entrypoint=CanvasDocumentEntrypointHtml(type="html", value="<p/>"),
            )
            manifest = create_canvas_document(inp, state_dir=tmpdir)
            assert manifest.id in manifest.entry_url


# ---------------------------------------------------------------------------
# widget_tool
# ---------------------------------------------------------------------------

from src.canvas.widget_tool import (
    SHOW_WIDGET_REQUIRED_CLIENT_CAPS,
    WIDGET_CODE_MAX_CHARS,
    WIDGET_MAX_PER_SCOPE,
    WidgetHtmlInputError,
    create_show_widget_tool,
)

pytestmark = pytest.mark.asyncio


class TestShowWidgetToolDefinition:
    def test_name(self):
        tool = create_show_widget_tool()
        assert tool["name"] == "show_widget"

    def test_label(self):
        tool = create_show_widget_tool()
        assert tool["label"] == "Show Widget"

    def test_required_client_caps(self):
        tool = create_show_widget_tool()
        assert tool["required_client_caps"] == ["inline-widgets"]

    def test_required_params(self):
        tool = create_show_widget_tool()
        required = tool["parameters"]["required"]
        assert "title" in required
        assert "widget_code" in required

    def test_constants_match_openclaw(self):
        assert WIDGET_CODE_MAX_CHARS == 262_144
        assert WIDGET_MAX_PER_SCOPE == 32
        assert SHOW_WIDGET_REQUIRED_CLIENT_CAPS == ["inline-widgets"]


class TestShowWidgetToolValidation:
    async def test_empty_widget_code_raises(self):
        tool = create_show_widget_tool()
        with pytest.raises(WidgetHtmlInputError, match="widget_code required"):
            await tool["execute"]("tc-1", {"title": "T", "widget_code": "   "}, None, None)

    async def test_empty_title_raises(self):
        tool = create_show_widget_tool()
        with pytest.raises(WidgetHtmlInputError, match="title required"):
            await tool["execute"]("tc-1", {"title": "", "widget_code": "<p/>"}, None, None)

    async def test_oversized_widget_code_raises(self):
        tool = create_show_widget_tool()
        big = "x" * (WIDGET_CODE_MAX_CHARS + 1)
        with pytest.raises(WidgetHtmlInputError, match="exceeds maximum size"):
            await tool["execute"]("tc-1", {"title": "T", "widget_code": big}, None, None)


class TestShowWidgetToolHappyPath:
    async def test_returns_canvas_kind(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = create_show_widget_tool(state_dir=tmpdir)
            result = await tool["execute"](
                "tc-2",
                {"title": "My Widget", "widget_code": "<p>hello</p>"},
                None,
                None,
            )
            data = json.loads(result["content"][0]["text"])
            assert data["kind"] == "canvas"

    async def test_presentation_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = create_show_widget_tool(state_dir=tmpdir)
            result = await tool["execute"](
                "tc-3",
                {"title": "Widget X", "widget_code": "<div/>"},
                None,
                None,
            )
            data = json.loads(result["content"][0]["text"])
            assert data["presentation"]["target"] == "assistant_message"
            assert data["presentation"]["title"] == "Widget X"
            assert data["presentation"]["sandbox"] == "scripts"

    async def test_view_has_id_and_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = create_show_widget_tool(state_dir=tmpdir)
            result = await tool["execute"](
                "tc-4",
                {"title": "W", "widget_code": "<span/>"},
                None,
                None,
            )
            data = json.loads(result["content"][0]["text"])
            assert "id" in data["view"]
            assert "url" in data["view"]
            assert data["view"]["url"].endswith("index.html")

    async def test_widget_code_wrapped_in_shell(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = create_show_widget_tool(state_dir=tmpdir)
            result = await tool["execute"](
                "tc-5",
                {"title": "T", "widget_code": '<span id="my-unique-marker"/>'},
                None,
                None,
            )
            data = json.loads(result["content"][0]["text"])
            doc_id = data["view"]["id"]
            docs_dir = os.path.join(tmpdir, "canvas", "documents")
            index_path = os.path.join(docs_dir, doc_id, "index.html")
            with open(index_path) as f:
                content = f.read()
            assert "my-unique-marker" in content
            assert "openclaw:widget-theme" in content
            assert "openclaw:widget-size" in content

    async def test_session_id_used_for_retention_scope(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = create_show_widget_tool(session_id="ses-abc", state_dir=tmpdir)
            result = await tool["execute"](
                "tc-6",
                {"title": "T", "widget_code": "<p/>"},
                None,
                None,
            )
            data = json.loads(result["content"][0]["text"])
            doc_id = data["view"]["id"]
            docs_dir = os.path.join(tmpdir, "canvas", "documents")
            manifest_path = os.path.join(docs_dir, doc_id, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)
            expected_scope = hashlib.sha256(b"session:ses-abc").hexdigest()
            assert manifest.get("retentionScope") == expected_scope
