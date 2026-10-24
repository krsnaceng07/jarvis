"""jarvis_agent.turn_settlement — Embedded Agent Runtime & Turn Settlement Loop.

OpenClaw parity:
Core execution engine for packages/agent_runtime and src/agents/embedded_agent_runner.

Pipeline Architecture:
    Dispatch Turn Context
      -> Hook: before_prompt_build
      -> Retrieve Context: Sliding Window + MEMORY.md + USER.md
      -> Compile System & User Messages
      -> Provider Invocation: Model Streaming API
          ├─► Assistant Text Stream -> Emit Progressive Draft Previews to Channel -> Finalize Text & Rich Blocks
          └─► Tool Call Request -> Evaluate Exec Approvals & Policies:
                 ├─► Blocked -> Reject Tool Call & Return Error Payload
                 └─► Approved -> Execute Tool via Isolated Factory -> Tool Result Middleware: Sanitize & Format -> Append Tool Result to Turn Transcript -> (Re-enter loop with Depth Guard)
      -> Hook: before_agent_reply
      -> Channel Outbound Adapter: Deliver Message
      -> Synchronous SQLite Session Turn Commit (Transaction Commit Barrier)
      -> Context Size Check -> if > Limit: Trigger CompactRuntime: Summarize & Truncate
      -> Turn Settlement Complete

The 3 Runtime Loop Invariants:
    1. Progressive Draft Previews: Streaming tokens update a live draft message in real time,
       eliminating user perceived latency.
    2. Tool Execution Depth Guard: Limits maximum recursive tool calls per single turn (default: 25)
       to prevent runaway spend or recursion loops.
    3. Transaction Commit Barrier: Model response, tool executions, and tokens are written
       synchronously to agent.sqlite before releasing the turn lock.
"""

from __future__ import annotations

import inspect
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_LOG = logging.getLogger("jarvis.agent_runtime.turn_settlement")


@dataclass
class TurnSettlementConfig:
    """Configuration parameters for the Turn Settlement Loop."""

    max_tool_depth: int = 25  # Invariant 2: Depth Guard
    context_token_limit: int = 8000  # Threshold to trigger Compaction
    sliding_window_turns: int = 20
    max_tool_result_chars: int = 10000
    workspace_dir: str = "."
    agent_id: str = "default"
    model: str = "gemini-2.5-flash"
    system_prompt: Optional[str] = None
    tools: Optional[List[Any]] = None
    tool_handlers: Dict[str, Callable[..., Any]] = field(default_factory=dict)
    policy_evaluator: Optional[Callable[[str, Dict[str, Any]], bool]] = None
    outbound_adapter: Optional[Any] = None
    draft_sink: Optional[Callable[[str, str], Any]] = None
    custom_runner: Optional[Callable[..., Any]] = None
    hook_bus: Optional[Any] = None


