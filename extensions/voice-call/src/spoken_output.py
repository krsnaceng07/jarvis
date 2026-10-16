"""Defensive spoken output contract formatting and parsing for Voice Call auto-responses."""

from __future__ import annotations

import json
import re
from typing import Any

SPOKEN_OUTPUT_PROMPT_CONTRACT = (
    "\n\n[SPOKEN OUTPUT CONTRACT]\n"
    "You are speaking over a live telephone audio channel. "
    "Respond ONLY with a JSON object in the exact format:\n"
    '{"spoken": "Your spoken reply text here"}\n'
    "Keep replies concise, conversational, and direct. Do not include markdown, bullet points, "
    "or unformatted internal reasoning outside or inside the spoken field."
)


def append_spoken_output_contract(system_prompt: str | None) -> str:
    """Append the telephony spoken output contract to an agent system prompt."""
    base = (system_prompt or "").strip()
    if not base:
        return SPOKEN_OUTPUT_PROMPT_CONTRACT.strip()
    return base + SPOKEN_OUTPUT_PROMPT_CONTRACT


def extract_spoken_output_text(raw_response: str | dict[str, Any] | None) -> str:
    """Defensively extract spoken text from model responses.

    1. Direct dictionary with 'spoken' key.
    2. JSON string or fenced JSON block (```json ... ```).
    3. Inline regex search for "spoken": "...".
    4. Plain text fallback with planning/meta lead-in paragraphs stripped.
    """
    if raw_response is None:
        return ""

    if isinstance(raw_response, dict):
        if "spoken" in raw_response and isinstance(raw_response["spoken"], str):
            return raw_response["spoken"].strip()
        if "text" in raw_response and isinstance(raw_response["text"], str):
            return raw_response["text"].strip()
        return ""

    text = str(raw_response).strip()
    if not text:
        return ""

    # 1. Try parsing whole response as direct JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "spoken" in parsed and isinstance(parsed["spoken"], str):
            return parsed["spoken"].strip()
    except Exception:
        pass

    # 2. Try parsing fenced code blocks ```json ... ``` or ``` ... ```
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced_match:
        try:
            parsed = json.loads(fenced_match.group(1))
            if (
                isinstance(parsed, dict)
                and "spoken" in parsed
                and isinstance(parsed["spoken"], str)
            ):
                return parsed["spoken"].strip()
        except Exception:
            pass

    # 3. Inline JSON regex match for "spoken": "..."
    inline_match = re.search(r'"spoken"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if inline_match:
        try:
            val = json.loads(f'"{inline_match.group(1)}"')
            return str(val).strip()
        except Exception:
            return inline_match.group(1).strip()

    # 4. Fallback to clean plain text: strip planning, thought blocks, or meta lead-in
    cleaned = text
    # Strip <thought>...</thought> tags
    cleaned = re.sub(r"<thought>.*?</thought>", "", cleaned, flags=re.DOTALL)
    # Strip markdown headers or code fences
    cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL)

    # Split paragraphs and filter out obvious meta/planning lead-ins
    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    filtered_paragraphs: list[str] = []

    for p in paragraphs:
        p_lower = p.lower()
        if (
            p_lower.startswith("thinking process:")
            or p_lower.startswith("plan:")
            or p_lower.startswith("let me check")
            or p_lower.startswith("analysis:")
            or p_lower.startswith("internal reasoning:")
        ):
            continue
        filtered_paragraphs.append(p)

    if filtered_paragraphs:
        return " ".join(" ".join(filtered_paragraphs).split())

    return " ".join(cleaned.split())
