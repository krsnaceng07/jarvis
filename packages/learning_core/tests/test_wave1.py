"""tests for jarvis_learning — Wave 1 integration and unit tests.

Proves:
1. Experience persistence across simulated restart
2. Strategy learning from corrections
3. Outcome verification catches false claims
4. Reflection produces lessons and strategies
5. Reward scoring works correctly
6. Feedback collection works
7. Knowledge deduplication works
8. Full closed-loop: record → verify → reflect → retrieve
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis_learning import (
    Experience,
    FeedbackCollector,
    ImplicitFeedbackDetector,
    KnowledgeStore,
    LearningEngine,
    LearningEvent,
    LearningEventBus,
    RewardScorer,
    RewardWeights,
    Strategy,
    StrategyStore,
    TaskEpisode,
    TaskStep,
    CompositeVerifier,
    ToolResultVerifier,
    ClaimVerifier,
    generate_id,
    now_ms,
)
from jarvis_learning.storage.learning_db import LearningDatabase


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path: Path) -> LearningDatabase:
    """Create a temporary learning database."""
    return LearningDatabase(tmp_path / "test_learning.sqlite")


@pytest.fixture
def engine(tmp_path: Path) -> LearningEngine:
    """Create a learning engine with a temporary database."""
    eng = LearningEngine(db_path=str(tmp_path / "test_learning.sqlite"))
    eng.startup()
    return eng


# ── Experience Data Types ─────────────────────────────────────


class TestTaskStep:
    def test_create_and_serialize(self) -> None:
        step = TaskStep(
            step_index=0,
            tool_name="browser.open",
            tool_args={"url": "https://youtube.com"},
            tool_result_summary="Opened tab 3",
            step_outcome="success",
            verification_status="verified_success",
            duration_ms=150,
        )
        d = step.to_dict()
        assert d["tool_name"] == "browser.open"
        assert d["step_outcome"] == "success"
        roundtrip = TaskStep.from_dict(d)
        assert roundtrip.tool_name == step.tool_name
        assert roundtrip.step_outcome == step.step_outcome


class TestTaskEpisode:
    def test_success_rate(self) -> None:
        steps = (
            TaskStep(step_index=0, tool_name="a", step_outcome="success"),
            TaskStep(step_index=1, tool_name="b", step_outcome="failure"),
            TaskStep(step_index=2, tool_name="c", step_outcome="success"),
        )
        episode = TaskEpisode(
            episode_id="ep1",
            steps=steps,
            final_outcome="partial",
        )
        assert episode.total_steps == 3
        assert abs(episode.success_rate - 2 / 3) < 0.01

    def test_unnecessary_steps(self) -> None:
        steps = (
            TaskStep(step_index=0, tool_name="a", step_outcome="success"),
            TaskStep(step_index=1, tool_name="b", step_outcome="skipped"),
        )
        episode = TaskEpisode(episode_id="ep2", steps=steps)
        assert episode.unnecessary_steps == 1

    def test_credit_assignment(self) -> None:
        """Failure at step 2 should not blame steps 0 and 1."""
        steps = (
            TaskStep(step_index=0, tool_name="a", step_outcome="success"),
            TaskStep(step_index=1, tool_name="b", step_outcome="success"),
            TaskStep(
                step_index=2,
                tool_name="c",
                step_outcome="failure",
                caused_final_failure=True,
            ),
        )
        episode = TaskEpisode(
            episode_id="ep3",
            steps=steps,
            final_outcome="failure",
            failure_step_index=2,
        )
        assert episode.failure_step_index == 2
        assert not steps[0].caused_final_failure
        assert not steps[1].caused_final_failure
        assert steps[2].caused_final_failure


class TestExperience:
    def test_roundtrip_serialization(self) -> None:
        exp = Experience(
            id="exp1",
            created_at=now_ms(),
            session_id="s1",
            agent_id="a1",
            user_input="play Believer on YouTube",
            selected_tool="browser.open",
            tool_arguments='{"url": "youtube.com"}',
            success=True,
            reward_score=0.7,
            confidence=0.8,
            verification_status="verified_success",
            episode=TaskEpisode(
                episode_id="ep1",
                steps=(
                    TaskStep(
                        step_index=0,
                        tool_name="browser.open",
                        step_outcome="success",
                    ),
                ),
            ),
        )
        d = exp.to_dict()
        roundtrip = Experience.from_dict(d)
        assert roundtrip.id == exp.id
        assert roundtrip.success is True
        assert roundtrip.episode is not None
        assert roundtrip.episode.total_steps == 1


# ── Verification ──────────────────────────────────────────────


class TestToolResultVerifier:
    def test_dict_with_error(self) -> None:
        v = ToolResultVerifier()
        result = v.verify("test", {}, {"is_err": True, "error": "not found"})
        assert result.status == "verified_failure"

    def test_dict_with_success(self) -> None:
        v = ToolResultVerifier()
        result = v.verify("test", {}, {"is_ok": True, "value": "done"})
        assert result.status == "verified_success"

    def test_string_failure(self) -> None:
        v = ToolResultVerifier()
        result = v.verify("test", {}, "Error: file not found")
        assert result.status == "verified_failure"

    def test_string_success(self) -> None:
        v = ToolResultVerifier()
        result = v.verify("test", {}, "File created successfully")
        assert result.status == "verified_success"

    def test_ambiguous_result(self) -> None:
        v = ToolResultVerifier()
        result = v.verify("test", {}, "some random text")
        assert result.status == "unverified"


class TestClaimVerifier:
    def test_false_claim_detected(self) -> None:
        v = ClaimVerifier()
        result = v.verify(
            "volume.set",
            {"level": 50},
            {"is_err": True, "error": "permission denied"},
            "I've set the volume to 50%",
        )
        assert result.status == "false_claim"
        assert result.confidence >= 0.7

    def test_no_claim(self) -> None:
        v = ClaimVerifier()
        result = v.verify("test", {}, "ok", "")
        assert result.status == "unverified"


class TestCompositeVerifier:
    def test_false_claim_priority(self) -> None:
        """false_claim should take priority over verified_success."""
        v = CompositeVerifier()
        result = v.verify(
            "volume.set",
            {},
            {"is_err": True, "error": "failed"},
            "I've successfully set the volume",
        )
        assert result.status == "false_claim"


# ── Reward Scoring ────────────────────────────────────────────


class TestRewardScorer:
    def test_default_weights(self) -> None:
        scorer = RewardScorer()
        score = scorer.score(["explicit_success", "verified_tool_success"])
        assert score == 1.7

    def test_negative_signals(self) -> None:
        scorer = RewardScorer()
        score = scorer.score(["explicit_correction", "task_failure"])
        assert score == -1.8

    def test_clamping(self) -> None:
        scorer = RewardScorer()
        score = scorer.score(
            [
                "explicit_correction",
                "task_failure",
                "hallucinated_capability",
                "unnecessary_repeat",
            ]
        )
        assert score == -2.0  # clamped

    def test_experience_scoring(self) -> None:
        scorer = RewardScorer()
        score = scorer.score_experience(
            success=True,
            tool_succeeded=True,
            user_feedback="thumbs_up",
            verification_status="verified_success",
        )
        assert score > 0

    def test_false_claim_penalty(self) -> None:
        scorer = RewardScorer()
        score = scorer.score_experience(
            success=False,
            tool_succeeded=False,
            user_feedback="",
            verification_status="false_claim",
        )
        assert score < 0

    def test_custom_weights(self) -> None:
        weights = RewardWeights(explicit_success=2.0)
        scorer = RewardScorer(weights)
        score = scorer.score(["explicit_success"])
        assert score == 2.0


# ── Feedback ──────────────────────────────────────────────────


class TestFeedbackCollector:
    def test_explicit_feedback(self) -> None:
        collector = FeedbackCollector()
        fb = collector.record_explicit("exp1", "thumbs_up")
        assert fb.feedback_type == "explicit"
        assert fb.confidence == 1.0
        assert collector.get_feedback_for("exp1") == [fb]

    def test_implicit_feedback(self) -> None:
        collector = FeedbackCollector()
        fb = collector.record_implicit("exp1", "tool_success", confidence=0.7)
        assert fb.feedback_type == "implicit"
        assert fb.confidence == 0.7


class TestImplicitFeedbackDetector:
    def test_repeated_request(self) -> None:
        detector = ImplicitFeedbackDetector()
        assert detector.detect_repeated_request("open YouTube", ["open YouTube"])
        assert not detector.detect_repeated_request("open YouTube", ["check weather"])

    def test_correction_detection(self) -> None:
        detector = ImplicitFeedbackDetector()
        messages = [{"role": "user", "content": "No, I meant Chrome"}]
        assert detector.detect_immediate_correction(messages)
        messages2 = [{"role": "user", "content": "Thanks, that worked!"}]
        assert not detector.detect_immediate_correction(messages2)

    def test_tool_outcome(self) -> None:
        detector = ImplicitFeedbackDetector()
        assert detector.detect_tool_outcome({"is_ok": True}) == "tool_success"
        assert detector.detect_tool_outcome({"error": "fail"}) == "tool_failure"


# ── Strategies ────────────────────────────────────────────────


class TestStrategyStore:
    def test_create_and_find(self) -> None:
        store = StrategyStore()
        strategy = store.create_strategy_from_experience(
            intent="play YouTube video",
            tool="browser.navigate_tab",
            argument_pattern={"tab_id": 2},
            preferred_action="reuse existing YouTube tab",
        )
        found = store.find_strategies_for_intent("play YouTube")
        assert len(found) == 1
        assert found[0].tool == "browser.navigate_tab"
        assert strategy.id == found[0].id

    def test_outcome_tracking(self) -> None:
        store = StrategyStore()
        strategy = store.create_strategy_from_experience(
            intent="test", tool="t", argument_pattern={}
        )
        store.record_strategy_outcome(strategy.id, succeeded=True)
        store.record_strategy_outcome(strategy.id, succeeded=True)
        updated = store.get_strategy(strategy.id)
        assert updated is not None
        assert updated.success_count == 3  # 1 initial + 2 updates

    def test_failure_pattern(self) -> None:
        store = StrategyStore()
        store.create_failure_pattern(
            pattern_name="duplicate_tab",
            bad_action="browser.new_tab when YouTube already open",
            preferred_action="browser.navigate_tab to existing tab",
        )
        matches = store.check_failure_patterns("browser.new_tab", {})
        assert len(matches) == 1


# ── Knowledge ─────────────────────────────────────────────────


class TestKnowledgeStore:
    def test_deduplication(self) -> None:
        store = KnowledgeStore()
        e1 = store.create_entry("API key expires daily", "docs", confidence=0.6)
        e2 = store.create_entry("API key expires daily", "user", confidence=0.8)
        assert e2.id != ""
        # Should have merged into one entry
        assert len(store.all_entries()) == 1
        merged = store.get(e1.id)
        assert merged is not None
        assert merged.confidence == 0.8  # max of both

    def test_search(self) -> None:
        store = KnowledgeStore()
        store.create_entry("Chrome is the default browser", "preference")
        store.create_entry("Python 3.12 is required", "docs")
        results = store.search("browser")
        assert len(results) == 1
        assert "Chrome" in results[0].content


# ── SQLite Persistence ────────────────────────────────────────


class TestLearningDatabase:
    def test_experience_roundtrip(self, tmp_db: LearningDatabase) -> None:
        exp = Experience(
            id=generate_id(),
            created_at=now_ms(),
            session_id="s1",
            agent_id="a1",
            user_input="test input",
            success=True,
            reward_score=0.5,
        )
        tmp_db.store_experience(exp)
        loaded = tmp_db.get_experience(exp.id)
        assert loaded is not None
        assert loaded.user_input == "test input"
        assert loaded.success is True

    def test_strategy_roundtrip(self, tmp_db: LearningDatabase) -> None:
        ts = now_ms()
        strategy = Strategy(
            id=generate_id(),
            created_at=ts,
            updated_at=ts,
            intent="play video",
            tool="browser.navigate_tab",
            success_count=5,
            confidence=0.8,
        )
        tmp_db.store_strategy(strategy)
        loaded = tmp_db.load_all_strategies()
        assert len(loaded) == 1
        assert loaded[0].intent == "play video"
        assert loaded[0].success_count == 5

    def test_stats(self, tmp_db: LearningDatabase) -> None:
        stats = tmp_db.get_stats()
        assert "experiences" in stats
        assert stats["experiences"] == 0

    def test_persistence_across_connections(self, tmp_path: Path) -> None:
        """Prove data survives closing and reopening the database."""
        db_path = tmp_path / "persist_test.sqlite"

        # Write with one connection
        db1 = LearningDatabase(db_path)
        exp = Experience(
            id="persist_id",
            created_at=now_ms(),
            session_id="s1",
            agent_id="a1",
            user_input="remember this",
            success=True,
        )
        db1.store_experience(exp)

        # Open a completely new connection
        db2 = LearningDatabase(db_path)
        loaded = db2.get_experience("persist_id")
        assert loaded is not None
        assert loaded.user_input == "remember this"


# ── Learning Engine Integration ───────────────────────────────


class TestLearningEngine:
    def test_record_tool_execution(self, engine: LearningEngine) -> None:
        exp = engine.record_tool_execution(
            session_id="s1",
            agent_id="a1",
            user_input="open YouTube",
            tool_name="browser.open",
            tool_args={"url": "youtube.com"},
            tool_result={"is_ok": True, "value": "opened tab 1"},
        )
        assert exp.success is True
        assert exp.verification_status == "verified_success"
        assert exp.reward_score > 0

    def test_record_failed_tool(self, engine: LearningEngine) -> None:
        exp = engine.record_tool_execution(
            session_id="s1",
            agent_id="a1",
            user_input="set volume",
            tool_name="volume.set",
            tool_args={"level": 50},
            tool_result={"is_err": True, "error": "permission denied"},
        )
        assert exp.success is False
        assert exp.verification_status == "verified_failure"
        assert exp.reward_score < 0

    def test_false_claim_detection_in_engine(self, engine: LearningEngine) -> None:
        exp = engine.record_tool_execution(
            session_id="s1",
            agent_id="a1",
            user_input="set volume to 50",
            tool_name="volume.set",
            tool_args={"level": 50},
            tool_result={"is_err": True, "error": "failed"},
            claimed_outcome="I've set the volume to 50%",
        )
        # Should be caught as false claim
        assert exp.verification_status == "false_claim"
        assert exp.approved_for_training is False

    def test_reflection_creates_strategy(self, engine: LearningEngine) -> None:
        """Successful verified experience should create a strategy."""
        exp = engine.record_tool_execution(
            session_id="s1",
            agent_id="a1",
            user_input=(
                "Please play the song Believer by Imagine Dragons "
                "on YouTube using the existing tab if one is already open"
            ),
            tool_name="browser.navigate_tab",
            tool_args={"tab_id": 2, "url": "youtube.com/search?q=Believer"},
            tool_result={"is_ok": True, "value": "navigated to YouTube search"},
        )
        # Manually add interpreted_intent for richer experience
        exp = Experience(
            id=exp.id,
            created_at=exp.created_at,
            session_id=exp.session_id,
            agent_id=exp.agent_id,
            user_input=exp.user_input,
            interpreted_intent="play YouTube video using existing tab",
            plan="1. Find existing YouTube tab 2. Navigate to search",
            selected_tool=exp.selected_tool,
            tool_arguments=exp.tool_arguments,
            tool_result=exp.tool_result,
            success=exp.success,
            reward_score=exp.reward_score,
            confidence=exp.confidence,
            verification_status=exp.verification_status,
            episode=exp.episode,
        )
        lesson = engine.reflect_on_experience(exp)
        assert lesson is not None
        # Should have created a strategy for this successful tool use
        strategies = engine.strategy_store.find_strategies_for_intent("YouTube")
        assert len(strategies) >= 1

    def test_reflection_creates_failure_pattern(self, engine: LearningEngine) -> None:
        """Failed verified experience with false claim should create
        failure pattern."""
        exp = engine.record_tool_execution(
            session_id="s1",
            agent_id="a1",
            user_input="set volume",
            tool_name="volume.set",
            tool_args={"level": 50},
            tool_result={"is_err": True, "error": "failed"},
            claimed_outcome="I have successfully set the volume",
        )
        engine.reflect_on_experience(exp)
        patterns = engine.strategy_store.all_failure_patterns()
        assert len(patterns) >= 1

    def test_retrieve_relevant_strategies(self, engine: LearningEngine) -> None:
        """Learned strategies should be retrievable for similar tasks."""
        # First, create a strategy
        engine.strategy_store.create_strategy_from_experience(
            intent="play YouTube video",
            tool="browser.navigate_tab",
            argument_pattern={"tab_id": 2},
            preferred_action="reuse existing YouTube tab",
        )
        # Now retrieve for similar input
        context = engine.retrieve_relevant(user_input="play YouTube")
        assert len(context.relevant_strategies) >= 1
        prompt = context.to_prompt_section()
        assert "browser.navigate_tab" in prompt

    def test_retrieve_failure_patterns(self, engine: LearningEngine) -> None:
        engine.strategy_store.create_failure_pattern(
            pattern_name="duplicate_tab",
            bad_action="browser.new_tab when YouTube open",
            preferred_action="browser.navigate_tab to existing tab",
        )
        patterns = engine.check_tool_against_patterns("browser.new_tab", {})
        assert len(patterns) >= 1

    def test_explicit_feedback_recording(self, engine: LearningEngine) -> None:
        exp = engine.record_tool_execution(
            session_id="s1",
            agent_id="a1",
            user_input="test",
            tool_name="test.tool",
            tool_args={},
            tool_result={"is_ok": True},
        )
        fb = engine.record_explicit_feedback(exp.id, "thumbs_up", "good job")
        assert fb.feedback_type == "explicit"
        assert fb.confidence == 1.0

    def test_engine_status(self, engine: LearningEngine) -> None:
        status = engine.get_status()
        assert status["started"] is True
        assert "tables" in status
        assert "in_memory" in status


# ── Cross-Restart Persistence ─────────────────────────────────


class TestCrossRestartPersistence:
    """Proves learning survives process restart (simulated by
    creating a new engine instance pointing at the same DB file)."""

    def test_experience_survives_restart(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "restart_test.sqlite")

        # Session 1: record an experience and learn a strategy
        engine1 = LearningEngine(db_path=db_path)
        engine1.startup()
        exp = engine1.record_tool_execution(
            session_id="s1",
            agent_id="a1",
            user_input=(
                "Please play the song Believer by Imagine Dragons "
                "on YouTube using the existing tab if one is open"
            ),
            tool_name="browser.navigate_tab",
            tool_args={"tab_id": 2, "url": "youtube.com/search?q=Believer"},
            tool_result={"is_ok": True, "value": "navigated to YouTube search"},
        )
        rich_exp = Experience(
            id=exp.id,
            created_at=exp.created_at,
            session_id=exp.session_id,
            agent_id=exp.agent_id,
            user_input=exp.user_input,
            interpreted_intent="play YouTube video using existing tab",
            plan="1. Find existing YouTube tab 2. Navigate to search",
            selected_tool=exp.selected_tool,
            tool_arguments=exp.tool_arguments,
            tool_result=exp.tool_result,
            success=exp.success,
            reward_score=exp.reward_score,
            confidence=exp.confidence,
            verification_status=exp.verification_status,
            episode=exp.episode,
        )
        engine1.reflect_on_experience(rich_exp)
        engine1.flush()

        # Session 2: create a completely new engine (simulated restart)
        engine2 = LearningEngine(db_path=db_path)
        engine2.startup()

        # The strategy should have been loaded from SQLite
        strategies = engine2.strategy_store.find_strategies_for_intent("YouTube")
        assert len(strategies) >= 1, "Strategy learned in session 1 was not found after restart"

        # The experience should be queryable
        status = engine2.get_status()
        assert status["tables"]["experiences"] >= 1

    def test_strategy_with_correction_survives_restart(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "correction_test.sqlite")

        # Session 1: bad action detected
        engine1 = LearningEngine(db_path=db_path)
        engine1.startup()
        engine1.strategy_store.create_failure_pattern(
            pattern_name="duplicate_youtube_tab",
            bad_action="browser.new_tab for YouTube",
            preferred_action="browser.navigate_tab to existing YouTube tab",
        )
        engine1.flush()

        # Session 2: check the pattern persists
        engine2 = LearningEngine(db_path=db_path)
        engine2.startup()
        patterns = engine2.strategy_store.check_failure_patterns("browser.new_tab", {})
        assert len(patterns) >= 1, "Failure pattern from session 1 was not found after restart"
        assert "duplicate_youtube_tab" in patterns[0].pattern_name


# ── Events ────────────────────────────────────────────────────


class TestLearningEventBus:
    def test_emit_and_subscribe(self) -> None:
        bus = LearningEventBus()
        received: list[LearningEvent] = []
        bus.subscribe("test_event", received.append)
        event = bus.create_event("test_event", {"key": "val"}, source="test")
        bus.emit(event)
        assert len(received) == 1
        assert received[0].data["key"] == "val"

    def test_exception_isolation(self) -> None:
        """A failing subscriber should not prevent others from running."""
        bus = LearningEventBus()
        results: list[str] = []

        def good_handler(e: LearningEvent) -> None:
            results.append("ok")

        def bad_handler(e: LearningEvent) -> None:
            raise RuntimeError("deliberate failure")

        bus.subscribe("test", bad_handler)
        bus.subscribe("test", good_handler)
        event = bus.create_event("test")
        bus.emit(event)
        assert "ok" in results
