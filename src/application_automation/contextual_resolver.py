"""jarvis.application_automation.contextual_resolver — Contextual intent & pronoun resolution.

Resolves anaphoric expressions ("it", "this song", "pause", "resume", "skip ad", "volume up")
against the active application and media state, enabling natural multi-turn conversations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .active_tab_tracker import ActiveTabTracker


@dataclass(slots=True)
class ResolvedAction:
    """The resolved actionable intent with target application and parameters."""

    is_contextual: bool
    app_type: str
    action_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    target_tab_id: Optional[str] = None
    explanation: str = ""


class ContextualResolver:
    """Resolves elliptical and pronoun-based user requests against active application state."""

    def __init__(self, tab_tracker: Optional[ActiveTabTracker] = None) -> None:
        self._tab_tracker = tab_tracker or ActiveTabTracker.get_instance()
        self._last_media_title: Optional[str] = None
        self._last_search_query: Optional[str] = None

    def record_media_state(self, title: Optional[str] = None, query: Optional[str] = None) -> None:
        if title:
            self._last_media_title = title
        if query:
            self._last_search_query = query

    def resolve_utterance(
        self,
        utterance: str,
        current_app_state: Optional[str] = None,
        active_media_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[ResolvedAction]:
        """Attempt to resolve user utterance to an application action."""
        if not utterance:
            return None

        clean = utterance.strip().lower()
        active_tab = self._tab_tracker.get_tab()
        active_app = active_tab.app_type if active_tab else "generic"

        # If not already on YouTube tab, check if a YouTube tab is open
        if active_app != "youtube":
            yt_tab = self._tab_tracker.find_tab_by_app("youtube")
            if yt_tab:
                active_tab = yt_tab
                active_app = "youtube"

        target_id = active_tab.suggested_target_id if active_tab else None

        # ── 1. Search and Play Patterns ──────────────────────────────
        # e.g. "search believer and play it", "play believer on youtube", "search for believer"
        m_search_play = re.search(
            r"(?:search\s+(?:for\s+)?|play\s+)(.+?)(?:\s+and\s+play(?:\s+it)?|\s+on\s+youtube)?$",
            clean,
        )
        if m_search_play and ("youtube" in clean or active_app == "youtube"):
            query = m_search_play.group(1).strip()
            # Clean common filler prefixes/suffixes
            query = re.sub(r"^(?:for\s+|the\s+song\s+|video\s+)", "", query)
            query = re.sub(r"\s+on\s+youtube$", "", query)
            query = re.sub(r"\s+and\s+play(?:\s+it)?$", "", query)
            if query and query not in {"it", "this", "song", "video", "youtube"}:
                self._last_search_query = query
                return ResolvedAction(
                    is_contextual=True,
                    app_type="youtube",
                    action_name="search_and_play",
                    arguments={"query": query},
                    target_tab_id=target_id,
                    explanation=f"Resolved search and play for '{query}' on YouTube.",
                )

        # If we have an active YouTube application session:
        if active_app == "youtube":
            # ── 2. Play / Play It / Resume Patterns ───────────────────
            if clean in {
                "play",
                "play it",
                "resume",
                "resume it",
                "continue",
                "play the song",
                "play this",
                "play video",
                "start video",
            }:
                # If currently on search results, play first result
                if current_app_state in ("SEARCH_RESULTS", "SEARCHING"):
                    return ResolvedAction(
                        is_contextual=True,
                        app_type="youtube",
                        action_name="play_first_result",
                        arguments={},
                        target_tab_id=target_id,
                        explanation="Play first video from active search results.",
                    )
                # If paused, resume
                return ResolvedAction(
                    is_contextual=True,
                    app_type="youtube",
                    action_name="resume",
                    arguments={},
                    target_tab_id=target_id,
                    explanation="Resume paused YouTube playback.",
                )

            # ── 3. Pause / Stop Patterns ──────────────────────────────
            if clean in {
                "pause",
                "pause it",
                "stop",
                "stop it",
                "stop the music",
                "pause the music",
                "pause music",
                "stop music",
                "pause video",
                "stop video",
                "pause playback",
            }:
                return ResolvedAction(
                    is_contextual=True,
                    app_type="youtube",
                    action_name="pause",
                    arguments={},
                    target_tab_id=target_id,
                    explanation="Pause active YouTube video.",
                )

            # ── 4. Skip Ad Patterns ───────────────────────────────────
            if clean in {"skip", "skip ad", "skip ads", "skip the ad", "skip this ad"}:
                return ResolvedAction(
                    is_contextual=True,
                    app_type="youtube",
                    action_name="skip_ad",
                    arguments={},
                    target_tab_id=target_id,
                    explanation="Skip active video advertisement.",
                )

            # ── 5. Volume & Audio Control Patterns ────────────────────
            if any(k in clean for k in ("volume up", "louder", "turn it up", "sound up")):
                return ResolvedAction(
                    is_contextual=True,
                    app_type="youtube",
                    action_name="volume_up",
                    arguments={"step": 10},
                    target_tab_id=target_id,
                    explanation="Increase YouTube player volume.",
                )
            if any(k in clean for k in ("volume down", "softer", "turn it down", "sound down")):
                return ResolvedAction(
                    is_contextual=True,
                    app_type="youtube",
                    action_name="volume_down",
                    arguments={"step": 10},
                    target_tab_id=target_id,
                    explanation="Decrease YouTube player volume.",
                )
            if clean in {"mute", "mute it", "shut up"}:
                return ResolvedAction(
                    is_contextual=True,
                    app_type="youtube",
                    action_name="mute",
                    arguments={},
                    target_tab_id=target_id,
                    explanation="Mute YouTube player.",
                )
            if clean in {"unmute", "unmute it"}:
                return ResolvedAction(
                    is_contextual=True,
                    app_type="youtube",
                    action_name="unmute",
                    arguments={},
                    target_tab_id=target_id,
                    explanation="Unmute YouTube player.",
                )

        return None

    def format_context_prompt(
        self,
        current_state: Optional[str] = None,
        media_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format active application state into a grounded prompt section for the model."""
        active_tab = self._tab_tracker.get_tab()
        if not active_tab:
            return ""

        lines = ["[ACTIVE APPLICATION CONTEXT]"]
        lines.append(f"Foreground App: {active_tab.app_type.capitalize()} (tab: '{active_tab.suggested_target_id}')")
        lines.append(f"Current URL: {active_tab.url}")
        if active_tab.title:
            lines.append(f"Page Title: {active_tab.title}")

        if current_state:
            lines.append(f"App State: {current_state}")

        if media_info:
            title = media_info.get("title") or self._last_media_title
            if title:
                lines.append(f"Active Media: '{title}'")
            paused = media_info.get("paused")
            if paused is not None:
                lines.append(f"Playback Status: {'PAUSED' if paused else 'PLAYING'}")
            curr = media_info.get("currentTime")
            dur = media_info.get("duration")
            if curr is not None and dur is not None:
                lines.append(f"Position: {int(curr)}s / {int(dur)}s")

        lines.append(
            "Anaphora Guidance: When user refers to 'it', 'the video', or requests 'pause', 'resume', "
            "ground your response directly in the active application and media state above."
        )
        return "\n".join(lines) + "\n"
