"""Tests for src/sessions/model_overrides.py.

Mirrors OpenClaw's ``src/sessions/model-overrides.test.ts``.
"""
from __future__ import annotations

import time
from typing import Any

import pytest

from src.sessions.model_overrides import (
    MODEL_SELECTION_LOCKED_MESSAGE,
    ModelSelectionLockedError,
    apply_model_override_to_session_entry,
    repair_provider_wrapped_model_override,
)


def _apply_openai_selection(entry: dict[str, Any]) -> dict[str, bool]:
    return apply_model_override_to_session_entry(
        entry=entry,
        selection={"provider": "openai", "model": "gpt-5.4"},
    )


def _expect_runtime_model_fields_cleared(entry: dict[str, Any], before: int) -> None:
    assert entry.get("providerOverride") == "openai"
    assert entry.get("modelOverride") == "gpt-5.4"
    assert entry.get("modelProvider") is None
    assert entry.get("model") is None
    assert (entry.get("updatedAt") or 0) > before


def _context_budget_status(
    *,
    updated_at: int,
    provider: str,
    model: str,
    context_token_budget: int,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "source": "pre-prompt-estimate",
        "updatedAt": updated_at,
        "provider": provider,
        "model": model,
        "route": "fits",
        "shouldCompact": False,
        "estimatedPromptTokens": int(context_token_budget * 0.6),
        "contextTokenBudget": context_token_budget,
        "promptBudgetBeforeReserve": context_token_budget - 10_000,
        "reserveTokens": 10_000,
        "effectiveReserveTokens": 10_000,
        "remainingPromptBudgetTokens": int(context_token_budget * 0.4),
        "overflowTokens": 0,
        "toolResultReducibleChars": 0,
        "messageCount": 2,
        "unwindowedMessageCount": 2,
    }


