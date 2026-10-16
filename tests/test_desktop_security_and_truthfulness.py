"""Tests for desktop automation confirmation gating and anti-hallucination truthfulness grounding."""

from src.desktop_automation.security.confirmation_manager import ConfirmationManager
from src.agents.decision.truthfulness import ClaimGroundingFilter


def test_confirmation_manager_gating():
    # Sensitive action without confirmation
    assert ConfirmationManager.requires_confirmation("call_contact", {"call_type": "voice"}) is True
    assert ConfirmationManager.requires_confirmation("delete_file", {}) is True
    assert ConfirmationManager.requires_confirmation("whatsapp_send", {}) is False

    prompt = ConfirmationManager.build_confirmation_prompt("call_contact", {"recipient": "Boss"})
    assert "confirm" in prompt.lower()
    assert "Boss" in prompt


def test_claim_grounding_filter_blocks_unverified_desktop_actions():
    # 1. Model claims it sent a message to Aakash on WhatsApp, but no desktop tool ran
    res1 = ClaimGroundingFilter.validate_and_ground(
        "I have sent the message to Aakash on WhatsApp.",
        recent_actions=[],
    )
    assert res1.is_truthful is False
    assert res1.verified_evidence_found is False
    assert "have not executed that action yet" in res1.grounded_text

    # 2. Model claims it calculated something, but no calculator/desktop tool ran
    res2 = ClaimGroundingFilter.validate_and_ground(
        "I have calculated 50 * 20 = 1000 for you.",
        recent_actions=[],
    )
    assert res2.is_truthful is False
    assert "have not executed that action yet" in res2.grounded_text

    # 3. Model claims it saved the document, but no editor/desktop tool ran
    res3 = ClaimGroundingFilter.validate_and_ground(
        "I have saved the document successfully.",
        recent_actions=[],
    )
    assert res3.is_truthful is False

    # 4. Model claims it sent the message, and desktop tool executed successfully
    res4 = ClaimGroundingFilter.validate_and_ground(
        "I have sent the message to Aakash.",
        recent_actions=[{"tool": "desktop", "status": "success"}],
    )
    assert res4.is_truthful is True
    assert res4.verified_evidence_found is True

    # 5. Model claims it sent the message, but desktop tool failed
    res5 = ClaimGroundingFilter.validate_and_ground(
        "I have sent the message to Aakash.",
        recent_actions=[{"tool": "desktop", "status": "failed", "detail": "Window not found"}],
    )
    assert res5.is_truthful is False
    assert "did not succeed" in res5.grounded_text
