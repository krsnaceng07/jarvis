"""jarvis_learning.datasets.cleaner — multi-layer secret/PII/injection cleaning.

Three layers:
1. Regex patterns — API keys, tokens, passwords, PII
2. Structured detectors — .env format, private keys, JWTs, cloud credentials
3. Entropy-based — high-entropy tokens that look like secrets

Preserves ``[REDACTED_*]`` placeholders so training data remains
structurally useful while preventing leakage.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Redaction:
    """One redaction applied to text."""

    original_span: tuple[int, int]
    redaction_type: str
    placeholder: str


@dataclass(frozen=True, slots=True)
class CleaningResult:
    """Result of cleaning a text sample."""

    cleaned_text: str
    passed: bool
    redactions: tuple[Redaction, ...]

    @property
    def redaction_count(self) -> int:
        return len(self.redactions)


# ── Pattern definitions ──────────────────────────────────────

# Layer 1: Regex patterns
_API_KEY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "api_key",
        re.compile(
            r"""(?:api[_-]?key|apikey|api[_-]?token|access[_-]?token|"""
            r"""auth[_-]?token|secret[_-]?key|private[_-]?key)\s*"""
            r"""[=:]\s*["']?([A-Za-z0-9_\-/.]{16,})["']?""",
            re.IGNORECASE,
        ),
    ),
    (
        "bearer_token",
        re.compile(
            r"""Bearer\s+[A-Za-z0-9_\-/.+]{20,}""",
            re.IGNORECASE,
        ),
    ),
    ("sk_key", re.compile(r"""sk[-_][A-Za-z0-9]{20,}""")),
    ("aws_key", re.compile(r"""AKIA[A-Z0-9]{16}""")),
    ("gcp_key", re.compile(r"""AIza[A-Za-z0-9_\-]{35}""")),
]

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"""[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}""")),
    ("phone", re.compile(r"""(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}""")),
    ("ssn", re.compile(r"""\b\d{3}-\d{2}-\d{4}\b""")),
]

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "prompt_injection",
        re.compile(
            r"""(?:ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|"""
            r"""disregard\s+your\s+instructions|"""
            r"""you\s+are\s+now\s+|"""
            r"""new\s+system\s+prompt|"""
            r"""override\s+system|"""
            r"""jailbreak)""",
            re.IGNORECASE,
        ),
    ),
]

# Layer 2: Structured detectors
_STRUCTURED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("env_config", re.compile(r"""^[A-Z_]{3,}=\S+""", re.MULTILINE)),
    ("private_key", re.compile(r"""-----BEGIN\s+(?:RSA\s+)?(?:PRIVATE|ENCRYPTED)\s+KEY-----""")),
    (
        "jwt",
        re.compile(r"""eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_\-+/=]{10,}"""),
    ),
    ("azure_key", re.compile(r"""[A-Za-z0-9+/]{86}==""")),
    (
        "connection_string",
        re.compile(
            r"""(?:mongodb|postgres|mysql|redis|amqp)://[^\s]+""",
            re.IGNORECASE,
        ),
    ),
]

# Placeholder map
_PLACEHOLDERS: dict[str, str] = {
    "api_key": "[REDACTED_API_KEY]",
    "bearer_token": "[REDACTED_BEARER_TOKEN]",
    "sk_key": "[REDACTED_SECRET_KEY]",
    "aws_key": "[REDACTED_AWS_KEY]",
    "gcp_key": "[REDACTED_GCP_KEY]",
    "email": "[REDACTED_EMAIL]",
    "phone": "[REDACTED_PHONE]",
    "ssn": "[REDACTED_SSN]",
    "prompt_injection": "[REDACTED_INJECTION]",
    "env_config": "[REDACTED_ENV_CONFIG]",
    "private_key": "[REDACTED_PRIVATE_KEY]",
    "jwt": "[REDACTED_JWT]",
    "azure_key": "[REDACTED_AZURE_KEY]",
    "connection_string": "[REDACTED_CONNECTION_STRING]",
    "high_entropy": "[REDACTED_HIGH_ENTROPY_TOKEN]",
}


