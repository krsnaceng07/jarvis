"""tests/test_decision_parity.py — End-to-end tests for OpenClaw Decision & Truthfulness parity.

Validates:
1. Intent classification & Execution Bias (English, Nepali, and mixed requests).
2. Dynamic tool selection & argument preflight.
3. Tool loop intervention (detecting repetitive calls and breaking loops).
4. Multi-step task decomposition and dynamic replanning on failure.
5. Observation normalization and tangible evidence extraction.
6. Claim Grounding Filter & Truthfulness Engine (catching ungrounded/contradicted claims).
7. Provider Decision Adapter (Gemini and OpenAI/Groq normalization).
8. Closed-loop decision engine execution.
"""

from __future__ import annotations

import pytest

from src.agents.decision import (
    ClaimGroundingFilter,
    DecisionEngine,
    ExecutionPlanner,
    IntentCategory,
    IntentClassifier,
    NormalizedFunctionResponse,
    ObservationNormalizer,
    ProviderDecisionAdapter,
    ToolLoopInterventionError,
    ToolSelector,
)
from src.agents.verification.execution_verifier import VerificationOutcome


class TestIntentAndExecutionBiasParity:
    """Phase 2 & Phase 9: Intent classification and OpenClaw execution bias enforcement."""

    def test_english_actionable_process_kill(self):
        intent = IntentClassifier.classify("close whatsapp")
        assert intent.is_actionable is True
        assert intent.category == IntentCategory.ACTIONABLE_PROCESS
        assert intent.primary_tool == "process"
        assert intent.parameters["action"] == "kill"
        assert intent.parameters["session_id"] == "whatsapp"
        assert intent.requires_host_verification is True

    def test_nepali_actionable_process_kill(self):
        intent = IntentClassifier.classify("whatsapp banda gara")
        assert intent.is_actionable is True
        assert intent.category == IntentCategory.ACTIONABLE_PROCESS
        assert intent.primary_tool == "process"
        assert intent.parameters["session_id"] == "whatsapp"

    def test_window_controls(self):
        intent_min = IntentClassifier.classify("minimize all windows")
        assert intent_min.is_actionable is True
        assert intent_min.category == IntentCategory.ACTIONABLE_WINDOW
        assert intent_min.parameters["action"] == "minimize"

        intent_res = IntentClassifier.classify("restore windows")
        assert intent_res.is_actionable is True
        assert intent_res.parameters["action"] == "restore"

    def test_browser_direct_search(self):
        intent = IntentClassifier.classify("search funny cat videos on youtube")
        assert intent.is_actionable is True
        assert intent.category == IntentCategory.ACTIONABLE_BROWSER
        assert intent.primary_tool == "youtube_search"
        assert intent.parameters["engine"] == "youtube"

    def test_filesystem_creation_and_removal(self):
        mkdir_intent = IntentClassifier.classify("create folder E:\\my_project")
        assert mkdir_intent.is_actionable is True
        assert mkdir_intent.primary_tool == "mkdir"
        assert mkdir_intent.parameters["path"] == "E:\\my_project"

        rm_intent = IntentClassifier.classify("delete file C:\\temp\\notes.txt")
        assert rm_intent.is_actionable is True
        assert rm_intent.primary_tool == "remove_path"
        assert rm_intent.parameters["path"] == "C:\\temp\\notes.txt"

    def test_conversational_negation_detection(self):
        intent = IntentClassifier.classify("chaina")
        assert intent.category == IntentCategory.CORRECTION_NEGATION
        assert intent.is_negation is True
        assert intent.requires_host_verification is True

        intent2 = IntentClassifier.classify("bhayena")
        assert intent2.category == IntentCategory.CORRECTION_NEGATION
        assert intent2.is_negation is True
        assert intent2.requires_host_verification is True

        intent_act = IntentClassifier.classify("close notepad")
        assert intent_act.is_negation is False
        assert intent_act.suggested_tool == "process"

    def test_informational_request_not_forced_to_tools(self):
        intent = IntentClassifier.classify("what is quantum computing?")
        assert intent.is_actionable is False
        assert intent.category == IntentCategory.INFORMATIONAL_FACTUAL

        intent_hi = IntentClassifier.classify("hello jarvis")
        assert intent_hi.is_actionable is False
        assert intent_hi.category == IntentCategory.CONVERSATIONAL


