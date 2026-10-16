"""jarvis.agents.sessions.agent_session_prompting — prompting layer.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/agent-session-prompting.ts``.

Ships the public API for sending user
prompts to the agent:

- :meth:`AgentSessionPrompting.prompt` —
  the main entry point.
- :meth:`AgentSessionPrompting.steer` —
  queue a steering message during
  streaming.
- :meth:`AgentSessionPrompting.follow_up`
  — queue a follow-up message.
- :meth:`AgentSessionPrompting.send_custom_message`
  — inject a custom message.
- :meth:`AgentSessionPrompting.send_user_message`
  — inject a user message (text or
  text + images).
- :meth:`AgentSessionPrompting.clear_queue`
  — drop the steering + follow-up queues.
- :meth:`AgentSessionPrompting.abort` —
  abort the current run.
- :attr:`AgentSessionPrompting.pending_message_count`
  — count of queued messages.
- :meth:`AgentSessionPrompting.get_steering_messages`
  — read the steering queue.
- :meth:`AgentSessionPrompting.get_follow_up_messages`
  — read the follow-up queue.
- :attr:`AgentSessionPrompting.resource_loader`
  — the resource loader (mirrors the
  OpenClaw source's
  ``resourceLoader`` getter).

The class depends on a number of
methods / state from the base class +
the future execution / compaction /
models / extensions subclasses. The
base class ships no-op / ``None``
defaults for the missing pieces
(:meth:`flush_pending_bash_messages`,
:meth:`is_retryable_error`,
:meth:`prepare_retry`,
:meth:`check_compaction`,
:meth:`find_last_assistant_message`,
:meth:`abort_retry`, the
:attr:`model` + :attr:`is_streaming` +
:attr:`prompt_templates` state). The
real implementations land in 6.12d
(execution) + 6.12e (extensions) +
6.12g (compaction).

Phase 6.12c — focused port.
"""
from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
    Union,
)

from .agent_session_base import AgentSessionBase
from .agent_session_types import (
    PromptOptions,
)
from .auth_guidance import (
    format_no_api_key_found_message,
    format_no_model_selected_message,
)
from .frontmatter import stripFrontmatter
from .prompt_templates import (
    expandPromptTemplate,
)


if TYPE_CHECKING:
    from packages.jarvis_agent_runtime.src.jarvis_agent.types import (  # type: ignore[import-not-found]
        Agent,
        AgentMessage,
        AgentState,
        AgentTool,
        AssistantMessage,
        ThinkingLevel,
    )
    from packages.jarvis_llm_client.src.jarvis_llm.types import (  # type: ignore[import-not-found]
        ImageContent,
        Model,
        TextContent,
    )
else:
    # Runtime fallback aliases — see
    # ``agent_session_types.py`` for the
    # full explanation.
    Agent = Any
    AgentMessage = Any
    AgentState = Any
    AgentTool = Any
    AssistantMessage = Any
    ThinkingLevel = str
    ImageContent = Any
    Model = Any
    TextContent = Any


#: A user-turn transcript recorder.
UserTurnTranscriptRecorder = Any
PersistedUserTurnMessage = Any

#: The action returned by
#: :meth:`AgentSessionPrompting.handle_post_agent_run`.
#: Mirrors the local ``PostAgentRunAction``
#: type in the OpenClaw source.
PostAgentRunAction = str  # "continue" | "settled" | "handoff"


