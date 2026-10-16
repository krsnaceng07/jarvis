"""Tests for web-readability extractor and plugin."""

from __future__ import annotations

import pytest

from extensions.web_readability.src.extractor import (
    WebContentExtractionRequest,
    create_readability_web_content_extractor,
    exceeds_estimated_html_nesting_depth,
    normalize_whitespace,
    strip_invisible_unicode,
)

SAMPLE_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Example Article</title>
  </head>
  <body>
    <nav>
      <ul>
        <li><a href="/home">Home</a></li>
        <li><a href="/about">About</a></li>
      </ul>
    </nav>
    <main>
      <article>
        <h1>Example Article</h1>
        <p>Main content starts here with enough words to satisfy readability.</p>
        <p>Second paragraph for a bit more signal.</p>
        <p><a href="../next">Continue reading</a></p>
      </article>
    </main>
    <footer>Footer text</footer>
  </body>
</html>"""


@pytest.mark.asyncio
async def test_extracts_readable_text() -> None:
    """Test extracting plain text from HTML."""
    extractor = create_readability_web_content_extractor()
    result = await extractor.extract(
        WebContentExtractionRequest(
            html=SAMPLE_HTML,
            url="https://example.com/article",
            extract_mode="text",
        )
    )
    assert result is not None
    assert "Main content starts here" in result.text
    assert result.title == "Example Article"


@pytest.mark.asyncio
async def test_extracts_readable_markdown() -> None:
    """Test extracting markdown and resolving relative links."""
    extractor = create_readability_web_content_extractor()
    result = await extractor.extract(
        WebContentExtractionRequest(
            html=SAMPLE_HTML,
            url="https://example.com/article",
            extract_mode="markdown",
        )
    )
    assert result is not None
    assert "Main content starts here" in result.text
    assert "[Continue reading](https://example.com/next)" in result.text
    assert result.title == "Example Article"


@pytest.mark.asyncio
async def test_does_not_count_void_tags_toward_nesting_limit() -> None:
    """Void tags like <br> should not contribute to estimated depth."""
    extractor = create_readability_web_content_extractor()
    html = SAMPLE_HTML.replace("<article>", f"<article>{'<BR>' * 3100}")
    result = await extractor.extract(
        WebContentExtractionRequest(
            html=html,
            url="https://example.com/article",
            extract_mode="markdown",
        )
    )
    assert result is not None
    assert "Main content starts here" in result.text


@pytest.mark.asyncio
async def test_rejects_excessively_nested_html() -> None:
    """Nesting depth above limit causes early rejection returning None."""
    extractor = create_readability_web_content_extractor()
    html = f"{'<section>' * 3001}{SAMPLE_HTML}{'</section>' * 3001}"
    result = await extractor.extract(
        WebContentExtractionRequest(
            html=html,
            url="https://example.com/article",
            extract_mode="text",
        )
    )
    assert result is None


def test_depth_checker_primitives() -> None:
    """Test boundary cases for depth checking."""
    assert not exceeds_estimated_html_nesting_depth("<p>Hello</p>", 10)
    assert exceeds_estimated_html_nesting_depth("<div><div><div></div></div></div>", 2)
    assert not exceeds_estimated_html_nesting_depth("<div><img /><hr /><br /></div>", 1)


def test_unicode_and_whitespace_helpers() -> None:
    """Test unicode stripping and whitespace cleaning."""
    raw = "Hello\u200b \ufeffWorld   with \n\n\n extra   spaces."
    cleaned = strip_invisible_unicode(raw)
    assert "\u200b" not in cleaned
    assert "\ufeff" not in cleaned
    normalized = normalize_whitespace(cleaned)
    assert normalized == "Hello World with\n\nextra spaces."
