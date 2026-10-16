"""jarvis.agents.decision.truthfulness — Claim grounding and truthfulness verification engine.

OpenClaw parity: Enforces absolute truthfulness in agent communication.
The model must never claim a real-world action succeeded (opened, created,
deleted, minimized, closed, written) unless supported by verified runtime evidence.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class ClaimGroundingResult:
    is_truthful: bool
    grounded_text: str
    discrepancies: list[str] = field(default_factory=list)
    verified_evidence_found: bool = True


class ClaimGroundingFilter:
    """Detects hallucinated completion claims and grounds responses in physical OS reality."""

    # Affirmative success phrases indicating real-world host changes
    _AFFIRMATIVE_ACTION_PATTERNS = [
        # Process close
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? closed|closed|terminated|killed|shut down)\s+([a-zA-Z0-9_\-\.]+)",
                re.I,
            ),
            "process_kill",
        ),
        (
            re.compile(r"\b([a-zA-Z0-9_\-\.]+)\s+(?:banda\s+gare[ko]?|hataidie[ko]?)\b", re.I),
            "process_kill",
        ),
        # Window minimize / restore
        (
            re.compile(
                r"\b(?:minimized all windows|minimized the windows|showed the desktop|desktop dekhaye|minimize gare)\b",
                re.I,
            ),
            "window_minimize",
        ),
        (
            re.compile(r"\b(?:restored windows|unminimized windows|restore gare)\b", re.I),
            "window_restore",
        ),
        # File deletion
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? (?:deleted|removed|erased)|deleted the (?:file|folder)|hataidie|delete gare)\b",
                re.I,
            ),
            "fs_delete",
        ),
        # Folder creation
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? created (?:the|a)? (?:folder|directory)|created folder|banaidie|folder banaye)\b",
                re.I,
            ),
            "fs_mkdir",
        ),
        # Opening apps/paths
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? opened|opened|launched|started|kholidie|khole)\s+([a-zA-Z0-9_\-\.\:\\]+)",
                re.I,
            ),
            "app_open",
        ),
        # Media play
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? (?:played|started playing)|playing)\s+([a-zA-Z0-9_\-\.\s]+)",
                re.I,
            ),
            "media_play",
        ),
        (
            re.compile(
                r"\b([a-zA-Z0-9_\-\.\s]+?)\s+(?:bajaidie[ko]?|bajaye[ko]?|suru\s+gare[ko]?|bajeko\s+cha)\b",
                re.I,
            ),
            "media_play",
        ),
        # Media pause / resume
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? (?:paused|stopped the (?:video|song|music))|paused the (?:video|song|music)|paused it|rokidie|rokyo)\b",
                re.I,
            ),
            "media_pause",
        ),
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? (?:resumed|continued the (?:video|song|music))|pheri bajaye)\b",
                re.I,
            ),
            "media_resume",
        ),
        # Web Search
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? (?:searched|looked up|found results for))(?:\s+(?:on|in|google|youtube|bing|wikipedia|the web))?(?:\s+(?:for|about))?\s+([a-zA-Z0-9_\-\.\s]+)",
                re.I,
            ),
            "browser_search",
        ),
        (
            re.compile(
                r"\b([a-zA-Z0-9_\-\.\s]+?)\s+(?:khoje[ko]?|search\s+gare[ko]?)\b",
                re.I,
            ),
            "browser_search",
        ),
        # Web Navigation / Open tab
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? opened the (?:tab|website|page|site)|website khole)\s+([a-zA-Z0-9_\-\.\:\/\\]+)",
                re.I,
            ),
            "browser_open",
        ),
        # Web Click
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? clicked (?:on )?|clicked the (?:link|button)|click gare)\s+([a-zA-Z0-9_\-\.\s]+)",
                re.I,
            ),
            "browser_click",
        ),
        # WhatsApp / Messaging send
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? sent (?:the |a )?message to|sent (?:the |a )?message|message pathaye|pathaide|message pathaideko chu)\s*([a-zA-Z0-9_\-\.\s]*)",
                re.I,
            ),
            "whatsapp_send",
        ),
        # Window focus
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? focused (?:on )?(?:the )?window|focused (?:on )?|switch gare|focus gare)\s+([a-zA-Z0-9_\-\.\s]+)",
                re.I,
            ),
            "window_focus",
        ),
        # Calculator compute
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? calculated|calculated that|hisab gare|hisab nikale)\s+([a-zA-Z0-9_\-\.\s\+\*\/\=]+)",
                re.I,
            ),
            "calc_compute",
        ),
        # Subscription / Unsubscription
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? (?:subscribed|channel subscribe gare)|subscribed|subscribe gare)\b",
                re.I,
            ),
            "youtube_subscribe",
        ),
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? (?:unsubscribed|channel unsubscribe gare)|unsubscribed|unsubscribe gare)\b",
                re.I,
            ),
            "youtube_unsubscribe",
        ),
        # Document save
        (
            re.compile(
                r"\b(?:i(?:'ve| have)? saved the (?:document|file|presentation|sheet)|save gare|file save gare)\b",
                re.I,
            ),
            "doc_save",
        ),
    ]

    _ACTION_TO_ALLOWED_TOOLS: dict[str, set[str]] = {
        "process_kill": {"process", "exec", "youtube_close", "browser"},
        "window_minimize": {"process", "exec", "desktop"},
        "window_restore": {"process", "exec", "desktop"},
        "fs_delete": {"remove_path", "exec"},
        "fs_mkdir": {"mkdir", "exec"},
        "app_open": {"open_path", "exec", "browser", "desktop"},
        "media_play": {"browser", "media", "exec", "youtube_play"},
        "media_pause": {"browser", "media", "exec", "youtube_pause"},
        "media_resume": {"browser", "media", "exec", "youtube_resume"},
        "browser_search": {"browser", "web", "youtube_search"},
        "browser_open": {"browser", "web", "open_path"},
        "browser_click": {"browser", "web"},
        "youtube_subscribe": {"youtube_subscribe", "browser"},
        "youtube_unsubscribe": {"youtube_unsubscribe", "browser"},
        "whatsapp_send": {"desktop", "desktop_automation", "whatsapp"},
        "window_focus": {"desktop", "desktop_automation", "process", "exec"},
        "calc_compute": {"desktop", "desktop_automation", "calculator", "exec"},
        "doc_save": {"desktop", "desktop_automation", "editor", "office", "exec"},
    }

    @classmethod
    def validate_and_ground(
        cls,
        assistant_text: str,
        recent_actions: Optional[list[dict[str, Any]]] = None,
        last_execution_record: Optional[Any] = None,
    ) -> ClaimGroundingResult:
        """Inspects assistant text for unverified success claims and corrects them."""
        text = unicodedata.normalize("NFC", assistant_text.strip())
        recent = recent_actions or []
        discrepancies: list[str] = []

        for pattern, action_type in cls._AFFIRMATIVE_ACTION_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue

            target = match.group(1).strip().lower() if match.groups() else ""
            allowed_tools = cls._ACTION_TO_ALLOWED_TOOLS.get(action_type)

            # Find if any relevant tool was executed in recent actions or last_execution_record
            matching_act: Optional[dict[str, Any]] = None
            if recent:
                for act in reversed(recent):
                    act_tool = act.get("tool", "")
                    if not allowed_tools or act_tool in allowed_tools:
                        matching_act = act
                        break
            elif last_execution_record:
                rec_tool = getattr(last_execution_record, "tool_name", "")
                if not allowed_tools or rec_tool in allowed_tools:
                    status = getattr(last_execution_record, "status", None)
                    verif = getattr(last_execution_record, "verification", None)
                    err = getattr(verif, "error", None) if verif else None
                    if verif and not getattr(verif, "verified", True):
                        status = "failed"
                    matching_act = {
                        "tool": rec_tool,
                        "status": status,
                        "detail": err,
                    }

            # Verification Check 1: Did an action actually occur?
            if not matching_act:
                discrepancies.append(
                    f"Claimed success for '{action_type}' ({target or 'action'}), but no matching tool was executed."
                )
                grounded = (
                    "Sir, I have not executed that action yet. "
                    "Please allow me to run the required tool to complete it."
                )
                return ClaimGroundingResult(
                    is_truthful=False,
                    grounded_text=grounded,
                    discrepancies=discrepancies,
                    verified_evidence_found=False,
                )

            # Verification Check 2: Did the relevant tool fail?
            if matching_act.get("status") == "failed":
                err_detail = matching_act.get("detail") or "Verification failed"
                discrepancies.append(
                    f"Claimed success for '{action_type}', but the tool execution ({matching_act.get('tool')}) failed: {err_detail}"
                )
                err_summary = str(err_detail)[:120]
                grounded = (
                    f"Sir, the attempt to {action_type.replace('_', ' ')} did not succeed. "
                    f"Reported: {err_summary}."
                )
                return ClaimGroundingResult(
                    is_truthful=False,
                    grounded_text=grounded,
                    discrepancies=discrepancies,
                    verified_evidence_found=False,
                )

        return ClaimGroundingResult(
            is_truthful=True,
            grounded_text=text,
            discrepancies=[],
            verified_evidence_found=True,
        )
