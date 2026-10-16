"""jarvis_learning.engine — central learning engine coordinator.

The ``LearningEngine`` is the single entry point for the learning
system.  It wires together all subsystems (experience store,
feedback, reward, strategies, procedures, knowledge, verification,
reflection) and provides the API that the learning plugin calls.

The engine owns the closed-loop pipeline:
  observe → store → verify → reflect → extract → update → (generate)

Online operations (retrieval, recording, strategy updates) run
during the active agent loop.  Offline operations (dataset
generation, training) are explicitly gated and never run during
active voice/response loops.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .events import LearningEventBus, LearningEventType, LearningEvent
from .experience import Experience, Lesson, TaskEpisode, TaskStep, generate_id, now_ms
from .feedback import Feedback, FeedbackCollector, ImplicitFeedbackDetector
from .knowledge import KnowledgeStore
from .procedures import ProcedureStore
from .reflection import ReflectionEngine
from .reward import RewardScorer, RewardWeights
from .strategies import StrategyStore
from .storage.learning_db import LearningDatabase
from .verification import CompositeVerifier

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LearningRetrievalContext:
    """Context returned by retrieve_relevant() for injection into
    the agent's prompt."""

    relevant_experiences: list[Experience]
    relevant_strategies: list[Any]  # Strategy objects
    failure_patterns: list[Any]  # FailurePattern objects
    relevant_lessons: list[Lesson]
    relevant_knowledge: list[Any]  # KnowledgeEntry objects

    def to_prompt_section(self) -> str:
        """Format as a text section for prompt injection."""
        parts: list[str] = []

        if self.relevant_strategies:
            parts.append("## Learned Strategies")
            for s in self.relevant_strategies[:5]:
                confidence = f"{s.confidence:.0%}"
                parts.append(
                    f"- [{confidence}] For '{s.intent}': use {s.tool} ({s.preferred_action})"
                )

        if self.failure_patterns:
            parts.append("## Known Failure Patterns (AVOID)")
            for p in self.failure_patterns[:3]:
                parts.append(f"- AVOID: {p.bad_action} → instead: {p.preferred_action}")

        if self.relevant_lessons:
            parts.append("## Lessons from Past Experiences")
            for lesson in self.relevant_lessons[:5]:
                parts.append(f"- {lesson.summary}")

        if self.relevant_knowledge:
            parts.append("## Relevant Knowledge")
            for k in self.relevant_knowledge[:3]:
                parts.append(f"- {k.content}")

        return "\n".join(parts) if parts else ""


