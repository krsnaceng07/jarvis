"""Nextcloud Talk webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac


def verify_nextcloud_signature(
    body: bytes,
    secret: str,
    signature: str,
) -> bool:
    """Verify X-Nextcloud-Talk-Signature or sha256 HMAC signature."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    # Support signature with or without 'sha256=' prefix
    clean_sig = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, clean_sig)
