"""Tests for memory_host_error_utils — mirrors host/error-utils.ts.

Covers secret-pattern redaction, PEM block handling, and
the canonical error formatter.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the SDK importable when running this file in isolation.
_PKG_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PKG_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from jarvis_sdk.memory_host_error_utils import (  # noqa: E402
    format_error_message,
    redact_sensitive_text,
)


# ── redact_sensitive_text — token shapes ────────────────────────────


def test_redact_bearer_token_in_authorization_header() -> None:
    """``Authorization: Bearer <token>`` redacts the token."""
    text = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz1234"
    result = redact_sensitive_text(text)
    assert "Authorization:" in result
    # The token should be masked, not present verbatim.
    assert "abcdefghijklmnopqrstuvwxyz1234" not in result
    # Should show first 6 + ... + last 4.
    assert "abcdef...1234" in result


def test_redact_bearer_token_standalone() -> None:
    """A free-standing ``Bearer <long-token>`` is redacted."""
    text = "got Bearer abcdefghijklmnopqrstuvwxyz1234 from header"
    result = redact_sensitive_text(text)
    assert "abcdefghijklmnopqrstuvwxyz1234" not in result


def test_redact_short_bearer_not_triggered() -> None:
    """A short ``Bearer xxxxx`` (< 18 chars) is left alone."""
    text = "Bearer short"
    result = redact_sensitive_text(text)
    # The short token is not in the Bearer pattern's char range.
    assert result == text


def test_redact_openai_sk_token() -> None:
    """OpenAI ``sk-...`` tokens are redacted.

    The token ``sk-abcdefghijklmnop`` is 18 chars (exactly),
    so the ``mask_token`` threshold (``< 18``) is not hit
    and the masked form is ``sk-abc...mnop`` (first 6 +
    ``...`` + last 4). Shorter tokens collapse to ``***``.
    """
    text = "got key sk-abcdefghijklmnop from env"
    result = redact_sensitive_text(text)
    assert "sk-abcdefghijklmnop" not in result
    assert "sk-abc...mnop" in result


def test_redact_short_openai_token_collapses() -> None:
    """A short OpenAI token (>= 8 chars but < 18 total) becomes ``***``."""
    text = "got key sk-shortone from env"  # 12 chars total
    result = redact_sensitive_text(text)
    # "sk-shortone" is 12 chars, so it collapses to "***".
    assert "***" in result
    assert "sk-shortone" not in result


def test_redact_github_pat() -> None:
    """GitHub PATs are redacted."""
    text = "token ghp_abcdefghijklmnopqrst"
    result = redact_sensitive_text(text)
    assert "ghp_abcdefghijklmnopqrst" not in result


def test_redact_github_pat_new_format() -> None:
    """GitHub fine-grained PATs are redacted."""
    text = "token github_pat_11AAAAAAAA0_abcdefghijklmnopqrstuvwxyz"
    result = redact_sensitive_text(text)
    assert "github_pat_11AAAAAAAA0_abcdefghijklmnopqrstuvwxyz" not in result


def test_redact_slack_token() -> None:
    """Slack ``xoxb-...`` / ``xoxp-...`` tokens are redacted."""
    text = "slack xoxb-1234567890abcdefghij"
    result = redact_sensitive_text(text)
    assert "xoxb-1234567890abcdefghij" not in result


def test_redact_google_api_key() -> None:
    """Google ``AIza...`` keys are redacted."""
    text = "google AIzaSyA1234567890abcdefghijk"
    result = redact_sensitive_text(text)
    assert "AIzaSyA1234567890abcdefghijk" not in result


def test_redact_perplexity_key() -> None:
    """Perplexity ``pplx-...`` keys are redacted."""
    text = "perplexity pplx-abcdefghij1234567890"
    result = redact_sensitive_text(text)
    assert "pplx-abcdefghij1234567890" not in result


def test_redact_npm_token() -> None:
    """NPM tokens are redacted."""
    text = "npm npm_abcdefghijklmnopqrst"
    result = redact_sensitive_text(text)
    assert "npm_abcdefghijklmnopqrst" not in result


def test_redact_groq_key() -> None:
    """Groq ``gsk_...`` keys are redacted."""
    text = "groq gsk_abcdefghijklmnopqrst"
    result = redact_sensitive_text(text)
    assert "gsk_abcdefghijklmnopqrst" not in result


def test_redact_telegram_bot_token() -> None:
    """Telegram bot tokens are redacted."""
    text = "telegram bot1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    result = redact_sensitive_text(text)
    assert "bot1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef" not in result


def test_redact_xapp_token() -> None:
    """Slack ``xapp-...`` tokens are redacted."""
    text = "slack xapp-1234567890ABCDEFGHIJ"
    result = redact_sensitive_text(text)
    assert "xapp-1234567890ABCDEFGHIJ" not in result


# ── redact_sensitive_text — key=value shapes ───────────────────────


def test_redact_key_value_assignment() -> None:
    """``API_KEY=...`` is redacted."""
    text = "API_KEY=abcdefghijklmnop1234"
    result = redact_sensitive_text(text)
    assert "abcdefghijklmnop1234" not in result


def test_redact_token_quoted() -> None:
    """``TOKEN="..."`` is redacted."""
    text = 'TOKEN="abcdefghijklmnop1234"'
    result = redact_sensitive_text(text)
    assert "abcdefghijklmnop1234" not in result


def test_redact_query_string_param() -> None:
    """Query string ``?token=...`` is redacted."""
    text = "https://api.example.com/?token=abcdefghijklmnop1234&user=alice"
    result = redact_sensitive_text(text)
    assert "abcdefghijklmnop1234" not in result
    assert "user=alice" in result  # non-secret preserved


def test_redact_json_apikey() -> None:
    """JSON ``"apiKey": "..."`` is redacted."""
    text = '{"apiKey": "abcdefghijklmnop1234"}'
    result = redact_sensitive_text(text)
    assert "abcdefghijklmnop1234" not in result


def test_redact_cli_flag() -> None:
    """CLI ``--api-key ...`` is redacted."""
    text = "openclaw --api-key abcdefghijklmnop1234"
    result = redact_sensitive_text(text)
    assert "abcdefghijklmnop1234" not in result


# ── redact_sensitive_text — PEM block ──────────────────────────────


def test_redact_pem_block() -> None:
    """A PEM private key block is collapsed to header + redacted + footer."""
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEAabcdefghijklmnopqrstuvwxyz\n"
        "0123456789abcdefghijklmnopqrstuvwxyz\n"
        "-----END RSA PRIVATE KEY-----"
    )
    text = f"failed: {pem}"
    result = redact_sensitive_text(text)
    assert "-----BEGIN RSA PRIVATE KEY-----" in result
    assert "-----END RSA PRIVATE KEY-----" in result
    assert "...redacted..." in result
    # The body of the key should not be present.
    assert "MIIEpAIBAAKCAQEAabcdefghijklmnopqrstuvwxyz" not in result


def test_redact_pem_block_too_short() -> None:
    """A PEM block with only the BEGIN line is not matched by
    the regex (the END line is required), so the text is
    left unchanged. The OpenClaw regex requires both
    ``-----BEGIN ...PRIVATE KEY-----`` and the matching
    ``-----END ...PRIVATE KEY-----`` markers; lone BEGIN
    lines are intentionally not redacted (they're not a
    secret on their own).
    """
    pem = "-----BEGIN RSA PRIVATE KEY-----"
    text = f"failed: {pem}"
    result = redact_sensitive_text(text)
    # The lone BEGIN line is preserved (no PEM block to redact).
    assert "-----BEGIN RSA PRIVATE KEY-----" in result


# ── redact_sensitive_text — no-op cases ─────────────────────────────


def test_redact_passthrough_no_secrets() -> None:
    """Text without any secret shape is returned unchanged."""
    text = "this is a regular log message about a successful operation"
    assert redact_sensitive_text(text) == text


def test_redact_empty_string() -> None:
    """Empty string returns empty string."""
    assert redact_sensitive_text("") == ""


def test_redact_multiple_secrets() -> None:
    """Multiple secrets in one message are all redacted."""
    text = "OPENAI_KEY=sk-abcdefghijklmnop and GEMINI_KEY=AIzaSyA1234567890abcdefghijk"
    result = redact_sensitive_text(text)
    assert "sk-abcdefghijklmnop" not in result
    assert "AIzaSyA1234567890abcdefghijk" not in result


# ── format_error_message ──────────────────────────────────────────


def test_format_error_message_basic() -> None:
    """A plain exception is formatted as ``Type: message``."""
    err = ValueError("something went wrong")
    result = format_error_message(err)
    assert "ValueError" in result
    assert "something went wrong" in result


def test_format_error_message_redacts_secrets() -> None:
    """Secrets inside an error message are redacted by the formatter."""
    err = RuntimeError("failed with key sk-abcdefghijklmnop")
    result = format_error_message(err)
    assert "sk-abcdefghijklmnop" not in result
    assert "RuntimeError" in result


def test_format_error_message_redacts_in_cause() -> None:
    """Secrets in the ``__cause__`` chain are also redacted."""
    try:
        try:
            raise ValueError("inner with sk-abcdefghijklmnop")
        except ValueError as inner:
            raise RuntimeError("outer") from inner
    except RuntimeError as err:
        result = format_error_message(err)
    # The cause message is included in the formatted string.
    assert "sk-abcdefghijklmnop" not in result


def test_format_error_message_non_exception() -> None:
    """A non-exception input is converted to a string."""
    result = format_error_message("plain string with sk-abcdefghijklmnop")
    assert "sk-abcdefghijklmnop" not in result
    assert "plain string" in result


def test_format_error_message_none() -> None:
    """``None`` is formatted without error."""
    result = format_error_message(None)
    assert result == "None"


def test_format_error_message_preserves_non_secret_text() -> None:
    """Non-secret parts of the message are preserved."""
    err = ValueError("operation X failed because sk-abcdefghijklmnop was wrong")
    result = format_error_message(err)
    assert "operation X failed" in result
    assert "was wrong" in result
    assert "sk-abcdefghijklmnop" not in result
