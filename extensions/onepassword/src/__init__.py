"""1Password plugin implementation package."""

from __future__ import annotations

from .config import OnepasswordConfig, OnepasswordItemConfig, parse_onepassword_config
from .doctor import run_doctor_checks
from .op_cli import OpCliRunner, resolve_op_binary
from .policy import BoundedInMemoryCache, PolicyEvaluator
from .secretref import SecretRefResolver, build_secrets_setup_plan
from .storage import OnepasswordStorage
from .token import get_token_file_path, read_service_account_token, verify_token_prerequisites
from .tool import OnepasswordTool, redact_transcript_result
from .types import (
    ALL_ERROR_CODES,
    AUTH_FAILED,
    FIELD_NOT_FOUND,
    ITEM_NOT_FOUND,
    OP_ERROR,
    OP_NOT_FOUND,
    POLICY_NOT_EVALUATED,
    RATE_LIMITED,
    TIMEOUT,
    TOKEN_MISSING,
    UNKNOWN_SLUG,
    AuditRow,
    SecretItemResult,
    SecretRefResolution,
    StandingGrant,
)

__all__ = [
    "ALL_ERROR_CODES",
    "AUTH_FAILED",
    "AuditRow",
    "BoundedInMemoryCache",
    "FIELD_NOT_FOUND",
    "ITEM_NOT_FOUND",
    "OP_ERROR",
    "OP_NOT_FOUND",
    "OnepasswordConfig",
    "OnepasswordItemConfig",
    "OnepasswordStorage",
    "OnepasswordTool",
    "OpCliRunner",
    "POLICY_NOT_EVALUATED",
    "PolicyEvaluator",
    "RATE_LIMITED",
    "SecretItemResult",
    "SecretRefResolution",
    "SecretRefResolver",
    "StandingGrant",
    "TIMEOUT",
    "TOKEN_MISSING",
    "UNKNOWN_SLUG",
    "build_secrets_setup_plan",
    "get_token_file_path",
    "parse_onepassword_config",
    "read_service_account_token",
    "redact_transcript_result",
    "resolve_op_binary",
    "run_doctor_checks",
    "verify_token_prerequisites",
]