class TestToolSelectionAndPreflight:
    """Phase 5: Dynamic tool selection and schema preflight."""

    def test_argument_preflight_normalizes_paths(self):
        selector = ToolSelector()
        cleaned = selector.preflight_arguments(
            "mkdir", {"path": "C:\\\\Program Files\\\\test//dir"}
        )
        assert cleaned["path"] == "C:/Program Files/test/dir"

    def test_argument_preflight_cleans_process_name(self):
        selector = ToolSelector()
        cleaned = selector.preflight_arguments(
            "process", {"action": "terminate", "session_id": "Notepad.exe"}
        )
        assert cleaned["action"] == "kill"
        assert cleaned["session_id"] == "notepad"

    def test_argument_preflight_constructs_search_url(self):
        selector = ToolSelector()
        cleaned = selector.preflight_arguments(
            "browser", {"query": "noodles recipe", "engine": "youtube"}
        )
        assert cleaned["action"] == "open"
        assert cleaned["url"] == "https://www.youtube.com/results?search_query=noodles+recipe"


class TestToolLoopInterventionParity:
    """Phase 4 & 5: Tool loop detection and intervention."""

    def test_tool_loop_intervention_triggers_on_repeated_identical_calls(self):
        selector = ToolSelector(max_identical_calls=2)
        args = {"path": "C:/protected/dir"}

        # 1st call: OK
        selector.check_loop_intervention("remove_path", args)
        # 2nd call: OK
        selector.check_loop_intervention("remove_path", args)
        # 3rd call: Exceeds threshold, raises intervention
        with pytest.raises(ToolLoopInterventionError) as exc_info:
            selector.check_loop_intervention("remove_path", args)

        assert "Tool loop detected" in str(exc_info.value)
        assert "remove_path" in str(exc_info.value)


class TestExecutionPlannerAndReplanning:
    """Phase 7: Multi-step execution planning and dynamic recovery."""

    def test_plan_decomposition_for_compound_goal(self):
        planner = ExecutionPlanner()
        available = {"mkdir", "open_path", "process", "exec"}

        plan = planner.create_plan("create folder E:\\work and open E:\\work", available)
        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "mkdir"
        assert plan.steps[1].tool_name == "open_path"

    def test_dynamic_replanning_on_failure(self):
        planner = ExecutionPlanner()
        available = {"open_path", "exec"}

        plan = planner.create_plan("open notepad", available)
        assert plan.steps[0].tool_name == "open_path"

        # Simulate failure in open_path
        replanned = planner.replan_on_failure(plan, 1, "open_path execution failed", available)
        assert replanned.status == "executing"
        assert replanned.steps[0].tool_name == "exec"
        assert "Start-Process" in replanned.steps[0].arguments["command"]


class TestObservationNormalization:
    """Phase 6: Observation normalization and tangible evidence extraction."""

    def test_successful_observation_extracts_evidence(self):
        obs = ObservationNormalizer.normalize(
            tool_name="mkdir",
            args={"path": "E:/test_folder"},
            raw_output="Directory created successfully.",
        )
        assert obs.status == "success"
        assert obs.is_verified is True
        assert obs.tangible_evidence["path"] == "E:/test_folder"

    def test_error_detection_and_recovery_hint(self):
        obs = ObservationNormalizer.normalize(
            tool_name="remove_path",
            args={"path": "C:/Program Files/WindowsApps"},
            raw_output="[WinError 5] Access is denied: 'C:/Program Files/WindowsApps'",
        )
        assert obs.status == "failed"
        assert obs.is_verified is False
        assert "elevated permissions" in obs.actionable_recovery_hint.lower()


