"""src.agents.self_healing.strategies.provider_fallback — Multi-provider failover strategy.

OpenClaw parity: mirrors resolveRunFailoverDecision for provider and model rotation
when primary model is overloaded, rate-limited, or unavailable.
"""

from __future__ import annotations

import os

from ..failure_event import ErrorCategory, FailureEvent
from .base import RecoveryResult, RecoveryStrategy

#: Default failover chain for models
MODEL_FAILOVER_CHAIN: list[dict[str, str]] = [
    {
        "provider": "google",
        "model": "models/gemini-3.1-flash-live-preview",
        "env_check": "GEMINI_API_KEY",
    },
    {
        "provider": "groq",
        "model": "groq/llama-3.3-70b-versatile",
        "env_check": "GROQ_API_KEY",
    },
    {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "env_check": "OPENAI_API_KEY",
    },
    {
        "provider": "ollama",
        "model": "llama3.2",
        "env_check": None,
    },
]


class ProviderFallbackStrategy(RecoveryStrategy):
    """Selects secondary provider and model when primary provider fails."""

    name: str = "provider_fallback"

    def __init__(self, failover_chain: list[dict[str, str]] | None = None) -> None:
        self.chain = failover_chain or MODEL_FAILOVER_CHAIN

    async def can_handle(self, event: FailureEvent) -> bool:
        """Handles model overload, permanent rate limits, and provider server errors."""
        return event.category in (
            ErrorCategory.MODEL_OVERLOADED,
            ErrorCategory.RATE_LIMIT,
        )

    def select_fallback_model(self, current_model: str) -> dict[str, str] | None:
        """Select the next available fallback model in the chain."""
        found_current = False
        for entry in self.chain:
            if found_current:
                # Check if required environment variable exists if configured
                env_key = entry.get("env_check")
                if not env_key or os.getenv(env_key):
                    return entry
            elif current_model and (
                current_model == entry["model"] or entry["model"] in current_model
            ):
                found_current = True

        # If current not found or reached end, pick first alternative with an active API key
        for entry in self.chain:
            if entry["model"] != current_model:
                env_key = entry.get("env_check")
                if not env_key or os.getenv(env_key):
                    return entry

        return None

    async def execute(self, event: FailureEvent) -> RecoveryResult:
        """Execute model failover recommendation."""
        # OpenClaw parity: explicit user model selection is strict (no silent fallback)
        if event.context.get("model_override_source") == "user":
            return RecoveryResult(
                success=False,
                action_taken="Model fallback blocked by strict user selection",
                error="User session selection is strict; automatic fallback prohibited without operator approval.",
            )

        current_model = str(event.context.get("model") or "")
        fallback = self.select_fallback_model(current_model)

        if not fallback:
            return RecoveryResult(
                success=False,
                action_taken="No viable fallback provider available",
                error="All alternative providers lack credentials or are exhausted",
            )

        new_model = fallback["model"]
        new_provider = fallback["provider"]

        notice = self.format_fallback_notice(
            fallback_model=new_model,
            primary_model=current_model,
            reason=event.error_message or "primary model unavailable",
        )

        return RecoveryResult(
            success=True,
            action_taken=notice,
            requires_retry=True,
            details={
                "previous_model": current_model,
                "fallback_model": new_model,
                "fallback_provider": new_provider,
                "notice": notice,
            },
        )

    @staticmethod
    def format_fallback_notice(
        fallback_model: str,
        primary_model: str,
        reason: str = "primary model unavailable",
    ) -> str:
        """Mirrors OpenClaw's exact notice contract:
        '↪️ Model Fallback: <fallback> (selected <primary>; <reason>)'
        """
        clean_reason = reason.strip().replace("\n", " ")[:80]
        return f"↪️ Model Fallback: {fallback_model} (selected {primary_model}; {clean_reason})"

    @staticmethod
    def format_fallback_cleared_notice(primary_model: str, fallback_model: str) -> str:
        """Mirrors OpenClaw's exact notice contract:
        '↪️ Model Fallback cleared: <primary> (was <fallback>)'
        """
        return f"↪️ Model Fallback cleared: {primary_model} (was {fallback_model})"


__all__ = [
    "MODEL_FAILOVER_CHAIN",
    "ProviderFallbackStrategy",
]
