"""jarvis.agents.decision.intent — Intent understanding and actionability classification.

OpenClaw parity: Maps user requests to execution bias requirements,
detecting whether an action is required and identifying target entities.
Supports English, Nepali, and mixed conversational patterns.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class IntentCategory(str, Enum):
    ACTIONABLE_FILESYSTEM = "actionable_filesystem"
    ACTIONABLE_PROCESS = "actionable_process"
    ACTIONABLE_WINDOW = "actionable_window"
    ACTIONABLE_BROWSER = "actionable_browser"
    ACTIONABLE_SHELL = "actionable_shell"
    ACTIONABLE_MEMORY = "actionable_memory"
    INFORMATIONAL_FACTUAL = "informational_factual"
    CONVERSATIONAL = "conversational"
    CORRECTION_NEGATION = "correction_negation"
    SAFETY_SHUTDOWN = "safety_shutdown"


@dataclass(slots=True)
class AnalyzedIntent:
    raw_text: str
    category: IntentCategory
    is_actionable: bool
    primary_tool: Optional[str] = None
    target_entity: Optional[str] = None
    parameters: dict[str, str] = field(default_factory=dict)
    confidence: float = 1.0
    requires_host_verification: bool = False
    action_bias_directive: str = ""

    @property
    def is_negation(self) -> bool:
        """Indicates if this intent is conversational negation or state correction."""
        return self.category == IntentCategory.CORRECTION_NEGATION

    @property
    def suggested_tool(self) -> Optional[str]:
        """Convenience alias for primary_tool."""
        return self.primary_tool


class IntentClassifier:
    """Classifies user intent to enforce OpenClaw Execution Bias."""

    _NON_TARGET_WORDS = {
        # English articles, pronouns, prepositions, fillers
        "the",
        "this",
        "it",
        "that",
        "up",
        "a",
        "an",
        "now",
        "please",
        "to",
        "for",
        "in",
        "on",
        "at",
        "by",
        "from",
        "with",
        "me",
        "you",
        "him",
        "her",
        "us",
        "them",
        "something",
        "anything",
        "some",
        # Hindi/Urdu/Nepali auxiliary verbs, grammar markers, and filler words
        "karo",
        "kar",
        "gara",
        "gar",
        "gardeu",
        "garideu",
        "garnu",
        "khol",
        "khola",
        "kholideu",
        "kholdyu",
        "chalao",
        "chalaideu",
        "chalau",
        "bana",
        "banaideu",
        "banau",
        "hatau",
        "hataideu",
        "deu",
        "hai",
        "na",
        "re",
        "ta",
        "ho",
        "bhaneko",
        "kasto",
        "kina",
        "pani",
        "lai",
        "bata",
        "dekhi",
        "sanga",
        "kijiye",
        "karna",
        "kardo",
        "dikhaye",
        "dikhao",
        "bhayena",
        "chaina",
    }

    _WEB_SERVICES = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "github": "https://github.com",
        "reddit": "https://www.reddit.com",
        "twitter": "https://twitter.com",
        "x": "https://x.com",
        "facebook": "https://www.facebook.com",
        "instagram": "https://www.instagram.com",
        "gmail": "https://mail.google.com",
        "netflix": "https://www.netflix.com",
        "chatgpt": "https://chatgpt.com",
        "deepseek": "https://www.deepseek.com",
        "deep seek": "https://www.deepseek.com",
        "deep seek ai": "https://www.deepseek.com",
        "deep sleep ai": "https://www.deepseek.com",
        "deepseek ai": "https://www.deepseek.com",
        "deepseekai": "https://www.deepseek.com",
        "amazon": "https://www.amazon.com",
        "wikipedia": "https://www.wikipedia.org",
        "spotify": "https://open.spotify.com",
    }

    _YOUTUBE_CLOSE_PATTERNS = [
        re.compile(r"\b(?:close|banda\s+gara|banda\s+karo|exit|terminate)\s+(?:youtube|yt)(?:\s+tab)?\b", re.I),
        re.compile(r"\b(?:youtube|yt)(?:\s+ko)?(?:\s+tab)?\s+(?:banda\s+gara|close\s+gara|banda\s+karo|close\s+karo|hatau|hata)\b", re.I),
    ]

    _TAB_CLOSE_PATTERNS = [
        re.compile(r"\b(?:close|banda\s+gara|banda\s+karo)\s+(?:current\s+)?tab\b", re.I),
        re.compile(r"\b(?:yo|current|active)?\s*tab\s+(?:banda\s+gara|close\s+gara|banda\s+karo|close\s+karo|hatau)\b", re.I),
    ]

    _BROWSER_OPEN_PATTERNS = [
        re.compile(
            r"\b(?:open|khol|khola|chalao|start|launch)\s+(?:the\s+)?(?:browser|chrome|default\s+browser)\b",
            re.I,
        ),
        re.compile(
            r"\b(?:browser|chrome|default\s+browser)\s+(?:open|khol|khola|chalao|start|launch)(?:\s+(?:karo|kar|gara|gar|gardeu|garideu|garnu|deu|na|please))?\b",
            re.I,
        ),
    ]

    _PROCESS_KILL_PATTERNS = [
        re.compile(r"\b(?:close|kill|terminate|stop|exit)\s+([a-zA-Z0-9_\-\.]+)", re.I),
        re.compile(
            r"\b([a-zA-Z0-9_\-\.]+)\s+(?:banda\s+gara|close\s+gara|banda\s+karo|close\s+karo|hatau|bata\s+hata)\b",
            re.I,
        ),
    ]

    _WINDOW_PATTERNS = [
        (
            re.compile(
                r"\b(?:minimize|minimize\s+all|show\s+desktop|desktop\s+dekha|minimize\s+gara)\b",
                re.I,
            ),
            "minimize",
        ),
        (
            re.compile(r"\b(?:restore\s+windows|unminimize|maximize\s+all|restore\s+gara)\b", re.I),
            "restore",
        ),
    ]

    _BROWSER_SEARCH_PATTERNS = [
        re.compile(r"\b(?:search|khoja|play)\s+(.+?)\s+(?:on|in|ma)\s+(youtube|google)\b", re.I),
        re.compile(r"\b(?:youtube|google)\s+(?:ma|on|in)\s+(.+?)\s+(?:search|khoja|play)\b", re.I),
        re.compile(r"\b(?:youtube|google)\s+(?:search|khoja)\s+(.+)\b", re.I),
        re.compile(r"\b([a-zA-Z0-9_\-\.\s]+?)\s+(?:search|khoja)(?:\s+(?:gara|gardeu|garideu|karo|garnu))?\b", re.I),
        re.compile(r"\b(?:search|khoja)\s+(.+?)\s+on\s+the\s+web\b", re.I),
    ]

    _YOUTUBE_UNSUBSCRIBE_PATTERNS = [
        re.compile(r"\b(?:pheri\s+|aba\s+|re-?)?(?:unsubscribe|unsub)(?:\s+(?:gara|gardeu|gardau|garideu|karo|garnu|deu))?\b", re.I),
        re.compile(r"\b(?:channel\s+)?(?:unsubscribe|unsub)\b", re.I),
        re.compile(r"\b(?:unsubscribe\s+again|unsub\s+again)\b", re.I),
    ]

    _YOUTUBE_SUBSCRIBE_PATTERNS = [
        re.compile(r"\b(?:pheri\s+|aba\s+|re-?)?(?:subscribe)(?:\s+(?:gara|gardeu|garideu|karo|garnu|deu))?\b", re.I),
        re.compile(r"\b(?:channel\s+)?(?:subscribe)\b", re.I),
        re.compile(r"\b(?:subscribe\s+again|resubscribe)\b", re.I),
    ]

    _YOUTUBE_STATE_PATTERNS = [
        re.compile(r"\b(?:youtube\s+status|youtube\s+state|channel\s+status|channel\s+state)\b", re.I),
        re.compile(r"\b(?:subscribed\s+(?:cha\s+ki\s+chaina|x\s+ki\s+chaina|hai\s+ki\s+nahi))\b", re.I),
        re.compile(r"\byoutube\s+ma\s+k\s+(?:cha|vairacha|chaliracha)\b", re.I),
    ]

    _APP_OPEN_PATTERNS = [
        # Hindi/Nepali/Hinglish: <app> open karo / <app> khola / <app> chalao / <app> kholideu / <app> kholdeu
        re.compile(
            r"\b([a-zA-Z0-9_\-\.\:\\]+(?:\s+[a-zA-Z0-9_\-\.\:\\]+)?)\s+(?:open|khol|khola|kholideu|kholdeu|kholna|kholnu|chalao|chalaideu|chalaunu|start|launch)(?:\s+(?:karo|kar|gara|gar|gardeu|garideu|garnu|deu|na|hai|re|ta|please))?\b",
            re.I,
        ),
        # English: open <app> (allows multi-word targets like "file explorer", "task manager", "vs code")
        re.compile(
            r"\b(?:open|khol|khola|chalao|start|launch)\s+([a-zA-Z0-9_\-\.\:\\]+(?:\s+[a-zA-Z0-9_\-\.\:\\]+)?)",
            re.I,
        ),
    ]

    _SYSTEM_INFO_PATTERNS = [
        re.compile(r"\b(?:system\s+info|system\s+status|system\s+metrics|pc\s+status|pc\s+info|ram\s+usage|cpu\s+usage|disk\s+space|battery\s+status|system\s+specs)\b", re.I),
        re.compile(r"\b(?:system|pc|specs|ram|cpu|battery)\s+(?:check\s+gara|her|hera|dekhao)\b", re.I),
    ]

    _FS_MKDIR_PATTERNS = [
        re.compile(
            r"\b(?:create|make|mkdir|bana)\s+(?:a\s+)?(?:(?:folder|directory)\s+)?(?:named\s+|called\s+)?([^\s]+)",
            re.I,
        ),
        re.compile(r"\b(?:folder|directory)\s+([^\s]+)\s+(?:bana|create\s+gara)\b", re.I),
    ]

    _FS_REMOVE_PATTERNS = [
        re.compile(
            r"\b(?:delete|remove|rm|erase|hatau)\s+(?:(?:file|folder|directory)\s+)?([^\s]+)", re.I
        ),
        re.compile(r"\b([^\s]+)\s+(?:delete\s+gara|hatau|remove\s+gara)\b", re.I),
    ]

    _NEGATION_CORRECTION_PATTERNS = [
        re.compile(
            r"\b(?:chaina|bhayena|vayena|khulena|hataena|failed|didn't work|not open|still open)\b",
            re.I,
        ),
    ]

    _SHUTDOWN_PATTERNS = [
        re.compile(
            r"\b(?:shutdown\s+jarvis|close\s+jarvis|quit\s+jarvis|exit\s+jarvis|jarvis\s+banda\s+gara)\b",
            re.I,
        ),
    ]

    @classmethod
    def classify(cls, text: str) -> AnalyzedIntent:
        normalized = unicodedata.normalize("NFC", text.strip())
        lower = normalized.lower()

        # Check explicit shutdown first
        for pat in cls._SHUTDOWN_PATTERNS:
            if pat.search(lower):
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.SAFETY_SHUTDOWN,
                    is_actionable=True,
                    primary_tool="shutdown_jarvis",
                    requires_host_verification=False,
                    action_bias_directive="Explicit shutdown requested by user. Requires confirmation check.",
                )

        # Check YouTube state (perception queries take precedence over generic negation)
        for pat in cls._YOUTUBE_STATE_PATTERNS:
            if pat.search(normalized):
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.ACTIONABLE_BROWSER,
                    is_actionable=True,
                    primary_tool="youtube_get_state",
                    target_entity="youtube",
                    requires_host_verification=True,
                    action_bias_directive="Inspect active YouTube display status, channel, and subscription state using youtube_get_state.",
                )

        # Check conversational negation / correction
        for pat in cls._NEGATION_CORRECTION_PATTERNS:
            if pat.search(lower) and len(lower.split()) <= 4:
                try:
                    from src.desktop_automation.state.global_state_tracker import GlobalStateTracker

                    GlobalStateTracker.get_instance().record_user_negation_feedback(normalized)
                except Exception:
                    pass
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.CORRECTION_NEGATION,
                    is_actionable=True,
                    confidence=0.95,
                    requires_host_verification=True,
                    action_bias_directive="User reports previous action failed or did not take effect ('chaina'/'bhayena'). Re-check physical host state immediately, focus window or retry.",
                )

        # Check window minimize / restore
        for pat, win_act in cls._WINDOW_PATTERNS:
            if pat.search(normalized):
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.ACTIONABLE_WINDOW,
                    is_actionable=True,
                    primary_tool="process",
                    parameters={"action": win_act},
                    requires_host_verification=True,
                    action_bias_directive=f"Window action requested: call process(action='{win_act}'). Do not answer with plan only.",
                )

        # Check system telemetry and hardware metrics
        for pat in cls._SYSTEM_INFO_PATTERNS:
            if pat.search(normalized):
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.INFORMATIONAL_FACTUAL,
                    is_actionable=True,
                    primary_tool="system_info",
                    requires_host_verification=False,
                    action_bias_directive="Inspect host system metrics, live clock, CPU, RAM, or battery using system_info.",
                )

        # Check YouTube close
        for pat in cls._YOUTUBE_CLOSE_PATTERNS:
            if pat.search(normalized):
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.ACTIONABLE_BROWSER,
                    is_actionable=True,
                    primary_tool="youtube_close",
                    target_entity="youtube",
                    requires_host_verification=True,
                    action_bias_directive="Close only the active YouTube tab using youtube_close. Do NOT close the browser window or kill Chrome.",
                )

        # Check browser tab close
        for pat in cls._TAB_CLOSE_PATTERNS:
            if pat.search(normalized):
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.ACTIONABLE_BROWSER,
                    is_actionable=True,
                    primary_tool="browser",
                    target_entity="tab",
                    parameters={"action": "close"},
                    requires_host_verification=True,
                    action_bias_directive="Close only the active browser tab using browser(action='close'). Do NOT close the browser window or kill Chrome.",
                )

        for pat in cls._BROWSER_OPEN_PATTERNS:
            if pat.search(normalized):
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.ACTIONABLE_BROWSER,
                    is_actionable=True,
                    primary_tool="browser",
                    target_entity="browser",
                    parameters={"action": "open", "url": "about:blank"},
                    requires_host_verification=True,
                    action_bias_directive="Open or focus the browser automation runtime using browser(action='open', url='about:blank').",
                )

        # Check process closing
        for pat in cls._PROCESS_KILL_PATTERNS:
            m = pat.search(normalized)
            if m:
                target = m.group(1).strip()
                target_lower = target.lower()
                if target_lower not in cls._NON_TARGET_WORDS:
                    if target_lower in ("youtube", "yt"):
                        return AnalyzedIntent(
                            raw_text=normalized,
                            category=IntentCategory.ACTIONABLE_BROWSER,
                            is_actionable=True,
                            primary_tool="youtube_close",
                            target_entity="youtube",
                            requires_host_verification=True,
                            action_bias_directive="Close only the active YouTube tab using youtube_close. Do NOT close the browser window or kill Chrome.",
                        )
                    if target_lower in cls._WEB_SERVICES:
                        return AnalyzedIntent(
                            raw_text=normalized,
                            category=IntentCategory.ACTIONABLE_BROWSER,
                            is_actionable=True,
                            primary_tool="browser",
                            target_entity=target_lower,
                            parameters={"action": "close", "target": target_lower},
                            requires_host_verification=True,
                            action_bias_directive=f"Close only the '{target}' browser tab using browser(action='close', targetId='{target_lower}'). Do NOT close the browser window or kill Chrome.",
                        )
                    return AnalyzedIntent(
                        raw_text=normalized,
                        category=IntentCategory.ACTIONABLE_PROCESS,
                        is_actionable=True,
                        primary_tool="process",
                        target_entity=target,
                        parameters={"action": "kill", "session_id": target_lower},
                        requires_host_verification=True,
                        action_bias_directive=f"Close application '{target}' using process(action='kill', session_id='{target}'). Never ask for PID.",
                    )

        # Check YouTube unsubscribe
        for pat in cls._YOUTUBE_UNSUBSCRIBE_PATTERNS:
            if pat.search(normalized):
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.ACTIONABLE_BROWSER,
                    is_actionable=True,
                    primary_tool="youtube_unsubscribe",
                    target_entity="youtube",
                    requires_host_verification=True,
                    action_bias_directive="Unsubscribe from channel on active YouTube tab using youtube_unsubscribe. Confirms via dialog.",
                )

        # Check YouTube subscribe
        for pat in cls._YOUTUBE_SUBSCRIBE_PATTERNS:
            if pat.search(normalized):
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.ACTIONABLE_BROWSER,
                    is_actionable=True,
                    primary_tool="youtube_subscribe",
                    target_entity="youtube",
                    requires_host_verification=True,
                    action_bias_directive="Subscribe to channel on active YouTube tab using youtube_subscribe. Verifies subscription state.",
                )


        # Check browser search
        for pat in cls._BROWSER_SEARCH_PATTERNS:
            m = pat.search(normalized)
            if m:
                query = m.group(1).strip()
                dest = m.group(2).strip().lower() if len(m.groups()) >= 2 else "web"
                if "youtube" in normalized.lower() and dest == "web":
                    dest = "youtube"
                is_yt = (dest == "youtube")
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.ACTIONABLE_BROWSER,
                    is_actionable=True,
                    primary_tool="youtube_search" if is_yt else "browser",
                    target_entity=query,
                    parameters={"query": query, "engine": dest},
                    requires_host_verification=True,
                    action_bias_directive=(
                        f"Search YouTube for '{query}' using youtube_search(query='{query}'). Reuses active YouTube tab without opening duplicate tabs."
                        if is_yt
                        else f"Perform direct search for '{query}' on {dest} via browser(action='open', url=...). Do not explain."
                    ),
                )

        # Check folder creation
        for pat in cls._FS_MKDIR_PATTERNS:
            m = pat.search(normalized)
            if m:
                folder_path = m.group(1).strip()
                if folder_path.lower() not in cls._NON_TARGET_WORDS:
                    return AnalyzedIntent(
                        raw_text=normalized,
                        category=IntentCategory.ACTIONABLE_FILESYSTEM,
                        is_actionable=True,
                        primary_tool="mkdir",
                        target_entity=folder_path,
                        parameters={"path": folder_path},
                        requires_host_verification=True,
                        action_bias_directive=f"Create folder '{folder_path}' using mkdir. Verify host directory existence.",
                    )

        # Check file/folder deletion
        for pat in cls._FS_REMOVE_PATTERNS:
            m = pat.search(normalized)
            if m:
                target = m.group(1).strip()
                if target.lower() not in cls._NON_TARGET_WORDS:
                    return AnalyzedIntent(
                        raw_text=normalized,
                        category=IntentCategory.ACTIONABLE_FILESYSTEM,
                        is_actionable=True,
                        primary_tool="remove_path",
                        target_entity=target,
                        parameters={"path": target},
                        requires_host_verification=True,
                        action_bias_directive=f"Delete '{target}' using remove_path(path=...). Do not claim deletion without physical verification.",
                    )

        # Check app/path opening
        for service_name, url in cls._WEB_SERVICES.items():
            if re.search(
                rf"\b(?:open|khol|chalao|start|launch)\s+{re.escape(service_name)}\b",
                normalized,
                re.I,
            ):
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.ACTIONABLE_BROWSER,
                    is_actionable=True,
                    primary_tool="browser",
                    target_entity=service_name,
                    parameters={"action": "open", "url": url},
                    requires_host_verification=True,
                    action_bias_directive=f"Open '{service_name}' in web browser via browser(action='open', url='{url}').",
                )

        for pat in cls._APP_OPEN_PATTERNS:
            m = pat.search(normalized)
            if m:
                target = m.group(1).strip()
                t_lower = target.lower()
                if t_lower in cls._NON_TARGET_WORDS:
                    continue
                # If target is a known web service or URL, route to browser
                if t_lower in cls._WEB_SERVICES or t_lower.startswith(
                    ("http://", "https://", "www.")
                ):
                    url = cls._WEB_SERVICES.get(t_lower, target)
                    if not url.startswith("http"):
                        url = f"https://{url}"
                    return AnalyzedIntent(
                        raw_text=normalized,
                        category=IntentCategory.ACTIONABLE_BROWSER,
                        is_actionable=True,
                        primary_tool="browser",
                        target_entity=target,
                        parameters={"action": "open", "url": url},
                        requires_host_verification=True,
                        action_bias_directive=f"Open '{target}' in web browser via browser(action='open', url='{url}').",
                    )
                return AnalyzedIntent(
                    raw_text=normalized,
                    category=IntentCategory.ACTIONABLE_PROCESS,
                    is_actionable=True,
                    primary_tool="open_path",
                    target_entity=target,
                    parameters={"target": target},
                    requires_host_verification=True,
                    action_bias_directive=f"Open '{target}' on host PC using open_path(target='{target}').",
                )

        # Conversational fallback
        is_question = lower.endswith("?") or any(
            lower.startswith(w)
            for w in ("what", "how", "why", "who", "when", "where", "kasto", "kina", "ko")
        )
        return AnalyzedIntent(
            raw_text=normalized,
            category=IntentCategory.INFORMATIONAL_FACTUAL
            if is_question
            else IntentCategory.CONVERSATIONAL,
            is_actionable=False,
            requires_host_verification=False,
            action_bias_directive="Informational or conversational turn. Answer directly and concisely.",
        )
