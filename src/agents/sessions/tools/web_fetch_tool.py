"""jarvis.agents.sessions.tools.web_fetch_tool — Fast HTTP fetch with markdown extraction.

OpenClaw parity: mirrors OpenClaw's web_fetch tool (src/agents/tools/web-fetch.ts).
Fetches web pages via httpx with redirects, standard user-agent, bounded response bytes,
and readability/markdown conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
import html
import re
from typing import Optional
import urllib.parse

import httpx

from ..extensions.types import AgentToolResult, ToolDefinition

DEFAULT_MAX_BYTES: int = 50_000
MIN_MAX_BYTES: int = 1_000
MAX_MAX_BYTES: int = 10_000_000

DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 (JARVIS/1.0)"
)


@dataclass(frozen=True, slots=True)
class WebFetchResult:
    """Value object capturing the outcome of a web fetch operation."""

    url: str
    status_code: int
    content: str
    title: str | None = None
    content_type: str = ""
    truncated: bool = False
    byte_count: int = 0


def _extract_title(html_raw: str) -> str | None:
    """Extract document title from HTML <title> tag."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html_raw, flags=re.IGNORECASE | re.DOTALL)
    if match:
        title = html.unescape(match.group(1)).strip()
        title = re.sub(r"\s+", " ", title)
        return title[:256] if title else None
    return None