class LearningEngine:
    """Central coordinator for the JARVIS learning system.

    Lifecycle:
    1. ``__init__`` → creates subsystems
    2. ``startup()`` → loads persisted state from SQLite
    3. Runtime: ``record_*``, ``retrieve_*``, ``reflect`` called by hooks
    4. ``flush()`` → persists all dirty state to SQLite
    """

    def __init__(
        self,
        db_path: str | None = None,
        reward_weights: RewardWeights | None = None,
    ) -> None:
        # Storage
        self._db = LearningDatabase(db_path)

        # Subsystems
        self.event_bus = LearningEventBus()
        self.feedback = FeedbackCollector()
        self.implicit_detector = ImplicitFeedbackDetector()
        self.reward_scorer = RewardScorer(reward_weights)
        self.strategy_store = StrategyStore()
        self.procedure_store = ProcedureStore()
        self.knowledge_store = KnowledgeStore()
        self.verifier = CompositeVerifier()
        self.reflection_engine = ReflectionEngine(self.strategy_store)

        # Model Registry and Router
        from .advisory import StructuredAdvisoryInjector
        from .models.registry import ModelRegistry
        from .routing.router import ModelRouter, RouterConfig
        from .safe_execution import SafeExecutionBoundary
        from .task_continuity import TaskContinuityTracker
        from .truthfulness import TruthfulCompletionEnforcer

        self.registry = ModelRegistry(self._db.path)
        self.router = ModelRouter(
            config=RouterConfig(local_models_enabled=False, shadow_mode_enabled=True),
            strategy_store=self.strategy_store,
            registry=self.registry,
        )

        # Phase 4: Runtime Routing, Continuity, Truthfulness, and Safe Execution
        self.continuity_tracker = TaskContinuityTracker()
        self.truthfulness_enforcer = TruthfulCompletionEnforcer()
        self.advisory_injector = StructuredAdvisoryInjector()
        self.safe_execution_boundary = SafeExecutionBoundary(
            arg_builder=self.router.arg_builder,
            decision_guard=self.router.guard,
            truthfulness_enforcer=self.truthfulness_enforcer,
        )

        # Phase 5: Autonomous Reflection & Strategy Lifecycle
        from .feedback_attribution import FeedbackAttributor
        from .reflection_worker import ReflectionWorker
        from .strategy_conflict import ConflictResolver
        from .strategy_lifecycle import StrategyLifecycleManager

        self.lifecycle_manager = StrategyLifecycleManager()
        self.reflection_worker = ReflectionWorker()
        self.feedback_attributor = FeedbackAttributor()
        self.conflict_resolver = ConflictResolver()

        # In-memory pending writes
        self._pending_experiences: list[Experience] = []
        self._pending_feedback: list[Feedback] = []
        self._pending_lessons: list[Lesson] = []
        self._started = False

    @property
    def db(self) -> LearningDatabase:
        """Return the underlying SQLite learning database."""
        return self._db

    def startup(self) -> None:
        """Load persisted state from the learning database."""
        if self._started:
            return

        strategies = self._db.load_all_strategies()
        self.strategy_store.load_strategies(strategies)

        failure_patterns = self._db.load_all_failure_patterns()
        self.strategy_store.load_failure_patterns(failure_patterns)

        procedures = self._db.load_all_procedures()
        self.procedure_store.load(procedures)

        knowledge = self._db.load_all_knowledge()
        self.knowledge_store.load(knowledge)

        lessons = self._db.load_all_lessons()
        self.reflection_engine.load_lessons(lessons)

        stats = self._db.get_stats()
        logger.info(
            "learning engine started: %s",
            ", ".join(f"{k}={v}" for k, v in stats.items()),
        )
        self._started = True

    # ── Recording (online) ────────────────────────────────────

    def record_tool_execution(
        self,
        *,
        session_id: str,
        agent_id: str,
        user_input: str,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: Any,
        claimed_outcome: str = "",
    ) -> Experience:
        """Record a single tool execution as an experience.

        This is called from the ``after_tool_call`` hook.
        The experience is verified, scored, and stored.
        """
        # 1. Verify outcome
        verification = self.verifier.verify(
            tool_name,
            tool_args,
            tool_result,
            claimed_outcome,
        )

        # 2. Determine success
        success = verification.status in ("verified_success", "unverified")
        failure_type = ""
        if verification.status == "verified_failure":
            failure_type = "tool_failure"
        elif verification.status == "false_claim":
            failure_type = "false_claim"
            success = False

        # 3. Score
        reward = self.reward_scorer.score_experience(
            success=success,
            tool_succeeded=verification.status == "verified_success",
            user_feedback="",
            verification_status=verification.status,
        )

        # 4. Determine training approval based on provenance
        source_type = (
            "tool_verified"
            if verification.status in ("verified_success", "verified_failure")
            else "llm_inferred"
        )
        approved = source_type == "tool_verified" and success and reward > 0.0

        # 5. Build experience
        step = TaskStep(
            step_index=0,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result_summary=str(tool_result)[:500],
            step_outcome="success" if success else "failure",
            verification_status=verification.status,
        )
        episode = TaskEpisode(
            episode_id=generate_id(),
            steps=(step,),
            final_outcome="success" if success else "failure",
            failure_step_index=None if success else 0,
        )

        experience = Experience(
            id=generate_id(),
            created_at=now_ms(),
            session_id=session_id,
            agent_id=agent_id,
            user_input=user_input,
            selected_tool=tool_name,
            tool_arguments=json.dumps(tool_args),
            tool_result=str(tool_result)[:1000],
            success=success,
            failure_type=failure_type,
            reward_score=reward,
            confidence=verification.confidence,
            approved_for_training=approved,
            source_type=source_type,
            verification_status=verification.status,
            episode=episode,
        )

        # Store immediately
        self._db.store_experience(experience)
        self._pending_experiences.append(experience)

        # Emit event
        self.event_bus.emit(
            LearningEvent(
                event_type=LearningEventType.TOOL_SUCCEEDED
                if success
                else LearningEventType.TOOL_FAILED,
                timestamp=now_ms(),
                data={"experience_id": experience.id, "tool": tool_name},
                source="engine",
            )
        )

        logger.info(
            "tool execution recorded: tool=%s success=%s reward=%.2f verified=%s",
            tool_name,
            success,
            reward,
            verification.status,
        )
        return experience

    def record_explicit_feedback(
        self,
        experience_id: str,
        signal: str,
        value: str = "",
    ) -> Feedback:
        """Record explicit user feedback for an experience."""
        fb = self.feedback.record_explicit(experience_id, signal, value)
        self._db.store_feedback(fb)
        self._pending_feedback.append(fb)

        self.event_bus.emit(
            LearningEvent(
                event_type=LearningEventType.USER_CORRECTED
                if signal in ("correction", "user_correction", "incorrect")
                else LearningEventType.USER_CONFIRMED_SUCCESS,
                timestamp=now_ms(),
                data={"experience_id": experience_id, "signal": signal},
                source="engine",
            )
        )
        return fb

    def record_implicit_feedback(
        self,
        experience_id: str,
        signal: str,
        value: str = "",
        confidence: float = 0.5,
    ) -> Feedback:
        """Record implicit feedback inferred from patterns."""
        fb = self.feedback.record_implicit(experience_id, signal, value, confidence)
        self._db.store_feedback(fb)
        return fb

    # ── Reflection (online, threshold-gated) ──────────────────

    def reflect_on_experience(self, experience: Experience) -> Lesson | None:
        """Run post-task reflection and extract lessons.

        Creates strategies and failure patterns as side effects when
        the experience quality warrants it.
        """
        lesson = self.reflection_engine.reflect(experience)
        if lesson is not None:
            self._db.store_lesson(lesson)
            self._pending_lessons.append(lesson)

            self.event_bus.emit(
                LearningEvent(
                    event_type=LearningEventType.LESSON_EXTRACTED,
                    timestamp=now_ms(),
                    data={
                        "lesson_id": lesson.id,
                        "experience_id": experience.id,
                        "summary": lesson.summary[:200],
                    },
                    source="engine",
                )
            )

        # Persist any new strategies/failure patterns created by reflection
        for s in self.strategy_store.all_strategies():
            self._db.store_strategy(s)
        for fp in self.strategy_store.all_failure_patterns():
            self._db.store_failure_pattern(fp)

        return lesson

    def pause_background_learning(self) -> None:
        """Pause detached reflection during active user speech/audio turns."""
        self.reflection_worker.pause()

    def resume_background_learning(self) -> None:
        """Resume background learning when audio/voice is idle."""
        self.reflection_worker.resume()

    def enqueue_background_reflection(
        self, job_id: str, payload: dict[str, Any], priority: int = 5
    ) -> bool:
        """Queue reflection for async processing off the main interaction loop."""
        payload_json = json.dumps(payload)
        self._db.enqueue_reflection_job_record(job_id, priority, "queued", payload_json)
        return self.reflection_worker.enqueue_job(job_id, payload, priority)

    def step_background_reflection(self) -> str | None:
        """Process a single background reflection job if unpaused."""

        def _handler(job: Any) -> bool:
            self._db.update_reflection_job_status(job.job_id, "running")
            exp_id = job.payload.get("experience_id")
            if exp_id:
                exp = self._db.get_experience(exp_id)
                if exp:
                    self.reflect_on_experience(exp)
            self._db.update_reflection_job_status(job.job_id, "completed")
            return True

        return self.reflection_worker.step(_handler)

    # ── Retrieval (online) ────────────────────────────────────

    def retrieve_relevant(
        self,
        *,
        user_input: str,
        tool_name: str = "",
        agent_id: str = "",
    ) -> LearningRetrievalContext:
        """Retrieve relevant learning context for injection into the
        agent's prompt.

        Called from ``before_prompt_build`` hook.
        """
        # Strategies matching the user's intent
        strategies = self.strategy_store.find_strategies_for_intent(user_input)

        # Failure patterns for the proposed tool
        failure_patterns = []
        if tool_name:
            failure_patterns = self.strategy_store.check_failure_patterns(tool_name, {})

        # Recent experiences for this agent (limited for context size)
        experiences = self._db.list_experiences(agent_id=agent_id if agent_id else None, limit=5)

        # Relevant lessons
        lessons = [
            lesson
            for lesson in self.reflection_engine.get_lessons()
            if any(intent.lower() in user_input.lower() for intent in lesson.applicable_intents)
            or user_input.lower() in lesson.summary.lower()
        ]

        # Relevant knowledge
        knowledge = self.knowledge_store.search(user_input)

        return LearningRetrievalContext(
            relevant_experiences=experiences[:3],
            relevant_strategies=strategies[:5],
            failure_patterns=failure_patterns[:3],
            relevant_lessons=lessons[:5],
            relevant_knowledge=knowledge[:3],
        )

    def check_tool_against_patterns(self, tool_name: str, tool_args: dict[str, Any]) -> list[Any]:
        """Check if a proposed tool call matches known failure patterns.

        Called from ``before_tool_call`` hook.
        """
        return self.strategy_store.check_failure_patterns(tool_name, tool_args)

    # ── Status ────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Return learning system status and statistics."""
        db_stats = self._db.get_stats()
        return {
            "started": self._started,
            "database_path": str(self._db.path),
            "tables": db_stats,
            "in_memory": {
                "strategies": len(self.strategy_store.all_strategies()),
                "failure_patterns": len(self.strategy_store.all_failure_patterns()),
                "procedures": len(self.procedure_store.all_procedures()),
                "knowledge": len(self.knowledge_store.all_entries()),
                "lessons": len(self.reflection_engine.get_lessons()),
                "pending_feedback": len(self._pending_feedback),
            },
        }

    def flush(self) -> None:
        """Persist all dirty in-memory state to SQLite.

        Called at session end or shutdown.
        """
        for s in self.strategy_store.all_strategies():
            self._db.store_strategy(s)
        for fp in self.strategy_store.all_failure_patterns():
            self._db.store_failure_pattern(fp)
        for p in self.procedure_store.all_procedures():
            self._db.store_procedure(p)
        for k in self.knowledge_store.all_entries():
            self._db.store_knowledge(k)
        self._pending_experiences.clear()
        self._pending_feedback.clear()
        self._pending_lessons.clear()
        logger.info("learning engine flushed to disk")

    # ── Wave 2: Dataset + Evaluation ──────────────────────────

    def build_dataset(
        self,
        target: str,
        *,
        output_dir: str | None = None,
    ) -> Any:
        """Offline: build a versioned, validated training dataset.

        This method is the entry point for Wave 2 dataset generation.
        It runs the full 14-stage pipeline: load → provenance → clean
        → classify → label → format → negatives → group → split →
        dedup → validate → write JSONL → manifest.

        Never called during active voice/response loops.
        """
        from .datasets.builder import DatasetBuilder, DatasetConfig

        config = DatasetConfig(output_dir=output_dir or "")
        builder = DatasetBuilder(
            db=self._db,
            strategy_store=self.strategy_store,
            config=config,
        )
        result = builder.build(target)
        self.event_bus.emit(
            LearningEvent(
                event_type="dataset_built",
                timestamp=now_ms(),
                data={
                    "target": target,
                    "success": result.success,
                    "final_train": result.final_train,
                    "final_validation": result.final_validation,
                    "final_test": result.final_test,
                },
                source="learning_engine",
            )
        )
        return result

    def run_benchmarks(
        self,
        benchmark_dir: str | None = None,
        category: str | None = None,
    ) -> Any:
        """Run regression benchmarks against current strategy store."""
        from .evaluation.benchmark import BenchmarkRunner

        if benchmark_dir is None:
            # Default: benchmarks shipped with the package
            benchmark_dir = str(
                Path(__file__).parent.parent.parent / "benchmarks" / "jarvis_regression"
            )

        runner = BenchmarkRunner(benchmark_dir)
        if category:
            cases = runner.load_suite(category)
            results = runner.evaluate_strategy_store(self.strategy_store, cases)
            return runner._build_suite_result(results)
        return runner.evaluate_all(self.strategy_store)

    def check_regression_gate(
        self,
        benchmark_dir: str | None = None,
    ) -> Any:
        """Severity-aware promotion gate — must pass before model promotion."""
        from .evaluation.regression import RegressionGate

        suite_result = self.run_benchmarks(benchmark_dir)
        gate = RegressionGate()
        return gate.check(suite_result)

    # ── Wave 3: Model Training, Routing & Shadow Governance ────

    def train_model(
        self,
        target: str,
        dataset_dir: str,
        *,
        epochs: int = 25,
        min_samples_required: int = 10,
        min_accuracy_gain: float = 0.02,
        output_dir: str = "",
    ) -> Any:
        """Train a local model candidate on validated Wave 2 JSONL datasets."""
        from .training.config import TrainingConfig
        from .training.trainer import OfflineTrainer

        config = TrainingConfig(
            target=target,
            dataset_dir=dataset_dir,
            output_dir=output_dir,
            epochs=epochs,
            min_samples_required=min_samples_required,
            min_accuracy_gain=min_accuracy_gain,
        )
        trainer = OfflineTrainer()
        result = trainer.train(config)
        self.event_bus.emit(
            LearningEvent(
                event_type="model_trained",
                timestamp=now_ms(),
                data={
                    "target": target,
                    "success": result.success,
                    "status": result.status.value,
                    "message": result.message,
                },
                source="learning_engine",
            )
        )
        return result

    def attach_local_model(self, model: Any) -> None:
        """Attach active model to the runtime ModelRouter."""
        self.router.set_active_model(model)

    def attach_baseline_model(self, model: Any) -> None:
        """Attach baseline model to the runtime ModelRouter."""
        self.router.set_baseline_model(model)

    def route_turn(
        self,
        user_input: str,
        session_id: str = "sess_001",
        context: dict[str, Any] | None = None,
        *,
        local_models_enabled: bool = False,
        shadow_mode_enabled: bool = True,
        model: Any | None = None,
        task_family: str = "tool_policy",
    ) -> Any:
        """Route a turn through Strategy Store -> Local Model -> Foundation LLM."""
        from .routing.router import RouterConfig

        if model is not None:
            self.router.set_active_model(model)

        self.router.config = RouterConfig(
            local_models_enabled=local_models_enabled,
            shadow_mode_enabled=shadow_mode_enabled,
        )
        return self.router.route(
            user_input=user_input,
            session_id=session_id,
            context=context,
            task_family=task_family,
        )

    def build_advisory_for_turn(self, routing_result: Any) -> Any:
        """Construct bounded, sanitized advisory context for the given routing result."""
        return self.advisory_injector.build_advisory_context(routing_result)

    def evaluate_task_continuity(
        self,
        user_input: str,
        session_id: str,
        context: dict[str, Any] | None = None,
        workspace_id: str = "default",
    ) -> Any:
        """Disambiguate active-task continuation from new unrelated task."""
        return self.continuity_tracker.evaluate_turn(
            user_input=user_input,
            session_id=session_id,
            context=context,
            workspace_id=workspace_id,
        )

    def execute_safely(
        self,
        prediction: Any,
        user_input: str,
        context: dict[str, Any],
        tool_executor_fn: Any,
        verifier_fn: Any = None,
        schema_validator_fn: Any = None,
        operator_authorized: bool = False,
        local_models_enabled: bool = False,
    ) -> Any:
        """Execute local model prediction through the safe execution boundary."""
        return self.safe_execution_boundary.attempt_execution(
            prediction=prediction,
            user_input=user_input,
            context=context,
            tool_executor_fn=tool_executor_fn,
            verifier_fn=verifier_fn,
            schema_validator_fn=schema_validator_fn,
            operator_authorized=operator_authorized,
            local_models_enabled=local_models_enabled,
        )

    def record_shadow_turn(
        self,
        session_id: str,
        user_input: str,
        active_tool_chosen: str,
        verified_successful_tool: str,
        category: str = "general",
    ) -> Any:
        """Record shadow observations on live turn outcomes."""
        return self.router.shadow_executor.execute_shadow_turn(
            session_id=session_id,
            user_input=user_input,
            active_tool_chosen=active_tool_chosen,
            verified_successful_tool=verified_successful_tool,
            category=category,
        )

    # ── Wave 4/5: NanoTransformer Training & Lifecycle Proofs ──

    def train_transformer_model(
        self,
        records: list[Any],
        classes: list[str],
        *,
        output_dir: str,
        epochs: int = 25,
        lr: float = 0.01,
        d_model: int = 32,
        n_layers: int = 1,
    ) -> Any:
        """Trains a NanoTransformer model on TaskRecords and registers in SHADOW mode."""
        from .transformer.config import TransformerConfig
        from .transformer.dataset_adapter import DatasetAdapter
        from .transformer.heads import ToolClassificationHead
        from .transformer.model import NanoTransformer
        from .transformer.runtime_adapter import TransformerToolPolicyModel
        from .transformer.tokenizer import ByteTokenizer
        from .transformer.trainer import NanoTrainer

        tok = ByteTokenizer()
        adapter = DatasetAdapter(tok, max_seq_len=32)
        label_map = {c: i for i, c in enumerate(classes)}
        batch = adapter.tokenize_records(records, label_mapping=label_map)

        cfg = TransformerConfig(
            vocab_size=260, max_seq_len=32, d_model=d_model, n_heads=2, d_ff=64, n_layers=n_layers
        )
        model = NanoTransformer(cfg)
        head = ToolClassificationHead(d_model=d_model, num_classes=len(classes))
        trainer = NanoTrainer(model, head, lr=lr, max_steps=epochs)

        result = trainer.train(batch, epochs=epochs)
        if result.is_verified:
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            runtime_model = TransformerToolPolicyModel(config=cfg)
            runtime_model.classes = classes
            runtime_model.model = model
            runtime_model.head = head
            runtime_model._is_loaded = True
            runtime_model.save(out_path)

        return result

    def reflect_debounced(self, session_id: str, min_batch_size: int = 1) -> list[Lesson]:
        """Debounced reflection running only when verified experiences reach threshold."""
        recent = [
            exp for exp in self._db.list_experiences(limit=20) if exp.session_id == session_id
        ]
        if len(recent) < min_batch_size:
            return []
        lessons: list[Lesson] = []
        for exp in recent:
            res = self.reflect_on_experience(exp)
            if res:
                lessons.extend(res)
        return lessons
