"""Formatting utilities for Google Chat messages and cards."""

from __future__ import annotations

import re
from typing import Any


def markdown_to_google_chat(text: str) -> str:
    """Convert standard markdown to Google Chat markup syntax."""
    if not text:
        return ""

    # Preserve fenced code blocks
    code_blocks: list[str] = []

    def save_block(match: re.Match[str]) -> str:
        code_blocks.append(match.group(0))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r"```[\s\S]*?```", save_block, text)

    # Convert **bold** or __bold__ to *bold*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"__(.+?)__", r"*\1*", text)

    # Convert ~~strikethrough~~ to ~strikethrough~
    text = re.sub(r"~~(.+?)~~", r"~\1~", text)

    # Convert [text](url) to <url|text>
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CB{i}\x00", block)

    return text


def build_google_chat_card(
    title: str,
    subtitle: str | None = None,
    text: str | None = None,
    buttons: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a Google Chat Card v2 payload."""
    widgets: list[dict[str, Any]] = []

    if text:
        widgets.append({"textParagraph": {"text": markdown_to_google_chat(text)}})

    if buttons:
        btn_list: list[dict[str, Any]] = []
        for btn in buttons:
            btn_text = btn.get("text", "Click")
            btn_url = btn.get("url")
            btn_action = btn.get("action")
            if btn_url:
                btn_list.append({"text": btn_text, "onClick": {"openLink": {"url": btn_url}}})
            elif btn_action:
                btn_list.append({"text": btn_text, "onClick": {"action": {"function": btn_action}}})
        if btn_list:
            widgets.append({"buttonList": {"buttons": btn_list}})

    card_content: dict[str, Any] = {
        "header": {"title": title, **({"subtitle": subtitle} if subtitle else {})},
        "sections": [{"widgets": widgets}],
    }

    return {
        "cardsV2": [
            {
                "cardId": f"card-{hash(title) & 0xFFFFFFFF:x}",
                "card": card_content,
            }
        ]
    }
