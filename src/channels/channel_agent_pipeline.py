"""jarvis.channels.channel_agent_pipeline — OpenClaw-parity channel agent tool pipeline.

Executes host PC tools (filesystem, coding tools, terminal, desktop automation,
YouTube, memory, and channel tools) from external messaging channels (Telegram,
WhatsApp, etc.) with an iterative multi-turn function calling loop and strict
channel reply isolation.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from google import genai
from google.genai import types

_log = logging.getLogger("jarvis.channels.agent_pipeline")

_DEFAULT_CHANNEL_TEXT_MODEL = "gemini-2.5-flash"
_CHANNEL_TEXT_MODEL_ENV = "JARVIS_CHANNEL_TEXT_MODEL"
MAX_AGENT_TURNS = 6


def _get_workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_gemini_api_key() -> str:
    for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "JARVIS_GEMINI_API_KEY"):
        value = os.environ.get(env_name)
        if value:
            return value
    api_path = _get_workspace_root() / "config" / "api_keys.json"
    try:
        data = json.loads(api_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    value = data.get("gemini_api_key")
    return value if isinstance(value, str) else ""


def _read_canonical_config() -> dict[str, Any]:
    cfg_path = Path.home() / ".jarvis" / "config.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        _log.warning("Failed to parse %s: %s", cfg_path, e)
        return {}


def _load_channel_system_prompt() -> str:
    prompt_path = _get_workspace_root() / "core" / "prompt.txt"
    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS. Reply directly and concisely to the user's channel message. "
            "Do not claim actions were completed unless a tool actually verified them."
        )


def _unwrap_result(result: Any) -> str:
    """Convert a plugin or tool result to a readable string."""
    from jarvis_sdk import Err, Ok

    if isinstance(result, Ok):
        v = result.value
        return v if isinstance(v, str) else str(v)
    if isinstance(result, Err):
        return f"Error: {result.error}"
    return str(result)


def _extract_tool_output(result: Any) -> str:
    """Extract readable text from an AgentToolResult or raw dict/string."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list) and content:
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                elif isinstance(item, str):
                    parts.append(item)
            if parts:
                return "\n".join(parts)
        if "text" in result:
            return str(result["text"])
        if "result" in result:
            return str(result["result"])
        if "output" in result:
            return str(result["output"])
    return str(result)