class AgentSessionPrompting(AgentSessionBase):
    """The prompting layer of the
    :class:`AgentSession` family. Mirrors
    :class:`AgentSessionPrompting`
    (``agent-session-prompting.ts:19-545``).

    The class is ``abstract`` in the
    OpenClaw source — the concrete
    implementation lands in
    :class:`AgentSessionBase` in 6.12b,
    and the runtime-constructible
    :class:`BaseAgentSession` is created
    by :func:`create_agent_session` (the
    factory lands in 6.12h).

    Phase 6.12c port — public surface +
    private helpers, wired against the
    base-class no-op defaults for the
    methods the future subclasses own.
    """

    # ------------------------------------------------------------------
    # Agent loop
    # ------------------------------------------------------------------

    async def _run_agent_prompt(
        self, messages: Union[AgentMessage, list[AgentMessage]]
    ) -> None:
        """Run a single agent prompt, then
        loop while the post-run hook
        returns ``"continue"``. Mirrors
        :meth:`runAgentPrompt`
        (``agent-session-prompting.ts:24-47``)."""
        ended_for_turn_handoff = False
        try:
            await self.agent.prompt(messages)
            while True:
                action = await self._handle_post_agent_run()
                if action != "continue":
                    ended_for_turn_handoff = action == "handoff"
                    break
                # ``continue`` is a Python
                # keyword, so we use
                # ``getattr`` to call the
                # OpenClaw-style ``agent.continue()``
                # method without a parser
                # error.
                await getattr(self.agent, "continue")()
        finally:
            self.system_prompt_override = None
            self.flush_pending_bash_messages()
            # Consume handoff state before
            # callbacks can start a nested
            # run and set it again.
            ended_for_turn_handoff = (
                ended_for_turn_handoff or self.last_run_ended_for_turn_handoff
            )
            self.last_run_ended_for_turn_handoff = False
            # Failed / aborted runs can
            # still be idle; only handoff
            # leaves external delivery
            # pending.
            if not ended_for_turn_handoff and self.current_extension_runner is not None:
                await self.current_extension_runner.emit(
                    {"type": "agent_settled"}
                )

    async def _handle_post_agent_run(self) -> PostAgentRunAction:
        """Decide what to do after a run:
        ``"continue"`` (retry / compaction
        / queued), ``"settled"`` (done),
        or ``"handoff"`` (external
        delivery owns the next run).
        Mirrors :meth:`handlePostAgentRun`
        (``agent-session-prompting.ts:49-82``)."""
        msg = self.last_assistant_message
        self.last_assistant_message = None
        ended_for_turn_handoff = self.last_run_ended_for_turn_handoff
        self.last_run_ended_for_turn_handoff = False
        if ended_for_turn_handoff:
            return "handoff"
        if not msg:
            return "settled"
        if self.is_retryable_error(msg) and await self.prepare_retry(msg):
            return "continue"
        stop_reason = msg.get("stopReason") if isinstance(msg, dict) else getattr(msg, "stop_reason", None)
        error_message = (
            msg.get("errorMessage")
            if isinstance(msg, dict)
            else getattr(msg, "error_message", None)
        )
        if stop_reason == "error" and self.retry_count > 0:
            self.emit({
                "type": "auto_retry_end",
                "success": False,
                "attempt": self.retry_count,
                "finalError": error_message,
            })
            self.retry_count = 0
        if await self.check_compaction(msg):
            return "continue"
        # Messages queued by agent_end
        # handlers arrive after the loop's
        # final queue drain.
        has_queued = (
            self.agent.has_queued_messages()
            if hasattr(self.agent, "has_queued_messages")
            else False
        )
        return "continue" if has_queued else "settled"

    def _create_user_content(
        self,
        text: str,
        images: Optional[list[ImageContent]] = None,
    ) -> list:
        """Build a content array
        ``[text, ...images]``. Mirrors
        :meth:`createUserContent`
        (``agent-session-prompting.ts:84-89``)."""
        return [{"type": "text", "text": text}, *(images or [])]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def prompt(
        self, text: str, options: Optional[PromptOptions] = None
    ) -> None:
        """Send a prompt to the agent. Mirrors
        :meth:`prompt`
        (``agent-session-prompting.ts:100-242``).

        Handles extension commands
        immediately, expands file-based
        prompt templates by default, queues
        via :meth:`steer` /
        :meth:`follow_up` during streaming,
        validates the model + API key
        before sending (when not streaming).
        """
        options = options or PromptOptions()
        expand_prompt_templates = bool(
            getattr(options, "expand_prompt_templates", True)
        )
        preflight_result = getattr(options, "preflight_result", None)
        messages: Optional[list[AgentMessage]] = None
        try:
            # Handle extension commands
            # first (execute immediately,
            # even during streaming).
            if expand_prompt_templates and text.startswith("/"):
                handled = await self._try_execute_extension_command(text)
                if handled:
                    if preflight_result is not None:
                        preflight_result(True)
                    return
            # Emit input event for extension
            # interception (before skill /
            # template expansion).
            current_text = text
            current_images = getattr(options, "images", None)
            runner = self.current_extension_runner
            if runner is not None and runner.has_handlers("input"):
                input_result = await runner.emit_input(
                    current_text,
                    current_images,
                    getattr(options, "source", None) or "interactive",
                )
                if input_result.get("action") == "handled":
                    if preflight_result is not None:
                        preflight_result(True)
                    return
                if input_result.get("action") == "transform":
                    current_text = input_result.get("text", current_text)
                    current_images = input_result.get(
                        "images", current_images
                    )
            # Expand skill commands +
            # prompt templates.
            expanded_text = current_text
            if expand_prompt_templates:
                expanded_text = self._expand_skill_command(expanded_text)
                expanded_text = expandPromptTemplate(
                    expanded_text, list(self.prompt_templates)
                )
            # If streaming, queue via
            # steer() or followUp().
            if self.is_streaming:
                streaming_behavior = getattr(
                    options, "streaming_behavior", None
                )
                if not streaming_behavior:
                    raise RuntimeError(
                        "Agent is already processing. Specify "
                        "streamingBehavior ('steer' or 'followUp') "
                        "to queue the message."
                    )
                if streaming_behavior == "followUp":
                    await self._queue_follow_up(expanded_text, current_images)
                else:
                    await self._queue_steer(expanded_text, current_images)
                if preflight_result is not None:
                    preflight_result(True)
                return
            # Flush any pending bash messages
            # before the new prompt.
            self.flush_pending_bash_messages()
            # Validate model.
            if not self.model:
                raise RuntimeError(format_no_model_selected_message())
            if not self.session_model_registry.has_configured_auth(self.model):
                if self.session_model_registry.is_using_oauth(self.model):
                    raise RuntimeError(
                        f'Authentication failed for "{self._provider_name(self.model)}". '
                        "Credentials may have expired or network is unavailable. "
                        f"Run '/login {self._provider_name(self.model)}' to re-authenticate."
                    )
                raise RuntimeError(
                    format_no_api_key_found_message(
                        self._provider_name(self.model)
                    )
                )
            # Check if we need to compact
            # before sending (catches
            # aborted responses). The pending
            # user prompt below starts the
            # next run; no intermediate
            # continuation is needed.
            last_assistant = self.find_last_assistant_message()
            if last_assistant:
                await self.check_compaction(last_assistant, is_post_run=False)
            # Build messages array.
            messages = []
            messages.append({
                "role": "user",
                "content": self._create_user_content(
                    expanded_text, current_images
                ),
                "timestamp": self._now(),
            })
            # Inject any pending
            # "nextTurn" messages as context
            # alongside the user message.
            for msg in self.pending_next_turn_messages:
                messages.append(msg)
            self.pending_next_turn_messages = []
            # Emit before_agent_start
            # extension event.
            result = None
            if runner is not None:
                result = await runner.emit_before_agent_start(
                    expanded_text,
                    current_images,
                    self.base_system_prompt,
                    self.base_system_prompt_options,
                )

            # Emit before_prompt_build hook for active memory parity
            from src.hooks import HookBus
            bus = HookBus()
            if hasattr(self, "api") and hasattr(self.api, "_hooks"):
                for hook in self.api._hooks:
                    bus.register(hook)
                    
            if bus.count("before_prompt_build") > 0:
                payload = {
                    "event": "before_prompt_build",
                    "prompt": expanded_text,
                    "messages": messages,
                    "hookCtx": {
                        "runId": getattr(self.agent, "run_id", ""),
                        "trace": None,
                        "agentId": getattr(self.agent, "id", ""),
                        "sessionKey": self.config.get("id", "") if isinstance(self.config, dict) else getattr(self.config, "id", ""),
                        "sessionId": self.config.get("id", "") if isinstance(self.config, dict) else getattr(self.config, "id", ""),
                        "workspaceDir": self.config.get("workspaceDir", "") if isinstance(self.config, dict) else getattr(self.config, "workspaceDir", ""),
                        "modelProviderId": self.model.provider if self.model else "",
                        "modelId": self.model.id if self.model else "",
                        "trigger": getattr(self.agent, "trigger", "manual"),
                    }
                }
                await bus.fire("before_prompt_build", payload)
                if payload.get("prependContext"):
                    expanded_text = f"{payload['prependContext']}\n\n{expanded_text}"
                if payload.get("appendContext"):
                    expanded_text = f"{expanded_text}\n\n{payload['appendContext']}"
                if payload.get("systemPrompt"):
                    if result is None:
                        result = {}
                    result["systemPrompt"] = payload["systemPrompt"]

            # Add all custom messages from
            # extensions.
            if result is not None and result.get("messages"):
                for msg in result["messages"]:
                    messages.append({
                        "role": "custom",
                        "customType": msg.get("customType"),
                        "content": msg.get("content"),
                        "display": msg.get("display"),
                        "details": msg.get("details"),
                        "timestamp": self._now(),
                    })
            # Apply extension-modified
            # system prompt, or reset to
            # base.
            if result is not None and "systemPrompt" in result:
                self.system_prompt_override = result["systemPrompt"]
                self.agent.state.systemPrompt = result["systemPrompt"]
            else:
                self.system_prompt_override = None
                self.agent.state.systemPrompt = self.base_system_prompt
        except Exception:
            if preflight_result is not None:
                preflight_result(False)
            raise
        if not messages:
            return
        if preflight_result is not None:
            preflight_result(True)
        await self._run_agent_prompt(messages)

    async def steer(
        self,
        text: str,
        images: Optional[list[ImageContent]] = None,
        user_turn_transcript_recorder: Optional[UserTurnTranscriptRecorder] = None,
    ) -> None:
        """Queue a steering message while
        the agent is running. Mirrors
        :meth:`steer`
        (``agent-session-prompting.ts:319-341``)."""
        # Check for extension commands
        # (cannot be queued).
        if text.startswith("/"):
            self._throw_if_extension_command(text)
        # Expand skill commands and
        # prompt templates.
        expanded_text = self._expand_skill_command(text)
        expanded_text = expandPromptTemplate(
            expanded_text, list(self.prompt_templates)
        )
        # Resolve the user-turn transcript
        # recorder (if any).
        prepared_message = None
        if user_turn_transcript_recorder is not None:
            resolve = getattr(
                user_turn_transcript_recorder, "resolve_message", None
            )
            if callable(resolve):
                prepared_message = await resolve()  # type: ignore[func-returns-value]
        await self._queue_steer(
            expanded_text,
            images,
            (
                {
                    "message": prepared_message,
                    "recorder": user_turn_transcript_recorder,
                }
                if prepared_message is not None
                and user_turn_transcript_recorder is not None
                else None
            ),
        )

    async def follow_up(
        self,
        text: str,
        images: Optional[list[ImageContent]] = None,
    ) -> None:
        """Queue a follow-up message. Mirrors
        :meth:`followUp`
        (``agent-session-prompting.ts:350-361``)."""
        if text.startswith("/"):
            self._throw_if_extension_command(text)
        expanded_text = self._expand_skill_command(text)
        expanded_text = expandPromptTemplate(
            expanded_text, list(self.prompt_templates)
        )
        await self._queue_follow_up(expanded_text, images)

    async def send_custom_message(
        self,
        message: dict,
        options: Optional[dict] = None,
    ) -> None:
        """Send a custom message to the
        session. Mirrors
        :meth:`sendCustomMessage`
        (``agent-session-prompting.ts:428-461``)."""
        options = options or {}
        deliver_as = options.get("deliverAs")
        trigger_turn = options.get("triggerTurn", False)
        app_message = {
            "role": "custom",
            "customType": message.get("customType"),
            "content": message.get("content"),
            "display": message.get("display"),
            "details": message.get("details"),
            "timestamp": self._now(),
        }
        if deliver_as == "nextTurn":
            self.pending_next_turn_messages.append(app_message)
        elif self.is_streaming:
            if deliver_as == "followUp":
                self.agent.follow_up(app_message)
            else:
                self.agent.steer(app_message)
        elif trigger_turn:
            await self._run_agent_prompt(app_message)
        else:
            self.agent.state.messages.append(app_message)
            append = getattr(
                self.session_manager, "append_custom_message_entry", None
            )
            if callable(append):
                append(
                    message.get("customType"),
                    message.get("content"),
                    message.get("display"),
                    message.get("details"),
                )
            self.emit({"type": "message_start", "message": app_message})
            self.emit({"type": "message_end", "message": app_message})

    async def send_user_message(
        self,
        content: Union[str, list],
        options: Optional[dict] = None,
    ) -> None:
        """Send a user message to the agent.
        Mirrors :meth:`sendUserMessage`
        (``agent-session-prompting.ts:470-503``)."""
        options = options or {}
        deliver_as = options.get("deliverAs")
        if isinstance(content, str):
            text = content
            images: Optional[list[ImageContent]] = None
        else:
            text_parts: list[str] = []
            images_list: list[ImageContent] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                else:
                    images_list.append(part)
            text = "\n".join(text_parts)
            images = images_list if images_list else None
        # Use prompt() with
        # expand_prompt_templates: false
        # to skip command handling +
        # template expansion.
        await self.prompt(
            text,
            PromptOptions(
                expand_prompt_templates=False,
                streaming_behavior=deliver_as,
                images=images,
                source="extension",
            ),
        )

    def clear_queue(self) -> dict:
        """Drop the steering + follow-up
        queues + return their contents.
        Mirrors :meth:`clearQueue`
        (``agent-session-prompting.ts:510-518``)."""
        steering = list(self.steering_messages)
        follow_up = list(self.follow_up_messages)
        self.steering_messages = []
        self.follow_up_messages = []
        if hasattr(self.agent, "clear_all_queues"):
            self.agent.clear_all_queues()
        self.emit_queue_update()
        return {"steering": steering, "followUp": follow_up}

    @property
    def pending_message_count(self) -> int:
        """Total pending steering + follow-up
        messages. Mirrors
        :attr:`pendingMessageCount`
        (``agent-session-prompting.ts:520-523``)."""
        return len(self.steering_messages) + len(self.follow_up_messages)

    def get_steering_messages(self) -> list[str]:
        """Read-only view of the steering
        queue. Mirrors
        :meth:`getSteeringMessages`
        (``agent-session-prompting.ts:525-528``)."""
        return list(self.steering_messages)

    def get_follow_up_messages(self) -> list[str]:
        """Read-only view of the follow-up
        queue. Mirrors
        :meth:`getFollowUpMessages`
        (``agent-session-prompting.ts:530-533``)."""
        return list(self.follow_up_messages)

    @property
    def resource_loader(self):
        """The session's resource loader.
        Mirrors :attr:`resourceLoader`
        (``agent-session-prompting.ts:535-537``)."""
        return self.session_resource_loader

    async def abort(self, reason: Any = None) -> None:
        """Abort the current run. Mirrors
        :meth:`abort`
        (``agent-session-prompting.ts:540-544``)."""
        self.abort_retry()
        self.agent.abort(reason)
        wait = getattr(self.agent, "wait_for_idle", None)
        if callable(wait):
            await wait()  # type: ignore[func-returns-value]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _try_execute_extension_command(self, text: str) -> bool:
        """Try to execute ``text`` as an
        extension slash command. Returns
        ``True`` when the command was
        found (whether the handler
        succeeded or not). Mirrors
        :meth:`tryExecuteExtensionCommand`
        (``agent-session-prompting.ts:247-273``)."""
        space_index = text.find(" ")
        command_name = (
            text[1:space_index] if space_index != -1 else text[1:]
        )
        args = text[space_index + 1:] if space_index != -1 else ""
        runner = self.current_extension_runner
        if runner is None:
            return False
        command = runner.get_command(command_name)
        if not command:
            return False
        ctx = runner.create_command_context()
        try:
            handler = command.get("handler") if isinstance(command, dict) else None
            if callable(handler):
                await handler(args, ctx)
            return True
        except Exception as exc:
            runner.emit_error({
                "extensionPath": f"command:{command_name}",
                "event": "command",
                "error": str(exc) if exc else "unknown error",
            })
            return True

    def _expand_skill_command(self, text: str) -> str:
        """Expand a ``/skill:name args`` style
        prompt to the skill body. Returns
        the original text when the command
        is unknown or the skill file can't
        be read. Mirrors
        :meth:`expandSkillCommand`
        (``agent-session-prompting.ts:280-308``)."""
        if not text.startswith("/skill:"):
            return text
        space_index = text.find(" ")
        skill_name = (
            text[7:space_index] if space_index != -1 else text[7:]
        )
        args = text[space_index + 1:].strip() if space_index != -1 else ""
        skills = self.session_resource_loader.get_skills()
        skill = next(
            (
                s
                for s in skills.get("skills", [])
                if getattr(s, "name", None) == skill_name
            ),
            None,
        )
        if skill is None:
            return text
        try:
            with open(skill.file_path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except OSError as exc:
            runner = self.current_extension_runner
            if runner is not None:
                runner.emit_error({
                    "extensionPath": skill.file_path,
                    "event": "skill_expansion",
                    "error": str(exc),
                })
            return text
        body = stripFrontmatter(content).strip()
        skill_block = (
            f'<skill name="{skill.name}" '
            f'location="{skill.file_path}">\n'
            f"References are relative to {skill.base_dir}.\n\n"
            f"{body}\n</skill>"
        )
        return f"{skill_block}\n\n{args}" if args else skill_block

    async def _queue_steer(
        self,
        text: str,
        images: Optional[list[ImageContent]] = None,
        transcript_context: Optional[dict] = None,
    ) -> None:
        """Internal: queue a steering message
        (already expanded, no extension
        command check). Mirrors
        :meth:`queueSteer`
        (``agent-session-prompting.ts:366-386``)."""
        self.steering_messages.append(text)
        self.emit_queue_update()
        runtime_message = {
            "role": "user",
            "content": self._create_user_content(text, images),
            "timestamp": self._now(),
        }
        # The OpenClaw source attaches
        # transcript context (Phase 6.13+);
        # the Python port passes the
        # message through unchanged when
        # no transcript recorder is
        # configured.
        if transcript_context is not None:
            recorder = transcript_context.get("recorder")
            if recorder is not None and hasattr(recorder, "attach_to_message"):
                runtime_message = recorder.attach_to_message(
                    runtime_message, transcript_context.get("message")
                )
        self.agent.steer(runtime_message)

    async def _queue_follow_up(
        self,
        text: str,
        images: Optional[list[ImageContent]] = None,
    ) -> None:
        """Internal: queue a follow-up
        message. Mirrors :meth:`queueFollowUp`
        (``agent-session-prompting.ts:391-399``)."""
        self.follow_up_messages.append(text)
        self.emit_queue_update()
        self.agent.follow_up({
            "role": "user",
            "content": self._create_user_content(text, images),
            "timestamp": self._now(),
        })

    def _throw_if_extension_command(self, text: str) -> None:
        """Raise if ``text`` is an extension
        command (steer / followUp cannot
        queue commands). Mirrors
        :meth:`throwIfExtensionCommand`
        (``agent-session-prompting.ts:404-414``)."""
        space_index = text.find(" ")
        command_name = (
            text[1:space_index] if space_index != -1 else text[1:]
        )
        runner = self.current_extension_runner
        if runner is None:
            return
        command = runner.get_command(command_name)
        if command is not None:
            raise RuntimeError(
                f'Extension command "/{command_name}" cannot be '
                "queued. Use prompt() or execute the command "
                "when not streaming."
            )

    @staticmethod
    def _now() -> int:
        """Return the current epoch ms.
        Mirrors the ``Date.now()`` usage in
        the OpenClaw source."""
        import time

        return int(time.time() * 1000)


__all__ = [
    "AgentSessionPrompting",
    "PersistedUserTurnMessage",
    "PostAgentRunAction",
    "UserTurnTranscriptRecorder",
]
