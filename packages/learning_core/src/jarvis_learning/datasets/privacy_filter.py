r"""jarvis_learning.datasets.privacy_filter — PII and private environment scrubber.

Normalizes:
- User home and local absolute paths (C:\Users\<name>, /home/<name>, /Users/<name>)
- Personal Identifiable Information (Emails, Phone numbers, IP addresses)
- Replaces with typed semantic tokens (<PRIVATE_PATH>, <EMAIL>, <PHONE>, <IP_ADDRESS>).
"""

from __future__ import annotations

import re
from typing import Any

from .redaction import RedactionAuditRecord


PII_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "EMAIL_ADDRESS",
        "<EMAIL>",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        "PHONE_NUMBER",
        "<PHONE>",
        re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    ),
    (
        "IPV4_ADDRESS",
        "<IP_ADDRESS>",
        re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"),
    ),
    (
        "WINDOWS_USER_PATH",
        "<PRIVATE_PATH>",
        re.compile(r"[a-zA-Z]:\\Users\\[^\s\\\"']+", re.IGNORECASE),
    ),
    (
        "UNIX_USER_PATH",
        "<PRIVATE_PATH>",
        re.compile(r"/(?:home|Users)/[^\s/\"']+"),
    ),
]


class PrivacyFilter:
    """Detects and redacts PII and private environment paths."""

    def __init__(self, patterns: list[tuple[str, str, re.Pattern[str]]] | None = None) -> None:
        self._patterns = patterns or PII_PATTERNS

    def scrub_text(self, text: str, field_path: str = "") -> tuple[str, list[RedactionAuditRecord]]:
        """Scrub PII and paths from a text string."""
        if not text or not isinstance(text, str):
            return text, []

        audit_records: list[RedactionAuditRecord] = []
        sanitized = text

        for pattern_name, token, regex in self._patterns:
            matches = list(regex.finditer(sanitized))
            if not matches:
                continue

            for match in reversed(matches):
                start, end = match.span()
                audit_records.append(
                    RedactionAuditRecord(
                        field_path=field_path,
                        redaction_type=pattern_name,
                        replacement_token=token,
                        match_length=end - start,
                        detector_version="privacy_v1",
                    )
                )

            sanitized = regex.sub(token, sanitized)

        return sanitized, audit_records

    def scrub_structure(
        self, data: Any, current_path: str = ""
    ) -> tuple[Any, list[RedactionAuditRecord]]:
        """Recursively scrub PII across nested structures."""
        if isinstance(data, str):
            return self.scrub_text(data, field_path=current_path)

        audit_records: list[RedactionAuditRecord] = []

        if isinstance(data, dict):
            scrubbed_dict: dict[str, Any] = {}
            for k, v in data.items():
                p = f"{current_path}.{k}" if current_path else str(k)
                rv, records = self.scrub_structure(v, current_path=p)
                scrubbed_dict[k] = rv
                audit_records.extend(records)
            return scrubbed_dict, audit_records

        if isinstance(data, list):
            scrubbed_list: list[Any] = []
            for idx, item in enumerate(data):
                p = f"{current_path}[{idx}]"
                rv, records = self.scrub_structure(item, current_path=p)
                scrubbed_list.append(rv)
                audit_records.extend(records)
            return scrubbed_list, audit_records

        return data, []