class ChannelAgentPipeline:
    """Pipeline for executing full agentic turns and host tools from external channels."""

    _instance: Optional[ChannelAgentPipeline] = None

    def __init__(self) -> None:
        self._workspace_root = _get_workspace_root()
        self._tool_declarations: list[dict[str, Any]] = []
        self._plugin_dispatch: dict[str, tuple[Any, str]] = {}
        self._plugin_commands: list[Any] = []
        self._coding_tools: dict[str, Any] = {}
        self._initialized = False
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> ChannelAgentPipeline:
        if cls._instance is None:
            cls._instance = ChannelAgentPipeline()
        return cls._instance

    def _ensure_tools_loaded(self, live_host: Any = None) -> None:
        """Load and cache tool declarations and dispatch targets without UI side effects."""
        if self._initialized:
            # If live_host has coding tools, adopt them
            if live_host is not None and hasattr(live_host, "_coding_tools"):
                self._coding_tools.update(live_host._coding_tools)
            return

        from apps.desktop.src.jarvis_desktop.tool_declarations import (
            TOOL_DECLARATIONS as BASE_TOOL_DECLARATIONS,
            normalize_model_tool_declaration,
        )
        from jarvis_sdk.loader import load_all_plugins_from_workspace
        from src.agents.sessions.tools import create_coding_tools
        from src.agents.sessions.tools.channel_tools import (
            create_channel_status_tool,
            create_configure_channel_tool,
        )

        # 1. Base model declarations
        declarations = list(BASE_TOOL_DECLARATIONS)
        existing_names = {t["name"] for t in declarations}

        # 2. Plugin loader (pure data, no UI/gateway side-effects)
        try:
            plugin_result = load_all_plugins_from_workspace(self._workspace_root)
            self._plugin_dispatch = dict(plugin_result.plugin_dispatch)
            self._plugin_commands = list(plugin_result.commands)
            for decl in plugin_result.tool_decls:
                if decl["name"] not in existing_names:
                    declarations.append(normalize_model_tool_declaration(decl))
                    existing_names.add(decl["name"])
        except Exception as e:
            _log.warning("ChannelAgentPipeline: plugin discovery issue: %s", e)

        self._tool_declarations = declarations

        # 3. Built-in coding & system tools
        try:
            tools_list = create_coding_tools(str(self._workspace_root))
            self._coding_tools = {t["name"]: t for t in tools_list}
            conf_ch = create_configure_channel_tool(live_host)
            status_ch = create_channel_status_tool()
            self._coding_tools[conf_ch["name"]] = conf_ch
            self._coding_tools[status_ch["name"]] = status_ch
        except Exception as e:
            _log.warning("ChannelAgentPipeline: coding tools loading issue: %s", e)

        if live_host is not None and hasattr(live_host, "_coding_tools"):
            self._coding_tools.update(live_host._coding_tools)

        self._initialized = True

    async def _dispatch_slash_command(
        self,
        command_text: str,
        channel_id: str,
        sender_id: str,
    ) -> Optional[str]:
        """Dispatch a slash command (e.g. /status, /help) via CommandRouter."""
        try:
            from apps.desktop.src.jarvis_desktop.commands import CommandRouter

            self._ensure_tools_loaded()
            if not self._plugin_commands:
                return None

            router = CommandRouter(self._plugin_commands, config=_read_canonical_config())
            result = await router.dispatch(command_text)
            if result is not None and result.reply_text:
                return result.reply_text.strip()
        except Exception as e:
            _log.warning("Channel slash command dispatch failed for %r: %s", command_text, e)
        return None

    async def _execute_channel_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        channel_id: str,
        live_host: Any = None,
    ) -> str:
        """Execute a tool call safely in the host environment with strict channel isolation."""
        from src.routing.agent_id import DEFAULT_AGENT_ID, normalize_agent_id

        # Normalize or inject agentId
        if "agentId" in args and args["agentId"]:
            args["agentId"] = normalize_agent_id(args["agentId"])
        else:
            args.setdefault("agentId", DEFAULT_AGENT_ID)

        print(f"[CHANNEL: {channel_id}] 🔧 Executing tool '{tool_name}' with args: {args}")

        try:
            # 1. Plugin dispatch
            if tool_name in self._plugin_dispatch:
                plugin_inst, call_name = self._plugin_dispatch[tool_name]
                loop = asyncio.get_running_loop()
                plugin_result = await loop.run_in_executor(
                    None,
                    lambda inst=plugin_inst, cn=call_name, a=args: inst.call(cn, a),
                )
                if hasattr(plugin_result, "__await__"):
                    plugin_result = await plugin_result
                out = _unwrap_result(plugin_result)
                print(f"[CHANNEL: {channel_id}] 📤 {tool_name} → {str(out)[:80]}")
                return out or f"{tool_name} completed."

            # 2. Long-term memory
            if tool_name == "save_memory":
                from apps.desktop.src.jarvis_desktop.memory_bridge import update_memory

                category = args.get("category", "notes")
                key = args.get("key", "")
                value = args.get("value", "")
                if key and value:
                    update_memory({category: {key: {"value": value}}})
                    print(f"[CHANNEL: {channel_id}] 💾 save_memory: {category}/{key} = {value}")
                    return f"Successfully saved to memory: {category}/{key} = {value}"
                return "save_memory skipped: missing key or value."

            # 3. Desktop actions
            if tool_name in ("desktop", "desktop_action", "auto_control"):
                from apps.desktop.src.jarvis_desktop.tool_pipeline import execute_desktop_action

                out = await execute_desktop_action(args)
                print(f"[CHANNEL: {channel_id}] 📤 {tool_name} → {str(out)[:80]}")
                return out

            # 4. YouTube automation
            if tool_name.startswith("youtube_"):
                from src.application_automation.tools.youtube_tools import dispatch_youtube_tool

                out = await dispatch_youtube_tool(tool_name, args)
                print(f"[CHANNEL: {channel_id}] 📤 {tool_name} → {str(out)[:80]}")
                return out

            # 5. Set task goal
            if tool_name == "set_task_goal":
                goal = str(args.get("goal") or args.get("description") or "")
                return f"Task goal set to: {goal}"

            # 6. Coding & System tools (open_path, process, exec, mkdir, read, write, edit, ls, etc.)
            coding_tools = self._coding_tools
            if live_host is not None and hasattr(live_host, "_coding_tools"):
                coding_tools = live_host._coding_tools

            active_name = tool_name
            active_args = dict(args)

            # Parity delegation: process(action='open_path', ...) -> open_path
            if tool_name == "process" and args.get("action") in (
                "open",
                "open_path",
                "start",
                "launch",
            ):
                target_val = (
                    args.get("session_id")
                    or args.get("target")
                    or args.get("path")
                    or args.get("app")
                    or ""
                )
                if "open_path" in coding_tools:
                    active_name = "open_path"
                    active_args = {"target": target_val}

            if active_name in coding_tools:
                tool_entry = coding_tools[active_name]
                execute_fn = tool_entry.get("execute")
                if execute_fn:
                    raw_res = await execute_fn(f"chan_{tool_name}", active_args)
                    out = _extract_tool_output(raw_res)
                    print(f"[CHANNEL: {channel_id}] 📤 {active_name} → {str(out)[:80]}")
                    return out
                return f"Tool '{active_name}' has no execute handler."

            # 7. Security: Shutdown blocked via channel
            if tool_name == "shutdown_jarvis":
                return (
                    "Notice: Host PC shutdown cannot be executed remotely via messaging channels "
                    "for security. Please execute shutdown directly on the host machine."
                )

            return f"Tool '{tool_name}' is not recognized or available in this environment."

        except Exception as e:
            err_msg = f"Tool '{tool_name}' failed: {e}"
            _log.exception("Channel tool %s error: %s", tool_name, e)
            return err_msg

    async def dispatch_turn(self, assembled: Any, live_host: Any = None) -> Optional[str]:
        """Process an inbound channel turn with full tool capabilities and transcript persistence."""
        user_text = (assembled.message.text or "").strip()
        if not user_text:
            return None

        channel_id = assembled.message.channel_id
        sender_id = assembled.message.sender_id
        session_key = assembled.session.session_key

        # ── 1. Slash command fast-path ─────────────────────────────
        if user_text.startswith("/"):
            slash_res = await self._dispatch_slash_command(user_text, channel_id, sender_id)
            if slash_res:
                return slash_res

        # ── 2. Load API key & model candidates ──────────────────────
        api_key = _read_gemini_api_key()
        if not api_key:
            _log.warning("No Gemini API key available for channel turn")
            return None

        cfg = _read_canonical_config()
        configured_model = (
            os.environ.get(_CHANNEL_TEXT_MODEL_ENV)
            or cfg.get("channels", {}).get(channel_id, {}).get("model")
            or cfg.get("model")
            or _DEFAULT_CHANNEL_TEXT_MODEL
        )
        candidates = [
            configured_model,
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-flash-lite-latest",
            "gemini-2.5-pro",
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite-preview",
        ]
        unique_candidates: list[str] = []
        for c in candidates:
            if c and c not in unique_candidates:
                unique_candidates.append(c)

        # ── 3. Assemble Prompt & Context ────────────────────────────
        self._ensure_tools_loaded(live_host=live_host)

        # OpenClaw temporal context parity (LiveClock)
        temporal_ctx = ""
        try:
            from src.system.live_clock import LiveClock

            temporal_ctx = LiveClock.build_temporal_context_prompt()
        except Exception:
            pass

        # OpenClaw memory context parity (long-term memory facts)
        memory_ctx = ""
        try:
            from apps.desktop.src.jarvis_desktop.memory_bridge import (
                format_memory_for_prompt,
                load_memory,
            )

            memory = load_memory()
            memory_ctx = format_memory_for_prompt(memory, self._workspace_root)
        except Exception:
            pass

        # Configured external channels status
        channel_status_ctx = ""
        try:
            from src.channels.channel_manager import ChannelManager

            channel_status_ctx = ChannelManager.get_instance().format_channel_status_for_prompt()
        except Exception:
            pass

        prompt_blocks = [_load_channel_system_prompt()]
        if temporal_ctx:
            prompt_blocks.append(temporal_ctx)
        if memory_ctx:
            prompt_blocks.append(memory_ctx)
        if channel_status_ctx:
            prompt_blocks.append(channel_status_ctx)

        prompt_blocks.append(
            "[HOST TOOL ACCESS & CAPABILITIES]\n"
            "You have direct execution access to tools on the user's host PC (running Windows).\n"
            "Available capabilities include: file management (read, write, edit, mkdir, ls, open_path), "
            "terminal execution (exec, process), desktop GUI control (desktop, desktop_action), "
            "YouTube playback & search (youtube_*), long-term personal memory (save_memory), "
            "web search, and channel management (configure_channel, channel_status).\n\n"
            "RULES FOR CHANNEL OPERATIONS:\n"
            "1. When the user asks you to perform a task on their PC (such as creating files/folders, "
            "launching applications, running terminal commands, searching YouTube, or checking status), "
            "YOU MUST EXECUTE THE APPROPRIATE TOOL IMMEDIATELY.\n"
            "2. NEVER claim actions were done unless you actually called the tool and verified the result.\n"
            "3. NEVER say you cannot access their computer or ask them to do it manually.\n"
            "4. Be concise and direct in your channel reply. Confirm what was actually accomplished.\n"
            "5. Save personal user facts silently using save_memory whenever they share things worth remembering."
        )

        system_instruction = "\n\n".join(prompt_blocks)

        # ── 4. Retrieve conversation history from SessionTranscriptStore ───
        from src.agents.task.session_transcript_store import SessionTranscriptStore

        transcript_store = SessionTranscriptStore()
        recent_entries = transcript_store.get_recent_entries(session_key, limit=12)

        raw_contents: list[types.Content] = []
        for entry in recent_entries:
            data = entry.get("data", {})
            entry_type = entry.get("entry_type")
            if entry_type == "user_turn" and "text" in data and data["text"]:
                raw_contents.append(
                    types.Content(role="user", parts=[types.Part.from_text(text=str(data["text"]))])
                )
            elif entry_type == "assistant_reply" and "text" in data and data["text"]:
                raw_contents.append(
                    types.Content(
                        role="model", parts=[types.Part.from_text(text=str(data["text"]))]
                    )
                )

        # Add current user message
        channel_user_prompt = (
            f"[Channel Message from {channel_id} | Sender: {sender_id}]\n"
            f"{user_text}"
        )
        raw_contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=channel_user_prompt)],
            )
        )

        # Normalize to strict alternating roles (user -> model -> user -> model)
        normalized_contents: list[types.Content] = []
        for c in raw_contents:
            if not c.parts:
                continue
            if normalized_contents and normalized_contents[-1].role == c.role:
                prev = normalized_contents[-1]
                if prev.parts is None:
                    prev.parts = list(c.parts)
                else:
                    prev.parts.extend(c.parts)
            else:
                normalized_contents.append(c)

        # Ensure first turn is user role
        if normalized_contents and normalized_contents[0].role != "user":
            normalized_contents.pop(0)

        # ── 5. Agentic Multi-Turn Tool Execution Loop ─────────────────────
        client = genai.Client(api_key=api_key)
        tool_decl_list: Any = self._tool_declarations
        tool_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[types.Tool(function_declarations=tool_decl_list)],
        )

        final_reply: Optional[str] = None
        executed_tool_records: list[dict[str, Any]] = []

        for cand_model in unique_candidates:
            try:
                working_contents: Any = copy.deepcopy(normalized_contents)
                turn_succeeded = False

                for _ in range(MAX_AGENT_TURNS):
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=cand_model,
                        contents=working_contents,
                        config=tool_config,
                    )

                    candidates = getattr(response, "candidates", None)
                    if not response or not candidates:
                        break

                    candidate = candidates[0]
                    content = getattr(candidate, "content", None)

                    # Check for function calls
                    function_calls = getattr(response, "function_calls", None)
                    content_parts = getattr(content, "parts", None) if content else None
                    if not function_calls and content_parts:
                        function_calls = [
                            getattr(p, "function_call", None)
                            for p in content_parts
                            if getattr(p, "function_call", None) is not None
                        ]

                    if function_calls and content is not None:
                        # Append the assistant's turn with tool calls
                        working_contents.append(content)

                        tool_responses: list[types.Part] = []
                        for fc in function_calls:
                            if fc is None:
                                continue
                            fc_name = str(getattr(fc, "name", "") or "")
                            fc_args = dict(getattr(fc, "args", {}) or {})

                            tool_out = await self._execute_channel_tool(
                                tool_name=fc_name,
                                args=fc_args,
                                channel_id=channel_id,
                                live_host=live_host,
                            )
                            executed_tool_records.append(
                                {"name": fc_name, "args": fc_args, "result": tool_out}
                            )
                            tool_responses.append(
                                types.Part.from_function_response(
                                    name=fc_name,
                                    response={"result": tool_out},
                                )
                            )

                        # Append tool responses as user turn
                        working_contents.append(
                            types.Content(role="user", parts=tool_responses)
                        )
                    else:
                        # Final textual response reached
                        reply_text = getattr(response, "text", None)
                        if isinstance(reply_text, str) and reply_text.strip():
                            final_reply = reply_text.strip()
                            turn_succeeded = True
                            break

                        if content_parts:
                            text_parts: list[str] = [
                                str(getattr(p, "text", ""))
                                for p in content_parts
                                if getattr(p, "text", None) is not None
                            ]
                            if text_parts:
                                final_reply = "".join(text_parts).strip()
                                turn_succeeded = True
                                break
                        break

                if turn_succeeded and final_reply:
                    break

            except Exception as cand_err:
                _log.warning("Candidate model %s encountered error: %s", cand_model, cand_err)
                continue

        # If tools executed but model ended without text, synthesize confirmation
        if not final_reply and executed_tool_records:
            completed_tools = ", ".join(t["name"] for t in executed_tool_records)
            final_reply = f"Task completed on host PC ({completed_tools})."

        # ── 6. Persist turn to SQLite SessionTranscriptStore ──────────────
        if final_reply:
            try:
                transcript_store.append_entry(
                    session_id=session_key,
                    entry_type="user_turn",
                    data={
                        "text": user_text,
                        "channel": channel_id,
                        "sender": sender_id,
                    },
                )
                if executed_tool_records:
                    transcript_store.append_entry(
                        session_id=session_key,
                        entry_type="tool_executions",
                        data={"tools": executed_tool_records},
                        verified=True,
                    )
                transcript_store.append_entry(
                    session_id=session_key,
                    entry_type="assistant_reply",
                    data={"text": final_reply},
                )
            except Exception as e:
                _log.warning("Failed to persist transcript for %s: %s", session_key, e)

        return final_reply


__all__ = ["ChannelAgentPipeline"]
