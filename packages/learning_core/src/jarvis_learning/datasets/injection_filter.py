"""jarvis_learning.datasets.injection_filter — prompt injection vs quoted content analyzer.

Distinguishes instruction hierarchy violations from legitimate quoted task content.
A sample is rejected if untrusted external content or unquoted user commands attempt
to hijack system instructions, while preserving valid tasks that discuss or quote such phrases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ContentOrigin(StrEnum):
    USER_INSTRUCTION = "user_instruction"
    SYSTEM_INSTRUCTION = "system_instruction"
    TOOL_OUTPUT = "tool_output"
    QUOTED_CONTENT = "quoted_content"


@dataclass(frozen=True, slots=True)
class InjectionScanResult:
    is_safe: bool
    violation_type: str = ""
    evidence_snippet: str = ""
    is_quoted: bool = False


# High-confidence injection patterns
INJECTION_OVERRIDE_PATTERNS = [
    re.compile(
        r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+instructions",
        re.IGNORECASE,
    ),
    re.compile(r"you\s+are\s+now\s+(?:an?\s+unrestricted|a\s+new|dan|jailbroken)", re.IGNORECASE),
    re.compile(r"(?:new|override)\s+system\s+(?:prompt|instructions|directive)", re.IGNORECASE),
    re.compile(r"<\s*\|\s*im_start\s*\|\s*>\s*system", re.IGNORECASE),
]

# Patterns indicating quoted or analytical context
QUOTED_WRAPPERS = [
    re.compile(r"['\"](?:[^'\"]*?)['\"]"),
    re.compile(r"`(?:[^`]*?)`"),
    re.compile(r"(?:contains?|searched?|quoted?|titled?|find)\s*:\s*['\"].*?['\"]", re.IGNORECASE),
]


class InjectionFilter:
    """Evaluates whether text contains an active prompt injection attack."""

    def scan_content(
        self, text: str, origin: ContentOrigin = ContentOrigin.USER_INSTRUCTION
    ) -> InjectionScanResult:
        if not text or not isinstance(text, str):
            return InjectionScanResult(is_safe=True)

        for pattern in INJECTION_OVERRIDE_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue

            start, end = match.span()
            snippet = text[max(0, start - 20) : min(len(text), end + 20)]

            # Check if this occurrence is quoted
            is_quoted = self._is_within_quotes(text, start, end)

            # In tool output or untrusted content, unquoted injection is an immediate rejection
            if origin in (ContentOrigin.TOOL_OUTPUT, ContentOrigin.USER_INSTRUCTION):
                if not is_quoted:
                    return InjectionScanResult(
                        is_safe=False,
                        violation_type="UNQUOTED_INSTRUCTION_HIERARCHY_VIOLATION",
                        evidence_snippet=snippet,
                        is_quoted=False,
                    )

        return InjectionScanResult(is_safe=True)

    def scan_sample(self, input_data: dict[str, Any]) -> InjectionScanResult:
        """Scan all input fields of a dataset candidate."""
        user_input = input_data.get("user_input", "")
        if isinstance(user_input, str):
            res = self.scan_content(user_input, origin=ContentOrigin.USER_INSTRUCTION)
            if not res.is_safe:
                return res

        tool_output = input_data.get("tool_result", "")
        if isinstance(tool_output, str):
            res = self.scan_content(tool_output, origin=ContentOrigin.TOOL_OUTPUT)
            if not res.is_safe:
                return res

        return InjectionScanResult(is_safe=True)

    @staticmethod
    def _is_within_quotes(text: str, start: int, end: int) -> bool:
        """Check if character span is enclosed in quotation marks or backticks."""
        # Simple heuristic: count quotes before start
        single_quotes = text[:start].count("'")
        double_quotes = text[:start].count('"')
        backticks = text[:start].count("`")

        # Odd count before and at least one after implies enclosed
        in_single = (single_quotes % 2 == 1) and ("'" in text[end:])
        in_double = (double_quotes % 2 == 1) and ('"' in text[end:])
        in_backtick = (backticks % 2 == 1) and ("`" in text[end:])

        return in_single or in_double or in_backtick
