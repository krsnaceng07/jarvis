"""Web Readability content extraction module.

OpenClaw parity: mirrors the OpenClaw ``web-readability`` extractor
behavior and safeguards.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

READABILITY_MAX_HTML_CHARS = 1_000_000
READABILITY_MAX_ESTIMATED_NESTING_DEPTH = 3_000

HTML_VOID_TAGS: frozenset[str] = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

INVISIBLE_UNICODE_PATTERN = re.compile(
    r"[\u200B-\u200D\uFEFF\u200E\u200F\u202A-\u202E\u2060-\u206F]"
)


def exceeds_estimated_html_nesting_depth(
    html: str,
    max_depth: int = READABILITY_MAX_ESTIMATED_NESTING_DEPTH,
) -> bool:
    """Check if HTML exceeds estimated DOM nesting depth."""
    depth = 0
    length = len(html)
    i = html.find("<")
    while i >= 0:
        if i + 1 < length:
            next_code = ord(html[i + 1])
            if next_code == 33 or next_code == 63:  # ! or ?
                i = html.find("<", i + 1)
                continue

        j = i + 1
        closing = False
        if j < length and html[j] == "/":
            closing = True
            j += 1

        while j < length and html[j] <= " ":
            j += 1

        name_start = j
        while j < length:
            c = html[j]
            is_name_char = (
                ("A" <= c <= "Z") or ("a" <= c <= "z") or ("0" <= c <= "9") or c == ":" or c == "-"
            )
            if not is_name_char:
                break
            j += 1

        if j == name_start:
            i = html.find("<", i + 1)
            continue

        if closing:
            if depth > 0:
                depth -= 1
            i = html.find("<", i + 1)
            continue

        tag_name = html[name_start:j].lower()
        if tag_name in HTML_VOID_TAGS:
            i = html.find("<", i + 1)
            continue

        self_closing = False
        limit = min(length, j + 200)
        for k in range(j, limit):
            if html[k] == ">":
                self_closing = k > 0 and html[k - 1] == "/"
                break

        if self_closing:
            i = html.find("<", i + 1)
            continue

        depth += 1
        if depth > max_depth:
            return True

        i = html.find("<", i + 1)

    return False


def strip_invisible_unicode(text: str) -> str:
    """Remove invisible/zero-width unicode characters."""
    return INVISIBLE_UNICODE_PATTERN.sub("", text)


def normalize_whitespace(text: str) -> str:
    """Normalize repeated whitespace while keeping paragraph structure."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    non_empty: list[str] = []
    consecutive_empty = 0
    for line in lines:
        if line:
            non_empty.append(line)
            consecutive_empty = 0
        else:
            if consecutive_empty == 0 and non_empty:
                non_empty.append("")
            consecutive_empty += 1
    return "\n".join(non_empty).strip()


@dataclass(frozen=True, slots=True)
class WebContentExtractionRequest:
    """Request payload for web readability extraction."""

    html: str
    url: str
    extract_mode: Literal["text", "markdown"] = "text"


@dataclass(frozen=True, slots=True)
class WebContentExtractionResult:
    """Result from web readability extraction."""

    text: str
    title: str | None = None


def _node_to_markdown(node: Tag | NavigableString, base_url: str | None) -> str:
    """Recursively convert a BeautifulSoup node to clean markdown."""
    if isinstance(node, NavigableString):
        return str(node)

    if not isinstance(node, Tag):
        return ""

    tag_name = node.name.lower()
    if tag_name in ("script", "style", "nav", "footer", "noscript", "svg"):
        return ""

    if tag_name == "a":
        href = node.get("href", "")
        if isinstance(href, list):
            href = href[0] if href else ""
        resolved_url = urljoin(base_url, href) if base_url and href else href
        child_text = "".join(_node_to_markdown(child, base_url) for child in node.children).strip()
        if child_text and resolved_url:
            return f"[{child_text}]({resolved_url})"
        return child_text

    if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag_name[1])
        heading_text = "".join(
            _node_to_markdown(child, base_url) for child in node.children
        ).strip()
        return f"\n\n{'#' * level} {heading_text}\n\n"

    if tag_name == "p":
        p_text = "".join(_node_to_markdown(child, base_url) for child in node.children).strip()
        return f"\n\n{p_text}\n\n"

    if tag_name in ("ul", "ol"):
        items: list[str] = []
        for child in node.find_all("li", recursive=False):
            li_text = "".join(_node_to_markdown(c, base_url) for c in child.children).strip()
            if li_text:
                items.append(f"- {li_text}")
        return "\n\n" + "\n".join(items) + "\n\n"

    # Default: concatenate children
    return "".join(_node_to_markdown(child, base_url) for child in node.children)


class ReadabilityWebContentExtractor:
    """Extracts readable article text/markdown from raw HTML."""

    id: str = "readability"
    label: str = "Readability"
    auto_detect_order: int = 10

    async def extract(
        self,
        request: WebContentExtractionRequest,
    ) -> WebContentExtractionResult | None:
        """Extract article content from HTML request."""
        clean_html = request.html
        if len(clean_html) > READABILITY_MAX_HTML_CHARS or exceeds_estimated_html_nesting_depth(
            clean_html, READABILITY_MAX_ESTIMATED_NESTING_DEPTH
        ):
            return None

        try:
            soup = BeautifulSoup(clean_html, "html.parser")
            title: str | None = None
            if soup.title and soup.title.string:
                title = soup.title.string.strip()

            # Find main article element if present
            article_elem = (
                soup.find("article")
                or soup.find("main")
                or soup.find(id=re.compile(r"article|content|main", re.I))
                or soup.find(class_=re.compile(r"article|content|main", re.I))
                or soup.body
                or soup
            )

            if request.extract_mode == "text":
                # Strip non-content elements
                for tag in article_elem.find_all(["nav", "footer", "script", "style", "noscript"]):
                    tag.decompose()
                raw_text = article_elem.get_text(separator=" ")
                normalized = normalize_whitespace(raw_text)
                final_text = strip_invisible_unicode(normalized)
            else:
                rendered_md = _node_to_markdown(article_elem, request.url)
                normalized = normalize_whitespace(rendered_md)
                final_text = strip_invisible_unicode(normalized)

            if not final_text:
                return None

            return WebContentExtractionResult(
                text=final_text,
                title=title,
            )
        except Exception:
            return None


def create_readability_web_content_extractor() -> ReadabilityWebContentExtractor:
    """Factory creating a ReadabilityWebContentExtractor instance."""
    return ReadabilityWebContentExtractor()
