"""tests.test_browser_reliability_architecture — Comprehensive test suite for OpenClaw browser parity.

Validates all 22 required scenarios from the Master Engineering Prompt:
1. Open YouTube when already open (reuse same tab).
2. Search multiple queries without opening redundant tabs.
3. User manually changes tab (target tracking).
4. User manually navigates to another page (URL sync).
5. Subscribe when already subscribed (already_completed detection, zero duplicate clicks).
6. Subscribe when not subscribed (click + post-action observation + effect verified).
7. Selector changes (resilient semantic resolution).
8. Snapshot becomes stale (contextEpoch invalidation & StaleObservationError).
9. Target tab closes (TargetStaleError auto-recovery).
10. Browser redirects to Google login (auth boundary detected, stops automation).
11. Google asks for passkey (human verification required).
12. Google asks for 2FA (human verification required).
13. CAPTCHA appears (human verification required).
14. Click returns ok=true but effect does not happen (completed_unverified / suspected_noop).
15. Click succeeds and effect is verified (completed_verified with DOM evidence).
16. User changes task mid-execution (cancellation & abort).
17. Delayed model tool call arrives after turn ended (stale turn rejection).
18. Same action requested twice (idempotency guard & already_completed).
19. Browser disconnects (graceful recovery).
20. Wrong application / channel open (WrongTabError).
21. Continuation vs new task classification.
22. Action fails after side-effect may have occurred (re-observe before retry).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.task.runtime_state import RuntimeState, RuntimeStateManager, TaskStatus
from src.agents.task.stage_reporter import StagePhase, StageReporter
from src.agents.task.task_classifier import BrowserIntent, BrowserTaskClassifier
from src.agents.task.task_state_machine import TaskStage, TaskStateMachine, create_youtube_subscription_workflow
from src.application_automation.action_contracts import (
    ActionContract,
    ActionRejectedError,
    ActionRejectionCode,
    ActionTargetSpec,
    PreconditionChecker,
)
from src.application_automation.action_verifier import ActionEffect
from src.application_automation.active_tab_tracker import ActiveTabTracker
from src.application_automation.applications.youtube.actions import YouTubeActions
from src.application_automation.applications.youtube.adapter import YouTubeAdapter
from src.application_automation.applications.youtube.verifier import YouTubeVerifier
from src.application_automation.auth_manager import AuthBoundaryManager, AuthStage, sanitize_secrets
from src.application_automation.browser_target_manager import (
    BrowserTargetManager,
    TargetStaleError,
    WrongTabError,
)
from src.application_automation.observation_manager import (
    ObservationManager,
    PageObservation,
    SemanticElement,
    StaleObservationError,
)
from src.application_automation.recovery_engine import FailureClassification, RecoveryEngine, RetryClass
from src.application_automation.verification_engine import VerificationEngine, VerificationStatus


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 & 2: Tab Reuse & Multi-Query Search Without Redundant Tabs
# ─────────────────────────────────────────────────────────────────────────────
def test_tab_reuse_and_multi_query():
    """Scenario 1 & 2: Reuse active YouTube tab and track URL without opening redundant tabs."""
    tracker = ActiveTabTracker()
    tracker.register_tab(target_id="tab_yt_1", url="https://www.youtube.com", label="youtube")

    # Search query 1
    tab1 = tracker.get_active_tab_for_app("youtube")
    assert tab1 is not None
    assert tab1.target_id == "tab_yt_1"

    # Search query 2: should re-use same tab
    tracker.register_tab(target_id="tab_yt_1", url="https://www.youtube.com/results?search_query=tere+naam")
    tab2 = tracker.get_active_tab_for_app("youtube")
    assert tab2 is not None
    assert tab2.target_id == "tab_yt_1"
    assert "tere+naam" in tab2.url


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 & 4: Target Tab Validation & URL Change Detection
# ─────────────────────────────────────────────────────────────────────────────
def test_target_validation_and_url_tracking():
    """Scenario 3 & 4: Confirm target is validated against open tabs and URL changes are reflected."""
    target_mgr = BrowserTargetManager()
    target_mgr.register_target(target_id="tab_1", url="https://www.youtube.com")

    runtime_tabs = [{"targetId": "tab_1", "url": "https://www.youtube.com/watch?v=123", "title": "Song Video"}]
    ctx = target_mgr.validate_target("tab_1", expected_app="youtube", runtime_tabs=runtime_tabs)
    assert ctx.target_id == "tab_1"
    assert ctx.url == "https://www.youtube.com/watch?v=123"
    assert ctx.app_type == "youtube"


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Subscribe When Already Subscribed (Zero Clicks, already_completed)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_subscribe_when_already_subscribed():
    """Scenario 5: Pre-action check detects already subscribed channel; zero clicks executed."""
    mock_page = MagicMock()
    # Mock DOM evaluate returning is_subscribed: True
    mock_page.evaluate = AsyncMock(return_value={"found": True, "is_subscribed": True, "text": "Subscribed"})
    mock_page.query_selector = AsyncMock()

    res = await YouTubeActions.subscribe(mock_page)
    assert res.is_ok
    data = res.unwrap()
    assert data["already_subscribed"] is True
    assert data["status"] == "already_completed"
    # Ensure query_selector (click) was NEVER called!
    mock_page.query_selector.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Subscribe When Not Subscribed (Click Dispatched and Verified)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_subscribe_when_not_subscribed():
    """Scenario 6: Pre-action check detects not subscribed; locates button, clicks, and verifies."""
    mock_page = MagicMock()
    # First evaluate: not subscribed
    mock_page.evaluate = AsyncMock(return_value={"found": True, "is_subscribed": False, "text": "Subscribe"})
    mock_button = MagicMock()
    mock_button.is_visible = AsyncMock(return_value=True)
    mock_button.inner_text = AsyncMock(return_value="Subscribe")
    mock_button.get_attribute = AsyncMock(return_value=None)
    mock_button.click = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=mock_button)

    res = await YouTubeActions.subscribe(mock_page)
    assert res.is_ok
    data = res.unwrap()
    assert data["clicked"] is True
    assert data["already_subscribed"] is False
    mock_button.click.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Resilient Semantic Selector Resolution
# ─────────────────────────────────────────────────────────────────────────────
def test_semantic_element_resolution():
    """Scenario 7: Resolve target via semantic role & accessible name rather than brittle CSS."""
    obs_mgr = ObservationManager()
    elem = SemanticElement(ref="ax42", role="button", name="Subscribe", selector="ytd-subscribe-button button")
    obs = obs_mgr.record_snapshot(
        target_id="tab_1",
        url="https://www.youtube.com/@mrbeast",
        parsed_elements=[elem],
    )

    # Resolve by role and name
    resolved = obs_mgr.resolve_element(
        target_id="tab_1",
        observation_id=obs.observation_id,
        role="button",
        name="Subscribe",
    )
    assert resolved.ref == "ax42"
    assert resolved.name == "Subscribe"


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: Stale Observation Invalidation & StaleObservationError
# ─────────────────────────────────────────────────────────────────────────────
def test_stale_observation_invalidation():
    """Scenario 8: Context epoch increments on navigation; older observation_id raises StaleObservationError."""
    obs_mgr = ObservationManager()
    elem = SemanticElement(ref="ax1", role="button", name="Play")
    obs1 = obs_mgr.record_snapshot(target_id="tab_1", url="https://youtube.com", parsed_elements=[elem])

    # Navigation invalidates epoch
    obs_mgr.invalidate_target_epoch("tab_1", reason="navigation_to_video")
    obs2 = obs_mgr.record_snapshot(target_id="tab_1", url="https://youtube.com/watch?v=xyz")

    # Attempting to resolve with obs1 must raise StaleObservationError
    with pytest.raises(StaleObservationError) as exc_info:
        obs_mgr.resolve_element(target_id="tab_1", observation_id=obs1.observation_id, ref="ax1")
    assert "obsolete" in str(exc_info.value).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: TargetStaleError and Tab Auto-Recovery
# ─────────────────────────────────────────────────────────────────────────────
def test_target_stale_error_and_recovery():
    """Scenario 9: Closed target raises TargetStaleError; manager recovers candidate tab."""
    target_mgr = BrowserTargetManager()
    target_mgr.register_target("tab_old", url="https://www.youtube.com")

    # Runtime tabs where tab_old has been closed and replaced by tab_new
    runtime_tabs = [{"targetId": "tab_new", "url": "https://www.youtube.com/watch?v=abc", "title": "New Video"}]

    with pytest.raises(TargetStaleError):
        target_mgr.validate_target("tab_old", runtime_tabs=runtime_tabs)

    # Recover target
    recovered = target_mgr.recover_stale_target(
        stale_target_id="tab_old",
        desired_app="youtube",
        runtime_tabs=runtime_tabs,
    )
    assert recovered is not None
    assert recovered.target_id == "tab_new"
    assert recovered.app_type == "youtube"


# ─────────────────────────────────────────────────────────────────────────────
# Test 10, 11, 12, 13: Google Auth Boundary Detection (Password, 2FA, Passkey, CAPTCHA)
# ─────────────────────────────────────────────────────────────────────────────
def test_auth_boundary_detection():
    """Scenario 10-13: Detect Google authentication gates and require human verification."""
    auth_mgr = AuthBoundaryManager()

    # Normal page
    res_normal = auth_mgr.detect_auth_boundary("https://www.youtube.com")
    assert not res_normal.is_auth_page

    # Password page
    res_pwd = auth_mgr.detect_auth_boundary("https://accounts.google.com/signin/v2/challenge/pwd", "Enter your password")
    assert res_pwd.is_auth_page
    assert res_pwd.stage == AuthStage.PASSWORD_ENTRY
    assert res_pwd.requires_human

    # 2FA page
    res_2fa = auth_mgr.detect_auth_boundary("https://accounts.google.com/signin/v2/challenge/totp", "2-Step Verification")
    assert res_2fa.stage == AuthStage.TWO_FACTOR
    assert res_2fa.requires_human

    # Passkey page
    res_passkey = auth_mgr.detect_auth_boundary("https://accounts.google.com/signin", "Use your passkey")
    assert res_passkey.stage == AuthStage.PASSKEY
    assert res_passkey.requires_human

    # CAPTCHA challenge
    res_captcha = auth_mgr.detect_auth_boundary("https://accounts.google.com/ServiceLogin", "Please solve this captcha")
    assert res_captcha.stage == AuthStage.CAPTCHA
    assert res_captcha.requires_human


def test_secret_sanitization():
    """Scenario 10: Zero password leakage in logs and tool results."""
    raw = {
        "user": "kcs23",
        "password": "SuperSecretPassword123!",
        "api_key": "AIzaSySecretToken",
        "nested": {"token": "my_jwt_token", "info": "public"},
    }
    sanitized = sanitize_secrets(raw)
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["token"] == "[REDACTED]"
    assert sanitized["nested"]["info"] == "public"


# ─────────────────────────────────────────────────────────────────────────────
# Test 14 & 15: Post-Action Verification Precedence (Confirmed vs Suspected Noop)
# ─────────────────────────────────────────────────────────────────────────────
def test_verification_engine_precedence():
    """Scenario 14 & 15: effect: confirmed > unverifiable > suspected_noop."""
    ver_engine = VerificationEngine()
    contract = ActionContract(
        action_id="act_sub_1",
        expected_postconditions=["subscription_state_changes"],
    )

    elem_before = SemanticElement(ref="ax1", role="button", name="Subscribe")
    obs_before = PageObservation(
        observation_id="obs_1", target_id="tab_1", url="https://youtube.com/@test", title="Test",
        epoch=1, elements=[elem_before], raw_aria_tree="button: Subscribe"
    )

    # Case A: Click executed, but post-observation button STILL says "Subscribe" (No-op!)
    obs_noop = PageObservation(
        observation_id="obs_2", target_id="tab_1", url="https://youtube.com/@test", title="Test",
        epoch=2, elements=[elem_before], raw_aria_tree="button: Subscribe"
    )
    outcome_noop = ver_engine.verify_action_effect(
        contract=contract,
        pre_obs=obs_before,
        tool_result={"ok": True},
        post_obs=obs_noop,
    )
    assert outcome_noop.status == VerificationStatus.COMPLETED_UNVERIFIED
    assert outcome_noop.effect == ActionEffect.SUSPECTED_NOOP
    assert not outcome_noop.passed

    # Case B: Click executed, and post-observation button changed to "Subscribed" (Confirmed!)
    elem_after = SemanticElement(ref="ax1", role="button", name="Subscribed")
    obs_confirmed = PageObservation(
        observation_id="obs_3", target_id="tab_1", url="https://youtube.com/@test", title="Test",
        epoch=3, elements=[elem_after], raw_aria_tree="button: Subscribed"
    )
    outcome_confirmed = ver_engine.verify_action_effect(
        contract=contract,
        pre_obs=obs_before,
        tool_result={"ok": True},
        post_obs=obs_confirmed,
    )
    assert outcome_confirmed.status == VerificationStatus.COMPLETED_VERIFIED
    assert outcome_confirmed.effect == ActionEffect.CONFIRMED
    assert outcome_confirmed.passed
    assert len(outcome_confirmed.evidence) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 16: Task Cancellation Mid-Execution
# ─────────────────────────────────────────────────────────────────────────────
def test_task_cancellation():
    """Scenario 16: User cancels task; PreconditionChecker immediately rejects further actions."""
    state_mgr = RuntimeStateManager()
    state_mgr.begin_user_turn("turn_1", "Play Tere Naam")
    state_mgr.cancel_active_task(reason="user_cancel")

    checker = PreconditionChecker(state_mgr=state_mgr)
    contract = ActionContract(action_id="act_1", turn_id="turn_1", target_id="tab_1")

    with pytest.raises(ActionRejectedError) as exc_info:
        checker.validate_and_admit_action(contract)
    assert exc_info.value.code == ActionRejectionCode.TASK_CANCELLED


# ─────────────────────────────────────────────────────────────────────────────
# Test 17: Delayed Out-of-Turn Tool Call Rejection
# ─────────────────────────────────────────────────────────────────────────────
def test_delayed_stale_tool_call_rejection():
    """Scenario 17: Tool call arriving with previous turn_id is rejected with STALE_TURN."""
    state_mgr = RuntimeStateManager()
    # User is currently on turn_2
    state_mgr.begin_user_turn("turn_2", "What is the weather?")

    checker = PreconditionChecker(state_mgr=state_mgr)
    # Stale model response from turn_1
    stale_contract = ActionContract(action_id="act_late", turn_id="turn_1", target_id="tab_1")

    with pytest.raises(ActionRejectedError) as exc_info:
        checker.validate_and_admit_action(stale_contract)
    assert exc_info.value.code == ActionRejectionCode.STALE_TURN


# ─────────────────────────────────────────────────────────────────────────────
# Test 18: Retry Budget & Idempotency Protection on Duplicate Side-Effects
# ─────────────────────────────────────────────────────────────────────────────
def test_retry_budget_and_idempotency_guard():
    """Scenario 18 & 22: Forbids blind retries and limits retry budget to exactly 1."""
    recovery = RecoveryEngine()
    recovery.reset_budget("task_sub")
    contract = ActionContract(
        task_id="task_sub",
        action_type="subscribe",
        target=ActionTargetSpec(role="button", name="Subscribe"),
    )

    assert recovery.can_retry(contract)
    recovery.record_retry(contract)

    # Second retry attempt must be refused by budget
    assert not recovery.can_retry(contract)
    plan = recovery.analyze_failure(contract, "Timeout exceeded")
    assert not plan.is_safe_to_retry
    assert plan.retry_class == RetryClass.UNSAFE_DUPLICATE_ACTION


# ─────────────────────────────────────────────────────────────────────────────
# Test 19: Disconnected Browser Graceful Recovery
# ─────────────────────────────────────────────────────────────────────────────
def test_recovery_plan_on_stale_target():
    """Scenario 19: Classifies stale tab and recommends tab re-discovery."""
    recovery = RecoveryEngine()
    recovery.reset_budget()
    contract = ActionContract(task_id="t1", action_type="click", target=ActionTargetSpec(role="button"))

    plan = recovery.analyze_failure(contract, "TargetStaleError: Target not found")
    assert plan.failure_type == FailureClassification.STALE_TARGET
    assert plan.retry_class == RetryClass.SAFE_TARGET_RECOVERY
    assert plan.is_safe_to_retry


# ─────────────────────────────────────────────────────────────────────────────
# Test 20: Wrong Application Tab Prevention
# ─────────────────────────────────────────────────────────────────────────────
def test_wrong_tab_prevention():
    """Scenario 20: Prevents operating on a Google or Gmail tab when expecting YouTube."""
    target_mgr = BrowserTargetManager()
    target_mgr.register_target("tab_google", url="https://www.google.com")

    with pytest.raises(WrongTabError) as exc_info:
        target_mgr.validate_target("tab_google", expected_app="youtube")
    assert "Expected application 'youtube'" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# Test 21: Continuation vs New Task Intent Classification
# ─────────────────────────────────────────────────────────────────────────────
def test_browser_task_classification():
    """Scenario 21: Classifies continuation vs new task vs cancellation vs unrelated questions."""
    # A. Continuation referencing active session
    res_cont = BrowserTaskClassifier.classify(
        "Now subscribe to that channel",
        active_app="youtube",
        has_active_session=True,
    )
    assert res_cont.intent == BrowserIntent.CONTINUATION
    assert res_cont.reuse_active_session is True

    # B. Correction
    res_corr = BrowserTaskClassifier.classify("No, play the second one", active_app="youtube", has_active_session=True)
    assert res_corr.intent == BrowserIntent.CORRECTION

    # C. Unrelated question
    res_unrelated = BrowserTaskClassifier.classify("What is the speed of light?", active_app="youtube", has_active_session=True)
    assert res_unrelated.intent == BrowserIntent.UNRELATED_QUESTION
    assert res_unrelated.reuse_active_session is False

    # D. Cancellation
    res_cancel = BrowserTaskClassifier.classify("Stop, cancel this", active_app="youtube", has_active_session=True)
    assert res_cancel.intent == BrowserIntent.CANCELLATION


# ─────────────────────────────────────────────────────────────────────────────
# Test 22: Explicit Task Stages Progression (TaskStateMachine)
# ─────────────────────────────────────────────────────────────────────────────
def test_task_state_machine_workflow():
    """Explicit 13-stage subscription workflow verification."""
    wf = create_youtube_subscription_workflow()
    assert wf.current_stage is not None
    assert wf.current_stage.stage_id == "stage_1"

    # Advance stage with verified status
    next_stage = wf.advance_stage(verified=True, result={"channel": "MrBeast"})
    assert next_stage is not None
    assert next_stage.stage_id == "stage_2"

    # Test already_completed handling
    stage7 = wf.stages["stage_7"]
    wf.current_stage_index = 6  # at stage_7: check_already_subscribed
    wf.advance_stage(verified=True, already_completed=True)
    assert wf.state_mgr.state.task_status == TaskStatus.ALREADY_COMPLETED


# ─────────────────────────────────────────────────────────────────────────────
# Test 23: Unsubscribe & Spoken Continuity Classification
# ─────────────────────────────────────────────────────────────────────────────
def test_browser_task_classification_unsubscribe_and_nepali():
    """Verify unsubscribe commands in English & Nepali maintain active session continuity."""
    for phrase in ("unsubscribe gardau", "unsubscribe gara", "unsub", "aba unsubscribe gardeu"):
        res = BrowserTaskClassifier.classify(
            phrase,
            active_app="youtube",
            has_active_session=True,
        )
        assert res.intent == BrowserIntent.CONTINUATION
        assert res.reuse_active_session is True
        assert res.target_application == "youtube"


def test_intent_classifier_youtube_subscription_and_search():
    """Verify IntentClassifier accurately maps subscribe, unsubscribe, and search turns."""
    from src.agents.decision.intent import IntentClassifier

    res_sub = IntentClassifier.classify("subscribe gara")
    assert res_sub.primary_tool == "youtube_subscribe"
    assert res_sub.is_actionable is True

    res_unsub = IntentClassifier.classify("unsubscribe gardau")
    assert res_unsub.primary_tool == "youtube_unsubscribe"
    assert res_unsub.is_actionable is True

    res_search = IntentClassifier.classify("youtube ma mrbeast search gara")
    assert res_search.primary_tool == "youtube_search"
    assert res_search.parameters.get("query") == "mrbeast"


def test_speech_guard_preserves_and_repairs_subscription_tools():
    """Verify SpeechGroundingGuard protects youtube_subscribe and youtube_unsubscribe tools."""
    from src.talk.speech_guard import SpeechGroundingGuard

    guard = SpeechGroundingGuard()

    # Model calls youtube_subscribe on 'subscribe gara'
    res_sub = guard.validate_voice_tool_call("youtube_subscribe", {}, "subscribe gara")
    assert res_sub.is_allowed is True

    # Model calls browser on 'unsubscribe gardau' -> repaired to youtube_unsubscribe
    res_unsub = guard.validate_voice_tool_call("browser", {"action": "click"}, "unsubscribe gardau")
    assert res_unsub.is_allowed is True
    assert res_unsub.repaired_tool_name == "youtube_unsubscribe"

    # Model calls open_path on YouTube search -> repaired to browser with youtube.com search url
    res_search = guard.validate_voice_tool_call("open_path", {"target": "veritasium"}, "search veritasium on youtube")
    assert res_search.is_allowed is True
    assert res_search.repaired_tool_name == "browser"
    assert "youtube.com" in res_search.repaired_args.get("url", "")


def test_intent_classifier_youtube_close_and_tab_isolation():
    """Verify 'youtube banda gara' routes to youtube_close and is NEVER classified as process kill."""
    from src.agents.decision.intent import IntentClassifier, IntentCategory

    for phrase in ("youtube banda gara", "youtube tab banda gara", "close youtube", "youtube close gara", "yt banda gara"):
        res = IntentClassifier.classify(phrase)
        assert res.primary_tool == "youtube_close", f"Failed for {phrase}: got {res.primary_tool}"
        assert res.category == IntentCategory.ACTIONABLE_BROWSER
        assert res.is_actionable is True
        assert "Do NOT close the browser window or kill Chrome" in res.action_bias_directive

    # Generic tab close
    res_tab = IntentClassifier.classify("tab banda gara")
    assert res_tab.primary_tool == "browser"
    assert res_tab.parameters.get("action") == "close"
    assert res_tab.category == IntentCategory.ACTIONABLE_BROWSER


def test_speech_guard_preserves_and_repairs_youtube_close():
    """Verify SpeechGroundingGuard prevents killing Chrome on 'youtube banda gara' and ensures tab close."""
    from src.talk.speech_guard import SpeechGroundingGuard

    guard = SpeechGroundingGuard()

    # Model tries to call youtube_close -> allowed directly
    res_close = guard.validate_voice_tool_call("youtube_close", {}, "youtube banda gara")
    assert res_close.is_allowed is True
    assert res_close.repaired_tool_name is None

    # Model tries to call browser(action='close') -> allowed directly
    res_browser_close = guard.validate_voice_tool_call("browser", {"action": "close"}, "youtube banda gara")
    assert res_browser_close.is_allowed is True

    # Model erroneously calls process(action='kill', session_id='youtube') -> intercepted & repaired to youtube_close!
    res_proc_kill = guard.validate_voice_tool_call("process", {"action": "kill", "session_id": "youtube"}, "youtube banda gara")
    assert res_proc_kill.is_allowed is True
    # SpeechGroundingGuard Scenario B catches ACTIONABLE_BROWSER and repairs it to youtube_close
    assert res_proc_kill.repaired_tool_name == "youtube_close"


@pytest.mark.asyncio
async def test_process_tool_safety_guard_for_youtube():
    """Verify process_tool intercepts action='kill' with session_id='youtube' and safely closes tab without taskkill."""
    from src.agents.sessions.tools.process_tool import create_process_tool_definition
    from src.application_automation.tools.youtube_tools import set_youtube_provider
    from src.application_automation.providers.youtube_provider import YouTubeProvider
    from jarvis_sdk import Ok

    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.close = AsyncMock(
        return_value=Ok({"action": "close", "status": "closed", "message": "Closed YouTube tab. Other browser tabs remain open."})
    )
    set_youtube_provider(mock_provider)

    try:
        proc_def = create_process_tool_definition()
        res = await proc_def["execute"]("call_1", {"action": "kill", "session_id": "youtube"})

        assert res["details"]["killed"] is True
        assert res["details"]["tab_closed"] is True
        assert "Closed YouTube tab" in res["content"][0]["text"]
        mock_provider.close.assert_awaited_once()
    finally:
        set_youtube_provider(None)


def test_intent_classifier_pheri_subscribe_and_unsubscribe():
    """Verify IntentClassifier accurately recognizes resubscribe, unsubscribe, and state intents."""
    from src.agents.decision.intent import IntentClassifier

    # Subscribe / Resubscribe
    res1 = IntentClassifier.classify("pheri subscribe gara")
    assert res1.primary_tool == "youtube_subscribe"

    res2 = IntentClassifier.classify("subscribe again")
    assert res2.primary_tool == "youtube_subscribe"

    res3 = IntentClassifier.classify("channel subscribe")
    assert res3.primary_tool == "youtube_subscribe"

    # Unsubscribe
    res4 = IntentClassifier.classify("unsubscribe gardau")
    assert res4.primary_tool == "youtube_unsubscribe"

    res5 = IntentClassifier.classify("pheri unsubscribe gara")
    assert res5.primary_tool == "youtube_unsubscribe"

    res6 = IntentClassifier.classify("unsub again")
    assert res6.primary_tool == "youtube_unsubscribe"

    # State & Perception
    res7 = IntentClassifier.classify("youtube status")
    assert res7.primary_tool == "youtube_get_state"

    res8 = IntentClassifier.classify("subscribed cha ki chaina")
    assert res8.primary_tool == "youtube_get_state"


def test_speech_guard_resubscription_continuity():
    """Verify SpeechGroundingGuard validates or repairs resubscription and state queries."""
    from src.talk.speech_guard import SpeechGroundingGuard

    guard = SpeechGroundingGuard()

    # Resubscribe direct tool allowed
    r1 = guard.validate_voice_tool_call("youtube_subscribe", {}, "pheri subscribe gara")
    assert r1.is_allowed is True
    assert r1.repaired_tool_name is None

    # Resubscribe called via generic browser tool repaired to youtube_subscribe
    r2 = guard.validate_voice_tool_call("browser", {"action": "click"}, "pheri subscribe gara")
    assert r2.is_allowed is True
    assert r2.repaired_tool_name == "youtube_subscribe"

    # Unsubscribe direct tool allowed
    r3 = guard.validate_voice_tool_call("youtube_unsubscribe", {}, "unsubscribe gardau")
    assert r3.is_allowed is True
    assert r3.repaired_tool_name is None

    # State check tool allowed
    r4 = guard.validate_voice_tool_call("youtube_get_state", {}, "youtube status")
    assert r4.is_allowed is True
    assert r4.repaired_tool_name is None


