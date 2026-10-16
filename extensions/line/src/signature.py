"""LINE Webhook HMAC-SHA256 signature verification."""

from __future__ import annotations

import base64
import hashlib
import hmac


def verify_line_signature(body: bytes, channel_secret: str, signature: str) -> bool:
    """Verify X-Line-Signature against channel secret and request body bytes."""
    if not channel_secret or not signature:
        return False

    hash_val = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected_signature = base64.b64encode(hash_val).decode("utf-8")
    return hmac.compare_digest(expected_signature, signature)