class TestApplyModelOverrideToSessionEntry:
    def test_rejects_locked_session_model_mutations_before_changing_any_fields(self) -> None:
        entry: dict[str, Any] = {
            "sessionId": "sess-locked",
            "updatedAt": 10,
            "providerOverride": "openai",
            "modelOverride": "gpt-5.4",
            "modelSelectionLocked": True,
        }
        before = dict(entry)

        with pytest.raises(ModelSelectionLockedError):
            apply_model_override_to_session_entry(
                entry=entry,
                selection={"provider": "anthropic", "model": "claude-sonnet-4-6"},
            )
        with pytest.raises(Exception, match=MODEL_SELECTION_LOCKED_MESSAGE):
            apply_model_override_to_session_entry(
                entry=entry,
                selection={
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "isDefault": True,
                },
            )
        assert entry == before

    def test_clears_stale_runtime_model_fields_when_switching_overrides(self) -> None:
        before = int(time.time() * 1000) - 5_000
        entry: dict[str, Any] = {
            "sessionId": "sess-1",
            "updatedAt": before,
            "modelProvider": "anthropic",
            "model": "claude-sonnet-4-6",
            "providerOverride": "anthropic",
            "modelOverride": "claude-sonnet-4-6",
            "contextTokens": 160_000,
            "contextBudgetStatus": _context_budget_status(
                updated_at=before,
                provider="anthropic",
                model="claude-sonnet-4-6",
                context_token_budget=200_000,
            ),
            "fallbackNoticeSelectedModel": "anthropic/claude-sonnet-4-6",
            "fallbackNoticeActiveModel": "anthropic/claude-sonnet-4-6",
            "fallbackNoticeReason": "provider temporary failure",
        }

        result = _apply_openai_selection(entry)

        assert result["updated"] is True
        _expect_runtime_model_fields_cleared(entry, before)
        assert entry.get("contextTokens") is None
        assert entry.get("contextBudgetStatus") is None
        assert entry.get("fallbackNoticeSelectedModel") is None
        assert entry.get("fallbackNoticeActiveModel") is None
        assert entry.get("fallbackNoticeReason") is None
        assert entry.get("modelOverrideSource") == "user"

    def test_clears_stale_runtime_model_fields_even_when_override_selection_unchanged(self) -> None:
        before = int(time.time() * 1000) - 5_000
        entry: dict[str, Any] = {
            "sessionId": "sess-2",
            "updatedAt": before,
            "modelProvider": "anthropic",
            "model": "claude-sonnet-4-6",
            "providerOverride": "openai",
            "modelOverride": "gpt-5.4",
            "contextTokens": 160_000,
            "contextBudgetStatus": _context_budget_status(
                updated_at=before,
                provider="anthropic",
                model="claude-sonnet-4-6",
                context_token_budget=200_000,
            ),
        }

        result = _apply_openai_selection(entry)

        assert result["updated"] is True
        _expect_runtime_model_fields_cleared(entry, before)
        assert entry.get("contextTokens") is None
        assert entry.get("contextBudgetStatus") is None

    def test_retains_aligned_runtime_model_fields_when_selection_and_runtime_already_match(self) -> None:
        before = int(time.time() * 1000) - 5_000
        entry: dict[str, Any] = {
            "sessionId": "sess-3",
            "updatedAt": before,
            "modelProvider": "openai",
            "model": "gpt-5.4",
            "providerOverride": "openai",
            "modelOverride": "gpt-5.4",
            "contextTokens": 200_000,
            "contextBudgetStatus": _context_budget_status(
                updated_at=before,
                provider="openai",
                model="gpt-5.4",
                context_token_budget=200_000,
            ),
        }

        result = apply_model_override_to_session_entry(
            entry=entry,
            selection={"provider": "openai", "model": "gpt-5.4"},
        )

        assert result["updated"] is True
        assert entry.get("modelProvider") == "openai"
        assert entry.get("model") == "gpt-5.4"
        assert entry.get("modelOverrideSource") == "user"
        assert entry.get("contextTokens") == 200_000
        assert entry.get("contextBudgetStatus", {}).get("contextTokenBudget") == 200_000
        assert (entry.get("updatedAt") or 0) >= before

    def test_clears_stale_context_tokens_when_switching_back_to_default_model(self) -> None:
        before = int(time.time() * 1000) - 5_000
        entry: dict[str, Any] = {
            "sessionId": "sess-4",
            "updatedAt": before,
            "providerOverride": "local",
            "modelOverride": "sunapi386/llama-3-lexi-uncensored:8b",
            "contextTokens": 4_096,
            "contextBudgetStatus": _context_budget_status(
                updated_at=before,
                provider="local",
                model="sunapi386/llama-3-lexi-uncensored:8b",
                context_token_budget=4_096,
            ),
        }

        result = apply_model_override_to_session_entry(
            entry=entry,
            selection={"provider": "local", "model": "llama3.1:8b", "isDefault": True},
        )

        assert result["updated"] is True
        assert entry.get("providerOverride") is None
        assert entry.get("modelOverride") is None
        assert entry.get("modelOverrideSource") is None
        assert entry.get("contextTokens") is None
        assert entry.get("contextBudgetStatus") is None
        assert (entry.get("updatedAt") or 0) > before

    def test_sets_live_model_switch_pending_when_switching_to_default_with_runtime_only_fields(self) -> None:
        before = int(time.time() * 1000) - 5_000
        entry: dict[str, Any] = {
            "sessionId": "sess-96269",
            "updatedAt": before,
            "modelProvider": "anthropic",
            "model": "claude-sonnet-4-6",
            "contextTokens": 200_000,
            "contextBudgetStatus": _context_budget_status(
                updated_at=before,
                provider="anthropic",
                model="claude-sonnet-4-6",
                context_token_budget=200_000,
            ),
        }

        result = apply_model_override_to_session_entry(
            entry=entry,
            selection={
                "provider": "openai",
                "model": "gpt-5.4",
                "isDefault": True,
            },
            markLiveSwitchPending=True,
        )

        assert result["updated"] is True
        assert entry.get("modelProvider") is None
        assert entry.get("model") is None
        assert entry.get("contextTokens") is None
        assert entry.get("contextBudgetStatus") is None
        assert entry.get("liveModelSwitchPending") is True

    def test_marks_non_default_overrides_with_the_provided_source(self) -> None:
        entry: dict[str, Any] = {
            "sessionId": "sess-5a",
            "updatedAt": int(time.time() * 1000) - 5_000,
        }

        result = apply_model_override_to_session_entry(
            entry=entry,
            selection={"provider": "anthropic", "model": "claude-sonnet-4-6"},
            selectionSource="auto",
        )

        assert result["updated"] is True
        assert entry.get("providerOverride") == "anthropic"
        assert entry.get("modelOverride") == "claude-sonnet-4-6"
        assert entry.get("modelOverrideSource") == "auto"

    def test_sets_live_model_switch_pending_only_when_explicitly_requested(self) -> None:
        entry: dict[str, Any] = {
            "sessionId": "sess-5",
            "updatedAt": int(time.time() * 1000) - 5_000,
            "providerOverride": "anthropic",
            "modelOverride": "claude-sonnet-4-6",
        }
        before_entry: dict[str, Any] = dict(entry)

        without_flag = apply_model_override_to_session_entry(
            entry=before_entry,
            selection={"provider": "openai", "model": "gpt-5.4"},
        )
        assert without_flag["updated"] is True
        assert before_entry.get("liveModelSwitchPending") is None

        with_flag_entry: dict[str, Any] = dict(entry)
        with_flag = apply_model_override_to_session_entry(
            entry=with_flag_entry,
            selection={"provider": "openai", "model": "gpt-5.4"},
            markLiveSwitchPending=True,
        )
        assert with_flag["updated"] is True
        assert with_flag_entry.get("liveModelSwitchPending") is True

    def test_marks_profile_only_switches_as_pending_when_requested(self) -> None:
        entry: dict[str, Any] = {
            "sessionId": "sess-profile-switch",
            "updatedAt": int(time.time() * 1000) - 5_000,
            "providerOverride": "openai",
            "modelOverride": "gpt-5.4",
            "authProfileOverride": "oldprofile",
            "authProfileOverrideSource": "user",
        }

        result = apply_model_override_to_session_entry(
            entry=entry,
            selection={"provider": "openai", "model": "gpt-5.4"},
            profileOverride="newprofile",
            markLiveSwitchPending=True,
        )

        assert result["updated"] is True
        assert entry.get("authProfileOverride") == "newprofile"
        assert entry.get("liveModelSwitchPending") is True


