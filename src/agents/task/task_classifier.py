"""jarvis.agents.task.task_classifier — Task intent classification & continuity disambiguation.

OpenClaw parity:
Enables robust determination of whether incoming user utterances represent:
1. NEW_TASK: A brand new independent goal or action.
2. CONTINUE_ACTIVE_TASK: Continuation of an active multi-step task ('continue', 'next step', 'bhayena feri gara', 'pachi ko step').
3. MODIFY_ACTIVE_TASK: Adjustment or alteration of the existing goal/steps.
4. CANCEL_ACTIVE_TASK: Explicit cancellation or abortion of current task ('cancel', 'stop this', 'chhodideu').
5. RESUME_PAUSED_TASK: Unpausing a suspended task ('resume', 'continue from where we stopped').
6. RETRY_FAILED_STEP: Retrying the most recent failed step or action ('try again', 'retry', 'feri prayas gara').
7. ANSWER_QUESTION_ABOUT_CURRENT_TASK: Inquiry about active task progress/status ('what are you doing?', 'status k chha?').
8. NEW_TASK_REQUIRING_CONTEXT_SWITCH: A new task that explicitly supersedes or switches away from current work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .task_state import TaskState


class TaskIntent(str, Enum):
    """Classified user task intent."""

    NEW_TASK = "NEW_TASK"
    CONTINUE_ACTIVE_TASK = "CONTINUE_ACTIVE_TASK"
    MODIFY_ACTIVE_TASK = "MODIFY_ACTIVE_TASK"
    CANCEL_ACTIVE_TASK = "CANCEL_ACTIVE_TASK"
    RESUME_PAUSED_TASK = "RESUME_PAUSED_TASK"
    RETRY_FAILED_STEP = "RETRY_FAILED_STEP"
    ANSWER_QUESTION_ABOUT_CURRENT_TASK = "ANSWER_QUESTION_ABOUT_CURRENT_TASK"
    NEW_TASK_REQUIRING_CONTEXT_SWITCH = "NEW_TASK_REQUIRING_CONTEXT_SWITCH"


@dataclass(frozen=True, slots=True)
class TaskClassificationResult:
    """Result of classifying a user turn relative to active task state."""

    intent: TaskIntent
    confidence: float
    reason: str
    suggested_action: str
    target_step_index: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
            "target_step_index": self.target_step_index,
        }


# Keywords and regex patterns for rapid deterministic matching (English & Nepali)
_CONTINUE_PATTERNS = [
    r"^(continue|proceed|next|next\s+step|go\s+ahead|keep\s+going)\b",
    r"^(aagadi\s+badha|aagadi\s+bada|agadi\s+badhau|pachhi\s+ko\s+gara|arko\s+gara)\b",
    r"^(continue\s+gara|continue\s+gardeu)\b",
]

_RETRY_PATTERNS = [
    r"^(retry|try\s+again|do\s+it\s+again|repeat)\b",
    r"^(feri\s+gara|feri\s+prayash?\s+gara|feri\s+prayash?|feri\s+gar|arkopali\s+gara)\b",
    r"^(bhayena\s+feri|chaina\s+feri)\b",
]

_CANCEL_PATTERNS = [
    r"^(cancel|abort|stop\s+task|stop\s+this|nevermind|forget\s+it)\b",
    r"^(chhodideu|rokka\s+gara|bata\s+hata|banda\s+gara\s+yo|yo\s+nagara)\b",
]

_RESUME_PATTERNS = [
    r"^(resume|unpause|start\s+again)\b",
    r"^(rokeko\s+bata\s+suru\s+gara|resume\s+gara)\b",
]

_STATUS_PATTERNS = [
    r"^(what\s+are\s+you\s+doing|what\s+step|task\s+status|show\s+progress|how\s+is\s+it\s+going)\b",
    r"^(k\s+gardai\s+chhau|k\s+bhayiraheko\s+chha|progress\s+k\s+chha|status\s+k\s+chha)\b",
]

_CONTEXT_SWITCH_PATTERNS = [
    r"^(instead|wait,\s+do\s+this\s+instead|drop\s+that\s+and|leave\s+that\s+and)\b",
    r"^(yo\s+chhodera\s+arko\s+gara|teslai\s+chhodera|yo\s+bhanda\s+pahila)\b",
]


class TaskClassifier:
    """Classifies user turn intent relative to continuous task state and active context."""

    @classmethod
    def classify(
        cls,
        utterance: str,
        active_task: Optional[TaskState] = None,
        last_action_status: Optional[str] = None,
    ) -> TaskClassificationResult:
        """Classify user utterance into a discrete TaskIntent."""
        text = utterance.strip().lower()
        if not text:
            return TaskClassificationResult(
                intent=TaskIntent.NEW_TASK,
                confidence=1.0,
                reason="Empty utterance",
                suggested_action="idle",
            )

        # 1. Status query check
        for pat in _STATUS_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return TaskClassificationResult(
                    intent=TaskIntent.ANSWER_QUESTION_ABOUT_CURRENT_TASK,
                    confidence=0.95,
                    reason="Utterance matches task status/progress inquiry",
                    suggested_action="report_status",
                    target_step_index=active_task.current_step_index if active_task else None,
                )

        # 2. Cancellation check
        for pat in _CANCEL_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return TaskClassificationResult(
                    intent=TaskIntent.CANCEL_ACTIVE_TASK,
                    confidence=0.95,
                    reason="Utterance matches explicit task cancellation",
                    suggested_action="cancel_task",
                    target_step_index=active_task.current_step_index if active_task else None,
                )

        # 3. Resume paused check
        for pat in _RESUME_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return TaskClassificationResult(
                    intent=TaskIntent.RESUME_PAUSED_TASK,
                    confidence=0.90,
                    reason="Utterance matches resume suspended task",
                    suggested_action="resume_task",
                    target_step_index=active_task.current_step_index if active_task else None,
                )

        # 4. If an active task exists:
        if active_task and active_task.status not in ("COMPLETED", "CANCELLED", "FAILED"):
            # Context switch check
            for pat in _CONTEXT_SWITCH_PATTERNS:
                if re.search(pat, text, re.IGNORECASE):
                    return TaskClassificationResult(
                        intent=TaskIntent.NEW_TASK_REQUIRING_CONTEXT_SWITCH,
                        confidence=0.90,
                        reason="Utterance indicates superseding current active task with a new objective",
                        suggested_action="pause_or_replace_task",
                    )

            # Retry check (especially if last action failed or user indicates failure)
            if (
                last_action_status == "failed"
                or "bhayena" in text
                or "chaina" in text
                or "failed" in text
            ):
                for pat in _RETRY_PATTERNS:
                    if re.search(pat, text, re.IGNORECASE):
                        return TaskClassificationResult(
                            intent=TaskIntent.RETRY_FAILED_STEP,
                            confidence=0.95,
                            reason="Recent step failed and user requested retry",
                            suggested_action="retry_step",
                            target_step_index=active_task.current_step_index,
                        )

            # Continue check
            for pat in _CONTINUE_PATTERNS:
                if re.search(pat, text, re.IGNORECASE):
                    next_idx = active_task.current_step_index + 1
                    return TaskClassificationResult(
                        intent=TaskIntent.CONTINUE_ACTIVE_TASK,
                        confidence=0.95,
                        reason="Utterance matches continuation keyword with active task",
                        suggested_action="advance_and_execute_step",
                        target_step_index=next_idx if next_idx <= len(active_task.steps) else None,
                    )

            # General retry pattern match
            for pat in _RETRY_PATTERNS:
                if re.search(pat, text, re.IGNORECASE):
                    return TaskClassificationResult(
                        intent=TaskIntent.RETRY_FAILED_STEP,
                        confidence=0.90,
                        reason="Utterance requests retry of current step",
                        suggested_action="retry_step",
                        target_step_index=active_task.current_step_index,
                    )

            # Short conversational affirmation ('yes', 'ok', 'go') when waiting for confirmation
            if text in ("yes", "ok", "sure", "proceed", "hunchha", "huss", "thik chha"):
                return TaskClassificationResult(
                    intent=TaskIntent.CONTINUE_ACTIVE_TASK,
                    confidence=0.85,
                    reason="Affirmative response continuing active task",
                    suggested_action="advance_and_execute_step",
                    target_step_index=active_task.current_step_index,
                )

        # 5. Default to NEW_TASK
        return TaskClassificationResult(
            intent=TaskIntent.NEW_TASK,
            confidence=0.80,
            reason="Utterance represents a new independent command or question",
            suggested_action="create_or_execute_new_task",
        )


class BrowserIntent(str, Enum):
    """Structured classification for browser task continuity matching OpenClaw parity."""

    CONTINUATION = "continuation"
    NEW_TASK = "new_task"
    PARALLEL_TASK = "parallel_task"
    CLARIFICATION = "clarification"
    CORRECTION = "correction"
    CANCELLATION = "cancellation"
    FOLLOW_UP = "follow_up"
    UNRELATED_QUESTION = "unrelated_question"


@dataclass(frozen=True, slots=True)
class BrowserTaskClassification:
    """Outcome of browser task continuity classification."""

    intent: BrowserIntent
    confidence: float
    reason: str
    reuse_active_session: bool
    target_application: str = ""
    suggested_action: str = ""


class BrowserTaskClassifier:
    """Classifies user intent relative to active browser session and tab state."""

    _PRONOUNS_AND_DEICTICS = {
        "that", "this", "it", "the", "that one", "this one", "first", "second",
        "tyo", "yo", "tyo channel", "yo video", "pahilo", "dosro"
    }

    _UNRELATED_QUESTION_PATTERNS = [
        r"^(what|who|when|where|why|how)\s+(is|are|was|were|do|does|did)\b",
        r"^(k\s+ho|kasari|kahile|kina)\b",
        r"^(tell\s+me\s+about|explain|define|calculate)\b",
    ]

    @classmethod
    def classify(
        cls,
        user_utterance: str,
        active_app: str = "",
        active_url: str = "",
        has_active_session: bool = False,
    ) -> BrowserTaskClassification:
        """Classify user intent with awareness of active browser state."""
        text = user_utterance.strip().lower()

        # 1. Cancellation check
        if any(w in text for w in ("cancel", "abort", "stop", "nevermind", "forget it", "chhodideu", "nagara")):
            return BrowserTaskClassification(
                intent=BrowserIntent.CANCELLATION,
                confidence=0.98,
                reason="User explicitly requested task cancellation",
                reuse_active_session=False,
                suggested_action="cancel_task",
            )

        # 2. Correction check (e.g. "No, the second one", "haina arko")
        if text.startswith(("no,", "not that", "haina", "instead", "rather")):
            return BrowserTaskClassification(
                intent=BrowserIntent.CORRECTION,
                confidence=0.92,
                reason="User corrected previous target or parameter",
                reuse_active_session=has_active_session,
                target_application=active_app,
                suggested_action="re_target_action",
            )

        # 3. Unrelated question check (e.g. "What is today's date?", "Who is Einstein?")
        if not any(w in text for w in ("youtube", "video", "channel", "song", "tab", "page", "browser", "play", "pause")):
            for pat in cls._UNRELATED_QUESTION_PATTERNS:
                if re.search(pat, text, re.IGNORECASE):
                    return BrowserTaskClassification(
                        intent=BrowserIntent.UNRELATED_QUESTION,
                        confidence=0.88,
                        reason="Informational question unrelated to browser session",
                        reuse_active_session=False,
                        suggested_action="answer_directly_without_browser",
                    )

        # 4. Continuation check if active session exists
        if has_active_session and active_app:
            # Check for pronouns or sequential follow-ups
            has_pronoun = any(re.search(rf"\b{re.escape(p)}\b", text) for p in cls._PRONOUNS_AND_DEICTICS)
            is_followup = any(w in text for w in ("now", "then", "next", "also", "ani", "aba", "pachi"))
            app_action_words = (
                "search", "play", "pause", "subscribe", "unsubscribe", "unsub",
                "like", "dislike", "follow", "click", "open", "mute", "unmute",
                "skip", "volume", "fullscreen", "khoja", "bajau", "chalao", "hatau",
            )
            has_app_action = any(w in text for w in app_action_words)

            if has_pronoun or is_followup or (has_app_action and not any(other_app in text for other_app in ("gmail", "whatsapp", "github", "spotify") if other_app != active_app)):
                return BrowserTaskClassification(
                    intent=BrowserIntent.CONTINUATION,
                    confidence=0.92,
                    reason=f"Follow-up command referencing active {active_app} session/target",
                    reuse_active_session=True,
                    target_application=active_app,
                    suggested_action="reuse_active_tab",
                )

        # 5. Explicit new application task
        for known_app in ("youtube", "google", "whatsapp", "github", "spotify", "gmail"):
            if known_app in text:
                is_same_app = (known_app == active_app)
                return BrowserTaskClassification(
                    intent=BrowserIntent.CONTINUATION if (is_same_app and has_active_session) else BrowserIntent.NEW_TASK,
                    confidence=0.90,
                    reason=f"Utterance specifies '{known_app}' target",
                    reuse_active_session=is_same_app and has_active_session,
                    target_application=known_app,
                    suggested_action="reuse_active_tab" if (is_same_app and has_active_session) else "open_or_switch_tab",
                )

        # 6. Default fallback
        return BrowserTaskClassification(
            intent=BrowserIntent.NEW_TASK,
            confidence=0.75,
            reason="Generic command; defaulting to fresh task",
            reuse_active_session=False,
            suggested_action="evaluate_as_new_task",
        )