class TestTruthfulnessAndClaimGroundingParity:
    """Phase 12: Truthfulness Engine and Claim Grounding Filter."""

    def test_ungrounded_success_claim_is_intercepted(self):
        # Model claims it closed WhatsApp, but no tool was executed
        res = ClaimGroundingFilter.validate_and_ground(
            assistant_text="I have closed WhatsApp for you.",
            recent_actions=[],
            last_execution_record=None,
        )
        assert res.is_truthful is False
        assert "have not executed that action yet" in res.grounded_text
        assert len(res.discrepancies) > 0

    def test_contradicted_success_claim_after_tool_failure_is_corrected(self):
        # Model claims folder was deleted, but the tool failed with Access Denied
        failed_record = VerificationOutcome(
            status="failed",
            verified=False,
            tool_name="remove_path",
            error="Access is denied: C:/Program Files/WindowsApps",
        )

        class MockRecord:
            tool_name = "remove_path"
            status = "failed"
            verification = failed_record

        res = ClaimGroundingFilter.validate_and_ground(
            assistant_text="I have deleted the folder successfully.",
            recent_actions=[
                {"tool": "remove_path", "status": "failed", "detail": "Access is denied"}
            ],
            last_execution_record=MockRecord(),
        )
        assert res.is_truthful is False
        assert "did not succeed" in res.grounded_text
        assert "Access is denied" in res.grounded_text

    def test_verified_success_claim_is_allowed(self):
        # Tool was executed and verified on the host
        res = ClaimGroundingFilter.validate_and_ground(
            assistant_text="I have opened notepad.",
            recent_actions=[{"tool": "open_path", "status": "success", "target": "notepad"}],
        )
        assert res.is_truthful is True
        assert res.grounded_text == "I have opened notepad."


class TestProviderDecisionAdapterParity:
    """Phase 11: Multi-provider abstraction."""

    def test_gemini_and_openai_call_normalization(self):
        # Test OpenAI format
        openai_call = {
            "id": "call_123",
            "function": {
                "name": "process",
                "arguments": '{"action": "kill", "session_id": "notepad"}',
            },
        }
        adapted = ProviderDecisionAdapter.adapt_openai_call(openai_call)
        assert adapted.call_id == "call_123"
        assert adapted.name == "process"
        assert adapted.arguments["action"] == "kill"
        assert adapted.arguments["session_id"] == "notepad"

        # Test OpenAI response creation
        nfr = NormalizedFunctionResponse(
            call_id="call_123",
            name="process",
            result_text="Process closed.",
            is_error=False,
        )
        resp_dict = ProviderDecisionAdapter.create_openai_response(nfr)
        assert resp_dict["role"] == "tool"
        assert resp_dict["tool_call_id"] == "call_123"
        assert resp_dict["content"] == "Process closed."


class TestClosedLoopDecisionEngine:
    """Integration: Full Decision Engine loop."""

    def test_decision_engine_closed_loop(self):
        engine = DecisionEngine()

        # 1. Analyze Intent
        intent = engine.analyze_intent("create folder E:/test_closed_loop")
        assert intent.is_actionable is True

        # 2. Preflight Arguments
        args = engine.preflight_tool_execution("mkdir", {"path": "E:\\\\test_closed_loop"})
        assert args["path"] == "E:/test_closed_loop"

        # 3. Process Observation
        obs = engine.process_tool_observation(
            tool_name="mkdir",
            arguments=args,
            raw_output="Directory created successfully.",
        )
        assert obs.is_verified is True

        # 4. Ground Response
        grounding = engine.ground_response(
            assistant_text="I have created the folder for you.",
            recent_actions=[
                {"tool": "mkdir", "status": "success", "target": "E:/test_closed_loop"}
            ],
        )
        assert grounding.is_truthful is True
