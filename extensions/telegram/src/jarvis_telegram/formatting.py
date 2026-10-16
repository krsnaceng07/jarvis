from __future__ import annotations

import html
import re


def escape_html(text: str) -> str:
    """Escape HTML characters to prevent Telegram ParseMode errors."""
    return html.escape(text, quote=False)


def format_for_telegram(text: str) -> str:
    """Format JARVIS markdown into Telegram HTML.

    Telegram supports a limited subset of HTML:
    <b>bold</b>, <strong>bold</strong>
    <i>italic</i>, <em>italic</em>
    <u>underline</u>, <ins>underline</ins>
    <s>strikethrough</s>, <strike>strikethrough</strike>, <del>strikethrough</del>
    <span class="tg-spoiler">spoiler</span>, <tg-spoiler>spoiler</tg-spoiler>
    <b>bold <i>italic bold <s>italic bold strikethrough <span class="tg-spoiler">italic bold strikethrough spoiler</span></s> <u>underline italic bold</u></i> bold</b>
    <a href="http://www.example.com/">inline URL</a>
    <a href="tg://user?id=123456789">inline mention of a user</a>
    <tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>
    <code>inline fixed-width code</code>
    <pre>pre-formatted fixed-width code block</pre>
    <pre><code class="language-python">pre-formatted fixed-width code block written in the Python programming language</code></pre>
    """
    if not text:
        return ""

    # This is a very simplistic conversion for Phase 4.
    # We will escape the HTML first, then restore supported tags.
    # A robust implementation would use a proper markdown parser.

    # 1. Escape HTML to prevent injection
    safe_text = escape_html(text)

    # 2. Convert markdown bold/italic/code
    # Bold: **text** -> <b>text</b>
    safe_text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe_text)
    # Italic: *text* or _text_ -> <i>text</i>
    safe_text = re.sub(r"\b_(.+?)_\b", r"<i>\1</i>", safe_text)
    safe_text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", safe_text)
    # Inline code: `code` -> <code>code</code>
    safe_text = re.sub(r"`(.+?)`", r"<code>\1</code>", safe_text)
    # Pre-formatted blocks: ```...``` -> <pre><code>...</code></pre>
    safe_text = re.sub(
        r"```(?:\w+)?\n?(.*?)\n?```", r"<pre><code>\1</code></pre>", safe_text, flags=re.DOTALL
    )
    # Links: [text](url) -> <a href="url">text</a>
    safe_text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', safe_text)

    return safe_text


def chunk_message(text: str, max_length: int = 4096) -> list[str]:
    """Split message into chunks of max_length to respect Telegram limits."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    # Very naive chunking that doesn't split HTML tags properly.
    # For a robust version, we'd need an HTML-aware splitter.
    current = 0
    while current < len(text):
        chunks.append(text[current : current + max_length])
        current += max_length
    return chunks
