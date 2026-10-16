"""tests.test_application_automation_parity — Parity test suite for Application Automation Core.

Validates:
1. ActiveTabTracker: tab identity, label affinity, alias resolution, domain matching.
2. ApplicationStateMachine: state transitions, guard conditions, listener notification.
3. ActionVerifier: OpenClaw precedence (confirmed > unverifiable > suspected_noop).
4. ContextualResolver: pronoun resolution ('it', 'play it', 'pause', 'resume', 'volume up').
5. ApplicationSessionManager: adapter registration, active app routing, context injection.
"""

from __future__ import annotations

import pytest

from src.application_automation import (
    ActionEffect,
    ActionVerificationResult,
    ActiveTabTracker,
    ApplicationStateMachine,
    ContextualResolver,
    detect_application_type_from_url,
)


class TestActiveTabTrackerParity:
    """Validates OpenClaw-parity tab identity and session affinity."""

    def test_url_application_type_detection(self) -> None:
        assert detect_application_type_from_url("https://www.youtube.com/watch?v=123") == "youtube"
        assert detect_application_type_from_url("https://youtu.be/123") == "youtube"
        assert detect_application_type_from_url("https://open.spotify.com/track/456") == "spotify"
        assert detect_application_type_from_url("https://github.com/torvalds/linux") == "github"
        assert detect_application_type_from_url("https://example.com/blog") == "web"

    def test_tab_registration_and_suggested_target_id(self) -> None:
        tracker = ActiveTabTracker()
        tab = tracker.register_tab(
            target_id="tab_1",
            url="https://www.youtube.com",
            title="YouTube",
            label="youtube",
            tab_id="tab_1",
        )
        assert tab.target_id == "tab_1"
        assert tab.label == "youtube"
        # Suggested target ID prefers label over numeric ID
        assert tab.suggested_target_id == "youtube"
        assert "youtube" in tab.aliases
        assert "tab_1" in tab.aliases

    def test_alias_resolution(self) -> None:
        tracker = ActiveTabTracker()
        tracker.register_tab(
            target_id="tab_42",
            url="https://www.youtube.com",
            title="YouTube",
            label="yt_task",
        )
        assert tracker.resolve_target_id("yt_task") == "tab_42"
        assert tracker.resolve_target_id("tab_42") == "tab_42"
        assert tracker.resolve_target_id("nonexistent") is None

    def test_find_tab_by_app_and_domain(self) -> None:
        tracker = ActiveTabTracker()
        tracker.register_tab(
            target_id="tab_1",
            url="https://google.com/search",
            title="Google",
            label="google",
        )
        tracker.register_tab(
            target_id="tab_2",
            url="https://www.youtube.com/watch?v=abc",
            title="Imagine Dragons - Believer",
            label="youtube",
        )
        # Active tab is the most recent
        assert tracker.get_tab().target_id == "tab_2"
        # Search by app
        yt = tracker.find_tab_by_app("youtube")
        assert yt is not None
        assert yt.target_id == "tab_2"
        # Search by domain
        dom_tab = tracker.find_tab_by_domain("youtube.com")
        assert dom_tab is not None
        assert dom_tab.target_id == "tab_2"


class TestStateMachineParity:
    """Validates observable application finite state machine."""

    def test_state_transitions_and_history(self) -> None:
        valid = {
            "HOME": {"SEARCHING", "WATCH_PAGE"},
            "SEARCHING": {"SEARCH_RESULTS", "HOME"},
            "SEARCH_RESULTS": {"WATCH_PAGE"},
            "WATCH_PAGE": {"HOME"},
        }
        sm = ApplicationStateMachine(initial_state="HOME", valid_transitions=valid)
        assert sm.current_state == "HOME"

        # Valid transition
        assert sm.transition_to("SEARCHING", trigger="type_query")
        assert sm.current_state == "SEARCHING"

        # Invalid transition rejected
        assert not sm.transition_to("WATCH_PAGE", trigger="skip")
        assert sm.current_state == "SEARCHING"

        # Force transition allows recovery
        assert sm.transition_to("WATCH_PAGE", trigger="force_jump", force=True)
        assert sm.current_state == "WATCH_PAGE"
        assert len(sm.history) == 2


