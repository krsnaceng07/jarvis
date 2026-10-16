"""jarvis_learning.datasets.redaction — dedicated secret and credential scrubbing.

Enforces pre-persistence redaction:
raw evidence -> secret/credential detection -> redaction -> sanitized payload -> persistence.
Secrets are never hashed and kept in training text; they are replaced with typed tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RedactionAuditRecord:
    """Non-sensitive record of a redaction event."""

    field_path: str
    redaction_type: str
    replacement_token: str
    match_length: int
    detector_version: str = "v1"


# Canonical high-precision regex patterns for sensitive data
SECRET_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "OPENAI_API_KEY",
        "<API_KEY>",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b", re.IGNORECASE),
    ),
    (
        "ANTHROPIC_API_KEY",
        "<API_KEY>",
        re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b", re.IGNORECASE),
    ),
    (
        "AWS_ACCESS_KEY",
        "<API_KEY>",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
    (
        "BEARER_TOKEN",
        "<ACCESS_TOKEN>",
        re.compile(r"\bBearer\s+[A-Za-z0-9_.\-~+/]{20,}={0,2}\b", re.IGNORECASE),
    ),
    (
        "GITHUB_TOKEN",
        "<ACCESS_TOKEN>",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "PRIVATE_KEY",
        "<PRIVATE_KEY>",
        re.compile(
            r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----"
        ),
    ),
    (
        "COOKIE_AUTH",
        "<COOKIE>",
        re.compile(r"(?:sessionid|auth_token|jwt|token)=[A-Za-z0-9_.\-~+/]{16,}", re.IGNORECASE),
    ),
    (
        "PASSWORD_FIELD",
        "<PASSWORD>",
        re.compile(
            r"(?:password|passwd|secret|api_secret)\s*[:=]\s*['\"][^'\"]{6,}['\"]", re.IGNORECASE
        ),
    ),
]


class SecretScanner:
    """Scans and redacts credentials, secrets, and authorization headers."""

    def __init__(self, patterns: list[tuple[str, str, re.Pattern[str]]] | None = None) -> None:
        self._patterns = patterns or SECRET_PATTERNS

    def redact_text(
        self, text: str, field_path: str = ""
    ) -> tuple[str, list[RedactionAuditRecord]]:
        """Redact known secret patterns from a text string."""
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
                    )
                )

            sanitized = regex.sub(token, sanitized)

        return sanitized, audit_records

    def redact_structure(
        self, data: Any, current_path: str = ""
    ) -> tuple[Any, list[RedactionAuditRecord]]:
        """Recursively scan and redact secrets throughout structured data."""
        if isinstance(data, str):
            return self.redact_text(data, field_path=current_path)

        audit_records: list[RedactionAuditRecord] = []

        if isinstance(data, dict):
            redacted_dict: dict[str, Any] = {}
            for k, v in data.items():
                p = f"{current_path}.{k}" if current_path else str(k)
                rv, records = self.redact_structure(v, current_path=p)
                redacted_dict[k] = rv
                audit_records.extend(records)
            return redacted_dict, audit_records

        if isinstance(data, list):
            redacted_list: list[Any] = []
            for idx, item in enumerate(data):
                p = f"{current_path}[{idx}]"
                rv, records = self.redact_structure(item, current_path=p)
                redacted_list.append(rv)
                audit_records.extend(records)
            return redacted_list, audit_records

        return data, []
