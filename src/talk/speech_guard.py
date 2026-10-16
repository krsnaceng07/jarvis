"""jarvis.talk.speech_guard — Speech-to-Intent Grounding, Anti-Guessing, and Tool Alignment.

Ensures that:
1. Model never guesses tool calls on empty, muffled, or unparsed speech.
2. Unclear, partial, or ambiguous utterances trigger clarification requests instead of premature tool calls.
3. Spoken commands are semantically aligned with the correct host tool (e.g. desktop apps use open_path,
   web searches use browser, app terminations use process, file deletions use remove_path).
4. High-impact destructive voice actions require explicit user affirmation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from src.agents.decision.intent import IntentClassifier, IntentCategory
from src.talk.voice_confirmation import (
    normalize_utterance,
    is_explicit_affirmation,
    is_explicit_refusal,
    requires_high_impact_voice_confirmation,
    VoiceConfirmationScope,
)


@dataclass(slots=True)
class SpeechGroundingResult:
    is_allowed: bool
    clarification_message: Optional[str] = None
    repaired_tool_name: Optional[str] = None
    repaired_args: Optional[dict[str, Any]] = None
    reason: str = ""
    requires_confirmation: bool = False
    confirmation_id: Optional[str] = None


class SpeechGroundingGuard:
    """Grounds incoming voice tool calls against verified user utterances."""

    _FILLER_WORDS = {
        "uh",
        "um",
        "ah",
        "hmm",
        "er",
        "oh",
        "eh",
        "hajur",
        "k",
        "re",
        "like",
        "you",
        "know",
        "well",
        "so",
        "actually",
    }

    _AMBIGUOUS_OPEN = re.compile(
        r"^\s*(?:open|khol|kholideu|start|launch|chalao|explore|explore open kar)\s*$",
        re.I,
    )
    _AMBIGUOUS_CLOSE = re.compile(
        r"^\s*(?:close|kill|banda gara|hata|hatau|exit)\s*$",
        re.I,
    )
    _AMBIGUOUS_DELETE = re.compile(
        r"^\s*(?:delete|remove|hatau|delete gara|erase)\s*$",
        re.I,
    )

    _UNRESOLVED_SPEECH = {
        "i was thinking",
        "maybe we should check",
        "राम्रोसँग सुन",
        "listen carefully",
        "just thinking",
        "let me see",
        "maybe we can check",
        "we should check",
    }

    def __init__(self) -> None:
        self.confirmation_scope = VoiceConfirmationScope()
        self._last_grounded_speech: str = ""

    def validate_voice_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        user_speech: str,
    ) -> SpeechGroundingResult:
        """Validate a tool call generated from voice input.

        Returns SpeechGroundingResult indicating whether the call is allowed,
        must be blocked with clarification, or needs argument/tool repair.
        """
        clean_speech = normalize_utterance(user_speech)
        self._last_grounded_speech = clean_speech
        words = clean_speech.split()

        # ── 1. Check for Pending Voice Confirmation ───────────────────────
        pending = self.confirmation_scope.pending
        if pending is not None:
            if is_explicit_affirmation(clean_speech):
                # The user just affirmed the pending action aloud!
                self.confirmation_scope.pending = None
                return SpeechGroundingResult(
                    is_allowed=True,
                    repaired_tool_name=pending.tool_name,
                    repaired_args=pending.params,
                    reason="User confirmed pending high-impact action aloud.",
                )
            if is_explicit_refusal(clean_speech):
                self.confirmation_scope.pending = None
                return SpeechGroundingResult(
                    is_allowed=False,
                    clarification_message="The user declined or cancelled this action. Acknowledge the cancellation politely.",
                    reason="User explicitly declined pending action.",
                )

        # ── 2. Empty or Pure Noise Transcript Interception ────────────────
        if len(clean_speech) < 2 or not words:
            return SpeechGroundingResult(
                is_allowed=False,
                clarification_message=(
                    "[UNGROUNDED VOICE INTERCEPTION] I did not hear any speech or command from the user. "
                    "DO NOT guess, assume, or call any tool. Politely tell the user that you did not hear them "
                    "clearly and ask them to repeat what they want you to do."
                ),
                reason="Empty or non-existent speech transcript.",
            )

        # Pure filler words check
        if all(w in self._FILLER_WORDS for w in words):
            return SpeechGroundingResult(
                is_allowed=False,
                clarification_message=(
                    f"[UNGROUNDED VOICE INTERCEPTION] The user only uttered hesitation/filler sound ('{user_speech}'). "
                    "DO NOT call any tool. Ask the user politely how you can help them."
                ),
                reason="Speech contains only filler tokens.",
            )

        # Speculative / Unresolved speech interception (never authorize unsolicited tools)
        if clean_speech in self._UNRESOLVED_SPEECH or user_speech.strip() in self._UNRESOLVED_SPEECH:
            return SpeechGroundingResult(
                is_allowed=False,
                clarification_message=(
                    f"[UNGROUNDED VOICE INTERCEPTION] The user's speech appears speculative or unresolved ('{user_speech}'). "
                    "DO NOT guess or execute any tool. Politely ask the user how you can assist them."
                ),
                reason="Unresolved speech cannot authorize tool execution.",
            )

        # ── 3. Ambiguity & Missing Entity Detection ───────────────────────
        if self._AMBIGUOUS_OPEN.match(clean_speech):
            return SpeechGroundingResult(
                is_allowed=False,
                clarification_message=(
                    "The user said to open something but did not specify what app, folder, or file. "
                    "DO NOT guess an app. Ask the user: 'What would you like me to open?' "
                    "(Nepali: 'के खोल्न चाहनुहुन्छ?')"
                ),
                reason="Ambiguous open without entity.",
            )

        if self._AMBIGUOUS_CLOSE.match(clean_speech):
            return SpeechGroundingResult(
                is_allowed=False,
                clarification_message=(
                    "The user said to close something but did not specify which app. "
                    "DO NOT guess an app. Ask the user: 'Which application would you like me to close?' "
                    "(Nepali: 'कुन एप बन्द गर्न चाहनुहुन्छ?')"
                ),
                reason="Ambiguous close without entity.",
            )

        if self._AMBIGUOUS_DELETE.match(clean_speech):
            return SpeechGroundingResult(
                is_allowed=False,
                clarification_message=(
                    "The user said to delete something but did not specify the file or folder. "
                    "DO NOT guess a path. Ask the user: 'Which file or folder would you like to delete?'"
                ),
                reason="Ambiguous delete without entity.",
            )

        # ── 4. Semantic Intent Alignment & Tool Routing ───────────────────
        if tool_name == "audio":
            return self._validate_audio(tool_args, clean_speech)
        if tool_name == "system_info":
            return SpeechGroundingResult(
                is_allowed=True,
                reason="System telemetry and status diagnostics authorized.",
            )
        if tool_name in {"open_path", "remove_path"}:
            # Recognize complete Devanagari commands without weakening unknown-input
            # rejection. Compare against the original transcript: paths need punctuation.
            command = re.fullmatch(
                r"\s*(?:कृपया\s+)?(.+?)\s+(खोल|खोल्नु|खोलिदेऊ|खोलिदेउ|हटाऊ|हटाउ|मेटाऊ|मेटाउ)(?:होस्)?[।.!]?\s*",
                user_speech,
            )
            if command:
                target, verb = command.groups()
                expected_tool = "open_path" if verb.startswith("खोल") else "remove_path"
                if expected_tool == "open_path" and tool_name == "open_path":
                    return SpeechGroundingResult(
                        is_allowed=True,
                        reason="Spoken Devanagari open command authorized.",
                    )
                argument = "target" if expected_tool == "open_path" else "path"
                allowed = tool_name == expected_tool and str(tool_args.get(argument, "")).strip() == target.strip()
                return SpeechGroundingResult(
                    is_allowed=allowed,
                    reason="Spoken path and operation matched." if allowed else "Tool target or operation differs from the spoken request.",
                    clarification_message=None if allowed else "Do not execute this action. Confirm the exact intended target; do not guess a different path.",
                )
        if tool_name == "channel_status":
            # Status is a read-only diagnostic, including when a user reports that
            # messages are not arriving. It is not an app-opening intent.
            requested = re.search(
                r"\b(channel|telegram|whatsapp|discord|imessage)\b|च्यानल|टेलिग्राम|टेलेग्राम|व्हाट्सएप|डिस्कर्ड",
                clean_speech,
            )
            return SpeechGroundingResult(
                is_allowed=bool(requested),
                reason="Channel diagnostic requested."
                if requested
                else "No channel diagnostic request established.",
                clarification_message=None
                if requested
                else "Ask which channel the user wants checked. Do not retry without clarification.",
            )
        if tool_name == "memory_search":
            requested = self._has_explicit_memory_search(clean_speech, tool_args)
            return SpeechGroundingResult(
                is_allowed=requested,
                reason="Memory search matched spoken request."
                if requested
                else "No memory search request established.",
                clarification_message=None
                if requested
                else "Ask what the user wants searched in memory. Do not invent a memory query.",
            )
        if tool_name == "configure_channel":
            requested = self._has_explicit_channel_configuration(clean_speech, tool_args)
            return SpeechGroundingResult(
                is_allowed=requested,
                reason="Channel configuration matched spoken request."
                if requested
                else "No channel configuration request established.",
                clarification_message=None
                if requested
                else "Ask which channel and credential the user wants configured. Do not configure a channel from unclear speech.",
            )
        if tool_name == "save_memory":
            requested = self._has_explicit_memory_save(clean_speech, tool_args)
            return SpeechGroundingResult(
                is_allowed=requested,
                reason="Memory save matched spoken request."
                if requested
                else "No memory save request established by speech.",
                clarification_message=None
                if requested
                else "Ask the user to clarify what fact or preference they would like saved into memory.",
            )
        analyzed = IntentClassifier.classify(user_speech)

        if (
            tool_name == "browser"
            and not analyzed.is_actionable
            and self._has_explicit_browser_action(clean_speech, tool_args)
        ):
            return SpeechGroundingResult(
                is_allowed=True,
                reason="Explicit browser action matched the spoken request.",
            )
        if (
            tool_name == "open_path"
            and not analyzed.is_actionable
            and self._has_explicit_open_path_action(clean_speech, tool_args)
        ):
            return SpeechGroundingResult(
                is_allowed=True,
                reason="Explicit open-path action matched the spoken request.",
            )

        # Desktop messaging can arrive as a generic host action even when the
        # intent classifier has not assigned a narrow category yet. Repair it
        # before the unknown-intent guard so explicit recipient+message speech
        # is not dropped as a false "No actionable intent" block.
        if tool_name == "desktop":
            action = str(tool_args.get("action", "")).lower()
            if "recipient" in tool_args and ("message" in tool_args or "text" in tool_args):
                has_msg_intent = bool(
                    re.search(
                        r"\b(send|message|msg|text|whatsapp|bhan|pathau|bhana)\b|पठाउ|भन|सन्देश",
                        clean_speech,
                    )
                )
                recipient = str(tool_args.get("recipient", "")).lower()
                has_recipient = bool(recipient and recipient in clean_speech.lower())
                if has_msg_intent or has_recipient:
                    if action in ("generic", "send", "send_message", "message", ""):
                        repaired = dict(tool_args)
                        repaired["action"] = "whatsapp_send"
                        if "text" in repaired and "message" not in repaired:
                            repaired["message"] = repaired["text"]
                        return SpeechGroundingResult(
                            is_allowed=True,
                            repaired_tool_name="desktop",
                            repaired_args=repaired,
                            reason="Repaired desktop action to 'whatsapp_send' based on recipient and message arguments.",
                        )

        # User feedback ('bhayena' / 'chaina' / 'khulena') establishes retry or inspection intent
        if analyzed.category == IntentCategory.CORRECTION_NEGATION:
            if tool_name in ("open_path", "process", "browser", "desktop", "system_info"):
                return SpeechGroundingResult(
                    is_allowed=True,
                    reason="User correction/negation feedback authorized retry or state inspection.",
                )

        # A transcript is evidence of speech, not permission for an arbitrary tool.
        # Unknown commands must be clarified instead of trusting model-made arguments.
        if not analyzed.is_actionable or analyzed.category == IntentCategory.SAFETY_SHUTDOWN:
            return SpeechGroundingResult(
                is_allowed=False,
                clarification_message="Do not execute this tool. The spoken request does not establish this action. Respond to the user, or ask them to clarify the intended task.",
                reason="No actionable spoken intent established.",
            )

        # Scenario A: User asked to open local app/drive/folder (e.g. 'open notepad', 'khol notepad')
        # But model called 'browser' or 'process' or 'exec'
        if (
            analyzed.category == IntentCategory.ACTIONABLE_PROCESS
            and analyzed.primary_tool == "open_path"
        ):
            target = analyzed.target_entity or tool_args.get("target") or ""
            target_lower = target.lower().strip()
            # If target is non-actionable, filler, or web service, do NOT repair browser
            if (
                target_lower in getattr(IntentClassifier, "_NON_TARGET_WORDS", set())
                or not target_lower
            ):
                return SpeechGroundingResult(
                    is_allowed=True, reason="Pass-through for conversational or non-target turn."
                )

            if target_lower in getattr(IntentClassifier, "_WEB_SERVICES", set()):
                return SpeechGroundingResult(
                    is_allowed=True, reason="Web service intent preserved."
                )

            # If tool_name is already open_path -> explicitly authorize!
            if tool_name == "open_path":
                return SpeechGroundingResult(
                    is_allowed=True,
                    reason=f"Open-path for '{target}' authorized based on spoken desktop app intent.",
                )

            # If target is local app, but tool_name is browser -> FIX to open_path!
            if tool_name == "browser":
                return SpeechGroundingResult(
                    is_allowed=True,
                    repaired_tool_name="open_path",
                    repaired_args={"target": target},
                    reason=f"Repaired tool from 'browser' to 'open_path(target={target})' based on spoken desktop app intent.",
                )
            if tool_name == "process" and tool_args.get("action") == "kill":
                # User said OPEN, but model called KILL!
                return SpeechGroundingResult(
                    is_allowed=True,
                    repaired_tool_name="open_path",
                    repaired_args={"target": target},
                    reason=f"Repaired conflicting tool from 'process(kill)' to 'open_path(target={target})' based on open intent.",
                )

        # Scenario B: User asked for browser action, web search, or YouTube operation
        if analyzed.category == IntentCategory.ACTIONABLE_BROWSER:
            if analyzed.primary_tool in (
                "youtube_subscribe",
                "youtube_unsubscribe",
                "youtube_close",
                "youtube_get_state",
            ):
                if tool_name == analyzed.primary_tool:
                    return SpeechGroundingResult(
                        is_allowed=True,
                        reason=f"Dedicated browser tool '{tool_name}' verified.",
                    )
                if (
                    analyzed.primary_tool == "youtube_close"
                    and tool_name == "browser"
                    and tool_args.get("action") == "close"
                ):
                    return SpeechGroundingResult(
                        is_allowed=True,
                        reason="Browser tab close tool allowed for YouTube tab close intent.",
                    )
                return SpeechGroundingResult(
                    is_allowed=True,
                    repaired_tool_name=analyzed.primary_tool,
                    repaired_args={},
                    reason=f"Repaired tool to '{analyzed.primary_tool}' based on spoken intent.",
                )

            if analyzed.primary_tool == "browser" and analyzed.parameters.get("action") == "close":
                target_entity = analyzed.target_entity or "tab"
                if tool_name == "browser" and tool_args.get("action") == "close":
                    return SpeechGroundingResult(
                        is_allowed=True,
                        reason="Browser tab close tool verified.",
                    )
                if target_entity in ("youtube", "yt") and tool_name == "youtube_close":
                    return SpeechGroundingResult(
                        is_allowed=True,
                        reason="youtube_close tool verified for YouTube tab close intent.",
                    )
                return SpeechGroundingResult(
                    is_allowed=True,
                    repaired_tool_name="browser",
                    repaired_args={
                        "action": "close",
                        "targetId": target_entity if target_entity != "tab" else "",
                    },
                    reason="Repaired tool to 'browser(action=close)' based on tab close intent.",
                )

            query = analyzed.target_entity or tool_args.get("query") or ""
            engine = analyzed.parameters.get("engine", "google")
            if tool_name.startswith("youtube_") or tool_name in ("youtube", "web_search"):
                return SpeechGroundingResult(
                    is_allowed=True,
                    reason=f"Dedicated media/search tool '{tool_name}' preserved.",
                )

            if tool_name != "browser":
                url = analyzed.parameters.get("url")
                if not url:
                    url = f"https://www.google.com/search?q={query}"
                    if "youtube" in engine.lower():
                        url = f"https://www.youtube.com/results?search_query={query}"
                return SpeechGroundingResult(
                    is_allowed=True,
                    repaired_tool_name="browser",
                    repaired_args={"action": "open", "url": url},
                    reason="Repaired tool to 'browser(action=open, url=...)' for web search intent.",
                )

        # Scenario C: User asked to close/kill an app (e.g. 'notepad banda gara', 'close terminal')
        # But model called 'browser' or 'remove_path' or 'open_path'
        if (
            analyzed.category == IntentCategory.ACTIONABLE_PROCESS
            and analyzed.parameters.get("action") == "kill"
        ):
            target_app = (analyzed.target_entity or tool_args.get("session_id") or "").lower()
            # DEFENSE-IN-DEPTH: Web services must NEVER be repaired to process(action='kill')!
            if target_app in ("youtube", "yt"):
                return SpeechGroundingResult(
                    is_allowed=True,
                    repaired_tool_name="youtube_close",
                    repaired_args={},
                    reason="Repaired web service close intent to 'youtube_close' instead of killing host browser.",
                )
            if target_app in getattr(IntentClassifier, "_WEB_SERVICES", set()):
                return SpeechGroundingResult(
                    is_allowed=True,
                    repaired_tool_name="browser",
                    repaired_args={"action": "close", "targetId": target_app},
                    reason=f"Repaired web service close intent to 'browser(action=close, targetId={target_app})' instead of killing host browser.",
                )
            if tool_name in ("browser", "remove_path", "open_path"):
                return SpeechGroundingResult(
                    is_allowed=True,
                    repaired_tool_name="process",
                    repaired_args={"action": "kill", "session_id": target_app},
                    reason=f"Repaired tool to 'process(action=kill, session_id={target_app})' for app termination intent.",
                )

        # Scenario D: User asked to create folder (mkdir)
        if (
            analyzed.category == IntentCategory.ACTIONABLE_FILESYSTEM
            and analyzed.primary_tool == "mkdir"
        ):
            folder_path = analyzed.target_entity or tool_args.get("path") or ""
            if tool_name != "mkdir" and tool_name not in ("exec", "open_path"):
                return SpeechGroundingResult(
                    is_allowed=True,
                    repaired_tool_name="mkdir",
                    repaired_args={"path": folder_path},
                    reason=f"Repaired tool to 'mkdir(path={folder_path})' based on folder creation intent.",
                )

        # ── 5. High-Impact Destructive Action Confirmation ────────────────
        if requires_high_impact_voice_confirmation(tool_name, tool_args):
            # If user explicitly commanded this in their speech, allow it
            explicitly_commanded = False
            if tool_name == "remove_path":
                target_path = tool_args.get("path", "").lower()
                if any(w in clean_speech for w in ("delete", "remove", "hatau", "erase")):
                    explicitly_commanded = bool(
                        target_path
                        and (target_path in clean_speech or len(clean_speech.split()) >= 2)
                    )
            elif tool_name == "exec":
                cmd = str(tool_args.get("command", "")).lower()
                if any(w in clean_speech for w in ("run", "execute", "chalao", "exec")):
                    explicitly_commanded = bool(cmd and len(clean_speech.split()) >= 2)

            if not explicitly_commanded:
                conf_id = self.confirmation_scope.create_pending_confirmation(tool_name, tool_args)
                return SpeechGroundingResult(
                    is_allowed=False,
                    requires_confirmation=True,
                    confirmation_id=conf_id,
                    clarification_message=(
                        f"VOICE_CONFIRMATION_REQUIRED:{conf_id} "
                        f"The high-impact voice action '{tool_name}' requires explicit spoken confirmation before executing. "
                        f"Please ask the user: 'Are you sure you want to {tool_name}?' before proceeding."
                    ),
                    reason="Spoken confirmation required for high-impact voice action.",
                )

        # All checks passed cleanly!
        return SpeechGroundingResult(
            is_allowed=True,
            reason="Tool call is grounded in verified user utterance and semantically aligned.",
        )

    @staticmethod
    def _validate_audio(args: dict[str, Any], speech: str) -> SpeechGroundingResult:
        """Ground host volume operations independently of the app-opening classifier."""
        has_audio = bool(
            re.search(
                r"\b(volume|audio|sound|speaker|mute|unmute|awaj|aawaj)\b|आवाज|भोल्युम|ध्वनि|म्युट",
                speech,
            )
        )
        negated = bool(re.search(r"\b(don't|do not|never|nagara|nagarnu)\b|नगर|नबढ|नघटा", speech))
        action = args.get("action")
        numbers = [int(n) for n in re.findall(r"\d+", speech)]
        increase = bool(re.search(r"\b(increase|raise|louder|up|badha|badhau)\b|बढा", speech))
        decrease = bool(re.search(r"\b(decrease|lower|quieter|down|ghata|ghatau)\b|घटा", speech))
        allowed = False
        if has_audio and not negated:
            if action == "get_volume":
                allowed = True
            elif action == "set_volume":
                value = args.get("percent")
                allowed = (
                    type(value) is int
                    and 0 <= value <= 100
                    and numbers == [value]
                    and not (increase or decrease)
                )
            elif action == "adjust_volume":
                value = args.get("delta")
                allowed = (
                    type(value) is int
                    and numbers == [abs(value)]
                    and (
                        (increase and not decrease and value > 0)
                        or (decrease and not increase and value < 0)
                    )
                )
            elif action == "unmute":
                allowed = bool(re.search(r"\bunmute\b|अनम्युट", speech))
            elif action == "mute":
                allowed = bool(re.search(r"\bmute\b|म्युट", speech)) and not bool(
                    re.search(r"\bunmute\b|अनम्युट", speech)
                )
        return SpeechGroundingResult(
            is_allowed=allowed,
            reason="Audio request matched spoken operation and value."
            if allowed
            else "Audio operation or value is not established by speech.",
            clarification_message=None
            if allowed
            else "Do not retry this audio action. Ask which volume operation and amount the user wants; do not invent a value.",
        )

    @staticmethod
    def _has_explicit_browser_action(speech: str, args: dict[str, Any]) -> bool:
        has_browser_target = bool(
            re.search(r"\b(browser|chrome|web|website|site|tab|url|page)\b", speech)
        )
        has_browser_verb = bool(
            re.search(
                r"\b(open|khol|khola|chalao|start|launch|search|khoja|click|type|navigate|go|close|banda)\b",
                speech,
            )
        )
        if has_browser_target and has_browser_verb:
            return True

        action = str(args.get("action", "")).lower()
        if action in {"open", "navigate"}:
            url = str(args.get("url") or args.get("targetUrl") or "").lower()
            return bool(url and url in speech and has_browser_verb)
        if action in {"click", "type"}:
            selector = str(args.get("selector") or args.get("text") or "").lower()
            return bool(selector and selector in speech and has_browser_verb)
        return False

    @staticmethod
    def _has_explicit_open_path_action(speech: str, args: dict[str, Any]) -> bool:
        target = str(args.get("target") or args.get("path") or "").strip().lower()
        if not target:
            return False
        has_open_verb = bool(
            re.search(
                r"\b(open|khol|khola|kholideu|kholdeu|kholna|kholnu|start|launch|explore|chalao|chalaideu|chalaunu|run|show)\b|खोल|चलाउ",
                speech,
            )
        )
        is_negation = bool(
            re.search(
                r"\b(chaina|bhayena|vayena|khulena|hataena|failed|didn't work|not open|still open)\b",
                speech,
            )
        )
        if not has_open_verb and not is_negation:
            return False

        target_aliases = {target}
        if target.endswith(".exe"):
            target_aliases.add(target[:-4])
        if "\\" in target or "/" in target:
            target_aliases.add(target.rsplit("\\", 1)[-1].rsplit("/", 1)[-1])

        alias_map = {
            "notepad": {"notepad", "note pad", "नोटप्याड"},
            "code": {"code", "vscode", "vs code", "visual studio code"},
            "explorer": {"explorer", "file explorer", "files", "folder", "drive", "my computer", "this pc", "फाइल"},
            "chrome": {"chrome", "browser", "google chrome", "क्रोम"},
            "msedge": {"edge", "msedge", "browser", "microsoft edge"},
            "calc": {"calc", "calculator", "क्यालकुलेटर"},
            "cmd": {"cmd", "command prompt", "terminal", "console", "powershell", "टर्मिनल"},
            "taskmgr": {"taskmgr", "task manager", "tasks"},
            "ms-settings:": {"settings", "setting", "सेटिङ"},
        }
        for key, aliases in alias_map.items():
            if target == key or any(target.startswith(k) or target.endswith(f"{k}.exe") for k in (key,)):
                target_aliases.update(aliases)

        if is_negation:
            return True

        if any(alias and alias in speech for alias in target_aliases):
            return True

        words = [
            w
            for w in speech.split()
            if w
            not in {
                "open",
                "khol",
                "khola",
                "kholideu",
                "kholdeu",
                "start",
                "launch",
                "chalao",
                "gara",
                "garideu",
                "na",
                "please",
                "ta",
                "hai",
                "re",
            }
        ]
        return len(words) >= 1

    @staticmethod
    def _has_explicit_memory_search(speech: str, args: dict[str, Any]) -> bool:
        query = str(args.get("query") or args.get("text") or "").strip().lower()
        has_memory = bool(
            re.search(
                r"\b(memory|remember|yaad|yad|recall|know|history|past|preference|profile|record)\b|मेमोरी|याद|पहिला|इतिहास",
                speech,
            )
        )
        has_search = bool(
            re.search(
                r"\b(search|find|lookup|khoja|her|hera|check|bhan|tell|k|what|who|where)\b|खोज|हेर|भन",
                speech,
            )
        )
        if has_memory:
            return True
        if query and has_search:
            query_words = [w for w in query.split() if len(w) > 2]
            if query_words and any(qw in speech for qw in query_words):
                return True
        return False

    @staticmethod
    def _has_explicit_channel_configuration(speech: str, args: dict[str, Any]) -> bool:
        channel = str(args.get("channel") or "").strip().lower()
        has_channel = bool(
            re.search(
                r"\b(channel|telegram|whatsapp|discord|imessage|bot)\b|च्यानल|टेलिग्राम|टेलेग्राम|व्हाट्सएप|डिस्कर्ड",
                speech,
            )
        )
        has_configure = bool(
            re.search(
                r"\b(configure|connect|setup|set\s+up|enable|start|token|credential|botfather)\b|कन्फिग|जोड|सेटअप|टोकन",
                speech,
            )
        )
        if channel and channel in speech and has_configure:
            return True
        return has_channel and has_configure

    @staticmethod
    def _has_explicit_memory_save(speech: str, args: dict[str, Any]) -> bool:
        has_save_verb = bool(
            re.search(
                r"\b(remember|save|note|keep|store|record)\b|याद|राख|राख्नु|टिप्नु|टिपाउ|सेभ",
                speech,
            )
        )
        has_identity_fact = bool(
            re.search(
                r"\b(my\s+name|my\s+favorite|i\s+like|i\s+live|my\s+birthday|my\s+email|my\s+phone|my\s+address|preference)\b|मेरो\s+नाम|मलाई\s+मन|मेरो\s+घर|मेरो\s+नम्बर",
                speech,
            )
        )
        value = str(args.get("value") or "").strip().lower()
        key = str(args.get("key") or "").strip().lower()
        has_val_match = bool(value and len(value) >= 3 and value in speech)
        has_key_match = bool(key and len(key) >= 3 and key in speech)
        return has_save_verb or has_identity_fact or has_val_match or has_key_match
