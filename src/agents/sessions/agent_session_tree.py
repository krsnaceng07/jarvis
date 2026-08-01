"""jarvis.agents.sessions.agent_session_tree — session tree navigation.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/agent-session-tree.ts``.

Adds the session-tree navigation layer
on top of the execution chain:

- :meth:`AgentSessionTree.navigate_tree` — navigate to a
  different node in the session tree.
- :meth:`AgentSessionTree.get_user_messages_for_forking` — get
  the user messages for the fork
  selector.
- :meth:`AgentSessionTree.create_replaced_session_context` —
  build a :class:`ReplacedSessionContext`
  for the session.
- :meth:`AgentSessionTree.has_extension_handlers` — check if
  extensions have handlers for an event
  type.
- :attr:`AgentSessionTree.extension_runner` — the extension
  runner.

Phase 6.12f — focused port.

Adaptations
-----------
- The OpenClaw source's
  :func:`collectEntriesForBranchSummaryFromBranches` +
  :func:`generateBranchSummary` come
  from ``@openclaw/ai/internal/runtime``.
  The Python port's
  :meth:`navigate_tree` skips the
  summarization step (the
  :func:`generateBranchSummary`
  integration lands in 6.13+); the
  navigation still works (with
  ``summarize=False``).
"""
from __future__ import annotations

import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Optional,
)

from .agent_session_extensions import AgentSessionExtensions
from .agent_session_utils import extract_text_content
from .extensions.runner import ExtensionRunner
from .extensions.types import ReplacedSessionContext


if TYPE_CHECKING:
    pass


_LOG = logging.getLogger("jarvis.agents.sessions.agent_session_tree")


#: A branch summary entry. Mirrors
#: ``BranchSummaryEntry`` in
#: ``session-manager.ts`` (the real
#: type lands in 6.13+).
BranchSummaryEntry = dict


