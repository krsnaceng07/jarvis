"""Operator authentication, role-based authorization, and single-use anti-replay tokens.

Enforces INV-P10-OPS-002: Approval tokens must be cryptographically signed,
single-use (nonce), time-bound, and candidate-bound.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import hmac
import json
import time
import uuid


class OperatorRole(enum.Enum):
    """Operator privilege tiers."""

    VIEWER = "VIEWER"
    REVIEWER = "REVIEWER"
    APPROVER = "APPROVER"
    RECOVERY_OPERATOR = "RECOVERY_OPERATOR"
    ADMIN = "ADMIN"


class TokenReplayError(RuntimeError):
    """Raised when an approval token nonce is reused."""


class TokenExpiredError(RuntimeError):
    """Raised when an approval token timestamp exceeds expiry."""


class UnauthorizedOperatorError(RuntimeError):
    """Raised when operator role is insufficient for requested action."""


@dataclasses.dataclass(frozen=True)
class ApprovalTokenPayload:
    """Cryptographically bound operator approval token payload."""

    candidate_id: str
    report_digest: str
    operator_sid: str
    session_id: str
    operator_role: str
    action: str
    issued_at: float
    expires_at: float
    nonce: str

    def serialize(self) -> bytes:
        data = {
            "candidate_id": self.candidate_id,
            "report_digest": self.report_digest,
            "operator_sid": self.operator_sid,
            "session_id": self.session_id,
            "operator_role": self.operator_role,
            "action": self.action,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
        }
        return json.dumps(data, sort_keys=True).encode("utf-8")


@dataclasses.dataclass(frozen=True)
class SignedApprovalToken:
    """Signed approval token with HMAC signature."""

    payload: ApprovalTokenPayload
    signature: str

    def to_compact_string(self) -> str:
        payload_json = self.payload.serialize().decode("utf-8")
        return f"{payload_json}|{self.signature}"


class OperatorAuthManager:
    """Manages operator sessions, signed token creation, and anti-replay verification."""

    def __init__(self, secret_key: bytes) -> None:
        self._secret_key = secret_key
        self._consumed_nonces: set[str] = set()

    def generate_token(
        self,
        candidate_id: str,
        report_digest: str,
        operator_sid: str,
        session_id: str,
        operator_role: OperatorRole,
        action: str = "APPROVE_CANDIDATE",
        ttl_seconds: float = 300.0,
    ) -> SignedApprovalToken:
        """Issue a new single-use approval token."""
        now = time.time()
        nonce = f"nonce_{uuid.uuid4().hex}"
        payload = ApprovalTokenPayload(
            candidate_id=candidate_id,
            report_digest=report_digest,
            operator_sid=operator_sid,
            session_id=session_id,
            operator_role=operator_role.value,
            action=action,
            issued_at=now,
            expires_at=now + ttl_seconds,
            nonce=nonce,
        )
        sig = hmac.new(self._secret_key, payload.serialize(), hashlib.sha256).hexdigest()
        return SignedApprovalToken(payload=payload, signature=sig)

    def consume_token(
        self,
        token: SignedApprovalToken,
        required_role: OperatorRole = OperatorRole.APPROVER,
        current_time: float | None = None,
    ) -> bool:
        """Validate signature, verify expiry, and consume single-use nonce."""
        now = time.time() if current_time is None else current_time

        # 1. Verify HMAC signature
        expected_sig = hmac.new(
            self._secret_key, token.payload.serialize(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, token.signature):
            raise ValueError("TOKEN_SIGNATURE_INVALID")

        # 2. Verify expiry
        if now > token.payload.expires_at:
            raise TokenExpiredError(f"Token expired at {token.payload.expires_at}, now is {now}")

        # 3. Verify role
        role_hierarchy = {
            OperatorRole.VIEWER: 0,
            OperatorRole.REVIEWER: 1,
            OperatorRole.APPROVER: 2,
            OperatorRole.RECOVERY_OPERATOR: 3,
            OperatorRole.ADMIN: 4,
        }
        token_role = OperatorRole(token.payload.operator_role)
        if role_hierarchy[token_role] < role_hierarchy[required_role]:
            raise UnauthorizedOperatorError(
                f"Role {token_role.value} insufficient, requires {required_role.value}"
            )

        # 4. Anti-replay verification
        if token.payload.nonce in self._consumed_nonces:
            raise TokenReplayError(f"Token nonce {token.payload.nonce} has already been consumed")

        self._consumed_nonces.add(token.payload.nonce)
        return True