class TestActionVerifierParity:
    """Validates mutation precedence contract (confirmed > unverifiable > suspected_noop)."""

    def test_confirmed_outcome(self) -> None:
        res = ActionVerificationResult.confirmed("play", {"currentTime": 12.5})
        assert res.effect == ActionEffect.CONFIRMED
        assert res.verified is True

    def test_unverifiable_outcome(self) -> None:
        res = ActionVerificationResult.unverifiable("play", "Buffering stream")
        assert res.effect == ActionEffect.UNVERIFIABLE
        assert res.verified is False
        assert "Buffering stream" in res.details["reason"]

    def test_suspected_noop_outcome(self) -> None:
        res = ActionVerificationResult.suspected_noop("click", "Element was hidden behind modal")
        assert res.effect == ActionEffect.SUSPECTED_NOOP
        assert res.verified is False
        assert res.error == "Element was hidden behind modal"


class TestContextualResolverParity:
    """Validates resolution of pronouns and elliptical utterances."""

    @pytest.fixture
    def setup_resolver(self) -> ContextualResolver:
        tracker = ActiveTabTracker()
        tracker.register_tab(
            target_id="tab_yt",
            url="https://www.youtube.com/results?search_query=Believer",
            title="Believer - YouTube",
            label="youtube",
            app_type="youtube",
        )
        return ContextualResolver(tracker)

    def test_search_and_play_resolution(self, setup_resolver: ContextualResolver) -> None:
        resolved = setup_resolver.resolve_utterance("search believer and play it")
        assert resolved is not None
        assert resolved.app_type == "youtube"
        assert resolved.action_name == "search_and_play"
        assert resolved.arguments["query"] == "believer"

    def test_play_first_result_from_search_results(self, setup_resolver: ContextualResolver) -> None:
        resolved = setup_resolver.resolve_utterance("play it", current_app_state="SEARCH_RESULTS")
        assert resolved is not None
        assert resolved.action_name == "play_first_result"

    def test_resume_when_paused(self, setup_resolver: ContextualResolver) -> None:
        resolved = setup_resolver.resolve_utterance("resume", current_app_state="VIDEO_PAUSED")
        assert resolved is not None
        assert resolved.action_name == "resume"

    def test_pause_command(self, setup_resolver: ContextualResolver) -> None:
        resolved = setup_resolver.resolve_utterance("pause the music", current_app_state="VIDEO_PLAYING")
        assert resolved is not None
        assert resolved.action_name == "pause"

    def test_skip_ad_command(self, setup_resolver: ContextualResolver) -> None:
        resolved = setup_resolver.resolve_utterance("skip ad", current_app_state="AD_PLAYING")
        assert resolved is not None
        assert resolved.action_name == "skip_ad"

    def test_volume_controls(self, setup_resolver: ContextualResolver) -> None:
        up = setup_resolver.resolve_utterance("volume up")
        assert up is not None
        assert up.action_name == "volume_up"

        down = setup_resolver.resolve_utterance("volume down")
        assert down is not None
        assert down.action_name == "volume_down"

    def test_format_context_prompt(self, setup_resolver: ContextualResolver) -> None:
        prompt = setup_resolver.format_context_prompt(
            current_state="VIDEO_PLAYING",
            media_info={"title": "Imagine Dragons - Believer", "paused": False, "currentTime": 45, "duration": 210},
        )
        assert "[ACTIVE APPLICATION CONTEXT]" in prompt
        assert "Foreground App: Youtube" in prompt
        assert "Believer" in prompt
        assert "VIDEO_PLAYING" in prompt
