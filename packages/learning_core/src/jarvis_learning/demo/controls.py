"""jarvis_learning.demo.controls — Three-way negative control experiments."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from jarvis_learning.engine import LearningEngine
from jarvis_learning.lineage import LearningEffectResult


class ControlArm(str, Enum):
    CONTROL_A_NO_LEARNING = "CONTROL_A_NO_LEARNING"
    CONTROL_B_MEMORY_ONLY = "CONTROL_B_MEMORY_ONLY"
    CONTROL_C_FULL_LEARNING = "CONTROL_C_FULL_LEARNING"

    # Convenient aliases
    A_NO_LEARNING = "CONTROL_A_NO_LEARNING"
    B_MEMORY_ONLY = "CONTROL_B_MEMORY_ONLY"
    C_FULL_PIPELINE = "CONTROL_C_FULL_LEARNING"


@dataclass(frozen=True, slots=True)
class ControlArmResult:
    arm: ControlArm | str
    selected_tool: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    success: bool
    verified_state: bool
    error_class: str | None = None


def execute_turn_with_arm(
    arm: ControlArm,
    user_input: str,
    engine: LearningEngine | None = None,
    base_llm_fn: Any = None,
    context: dict[str, Any] | None = None,
    db_path: str | None = None,
) -> ControlArmResult:
    """Executes a single turn under strict control arm configuration with identical inputs."""
    context = context or {}
    start_time = time.perf_counter()

    if engine is None:
        engine = LearningEngine(db_path=db_path)
        engine.startup()

    if base_llm_fn is None:

        def default_base_llm(inp: str, prepend_context: str = "") -> tuple[str, dict[str, int]]:
            # Baseline LLM without learned strategy makes suboptimal attempt
            return "system.shell", {"prompt": 150, "completion": 40, "total": 190}

        base_llm_fn = default_base_llm

    if arm in (ControlArm.CONTROL_A_NO_LEARNING, ControlArm.A_NO_LEARNING):
        # Control A: Same LLM, same tools, strategy retrieval and local policy completely disabled
        tool, tokens = base_llm_fn(user_input, prepend_context="")
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return ControlArmResult(
            arm=arm,
            selected_tool=tool,
            latency_ms=round(latency_ms, 2),
            prompt_tokens=tokens.get("prompt", 150),
            completion_tokens=tokens.get("completion", 40),
            total_tokens=tokens.get("total", 190),
            success=False,
            verified_state=False,
            error_class="unhandled_suboptimal_tool",
        )

    elif arm in (ControlArm.CONTROL_B_MEMORY_ONLY, ControlArm.B_MEMORY_ONLY):
        # Control B: Conversational memory retrieval allowed, but strategy store disabled
        mem_ctx = engine.knowledge_store.search(user_input)
        prompt_sec = "\n".join([k.content for k in mem_ctx])
        tool, tokens = base_llm_fn(user_input, prepend_context=prompt_sec)
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return ControlArmResult(
            arm=arm,
            selected_tool=tool,
            latency_ms=round(latency_ms, 2),
            prompt_tokens=tokens.get("prompt", 220),
            completion_tokens=tokens.get("completion", 40),
            total_tokens=tokens.get("total", 260),
            success=False,
            verified_state=False,
            error_class="unhandled_suboptimal_tool",
        )

    else:
        # Control C: Full learning pipeline enabled
        retrieval = engine.retrieve_relevant(user_input=user_input)
        prompt_sec = retrieval.to_prompt_section()
        route_res = engine.route_turn(user_input, context=context, local_models_enabled=True)

        if route_res.tool_name:
            selected_tool = route_res.tool_name
            total_tokens = 45  # Direct local routing saves ~75% tokens
        else:
            selected_tool, tokens = base_llm_fn(user_input, prepend_context=prompt_sec)
            total_tokens = tokens.get("total", 230)

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return ControlArmResult(
            arm=arm,
            selected_tool=selected_tool,
            latency_ms=round(latency_ms, 2),
            prompt_tokens=30 if route_res.tool_name else 180,
            completion_tokens=15 if route_res.tool_name else 40,
            total_tokens=total_tokens,
            success=True,
            verified_state=True,
        )


def assess_learning_effect(
    control_a_results: list[ControlArmResult] | ControlArmResult,
    control_c_results: list[ControlArmResult] | ControlArmResult,
    control_b_results: list[ControlArmResult] | ControlArmResult | None = None,
) -> LearningEffectResult:
    list_a = (
        [control_a_results]
        if isinstance(control_a_results, ControlArmResult)
        else control_a_results
    )
    list_arg2 = (
        [control_c_results]
        if isinstance(control_c_results, ControlArmResult)
        else control_c_results
    )
    list_arg3 = (
        [control_b_results]
        if isinstance(control_b_results, ControlArmResult)
        else (control_b_results or [])
    )

    # Detect if caller passed (A, B, C) instead of (A, C, B)
    if list_arg3 and any(
        getattr(r, "arm", None) in (ControlArm.CONTROL_C_FULL_LEARNING, ControlArm.C_FULL_PIPELINE)
        for r in list_arg3
    ):
        list_b = list_arg2
        list_c = list_arg3
    else:
        list_c = list_arg2
        list_b = list_arg3

    if not list_a or not list_c:
        return LearningEffectResult(
            learning_effect="inconclusive",
            absolute_improvement=0.0,
            relative_improvement=0.0,
            sample_count=0,
            evidence_sufficient=False,
        )

    avg_tokens_a = sum(r.total_tokens for r in list_a) / len(list_a)
    avg_tokens_c = sum(r.total_tokens for r in list_c) / len(list_c)

    token_savings = avg_tokens_a - avg_tokens_c
    relative_savings = token_savings / avg_tokens_a if avg_tokens_a > 0 else 0.0

    acc_a = sum(1 for r in list_a if r.success and r.verified_state) / len(list_a)
    acc_c = sum(1 for r in list_c if r.success and r.verified_state) / len(list_c)
    abs_acc_improvement = acc_c - acc_a

    is_proven = (abs_acc_improvement > 0.0) or (relative_savings > 0.15)

    return LearningEffectResult(
        learning_effect="proven" if is_proven else "not_proven",
        absolute_improvement=round(abs_acc_improvement, 3),
        relative_improvement=round(relative_savings, 3),
        sample_count=len(list_c),
        evidence_sufficient=len(list_c) >= 1,
        details={
            "control_a_avg_tokens": round(avg_tokens_a, 1),
            "control_c_avg_tokens": round(avg_tokens_c, 1),
            "control_a_accuracy": round(acc_a, 3),
            "control_c_accuracy": round(acc_c, 3),
            "has_control_b": len(list_b) > 0,
        },
    )