def _html_to_markdown(html_raw: str) -> tuple[str, str | None]:
    """Convert raw HTML into readable plain markdown text."""
    title = _extract_title(html_raw)

    # 1. Remove non-content tags entirely (script, style, noscript, svg, head)
    cleaned = re.sub(
        r"<(?:script|style|noscript|svg|head)\b[^>]*>.*?</(?:script|style|noscript|svg|head)>",
        "",
        html_raw,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 2. Convert preformatted code blocks
    cleaned = re.sub(
        r"<pre\b[^>]*>(?:<code\b[^>]*>)?(.*?)(?:</code>)?</pre>",
        lambda m: f"\n```\n{html.unescape(m.group(1)).strip()}\n```\n",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 3. Convert inline code
    cleaned = re.sub(
        r"<code\b[^>]*>(.*?)</code>",
        lambda m: f" `{html.unescape(m.group(1)).strip()}` ",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 4. Convert headings h1 through h6
    for level in range(1, 7):
        hashes = "#" * level
        cleaned = re.sub(
            rf"<h{level}\b[^>]*>(.*?)</h{level}>",
            lambda m, h=hashes: f"\n\n{h} {m.group(1).strip()}\n\n",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )

    # 5. Convert hyperlinks: <a href="url">text</a> -> [text](url)
    def _link_repl(match: re.Match) -> str:
        tag_attrs = match.group(1)
        text_content = match.group(2).strip()
        href_match = re.search(r'href=["\']([^"\']+)["\']', tag_attrs, flags=re.IGNORECASE)
        if href_match and text_content:
            href = href_match.group(1).strip()
            # Skip javascript: or empty anchor links
            if href.startswith("javascript:") or href == "#":
                return text_content
            return f"[{text_content}]({href})"
        return text_content

    cleaned = re.sub(
        r"<a\b([^>]*)>(.*?)</a>",
        _link_repl,
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 6. Convert strong and emphasis
    cleaned = re.sub(
        r"<(?:strong|b)\b[^>]*>(.*?)</(?:strong|b)>",
        lambda m: f"**{m.group(1).strip()}**",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"<(?:em|i)\b[^>]*>(.*?)</(?:em|i)>",
        lambda m: f"*{m.group(1).strip()}*",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 7. Convert list items
    cleaned = re.sub(
        r"<li\b[^>]*>(.*?)</li>",
        lambda m: f"\n- {m.group(1).strip()}",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 8. Convert block breaks to newlines
    cleaned = re.sub(
        r"<(?:p|div|section|article|blockquote|tr|table|ul|ol|header|footer)\b[^>]*>",
        "\n\n",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<hr\s*/?>", "\n---\n", cleaned, flags=re.IGNORECASE)

    # 9. Strip any remaining HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)

    # 10. Decode entities & clean excessive whitespace
    text = html.unescape(cleaned)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return text, title


def _truncate_bytes(text: str, max_bytes: int) -> tuple[str, bool]:
    """Truncate text so UTF-8 encoded bytes do not exceed max_bytes."""
    raw_bytes = text.encode("utf-8")
    if len(raw_bytes) <= max_bytes:
        return text, False

    notice = (
        f"\n\n[Content truncated: exceeded {max_bytes} bytes limit ({len(raw_bytes)} total bytes)]"
    )
    notice_bytes_len = len(notice.encode("utf-8"))
    keep_bytes_len = max(0, max_bytes - notice_bytes_len)

    # Slice at safe byte length and decode ignoring trailing fragment
    sliced = raw_bytes[:keep_bytes_len].decode("utf-8", errors="ignore")
    return sliced + notice, True


def create_web_fetch_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the ToolDefinition for the web_fetch tool."""
    _ = (cwd, options)

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        _ = (tool_call_id, on_update, ctx)
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")

        raw_url = str(params.get("url", "")).strip()
        if not raw_url:
            raise ValueError("url parameter is required for web_fetch.")

        # Validate URL scheme
        parsed = urllib.parse.urlparse(raw_url)
        if parsed.scheme.lower() not in ("http", "https"):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Invalid URL scheme '{parsed.scheme}': only http and https are supported.",
                    }
                ],
                "details": {"url": raw_url, "error": f"Invalid URL scheme '{parsed.scheme}'"},
            }
        if not parsed.netloc:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Invalid URL: host is missing in '{raw_url}'.",
                    }
                ],
                "details": {"url": raw_url, "error": "Invalid URL: host is missing"},
            }

        # Resolve options
        raw_max_bytes = params.get("max_bytes")
        if raw_max_bytes is not None:
            try:
                max_bytes = max(MIN_MAX_BYTES, min(MAX_MAX_BYTES, int(raw_max_bytes)))
            except (ValueError, TypeError):
                max_bytes = DEFAULT_MAX_BYTES
        else:
            max_bytes = DEFAULT_MAX_BYTES

        extract_text = bool(params.get("extract_text", True))

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(25.0, connect=10.0),
                verify=True,
            ) as client:
                response = await client.get(raw_url, headers=headers)
        except httpx.TimeoutException as exc:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Request timed out fetching '{raw_url}': {exc}",
                    }
                ],
                "details": {"url": raw_url, "error": "timeout"},
            }
        except httpx.RequestError as exc:
            return {
                "content": [{"type": "text", "text": f"Error: Failed to fetch '{raw_url}': {exc}"}],
                "details": {"url": raw_url, "error": str(exc)},
            }

        status_code = response.status_code
        content_type = response.headers.get("content-type", "")
        raw_text = response.text

        title: str | None = None
        if extract_text and ("html" in content_type.lower() or raw_text.strip().startswith("<")):
            extracted, title = _html_to_markdown(raw_text)
            final_content = extracted
        else:
            final_content = raw_text

        final_content, is_truncated = _truncate_bytes(final_content, max_bytes)
        byte_len = len(final_content.encode("utf-8"))

        result_obj = WebFetchResult(
            url=str(response.url),
            status_code=status_code,
            content=final_content,
            title=title,
            content_type=content_type,
            truncated=is_truncated,
            byte_count=byte_len,
        )

        # Output text presentation
        header_lines: list[str] = [f"URL: {result_obj.url}", f"Status: {result_obj.status_code}"]
        if result_obj.title:
            header_lines.append(f"Title: {result_obj.title}")
        header_text = "\n".join(header_lines)

        output_display = (
            f"{header_text}\n\n{result_obj.content}"
            if result_obj.content
            else f"{header_text}\n\n(No content)"
        )

        return {
            "content": [{"type": "text", "text": output_display}],
            "details": {
                "url": result_obj.url,
                "status_code": result_obj.status_code,
                "content_type": result_obj.content_type,
                "title": result_obj.title,
                "bytes": result_obj.byte_count,
                "truncated": result_obj.truncated,
            },
        }

    return {
        "name": "web_fetch",
        "description": (
            "Fast HTTP fetch with readability and markdown extraction. "
            "Fetches web page content over HTTP/HTTPS, extracts article text or converts HTML to markdown, "
            "respects maximum byte limits, and handles redirects automatically."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {
                    "type": "STRING",
                    "description": "The HTTP or HTTPS URL of the web page to fetch.",
                },
                "max_bytes": {
                    "type": "INTEGER",
                    "description": f"Maximum response bytes to return or process (default: {DEFAULT_MAX_BYTES}).",
                },
                "extract_text": {
                    "type": "BOOLEAN",
                    "description": "Whether to extract readable text/markdown from HTML (default: true). If false, raw HTML is returned.",
                },
            },
            "required": ["url"],
        },
        "execute": _execute,
    }


def create_web_fetch_tool(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Convenience alias matching create_write_tool / create_open_path_tool naming."""
    return create_web_fetch_tool_definition(cwd=cwd, options=options)


__all__ = [
    "WebFetchResult",
    "create_web_fetch_tool",
    "create_web_fetch_tool_definition",
]