class AgentSessionTree(AgentSessionExtensions):
    """The session-tree navigation layer
    of the :class:`AgentSession` family.
    Mirrors :class:`AgentSessionTree`
    (``agent-session-tree.ts:14-275``).

    Phase 6.12f port.
    """

    # ------------------------------------------------------------------
    # Tree Navigation
    # ------------------------------------------------------------------

    async def navigate_tree(
        self,
        target_id: str,
        options: Optional[dict] = None,
    ) -> dict:
        """Navigate to a different node in
        the session tree. Mirrors
        :meth:`navigateTree`
        (``agent-session-tree.ts:30-222``).

        Parameters
        ----------
        target_id : str
            The entry ID to navigate to.
        options : dict, optional
            - ``summarize`` (bool): whether
              to summarize the abandoned
              branch (Phase 6.13+).
            - ``customInstructions`` (str):
              custom summarizer instructions.
            - ``replaceInstructions`` (bool).
            - ``label`` (str): label to attach
              to the branch summary entry.

        Returns
        -------
        dict
            ``{"editorText"?, "cancelled",
            "aborted"?, "summaryEntry"?}``
        """
        options = options or {}
        get_leaf_id = getattr(self.session_manager, "get_leaf_id", None)
        old_leaf_id = get_leaf_id() if callable(get_leaf_id) else None
        # No-op when already at the target.
        if target_id == old_leaf_id:
            return {"cancelled": False}
        # Model required for summarization.
        if options.get("summarize") and not self.model:
            raise RuntimeError("No model available for summarization")
        get_entry = getattr(self.session_manager, "get_entry", None)
        if not callable(get_entry):
            raise RuntimeError("Session manager has no get_entry helper")
        target_entry = get_entry(target_id)
        if target_entry is None:
            raise RuntimeError(f"Entry {target_id} not found")
        # Phase 6.12f — STUB. The
        # branch-summary collection +
        # summarization lands in 6.13+.
        # We skip the summary step and
        # proceed with the navigation.
        entries_to_summarize: list = []
        common_ancestor_id: Optional[str] = None
        # Set up the abort controller for
        # the branch summary. The OpenClaw
        # source uses the global
        # ``AbortController``; the Python
        # port uses the
        # ``_AbortControllerLike`` helper
        # from the execution module (which
        # mirrors the JS API).
        from src.agents.sessions.agent_session_execution import (
            _AbortControllerLike,
        )
        self.branch_summary_abort_controller = _AbortControllerLike()
        # Allow extensions to override the
        # preparation via session_before_tree.
        custom_instructions = options.get("customInstructions")
        replace_instructions = options.get("replaceInstructions")
        label = options.get("label")
        try:
            from .extensions.types import TreePreparation

            preparation = TreePreparation(
                targetId=target_id,
                oldLeafId=old_leaf_id,
                commonAncestorId=common_ancestor_id,
                entriesToSummarize=entries_to_summarize,
                userWantsSummary=bool(options.get("summarize", False)),
                customInstructions=custom_instructions,
                replaceInstructions=replace_instructions,
                label=label,
            )
        except Exception:
            # Defensive: TreePreparation
            # may not exist as a class (it's
            # a TypedDict in 6.9c). Use a
            # plain dict.
            preparation = {
                "targetId": target_id,
                "oldLeafId": old_leaf_id,
                "commonAncestorId": common_ancestor_id,
                "entriesToSummarize": entries_to_summarize,
                "userWantsSummary": bool(options.get("summarize", False)),
                "customInstructions": custom_instructions,
                "replaceInstructions": replace_instructions,
                "label": label,
            }
        if self.current_extension_runner.has_handlers("session_before_tree"):
            before_result = await self.current_extension_runner.emit(
                {
                    "type": "session_before_tree",
                    "preparation": preparation,
                    "signal": self.branch_summary_abort_controller,
                }
            )
            if before_result and before_result.get("cancel"):
                return {"cancelled": True}
            if before_result and before_result.get("summary"):
                # Extension provided a
                # summary — but the Python
                # port's summarization is a
                # 6.13+ feature. Skip the
                # summary for now.
                pass
            if before_result and "customInstructions" in before_result:
                custom_instructions = before_result["customInstructions"]
            if before_result and "replaceInstructions" in before_result:
                replace_instructions = before_result["replaceInstructions"]
            if before_result and "label" in before_result:
                label = before_result["label"]
        # Default-summarizer step: skip
        # (Phase 6.13+).
        summary_text: Optional[str] = None
        summary_details: Any = None
        # Determine the new leaf position.
        entry_type = (
            target_entry.get("type")
            if isinstance(target_entry, dict)
            else getattr(target_entry, "type", None)
        )
        message = (
            target_entry.get("message")
            if isinstance(target_entry, dict)
            else getattr(target_entry, "message", None)
        )
        message_role = (
            message.get("role")
            if isinstance(message, dict)
            else getattr(message, "role", None)
        )
        editor_text: Optional[str] = None
        if entry_type == "message" and message_role == "user":
            parent_id = (
                target_entry.get("parentId")
                if isinstance(target_entry, dict)
                else getattr(target_entry, "parentId", None)
            )
            new_leaf_id = parent_id
            content = (
                message.get("content")
                if isinstance(message, dict)
                else getattr(message, "content", None)
            )
            editor_text = extract_text_content(content)
        elif entry_type == "custom_message":
            parent_id = (
                target_entry.get("parentId")
                if isinstance(target_entry, dict)
                else getattr(target_entry, "parentId", None)
            )
            new_leaf_id = parent_id
            content = (
                target_entry.get("content")
                if isinstance(target_entry, dict)
                else getattr(target_entry, "content", None)
            )
            editor_text = extract_text_content(content)
        else:
            new_leaf_id = target_id
        # Switch the leaf (with or
        # without a summary).
        summary_entry: Optional[BranchSummaryEntry] = None
        if summary_text:
            branch_with_summary = getattr(
                self.session_manager, "branch_with_summary", None
            )
            if callable(branch_with_summary):
                summary_id = branch_with_summary(
                    new_leaf_id,
                    summary_text,
                    summary_details,
                    False,
                )
                get_entry_after = getattr(
                    self.session_manager, "get_entry", None
                )
                if callable(get_entry_after):
                    summary_entry = get_entry_after(summary_id)
        elif new_leaf_id is None:
            reset_leaf = getattr(self.session_manager, "reset_leaf", None)
            if callable(reset_leaf):
                reset_leaf()
        else:
            branch = getattr(self.session_manager, "branch", None)
            if callable(branch):
                branch(new_leaf_id)
        # Attach label to the target
        # when no summary was created.
        if label and not summary_text:
            append_label = getattr(
                self.session_manager, "append_label_change", None
            )
            if callable(append_label):
                append_label(target_id, label)
        # Update the agent state.
        build_ctx = getattr(
            self.session_manager, "build_session_context", None
        )
        if callable(build_ctx):
            ctx = build_ctx()
            messages = (
                ctx.get("messages", [])
                if isinstance(ctx, dict)
                else getattr(ctx, "messages", [])
            )
            state = self.agent.state
            if isinstance(state, dict):
                state["messages"] = list(messages)
            else:
                setattr(state, "messages", list(messages))
        # Emit the session_tree event.
        new_leaf_id_after = (
            get_leaf_id() if callable(get_leaf_id) else None
        )
        await self.current_extension_runner.emit({
            "type": "session_tree",
            "newLeafId": new_leaf_id_after,
            "oldLeafId": old_leaf_id,
            "summaryEntry": summary_entry,
        })
        return {
            "editorText": editor_text,
            "cancelled": False,
            "summaryEntry": summary_entry,
        }
        # Reset the abort controller.
        _ = (_AbortControllerLike,)  # Unused.

    def get_user_messages_for_forking(self) -> list:
        """Get all user messages from the
        session for the fork selector.
        Mirrors :meth:`getUserMessagesForForking`
        (``agent-session-tree.ts:227-246``)."""
        get_entries = getattr(self.session_manager, "get_entries", None)
        if not callable(get_entries):
            return []
        entries = get_entries()
        result: list = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") != "message":
                continue
            message = entry.get("message")
            if not isinstance(message, dict):
                continue
            if message.get("role") != "user":
                continue
            text = extract_text_content(message.get("content"))
            if text:
                result.append(
                    {
                        "entryId": entry.get("id"),
                        "text": text,
                    }
                )
        return result

    # ------------------------------------------------------------------
    # Extension System
    # ------------------------------------------------------------------

    def create_replaced_session_context(self) -> ReplacedSessionContext:
        """Create a
        :class:`ReplacedSessionContext`.
        Mirrors
        :meth:`createReplacedSessionContext`
        (``agent-session-tree.ts:252-260``).

        The OpenClaw source uses
        :func:`Object.defineProperties({}, Object.getOwnPropertyDescriptors(this.createCommandContext()))`
        to copy the property descriptors
        from the command context into a
        fresh plain object, then overrides
        the ``sendMessage`` /
        ``sendUserMessage`` keys. The
        Python port wraps the
        :class:`_CommandContextView` in
        a small proxy class (the
        underlying view doesn't support
        item assignment, so we use
        delegation via ``__getattr__`` +
        the two override methods on the
        subclass).
        """
        runner = self.current_extension_runner
        base_ctx = runner.create_command_context()

        class _ReplacedSessionContextView(type(base_ctx)):  # type: ignore[misc]
            """A subclass of
            :class:`_CommandContextView`
            that overrides
            :meth:`sendMessage` +
            :meth:`sendUserMessage` to
            delegate back to the session.
            Mirrors the OpenClaw source's
            ``context.sendMessage =
            (message, options) =>
            this.sendCustomMessage(message,
            options)`` pattern."""

            def sendMessage(
                self,
                message: dict,
                options: Optional[dict] = None,
            ) -> Awaitable[None]:
                return self._session.send_custom_message(  # type: ignore[attr-defined]
                    message, options
                )

            def sendUserMessage(
                self,
                content: Any,
                options: Optional[dict] = None,
            ) -> Awaitable[None]:
                return self._session.send_user_message(  # type: ignore[attr-defined]
                    content, options
                )

        view = _ReplacedSessionContextView()
        view._session = self  # type: ignore[attr-defined]
        return view  # type: ignore[return-value]

    def has_extension_handlers(self, event_type: str) -> bool:
        """Check if extensions have
        handlers for ``event_type``.
        Mirrors
        :meth:`hasExtensionHandlers`
        (``agent-session-tree.ts:265-267``)."""
        return self.current_extension_runner.has_handlers(event_type)

    @property
    def extension_runner(self) -> ExtensionRunner:
        """The extension runner. Mirrors
        the ``extensionRunner`` getter
        (``agent-session-tree.ts:272-274``)."""
        return self.current_extension_runner


__all__ = [
    "AgentSessionTree",
    "BranchSummaryEntry",
]
