"""jarvis.application_automation.auth_manager — Authentication boundaries & secret sanitization.

OpenClaw parity:
- Strict isolation of authentication boundaries.
- Zero credential / password leakage in logs, events, or tool results.
- Detection of 2FA, passkeys, security challenges, and CAPTCHAs with mandatory
  human verification handoff rather than blind automation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


class AuthStage(str, Enum):
    """Structured authentication stages."""

    NOT_AUTH = "not_auth"
    AUTH_REQUIRED = "auth_required"
    EMAIL_ENTRY = "email_entry"
    PASSWORD_ENTRY = "password_entry"
    TWO_FACTOR = "two_factor"
    PASSKEY = "passkey"
    CAPTCHA = "captcha"
    SECURITY_CHALLENGE = "security_challenge"
    HUMAN_VERIFICATION_REQUIRED = "human_verification_required"
    AUTH_SUCCESS_VERIFIED = "auth_success_verified"
    AUTH_FAILED = "auth_failed"
    AUTH_BLOCKED = "auth_blocked"


@dataclass(slots=True)
class AuthDetectionResult:
    """Outcome of page authentication detection."""

    is_auth_page: bool
    stage: AuthStage
    provider: str  # google, generic
    requires_human: bool
    guidance_message: str


def sanitize_secrets(data: Any) -> Any:
    """Recursively redact passwords, tokens, and secret fields from dictionaries and strings."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(sec in k_lower for sec in ("password", "secret", "token", "passwd", "credential", "api_key")):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_secrets(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_secrets(item) for item in data]
    elif isinstance(data, str):
        # Redact patterns like password="xyz" or token="abc"
        cleaned = re.sub(
            r'(password|passwd|secret|token|api_key)\s*[:=]\s*["\']?[^\s"\'&,;]+["\']?',
            r'\1="[REDACTED]"',
            data,
            flags=re.IGNORECASE,
        )
        return cleaned
    return data


class AuthBoundaryManager:
    """Detects login pages and enforces safe, non-leaking authentication boundaries."""

    _instance: Optional[AuthBoundaryManager] = None

    @classmethod
    def get_instance(cls) -> AuthBoundaryManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def detect_auth_boundary(self, url: str, page_text: str = "") -> AuthDetectionResult:
        """Inspect page URL and DOM text to identify authentication gates."""
        if not url:
            return AuthDetectionResult(
                is_auth_page=False,
                stage=AuthStage.NOT_AUTH,
                provider="none",
                requires_human=False,
                guidance_message="",
            )

        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        text_lower = page_text.lower()

        # 1. Google Authentication
        if "accounts.google.com" in host or "myaccount.google.com" in host:
            # Check for CAPTCHA
            if "captcha" in text_lower or "unusual traffic" in text_lower:
                return AuthDetectionResult(
                    is_auth_page=True,
                    stage=AuthStage.CAPTCHA,
                    provider="google",
                    requires_human=True,
                    guidance_message="Google CAPTCHA challenge detected. Please complete the CAPTCHA in the browser.",
                )

            # Check for 2FA / 2-Step Verification
            if any(w in text_lower for w in ("2-step verification", "two-factor", "tap yes on your phone", "enter the code sent to")):
                return AuthDetectionResult(
                    is_auth_page=True,
                    stage=AuthStage.TWO_FACTOR,
                    provider="google",
                    requires_human=True,
                    guidance_message="Google 2-Step Verification required. Please confirm on your mobile device or enter your code.",
                )

            # Check for Passkey
            if "passkey" in text_lower or "use your passkey" in text_lower:
                return AuthDetectionResult(
                    is_auth_page=True,
                    stage=AuthStage.PASSKEY,
                    provider="google",
                    requires_human=True,
                    guidance_message="Google Passkey authentication requested. Please verify using your device's biometric/security key.",
                )

            # Check for Password entry
            if "enter your password" in text_lower or 'type="password"' in text_lower:
                return AuthDetectionResult(
                    is_auth_page=True,
                    stage=AuthStage.PASSWORD_ENTRY,
                    provider="google",
                    requires_human=True,
                    guidance_message="Google Password entry page. For security, JARVIS will not guess or inject passwords without authorization.",
                )

            # Check for Email entry
            if "sign in" in text_lower or "identifier" in url:
                return AuthDetectionResult(
                    is_auth_page=True,
                    stage=AuthStage.EMAIL_ENTRY,
                    provider="google",
                    requires_human=False,
                    guidance_message="Google Sign-In email entry.",
                )

            return AuthDetectionResult(
                is_auth_page=True,
                stage=AuthStage.AUTH_REQUIRED,
                provider="google",
                requires_human=True,
                guidance_message="Google Authentication required.",
            )

        # 2. Generic login
        if any(w in parsed.path.lower() for w in ("/login", "/signin", "/auth")):
            if "captcha" in text_lower:
                return AuthDetectionResult(
                    is_auth_page=True,
                    stage=AuthStage.CAPTCHA,
                    provider="generic",
                    requires_human=True,
                    guidance_message="CAPTCHA detected. Please complete the challenge in your browser.",
                )
            return AuthDetectionResult(
                is_auth_page=True,
                stage=AuthStage.AUTH_REQUIRED,
                provider="generic",
                requires_human=True,
                guidance_message="Authentication page detected. Please complete sign-in.",
            )

        return AuthDetectionResult(
            is_auth_page=False,
            stage=AuthStage.NOT_AUTH,
            provider="none",
            requires_human=False,
            guidance_message="",
        )