class TestRepairProviderWrappedModelOverride:
    def test_rejects_provider_wrapped_repair_for_locked_sessions_without_mutating(self) -> None:
        entry: dict[str, Any] = {
            "sessionId": "sess-locked-openrouter-repair",
            "updatedAt": int(time.time() * 1000) - 5_000,
            "providerOverride": "anthropic",
            "modelOverride": "claude-haiku-4.5",
            "modelOverrideSource": "user",
            "modelProvider": "openrouter",
            "model": "anthropic/claude-haiku-4.5",
            "contextTokens": 200_000,
            "modelSelectionLocked": True,
        }
        before = dict(entry)

        with pytest.raises(ModelSelectionLockedError):
            repair_provider_wrapped_model_override(
                entry=entry,
                defaultProvider="openai",
                defaultModel="gpt-5.4",
            )
        assert entry == before

    def test_restores_provider_wrapped_override_from_aligned_runtime_model_fields(self) -> None:
        before = int(time.time() * 1000) - 5_000
        entry: dict[str, Any] = {
            "sessionId": "sess-openrouter-repair-runtime",
            "updatedAt": before,
            "providerOverride": "anthropic",
            "modelOverride": "claude-haiku-4.5",
            "modelOverrideSource": "user",
            "modelProvider": "openrouter",
            "model": "anthropic/claude-haiku-4.5",
            "contextTokens": 200_000,
        }

        result = repair_provider_wrapped_model_override(
            entry=entry,
            defaultProvider="openai",
            defaultModel="gpt-5.4",
        )

        assert result["updated"] is True
        assert entry.get("providerOverride") == "openrouter"
        assert entry.get("modelOverride") == "anthropic/claude-haiku-4.5"
        assert entry.get("modelOverrideSource") == "user"
        assert entry.get("modelProvider") is None
        assert entry.get("model") is None
        assert entry.get("contextTokens") is None
        assert (entry.get("updatedAt") or 0) > before

    def test_clears_provider_wrapped_override_that_matches_configured_default(self) -> None:
        before = int(time.time() * 1000) - 5_000
        entry: dict[str, Any] = {
            "sessionId": "sess-openrouter-repair-default",
            "updatedAt": before,
            "providerOverride": "anthropic",
            "modelOverride": "claude-haiku-4.5",
            "modelOverrideSource": "user",
        }

        result = repair_provider_wrapped_model_override(
            entry=entry,
            defaultProvider="openrouter",
            defaultModel="anthropic/claude-haiku-4.5",
        )

        assert result["updated"] is True
        assert entry.get("providerOverride") is None
        assert entry.get("modelOverride") is None
        assert entry.get("modelOverrideSource") is None
        assert (entry.get("updatedAt") or 0) > before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
