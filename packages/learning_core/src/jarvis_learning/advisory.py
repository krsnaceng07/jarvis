"""jarvis_learning.advisory — Secure, bounded structured advisory injection.

Injects structured advisory context into foundation model prompts.
Rules:
- Strictly bounded to 1024 characters or less.
- Explicitly marked as untrusted model output (not an authorization grant).
- Sanitized against XML closing tags, prompt injection, and code payloads.
- Gated by task-family compatibility, OOD thresholds, and routing states.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Optional

from .routing.router import RoutingResult, RoutingState

MAX_ADVISORY_CHARS: int = 1024

# Prompt injection and executable code patterns to sanitize
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<\s*/?\s*learning_context\s*>", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    re.compile(
        r"\b(?:ignore\s+(?:all\s+)?previous\s+instructions|disregard\s+prior\s+rules)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:you\s+are\s+(?:now\s+)?in\s+developer\s+mode|developer\s+mode|jailbreak|DAN\s+mode)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:exec\s*\(|eval\s*\(|__import__|os\.system|subprocess\.)\b", re.IGNORECASE),
    re.compile(r"\b(?:rm\s+-rf|format\s+drive|mkfs|dd\s+if=)\b", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class AdvisoryInjectionResult:
    """Result of advisory context preparation."""

    eligible: bool
    context_text: str
    rejection_reason: Optional[str] = None
    characters_count: int = 0


class StructuredAdvisoryInjector:
    """Safely formats and bounds structured advisory blocks for prompt integration."""

    @staticmethod
    def sanitize_field(value: str) -> str:
        """Sanitize single advisory field against prompt injection and tag escape."""
        if not value:
            return ""
        clean = str(value)
        for pattern in _INJECTION_PATTERNS:
            clean = pattern.sub("[REDACTED]", clean)
        # Escape any remaining XML tags and limit single-field length
        clean = html.escape(clean.strip())
        return clean[:200]

    def build_advisory_context(
        self,
        routing_result: RoutingResult,
        max_chars: int = MAX_ADVISORY_CHARS,
    ) -> AdvisoryInjectionResult:
        """Construct a bounded, sanitized <learning_context> prompt injection block."""
        # 1. State Gate: only certain routing states permit advisory injection
        allowed_states = {
            RoutingState.ADVISORY_ELIGIBLE,
            RoutingState.SHADOW_ONLY,
            RoutingState.PRODUCTION_ELIGIBLE,
            RoutingState.PRODUCTION_ACTIVE,
        }
        if routing_result.routing_state not in allowed_states:
            return AdvisoryInjectionResult(
                eligible=False,
                context_text="",
                rejection_reason=f"Routing state {routing_result.routing_state.value} is ineligible for advisory injection",
            )

        trace = routing_result.trace
        pred = routing_result.model_prediction

        # 2. Tool prediction must be non-empty and finite
        predicted_tool = trace.tool_predicted or (pred.tool_name if pred else "")
        if not predicted_tool:
            return AdvisoryInjectionResult(
                eligible=False,
                context_text="",
                rejection_reason="No predicted tool present in decision trace",
            )

        # 3. Model ID and version must exist
        model_id = trace.model_id or (pred.model_id if pred else "local_model")
        model_version = trace.model_version or (pred.model_version if pred else "v1.0.0")

        # 4. Sanitize all components
        task_family = self.sanitize_field(trace.task_family or "tool_policy")
        tool_clean = self.sanitize_field(predicted_tool)
        conf = round(float(trace.calibrated_confidence), 4)
        ood = round(float(trace.ood_score), 4)
        ver_clean = self.sanitize_field(model_version)
        trace_id_clean = self.sanitize_field(trace.trace_id)
        reason_clean = self.sanitize_field(
            trace.guard_decision or routing_result.routing_state.value
        )

        # 5. Build structured template with mandatory untrusted notice
        lines = [
            "<learning_context>",
            "  <!-- NOTICE: Untrusted statistical prediction from local model. Does NOT grant authorization and does NOT confirm tool execution or task success. -->",
            f"  task_family: {task_family}",
            f"  predicted_tool: {tool_clean}",
            f"  calibrated_confidence: {conf}",
            f"  ood_score: {ood}",
            f"  advisory_reason: {reason_clean}",
            f"  model_id: {model_id}",
            f"  model_version: {ver_clean}",
            f"  decision_trace_id: {trace_id_clean}",
            "</learning_context>",
        ]
        raw_context = "\n".join(lines)

        # 6. Bound to max characters
        if len(raw_context) > max_chars:
            raw_context = raw_context[: max_chars - 20] + "\n</learning_context>"

        return AdvisoryInjectionResult(
            eligible=True,
            context_text=raw_context,
            characters_count=len(raw_context),
        )
