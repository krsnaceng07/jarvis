"""jarvis.agents.embedded_agent_runner.run.session_prompt_state — embedded-run session/prompt state.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/session-prompt-state.ts``.

Public surface:

- :func:`create_embedded_run_session_prompt_state`
- :data:`MID_TURN_PRECHECK_CONTINUATION_PROMPT`

Phase 7.6h-7 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


#: Continuation prompt used by mid-turn precheck + compacted-transcript retry.
MID_TURN_PRECHECK_CONTINUATION_PROMPT = (
    "Continue from the current transcript after the latest tool result. "
    "Do not repeat the original user request, and do not rerun completed tools "
    "unless the transcript shows they are still needed."
)


# Installable hooks ---------------------------------------------------------

_create_embedded_run_session_prompt_state_hook = None
_build_context_engine_compaction_session_target_hook = None
_register_agent_run_context_hook = None
_resolve_agent_run_session_target_hook = None


def set_create_embedded_run_session_prompt_state_hook(fn) -> None:
    global _create_embedded_run_session_prompt_state_hook
    _create_embedded_run_session_prompt_state_hook = fn


def set_build_context_engine_compaction_session_target_hook(fn) -> None:
    global _build_context_engine_compaction_session_target_hook
    _build_context_engine_compaction_session_target_hook = fn


def set_register_agent_run_context_hook(fn) -> None:
    global _register_agent_run_context_hook
    _register_agent_run_context_hook = fn


def set_resolve_agent_run_session_target_hook(fn) -> None:
    global _resolve_agent_run_session_target_hook
    _resolve_agent_run_session_target_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_embedded_run_session_prompt_state(input: Dict[str, Any]) -> Any:
    """Create the active session/prompt state container for an embedded run.

    Mirrors :func:`createEmbeddedRunSessionPromptState`
    (``session-prompt-state.ts``).
    """
    if _create_embedded_run_session_prompt_state_hook is not None:
        return _create_embedded_run_session_prompt_state_hook(input) or {}
    params = input.get("runParams") if isinstance(input.get("runParams"), dict) else {}
    session_agent_id = input.get("sessionAgentId", "")
    resolved_session_key = input.get("resolvedSessionKey", "")
    lifecycle_generation = input.get("lifecycleGeneration")
    # Mutable containers so setters can update the underlying value.
    active_session_id_box: List[Any] = [params.get("sessionId")]
    active_session_file_box: List[Any] = [params.get("sessionFile")]
    active_session_target_box: List[Any] = [
        _build_context_engine_compaction_session_target(
            {
                "agentId": params.get("agentId") or session_agent_id,
                "config": params.get("config"),
                "sessionFile": active_session_file_box[0],
                "sessionId": active_session_id_box[0],
                "sessionKey": resolved_session_key,
                "sessionTarget": params.get("sessionTarget"),
            }
        )
    ]
    suppress_next_box: List[bool] = [bool(params.get("suppressNextUserMessagePersistence"))]
    active_prompt_box: List[Dict[str, Any]] = [
        {"persisted": suppress_next_box[0], "internal": False}
    ]
    run_id = params.get("runId")

    def _adopt_session_id(next_session_id: Optional[str]) -> None:
        if not next_session_id or next_session_id == active_session_id_box[0]:
            return
        active_session_id_box[0] = next_session_id
        reply_op = params.get("replyOperation")
        if isinstance(reply_op, dict) and callable(reply_op.get("updateSessionId")):
            try:
                reply_op["updateSessionId"](active_session_id_box[0])
            except Exception:
                pass
        on_changed = params.get("onSessionIdChanged")
        if callable(on_changed):
            try:
                on_changed(active_session_id_box[0])
            except Exception:
                pass
        if callable(_register_agent_run_context_hook):
            try:
                _register_agent_run_context_hook(run_id, {
                    "sessionId": active_session_id_box[0],
                    "lifecycleGeneration": lifecycle_generation,
                })
            except Exception:
                pass

    async def _adopt_session_target(next_target: Optional[Dict[str, Any]]) -> None:
        if not next_target:
            return
        resolved = next_target
        if callable(_resolve_agent_run_session_target_hook):
            try:
                resolved = await _resolve_agent_run_session_target_hook(
                    {
                        "agentId": next_target.get("agentId") or session_agent_id,
                        "config": params.get("config"),
                        "sessionId": next_target.get("sessionId") or active_session_id_box[0],
                        "sessionKey": next_target.get("sessionKey") or resolved_session_key,
                        "sessionTarget": next_target,
                    }
                ) or next_target
            except Exception:
                resolved = next_target
        active_session_target_box[0] = next_target
        if isinstance(resolved, dict) and resolved.get("sessionFile"):
            active_session_file_box[0] = resolved["sessionFile"]
        if isinstance(resolved, dict) and resolved.get("sessionId"):
            _adopt_session_id(resolved["sessionId"])

    def _activate_internal_prompt(prompt: str, persisted: bool) -> None:
        active_prompt_box[0] = {"override": prompt, "persisted": persisted, "internal": True}
        suppress_next_box[0] = persisted

    def _on_user_message_persisted(message: Any) -> None:
        metadata = message if isinstance(message, dict) else {}
        openclaw_meta = metadata.get("__openclaw") or {}
        if not isinstance(openclaw_meta, dict):
            openclaw_meta = {}
        blocked_before_agent_run = openclaw_meta.get("beforeAgentRunBlocked")
        recorder = params.get("userTurnTranscriptRecorder")

        def _mark_current_user_message_persisted() -> None:
            active_prompt_box[0]["persisted"] = True
            cb = params.get("onUserMessagePersisted")
            if callable(cb):
                try:
                    cb(message)
                except Exception:
                    pass

        if recorder is None or not isinstance(recorder, dict):
            _mark_current_user_message_persisted()
            return

        def _mark_when_persisted(persisted: Optional[Dict[str, Any]]) -> None:
            if (isinstance(persisted, dict) and persisted.get("message")) or (
                callable(recorder.get("hasPersisted")) and recorder["hasPersisted"]()
            ):
                _mark_current_user_message_persisted()

        canonical = None
        if blocked_before_agent_run is not None and callable(recorder.get("persistBlocked")):
            try:
                canonical = recorder["persistBlocked"](message)
            except Exception:
                canonical = None
        elif callable(recorder.get("persistApproved")):
            try:
                canonical = recorder["persistApproved"]()
            except Exception:
                canonical = None
        if canonical is not None and hasattr(canonical, "then"):
            observed = canonical.then(
                _mark_when_persisted,
                lambda _err: None,
            )
            if callable(recorder.get("markRuntimePersistencePending")):
                try:
                    recorder["markRuntimePersistencePending"](observed)
                except Exception:
                    pass

    async def _wait_for_current_user_message_persistence() -> None:
        recorder = params.get("userTurnTranscriptRecorder")
        if isinstance(recorder, dict) and callable(recorder.get("hasRuntimePersistencePending")):
            try:
                if recorder["hasRuntimePersistencePending"]() is True and callable(
                    recorder.get("waitForRuntimePersistence")
                ):
                    await recorder["waitForRuntimePersistence"]()
            except Exception:
                pass

    def _continue_from_current_transcript() -> None:
        _activate_internal_prompt(MID_TURN_PRECHECK_CONTINUATION_PROMPT, True)

    async def _prepare_compacted_transcript_retry() -> None:
        await _wait_for_current_user_message_persistence()
        if active_prompt_box[0].get("internal"):
            suppress_next_box[0] = bool(active_prompt_box[0].get("persisted"))
        elif active_prompt_box[0].get("persisted"):
            _activate_internal_prompt(MID_TURN_PRECHECK_CONTINUATION_PROMPT, True)

    return _SessionPromptState(
        active_session_id_getter=lambda: active_session_id_box[0],
        active_session_id_setter=lambda v: _set_active_session_id(v, active_session_id_box),
        active_session_file_getter=lambda: active_session_file_box[0],
        active_session_file_setter=lambda v: _set_active_session_file(v, active_session_file_box),
        active_session_target_getter=lambda: active_session_target_box[0],
        active_session_target_setter=lambda v: _set_active_session_target(v, active_session_target_box),
        active_prompt_getter=lambda: active_prompt_box[0],
        suppress_next_getter=lambda: suppress_next_box[0],
        suppress_next_setter=lambda v: _set_suppress_next(v, suppress_next_box),
        adopt_session_id=_adopt_session_id,
        adopt_session_target=_adopt_session_target,
        activate_internal_prompt=_activate_internal_prompt,
        continue_from_current_transcript=_continue_from_current_transcript,
        on_user_message_persisted=_on_user_message_persisted,
        wait_for_current_user_message_persistence=_wait_for_current_user_message_persistence,
        prepare_compacted_transcript_retry=_prepare_compacted_transcript_retry,
    )


class _SessionPromptState:
    """Container that mirrors the OpenClaw session-state object.

    Provides plain attribute access for ``sessionId``/``sessionFile``/
    ``sessionTarget``/``suppressNextUserMessagePersistence`` and method
    bindings for the lifecycle actions.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._get_session_id = kwargs["active_session_id_getter"]
        self._set_session_id = kwargs["active_session_id_setter"]
        self._get_session_file = kwargs["active_session_file_getter"]
        self._set_session_file = kwargs["active_session_file_setter"]
        self._get_session_target = kwargs["active_session_target_getter"]
        self._set_session_target = kwargs["active_session_target_setter"]
        self._get_active_prompt = kwargs["active_prompt_getter"]
        self._get_suppress_next = kwargs["suppress_next_getter"]
        self._set_suppress_next = kwargs["suppress_next_setter"]
        self._adopt_session_id = kwargs["adopt_session_id"]
        self._adopt_session_target = kwargs["adopt_session_target"]
        self._activate_internal_prompt = kwargs["activate_internal_prompt"]
        self._continue_from_current_transcript = kwargs["continue_from_current_transcript"]
        self._on_user_message_persisted = kwargs["on_user_message_persisted"]
        self._wait_for_current_user_message_persistence = kwargs["wait_for_current_user_message_persistence"]
        self._prepare_compacted_transcript_retry = kwargs["prepare_compacted_transcript_retry"]

    @property
    def sessionId(self) -> Any:
        return self._get_session_id()

    @sessionId.setter
    def sessionId(self, value: Any) -> None:
        self._set_session_id(value)

    @property
    def sessionFile(self) -> Any:
        return self._get_session_file()

    @sessionFile.setter
    def sessionFile(self, value: Any) -> None:
        self._set_session_file(value)

    @property
    def sessionTarget(self) -> Any:
        return self._get_session_target()

    @sessionTarget.setter
    def sessionTarget(self, value: Any) -> None:
        self._set_session_target(value)

    @property
    def activePrompt(self) -> Any:
        return self._get_active_prompt()

    @property
    def suppressNextUserMessagePersistence(self) -> Any:
        return self._get_suppress_next()

    @suppressNextUserMessagePersistence.setter
    def suppressNextUserMessagePersistence(self, value: Any) -> None:
        self._set_suppress_next(value)

    def adoptSessionId(self, next_session_id: Optional[str]) -> None:
        self._adopt_session_id(next_session_id)

    async def adoptSessionTarget(self, next_target: Optional[Dict[str, Any]]) -> None:
        await self._adopt_session_target(next_target)

    def activateInternalPrompt(self, prompt: str, persisted: bool) -> None:
        self._activate_internal_prompt(prompt, persisted)

    def continueFromCurrentTranscript(self) -> None:
        self._continue_from_current_transcript()

    def onUserMessagePersisted(self, message: Any) -> None:
        self._on_user_message_persisted(message)

    async def waitForCurrentUserMessagePersistence(self) -> None:
        await self._wait_for_current_user_message_persistence()

    async def prepareCompactedTranscriptRetry(self) -> None:
        await self._prepare_compacted_transcript_retry()

    # Dict-style passthrough for callers that prefer ``state["sessionId"]``.
    def __contains__(self, key: str) -> bool:
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __iter__(self):
        keys = (
            "sessionId",
            "sessionFile",
            "sessionTarget",
            "activePrompt",
            "suppressNextUserMessagePersistence",
            "adoptSessionId",
            "adoptSessionTarget",
            "activateInternalPrompt",
            "continueFromCurrentTranscript",
            "onUserMessagePersisted",
            "waitForCurrentUserMessagePersistence",
            "prepareCompactedTranscriptRetry",
        )
        return iter(keys)

    def keys(self):
        return list(self)

    def __getitem__(self, key: str) -> Any:
        if key == "sessionId":
            return self.sessionId
        if key == "sessionFile":
            return self.sessionFile
        if key == "sessionTarget":
            return self.sessionTarget
        if key == "activePrompt":
            return self.activePrompt
        if key == "suppressNextUserMessagePersistence":
            return self.suppressNextUserMessagePersistence
        if key == "adoptSessionId":
            return self.adoptSessionId
        if key == "adoptSessionTarget":
            return self.adoptSessionTarget
        if key == "activateInternalPrompt":
            return self.activateInternalPrompt
        if key == "continueFromCurrentTranscript":
            return self.continueFromCurrentTranscript
        if key == "onUserMessagePersisted":
            return self.onUserMessagePersisted
        if key == "waitForCurrentUserMessagePersistence":
            return self.waitForCurrentUserMessagePersistence
        if key == "prepareCompactedTranscriptRetry":
            return self.prepareCompactedTranscriptRetry
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "sessionId":
            self.sessionId = value
        elif key == "sessionFile":
            self.sessionFile = value
        elif key == "sessionTarget":
            self.sessionTarget = value
        elif key == "suppressNextUserMessagePersistence":
            self.suppressNextUserMessagePersistence = value
        else:
            raise KeyError(key)