def _token_entropy(token: str) -> float:
    """Shannon entropy of a string in bits per character."""
    if not token:
        return 0.0
    freq = Counter(token)
    length = len(token)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


class DatasetCleaner:
    """Multi-layer cleaning for training data.

    Layer 1: Regex patterns (API keys, PII, injection)
    Layer 2: Structured detectors (env vars, private keys, JWTs)
    Layer 3: Entropy-based detection (high-entropy tokens)
    """

    def __init__(
        self,
        *,
        entropy_threshold: float = 4.5,
        min_token_length: int = 20,
    ) -> None:
        self._entropy_threshold = entropy_threshold
        self._min_token_length = min_token_length

    def clean(self, text: str) -> CleaningResult:
        """Clean text, replacing detected secrets with placeholders.

        Returns ``CleaningResult`` with cleaned text, pass/fail, and
        list of redactions applied.
        """
        if not text:
            return CleaningResult(cleaned_text="", passed=True, redactions=())

        redactions: list[Redaction] = []
        cleaned = text

        # Layer 1: Regex patterns
        for name, pattern in _API_KEY_PATTERNS + _PII_PATTERNS + _INJECTION_PATTERNS:
            cleaned, layer_redactions = self._apply_pattern(cleaned, name, pattern)
            redactions.extend(layer_redactions)

        # Layer 2: Structured detectors
        for name, pattern in _STRUCTURED_PATTERNS:
            cleaned, layer_redactions = self._apply_pattern(cleaned, name, pattern)
            redactions.extend(layer_redactions)

        # Layer 3: Entropy-based detection
        cleaned, entropy_redactions = self._entropy_scan(cleaned)
        redactions.extend(entropy_redactions)

        passed = len(redactions) == 0
        return CleaningResult(
            cleaned_text=cleaned,
            passed=passed,
            redactions=tuple(redactions),
        )

    def is_safe(self, text: str) -> bool:
        """Quick check without modification."""
        result = self.clean(text)
        return result.passed

    def _apply_pattern(
        self, text: str, name: str, pattern: re.Pattern[str]
    ) -> tuple[str, list[Redaction]]:
        """Apply a regex pattern, replacing matches with placeholders."""
        redactions: list[Redaction] = []
        placeholder = _PLACEHOLDERS.get(name, f"[REDACTED_{name.upper()}]")

        for match in reversed(list(pattern.finditer(text))):
            redactions.append(
                Redaction(
                    original_span=(match.start(), match.end()),
                    redaction_type=name,
                    placeholder=placeholder,
                )
            )
            text = text[: match.start()] + placeholder + text[match.end() :]

        return text, redactions

    def _entropy_scan(self, text: str) -> tuple[str, list[Redaction]]:
        """Scan for high-entropy tokens that look like secrets."""
        redactions: list[Redaction] = []
        # Split on whitespace and check each token
        tokens = text.split()
        result_tokens: list[str] = []

        for token in tokens:
            # Skip tokens that are already placeholders
            if token.startswith("[REDACTED_"):
                result_tokens.append(token)
                continue

            # Only check long-enough tokens
            if (
                len(token) >= self._min_token_length
                and _token_entropy(token) >= self._entropy_threshold
                # Must contain mixed character classes to look like a secret
                and any(c.isdigit() for c in token)
                and any(c.isalpha() for c in token)
            ):
                placeholder = _PLACEHOLDERS["high_entropy"]
                redactions.append(
                    Redaction(
                        original_span=(0, 0),  # span lost after whitespace split
                        redaction_type="high_entropy",
                        placeholder=placeholder,
                    )
                )
                result_tokens.append(placeholder)
            else:
                result_tokens.append(token)

        return " ".join(result_tokens), redactions
