"""src.security.secret_redactor — In-memory and streaming secret masking.

Matches OpenClaw packages/secrets_core/src/redactor.py:
- Redacts API keys, tokens, bearer tokens, private keys, SSH keys
"""

from __future__ import annotations

import re


class SecretRedactor:
    PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
        ("OPENAI_KEY", re.compile(r"sk-[a-zA-Z0-9]{32,}")),
        ("GITHUB_TOKEN", re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}")),
        ("JWT_TOKEN", re.compile(r"ey[A-Za-z0-9-_=]+\.ey[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]*")),
        (
            "PRIVATE_KEY",
            re.compile(
                r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"
            ),
        ),
        ("BEARER_TOKEN", re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\..]{20,}")),
        (
            "API_KEY",
            re.compile(
                r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?"
            ),
        ),
    )

    @classmethod
    def redact(cls, text: str) -> str:
        if not text:
            return text

        redacted = text
        for name, pattern in cls.PATTERNS:

            def _replace(match: re.Match) -> str:
                full = match.group(0)
                if ":" in full or "=" in full:
                    key_part = re.split(r"[:=]", full, maxsplit=1)[0]
                    return f"{key_part}: [REDACTED_{name}]"
                return f"[REDACTED_{name}]"

            redacted = pattern.sub(_replace, redacted)

        return redacted