# Bound-state setter helpers ------------------------------------------------


def _set_active_session_id(value: Any, box: List[Any]) -> None:
    box[0] = value


def _set_active_session_file(value: Any, box: List[Any]) -> None:
    box[0] = value


def _set_active_session_target(value: Any, box: List[Any]) -> None:
    box[0] = value


def _set_suppress_next(value: Any, box: List[Any]) -> None:
    box[0] = bool(value)


def _build_context_engine_compaction_session_target(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a context-engine compaction session target from the run params.

    The full implementation lives in ``session-bootstrap.py``; the focused port
    just returns a minimal target object so callers can read it back.
    """
    if _build_context_engine_compaction_session_target_hook is not None:
        v = _build_context_engine_compaction_session_target_hook(params)
        return v if v is None or isinstance(v, dict) else None
    if not params.get("sessionId") and not params.get("sessionKey"):
        return None
    return {
        "agentId": params.get("agentId"),
        "sessionId": params.get("sessionId"),
        "sessionKey": params.get("sessionKey"),
        "sessionFile": params.get("sessionFile"),
        "sessionTarget": params.get("sessionTarget"),
    }


__all__ = [
    "MID_TURN_PRECHECK_CONTINUATION_PROMPT",
    "create_embedded_run_session_prompt_state",
    "set_create_embedded_run_session_prompt_state_hook",
    "set_build_context_engine_compaction_session_target_hook",
    "set_register_agent_run_context_hook",
    "set_resolve_agent_run_session_target_hook",
]
