"""Agent tool `onepassword` for listing and reading configured 1Password secrets.

OpenClaw parity: mirrors @openclaw/onepassword agent tool:
- Action `list`: returns configured slugs, policy, description, standing grant status.
  Never contacts 1Password, never returns secrets.
- Action `get`: requires non-empty `reason` <= 300 chars, validates authorization nonce,
  fetches field, records SQLite audit row, updates cache.
- Redaction hook: post-execution transcript persistence replaces secret values with redacted metadata.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .config import MAX_REASON_LENGTH, SLUG_PATTERN, OnepasswordConfig
from .op_cli import OpCliRunner
from .policy import PolicyEvaluator
from .storage import OnepasswordStorage
from .types import (
    INVALID_ACTION,
    INVALID_REASON,
    INVALID_SLUG,
    POLICY_NOT_EVALUATED,
    UNKNOWN_SLUG,
)

logger = logging.getLogger("jarvis.onepassword.tool")

TOOL_NAME = "onepassword"
TOOL_DESCRIPTION = (
    "Access curated, policy-controlled credentials from 1Password. "
    "Supports 'list' to view available slugs and 'get' to retrieve a secret with a required reason."
)

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["list", "get"],
            "description": "Action to perform: 'list' available secret slugs or 'get' a specific secret.",
        },
        "slug": {
            "type": "string",
            "description": "The registered secret slug identifier (required for 'get').",
        },
        "reason": {
            "type": "string",
            "description": "Non-sensitive explanation of why this credential is required (required for 'get', max 300 chars).",
        },
        "authorizationNonce": {
            "type": "string",
            "description": "Internal policy authorization nonce (injected automatically).",
        },
    },
    "required": ["action"],
}


def redact_transcript_result(result: dict[str, Any]) -> dict[str, Any]:
    """Redact raw secret values from the tool output before transcript persistence."""
    if not isinstance(result, dict):
        return result

    copied = dict(result)
    if "value" in copied:
        slug = copied.get("slug") or "unknown"
        copied["value"] = f"[REDACTED: 1Password secret for slug '{slug}']"
        copied["_redacted"] = True

    return copied


class OnepasswordTool:
    """Implementation of the onepassword agent tool."""

    def __init__(
        self,
        config: OnepasswordConfig,
        storage: OnepasswordStorage,
        op_runner: OpCliRunner | None = None,
        policy_evaluator: PolicyEvaluator | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.op_runner = op_runner or OpCliRunner(
            op_bin=config.op_bin,
            default_timeout_ms=config.op_timeout_ms,
        )
        self.policy = policy_evaluator or PolicyEvaluator(config=config, storage=storage)

    def get_tool_declaration(self) -> dict[str, Any]:
        """Return tool schema declaration for LLM registration."""
        return {
            "name": TOOL_NAME,
            "description": TOOL_DESCRIPTION,
            "parameters": TOOL_SCHEMA,
        }

    async def execute(
        self,
        params: dict[str, Any],
        agent_id: str = "",
        tool_call_id: str = "",
    ) -> dict[str, Any]:
        """Execute the onepassword tool call."""
        start_time = time.time()
        action = params.get("action")

        if not action or action not in ("list", "get"):
            return {
                "error": f"Invalid action '{action}'. Must be 'list' or 'get'.",
                "errorCode": INVALID_ACTION,
            }

        # ── Action: list ──────────────────────────────────────────────────────
        if action == "list":
            items_list: list[dict[str, Any]] = []
            now = time.time()
            for slug, item_cfg in self.config.items.items():
                effective_policy = self.config.get_effective_policy(slug)
                has_grant = self.storage.has_standing_grant(agent_id, slug, now=now)
                items_list.append(
                    {
                        "slug": slug,
                        "description": item_cfg.description,
                        "policy": effective_policy,
                        "hasStandingGrant": has_grant,
                    }
                )

            return {"items": items_list}

        # ── Action: get ───────────────────────────────────────────────────────
        slug = str(params.get("slug") or "").strip()
        reason = str(params.get("reason") or "").strip()
        nonce = str(params.get("authorizationNonce") or "").strip()

        # Input validations
        if not slug:
            return {
                "error": "Parameter 'slug' is required for action 'get'.",
                "errorCode": INVALID_SLUG,
            }

        if not SLUG_PATTERN.match(slug):
            return {
                "error": f"Invalid slug format '{slug}'.",
                "errorCode": INVALID_SLUG,
            }

        if not reason:
            return {
                "error": "Parameter 'reason' is required for action 'get'.",
                "errorCode": INVALID_REASON,
            }

        if len(reason) > MAX_REASON_LENGTH:
            return {
                "error": f"Reason exceeds maximum length of {MAX_REASON_LENGTH} characters.",
                "errorCode": INVALID_REASON,
            }

        if slug not in self.config.items:
            self.storage.record_audit(
                slug=slug,
                action="get",
                outcome="denied",
                agent_id=agent_id,
                error_code=UNKNOWN_SLUG,
                reason=reason,
                cached=False,
            )
            return {
                "error": f"Slug '{slug}' is not in the configured registry.",
                "errorCode": UNKNOWN_SLUG,
            }

        item_cfg = self.config.items[slug]
        vault = self.config.get_effective_vault(slug)
        field_name = item_cfg.field

        # Authorization validation: verify nonce or evaluate policy
        if nonce:
            valid_nonce, nonce_err = self.storage.consume_authorization_nonce(
                nonce=nonce,
                agent_id=agent_id,
                slug=slug,
            )
            if not valid_nonce:
                err_code = nonce_err or POLICY_NOT_EVALUATED
                self.storage.record_audit(
                    slug=slug,
                    action="get",
                    outcome="denied",
                    agent_id=agent_id,
                    error_code=err_code,
                    reason=reason,
                    cached=False,
                )
                return {
                    "error": f"Authorization verification failed: {err_code}",
                    "errorCode": err_code,
                }
        else:
            # Evaluate policy directly if nonce was not pre-injected
            auth_nonce, policy_err, err_msg = await self.policy.evaluate_access(
                slug=slug,
                reason=reason,
                agent_id=agent_id,
            )
            if policy_err or not auth_nonce:
                return {
                    "error": err_msg or "Access denied by policy",
                    "errorCode": policy_err or POLICY_NOT_EVALUATED,
                }
            # Consume the generated nonce
            self.storage.consume_authorization_nonce(
                nonce=auth_nonce,
                agent_id=agent_id,
                slug=slug,
            )

        # Check in-memory cache
        cached_val = self.policy.cache.get(slug)
        if cached_val is not None:
            duration_ms = (time.time() - start_time) * 1000.0
            self.storage.record_audit(
                slug=slug,
                action="get",
                outcome="allowed",
                agent_id=agent_id,
                error_code=None,
                reason=reason,
                cached=True,
                duration_ms=duration_ms,
            )
            return {
                "slug": slug,
                "item": item_cfg.item,
                "field": field_name,
                "value": cached_val,
            }

        # Cache miss -> Execute op CLI
        result, error_code, error_msg = await self.op_runner.get_item_field(
            slug=slug,
            item=item_cfg.item,
            field=field_name,
            vault=vault,
            timeout_ms=self.config.op_timeout_ms,
        )

        duration_ms = (time.time() - start_time) * 1000.0

        if error_code or not result:
            self.storage.record_audit(
                slug=slug,
                action="get",
                outcome="error",
                agent_id=agent_id,
                error_code=error_code,
                reason=reason,
                cached=False,
                duration_ms=duration_ms,
            )
            return {
                "error": error_msg or "Failed to retrieve secret from 1Password",
                "errorCode": error_code or "OP_ERROR",
            }

        # Store in cache
        self.policy.cache.set(slug, result.value)

        # Record audit row (never stores value)
        self.storage.record_audit(
            slug=slug,
            action="get",
            outcome="allowed",
            agent_id=agent_id,
            error_code=None,
            reason=reason,
            cached=False,
            duration_ms=duration_ms,
        )

        return {
            "slug": slug,
            "item": item_cfg.item,
            "field": field_name,
            "value": result.value,
        }