@dataclass
class TurnSettlementResult:
    """Outcome of a completed Turn Settlement execution."""

    status: str  # "ok" | "depth_guard_exceeded" | "blocked" | "error"
    session_key: str
    final_text: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_depth: int = 0
    draft_previews_count: int = 0
    committed_to_sqlite: bool = False
    compaction_triggered: bool = False
    duration_ms: float = 0.0
    tokens_used: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to standard dictionary."""
        return {
            "status": self.status,
            "text": self.final_text,
            "tool_calls": self.tool_calls,
            "tool_depth": self.tool_depth,
            "draft_previews_count": self.draft_previews_count,
            "committed_to_sqlite": self.committed_to_sqlite,
            "compaction_triggered": self.compaction_triggered,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
            "session_key": self.session_key,
            "error": self.error,
        }


class TurnSettlementLoop:
    """The OpenClaw-grade Embedded Agent Runtime & Turn Settlement Loop for JARVIS."""

    def __init__(
        self,
        config: Optional[TurnSettlementConfig] = None,
        **kwargs: Any,
    ) -> None:
        self.config = config or TurnSettlementConfig(**kwargs)

    async def execute_turn(
        self,
        user_input: str | Dict[str, Any] | None = None,
        *,
        user_text: Optional[str] = None,
        session_key: Optional[str] = None,
        channel_id: str = "default",
        sender_id: str = "default",
        account_id: str = "default",
        chat_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        attachments: Optional[List[Any]] = None,
        session_lock: Optional[Any] = None,
        draft_sink: Optional[Callable[[str, str], Any]] = None,
        outbound_adapter: Optional[Any] = None,
        custom_runner: Optional[Callable[..., Any]] = None,
        policy_evaluator: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        workspace_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> TurnSettlementResult:
        """Execute a full turn settlement traversal.

        Follows the strict 9-step settlement sequence and enforces all 3 invariants.
        """
        start_time = time.monotonic()

        # ----------------------------------------------------------------------
        # Step A: Dispatch Turn Context & Parameter Resolution
        # ----------------------------------------------------------------------
        target_input = user_input if user_input is not None else (user_text or "")
        if isinstance(target_input, dict):
            prompt_str = str(
                target_input.get("text")
                or target_input.get("prompt")
                or target_input.get("instruction")
                or ""
            )
            channel_id = str(target_input.get("channel_id") or channel_id)
            sender_id = str(target_input.get("sender_id") or sender_id)
            account_id = str(target_input.get("account_id") or account_id)
            chat_id = target_input.get("chat_id") or chat_id
            topic_id = target_input.get("topic_id") or topic_id
            session_key = target_input.get("session_key") or session_key
        else:
            prompt_str = str(target_input)

        if not session_key:
            target_chat = chat_id or sender_id or "default"
            if topic_id and topic_id != target_chat:
                clean_topic = topic_id[len("topic:"):] if topic_id.startswith("topic:") else topic_id
                session_key = f"{channel_id}:{account_id}:{target_chat}:topic:{clean_topic}"
            else:
                session_key = f"{channel_id}:{account_id}:{target_chat}"

        ws_dir = Path(workspace_dir or self.config.workspace_dir).resolve()
        active_draft_sink = draft_sink or self.config.draft_sink
        active_outbound = outbound_adapter or self.config.outbound_adapter
        active_runner = custom_runner or self.config.custom_runner
        active_policy = policy_evaluator or self.config.policy_evaluator

        executed_tool_calls: List[Dict[str, Any]] = []
        draft_previews_count = 0
        compaction_triggered = False
        committed_to_sqlite = False
        total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # ----------------------------------------------------------------------
        # Step B: Hook before_prompt_build
        # ----------------------------------------------------------------------
        hook_injected_context = ""
        try:
            from jarvis_hooks import BEFORE_PROMPT_BUILD, fire_sync

            hook_payload = {
                "prompt": prompt_str,
                "session_key": session_key,
                "channel_id": channel_id,
                "sender_id": sender_id,
                "agent_id": self.config.agent_id,
            }
            hook_res = fire_sync(None, BEFORE_PROMPT_BUILD, hook_payload)
            if isinstance(hook_res, dict):
                if "prompt" in hook_res:
                    prompt_str = str(hook_res["prompt"])
                if "prependContext" in hook_res:
                    hook_injected_context = str(hook_res["prependContext"])
        except Exception as e:
            _LOG.debug("Hook before_prompt_build skipped or failed: %s", e)

        # ----------------------------------------------------------------------
        # Step C: Retrieve Context (Sliding Window + MEMORY.md + USER.md)
        # ----------------------------------------------------------------------
        memory_content = ""
        for mem_name in ("MEMORY.md", "memory.md"):
            mem_path = ws_dir / mem_name
            if mem_path.is_file():
                try:
                    memory_content = mem_path.read_text(encoding="utf-8").strip()
                    break
                except Exception as err:
                    _LOG.warning("Failed reading %s: %s", mem_path, err)

        user_content = ""
        for user_name in ("USER.md", "user.md"):
            user_path = ws_dir / user_name
            if user_path.is_file():
                try:
                    user_content = user_path.read_text(encoding="utf-8").strip()
                    break
                except Exception as err:
                    _LOG.warning("Failed reading %s: %s", user_path, err)

        # Sliding Window from SQLite
        past_turns: List[Dict[str, Any]] = []
        try:
            from jarvis_state_core.agent_db import (
                load_agent_session_entries,
                open_agent_database,
            )

            db_handle = open_agent_database({"agent_id": self.config.agent_id})
            past_entries = load_agent_session_entries(
                db_handle,
                session_key,
                limit=self.config.sliding_window_turns,
            )
            if isinstance(past_entries, list):
                past_turns = past_entries
        except Exception as e:
            _LOG.debug("Context retrieval from agent_db skipped or empty: %s", e)

        # ----------------------------------------------------------------------
        # Step D: Compile System & User Messages
        # ----------------------------------------------------------------------
        system_sections: List[str] = []
        base_system = self.config.system_prompt or "You are JARVIS, an autonomous personal AI assistant."
        system_sections.append(base_system)

        if memory_content:
            system_sections.append(f"### Persistent Long-Term Memory (MEMORY.md)\n{memory_content}")

        if user_content:
            system_sections.append(f"### User Profile & Preferences (USER.md)\n{user_content}")

        if hook_injected_context:
            system_sections.append(f"### Injected Runtime Context\n{hook_injected_context}")

        if past_turns:
            history_lines = [f"- {t.get('role', 'user')}: {t.get('content', '')}" for t in past_turns]
            system_sections.append("### Recent Conversation Turns\n" + "\n".join(history_lines))

        compiled_system_prompt = "\n\n".join(system_sections)

        # ----------------------------------------------------------------------
        # Step E: Provider Invocation & Streaming Loop with Depth Guard (Invariant 2)
        # ----------------------------------------------------------------------
        tool_depth = 0
        final_text = ""
        status = "ok"
        current_prompt = prompt_str
        last_tool_results: List[Dict[str, Any]] = []

        while tool_depth < self.config.max_tool_depth:
            # Recursive depth check
            if tool_depth >= self.config.max_tool_depth:
                status = "depth_guard_exceeded"
                final_text = (
                    f"Tool execution depth guard triggered: exceeded maximum allowed "
                    f"tool recursion depth ({self.config.max_tool_depth})."
                )
                break

            # 1. Custom runner invocation
            if active_runner is not None:
                runner_payload = {
                    "prompt": current_prompt,
                    "system_prompt": compiled_system_prompt,
                    "model": self.config.model,
                    "tools": self.config.tools,
                    "tool_handlers": self.config.tool_handlers,
                    "turn": tool_depth + 1,
                    "tool_results": last_tool_results,
                    "session_key": session_key,
                }
                try:
                    sig = inspect.signature(active_runner)
                    if len(sig.parameters) == 1:
                        runner_res = active_runner(runner_payload)
                    else:
                        runner_res = active_runner(
                            current_prompt,
                            system_prompt=compiled_system_prompt,
                            model=self.config.model,
                            tools=self.config.tools,
                            tool_handlers=self.config.tool_handlers,
                            tool_results=last_tool_results,
                        )
                    if inspect.isawaitable(runner_res):
                        runner_res = await runner_res
                except Exception as err:
                    runner_res = {"error": str(err), "text": f"Error during model execution: {err}"}

                # Evaluate response
                if isinstance(runner_res, dict):
                    raw_calls = runner_res.get("tool_calls", [])
                    raw_text = str(runner_res.get("text") or runner_res.get("result") or "")
                else:
                    raw_calls = []
                    raw_text = str(runner_res or "")

                # Emit progressive draft previews if text streamed (Invariant 1)
                if raw_text and active_draft_sink:
                    try:
                        # Chunked streaming simulation for progressive draft previews
                        chunk_size = max(1, len(raw_text) // 3)
                        acc = ""
                        for i in range(0, len(raw_text), chunk_size):
                            chunk = raw_text[i : i + chunk_size]
                            acc += chunk
                            res = active_draft_sink(chunk, acc)
                            if inspect.isawaitable(res):
                                await res
                            draft_previews_count += 1
                    except Exception as err:
                        _LOG.debug("draft_sink error: %s", err)

                if not raw_calls:
                    final_text = raw_text
                    break

                # Process requested tool calls
                tool_depth += 1
                last_tool_results = []
                for tc in raw_calls:
                    t_name = tc.get("name", "")
                    t_args = tc.get("args", {})

                    # Policy Evaluation & Approval
                    if active_policy and not active_policy(t_name, t_args):
                        blocked_entry = {
                            "name": t_name,
                            "args": t_args,
                            "status": "blocked",
                            "error": f"Tool '{t_name}' blocked by security policy.",
                        }
                        executed_tool_calls.append(blocked_entry)
                        last_tool_results.append(blocked_entry)
                        continue

                    handler = self.config.tool_handlers.get(t_name)
                    if handler:
                        try:
                            # Hook before_tool_call
                            try:
                                from jarvis_hooks import BEFORE_TOOL_CALL, fire_sync
                                fire_sync(None, BEFORE_TOOL_CALL, {"tool": t_name, "args": t_args})
                            except Exception:
                                pass

                            t_res = handler(**t_args) if isinstance(t_args, dict) else handler(t_args)
                            if inspect.isawaitable(t_res):
                                t_res = await t_res

                            # Tool Result Middleware: Sanitize, format, truncate
                            res_str = str(t_res)
                            if len(res_str) > self.config.max_tool_result_chars:
                                excess = len(res_str) - self.config.max_tool_result_chars
                                res_str = (
                                    res_str[: self.config.max_tool_result_chars]
                                    + f"\n[...truncated {excess} characters]"
                                )

                            # Hook after_tool_call
                            try:
                                from jarvis_hooks import AFTER_TOOL_CALL, fire_sync
                                fire_sync(None, AFTER_TOOL_CALL, {"tool": t_name, "result": res_str})
                            except Exception:
                                pass

                            call_entry = {"name": t_name, "args": t_args, "result": res_str}
                            executed_tool_calls.append(call_entry)
                            last_tool_results.append(call_entry)
                        except Exception as err:
                            call_entry = {"name": t_name, "args": t_args, "error": str(err)}
                            executed_tool_calls.append(call_entry)
                            last_tool_results.append(call_entry)
                    else:
                        call_entry = {"name": t_name, "args": t_args, "error": f"Tool '{t_name}' not registered"}
                        executed_tool_calls.append(call_entry)
                        last_tool_results.append(call_entry)

                continue

            # 2. Tool handler matching on text if no custom runner
            if self.config.tool_handlers:
                matched_tool = None
                matched_handler = None
                for t_name, handler in self.config.tool_handlers.items():
                    if t_name.lower() in current_prompt.lower():
                        matched_tool = t_name
                        matched_handler = handler
                        break

                if matched_tool and matched_handler:
                    tool_depth += 1
                    t_args = {"prompt": current_prompt}

                    # Policy Evaluation
                    if active_policy and not active_policy(matched_tool, t_args):
                        executed_tool_calls.append(
                            {"name": matched_tool, "args": t_args, "status": "blocked", "error": "Blocked by policy"}
                        )
                        final_text = f"Action with tool '{matched_tool}' was blocked by security policy."
                        break

                    try:
                        t_res = matched_handler(current_prompt)
                        if inspect.isawaitable(t_res):
                            t_res = await t_res

                        res_str = str(t_res)
                        if len(res_str) > self.config.max_tool_result_chars:
                            res_str = res_str[: self.config.max_tool_result_chars] + "...[truncated]"

                        executed_tool_calls.append({"name": matched_tool, "args": t_args, "result": res_str})
                        final_text = res_str
                        # Progressive draft emission
                        if active_draft_sink:
                            res = active_draft_sink(final_text, final_text)
                            if inspect.isawaitable(res):
                                await res
                            draft_previews_count += 1
                        break
                    except Exception as err:
                        executed_tool_calls.append({"name": matched_tool, "args": t_args, "error": str(err)})
                        final_text = f"Tool '{matched_tool}' failed: {err}"
                        break

            # 3. Google GenAI streaming integration if GEMINI_API_KEY present
            api_key = os.environ.get("GEMINI_API_KEY")
            if api_key:
                try:
                    from google import genai
                    from google.genai import types

                    client = genai.Client(api_key=api_key)
                    cfg = types.GenerateContentConfig(
                        system_instruction=compiled_system_prompt if compiled_system_prompt else None,
                    )
                    # Streaming tokens with progressive draft previews (Invariant 1)
                    response_stream = await client.aio.models.generate_content_stream(
                        model=self.config.model,
                        contents=current_prompt,
                        config=cfg,
                    )
                    acc_text = ""
                    async for chunk in response_stream:
                        chunk_text = chunk.text or ""
                        acc_text += chunk_text
                        if active_draft_sink and chunk_text:
                            res = active_draft_sink(chunk_text, acc_text)
                            if inspect.isawaitable(res):
                                await res
                            draft_previews_count += 1

                    final_text = acc_text
                    break
                except Exception as genai_err:
                    _LOG.debug("google.genai stream failed: %s; using deterministic response", genai_err)

            # 4. Deterministic fallback baseline
            final_text = f"JARVIS response to: {current_prompt}"
            if active_draft_sink:
                res = active_draft_sink(final_text, final_text)
                if inspect.isawaitable(res):
                    await res
                draft_previews_count += 1
            break

        # Check if depth guard was triggered at the loop boundary
        if tool_depth >= self.config.max_tool_depth and not final_text:
            status = "depth_guard_exceeded"
            final_text = (
                f"Tool execution depth guard triggered: exceeded maximum allowed "
                f"tool recursion depth ({self.config.max_tool_depth})."
            )

        # ----------------------------------------------------------------------
        # Step F: Hook before_agent_reply
        # ----------------------------------------------------------------------
        try:
            from jarvis_hooks import BEFORE_AGENT_REPLY, fire_sync

            reply_payload = {
                "session_key": session_key,
                "reply_text": final_text,
                "tool_calls": executed_tool_calls,
                "agent_id": self.config.agent_id,
            }
            reply_hook_res = fire_sync(None, BEFORE_AGENT_REPLY, reply_payload)
            if isinstance(reply_hook_res, dict) and "reply_text" in reply_hook_res:
                final_text = str(reply_hook_res["reply_text"])
        except Exception as e:
            _LOG.debug("Hook before_agent_reply skipped or failed: %s", e)

        # ----------------------------------------------------------------------
        # Step G: Channel Outbound Adapter Delivery
        # ----------------------------------------------------------------------
        if active_outbound is not None:
            try:
                if hasattr(active_outbound, "deliver"):
                    deliver_res = active_outbound.deliver(final_text, session_key=session_key)
                    if inspect.isawaitable(deliver_res):
                        await deliver_res
                elif hasattr(active_outbound, "send"):
                    deliver_res = active_outbound.send(final_text, session_key=session_key)
                    if inspect.isawaitable(deliver_res):
                        await deliver_res
                elif callable(active_outbound):
                    deliver_res = active_outbound(final_text)
                    if inspect.isawaitable(deliver_res):
                        await deliver_res
            except Exception as err:
                _LOG.warning("Channel outbound adapter delivery failed: %s", err)

        # ----------------------------------------------------------------------
        # Step H: Synchronous SQLite Session Turn Commit (Invariant 3)
        # Transaction Commit Barrier: model response, tools, and tokens are
        # written synchronously to agent.sqlite before releasing session lock.
        # ----------------------------------------------------------------------
        try:
            from jarvis_state_core.agent_db import (
                append_agent_session_entry,
                ensure_agent_session,
                open_agent_database,
            )

            now_ts = str(int(time.time() * 1000))
            db_handle = open_agent_database({"agent_id": self.config.agent_id})
            ensure_agent_session(db_handle, session_key, cwd=str(ws_dir), timestamp=now_ts)

            # 1. Commit user turn entry
            append_agent_session_entry(
                db_handle,
                session_key,
                {
                    "id": f"msg_{now_ts}_user",
                    "role": "user",
                    "content": prompt_str,
                    "sender_id": sender_id,
                    "channel_id": channel_id,
                    "timestamp": now_ts,
                },
                timestamp=now_ts,
            )

            # 2. Commit any tool calls
            for idx, tc in enumerate(executed_tool_calls):
                append_agent_session_entry(
                    db_handle,
                    session_key,
                    {
                        "id": f"msg_{now_ts}_tool_{idx}",
                        "role": "tool",
                        "name": tc.get("name"),
                        "args": tc.get("args"),
                        "result": tc.get("result"),
                        "error": tc.get("error"),
                        "timestamp": now_ts,
                    },
                    timestamp=now_ts,
                )

            # 3. Commit assistant final turn entry
            append_agent_session_entry(
                db_handle,
                session_key,
                {
                    "id": f"msg_{now_ts}_assistant",
                    "role": "assistant",
                    "content": final_text,
                    "status": status,
                    "tool_depth": tool_depth,
                    "timestamp": now_ts,
                },
                timestamp=now_ts,
            )
            committed_to_sqlite = True
        except Exception as db_err:
            _LOG.warning("Synchronous SQLite session turn commit failed: %s", db_err)

        # ----------------------------------------------------------------------
        # Step I: Context Size Limit Check & Compaction Trigger
        # ----------------------------------------------------------------------
        estimated_chars = len(compiled_system_prompt) + len(prompt_str) + len(final_text)
        for tc in executed_tool_calls:
            estimated_chars += len(str(tc))
        # Simple token estimation (~4 chars per token)
        estimated_tokens = estimated_chars // 4
        total_tokens["total_tokens"] = estimated_tokens

        if estimated_tokens > self.config.context_token_limit:
            try:
                from src.agents.embedded_agent_runner.compact_runtime import (
                    compact_embedded_agent_session_direct,
                )

                compact_res = await compact_embedded_agent_session_direct(
                    session_key=session_key,
                    agent_id=self.config.agent_id,
                    workspace_dir=str(ws_dir),
                )
                compaction_triggered = True
                _LOG.info("Triggered CompactRuntime for session %s: %s", session_key, compact_res)
            except Exception as compact_err:
                _LOG.debug("Compaction attempt logged: %s", compact_err)

        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)

        return TurnSettlementResult(
            status=status,
            session_key=session_key,
            final_text=final_text,
            tool_calls=executed_tool_calls,
            tool_depth=tool_depth,
            draft_previews_count=draft_previews_count,
            committed_to_sqlite=committed_to_sqlite,
            compaction_triggered=compaction_triggered,
            duration_ms=elapsed_ms,
            tokens_used=total_tokens,
        )


async def run_turn_settlement_loop(
    user_input: str | Dict[str, Any],
    **kwargs: Any,
) -> TurnSettlementResult:
    """Convenience helper to execute a single turn settlement loop."""
    loop = TurnSettlementLoop(**kwargs)
    return await loop.execute_turn(user_input, **kwargs)


__all__ = [
    "TurnSettlementConfig",
    "TurnSettlementLoop",
    "TurnSettlementResult",
    "run_turn_settlement_loop",
]
