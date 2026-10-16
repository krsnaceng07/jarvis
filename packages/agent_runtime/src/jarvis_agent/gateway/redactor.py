"""Sensitive output redaction for client-facing telemetry in Track 3.4.

Enforces Invariant T34-22: Authoritative evidence in EventStore remains intact;
telemetry chunks projected to client transports have credentials and secrets redacted.
"""

from __future__ import annotations

import re

# Compiled regex patterns detecting secrets, bearer tokens, private keys, and passwords
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?i)(api[_-]?key|secret|token|password|passwd|auth)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"
    ),
    re.compile(r"Bearer\s+([a-zA-Z0-9_\-\.]{16,})", re.IGNORECASE),
    re.compile(
        r"-----BEGIN [A-Z ]+PRIVATE KEY-----[^-]+-----END [A-Z ]+PRIVATE KEY-----", re.DOTALL
    ),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub PAT
    re.compile(r"xox[baprs]-[a-zA-Z0-9\-]{10,}"),  # Slack token
]


def redact_sensitive_text(text: str) -> str:
    """Scrub common secrets, private keys, and passwords from streaming text."""
    if not text:
        return text

    redacted = text
    for pat in _SECRET_PATTERNS:
        # If pattern has capturing groups, redact the sensitive group
        if pat.groups > 0:

            def _replace(match: re.Match[str]) -> str:
                full = match.group(0)
                # Replace the last group (the secret value)
                val = match.group(pat.groups)
                return full.replace(val, "[REDACTED_SECRET]")

            redacted = pat.sub(_replace, redacted)
        else:
            redacted = pat.sub("[REDACTED_SECRET]", redacted)

    return redacted


__all__ = ["redact_sensitive_text"]
