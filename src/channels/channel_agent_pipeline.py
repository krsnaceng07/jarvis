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
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from google import genai
from google.genai import types

from src.agents.system_prompt_tool_list import build_tooling_section
from src.agents.tool_loop_detection import (
    detect_tool_call_loop,
    record_tool_call,
    record_tool_call_outcome,
)
from src.agents.tools_effective_inventory import (
    ToolExecutor,
    ToolSurface,
    _stringify_output,
    build_effective_tool_inventory,
    invoke_host_tool,
)

_log = logging.getLogger("jarvis.channels.agent_pipeline")

_DEFAULT_CHANNEL_TEXT_MODEL = "gemini-3.8-flash"
_CHANNEL_TEXT_MODEL_ENV = "JARVIS_CHANNEL_TEXT_MODEL"
MAX_AGENT_TURNS = 6

# Bounded channel turns need tighter trip points than the 10/20/30 defaults:
# a 6-round loop must stop on the third identical no-progress call, not the 20th.
_CHANNEL_LOOP_CONFIG: dict[str, Any] = {
    "enabled": True,
    "historySize": 30,
    "warningThreshold": 2,
    "unknownToolThreshold": 2,
    "criticalThreshold": 3,
    "globalCircuitBreakerThreshold": 4,
}


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


def _channel_control_executors() -> dict[str, ToolExecutor]:
    """Executors for core tools whose channel behaviour differs from the desktop."""

    async def shutdown(_args: dict[str, Any], _call_id: str) -> str:
        return (
            "Notice: Host PC shutdown cannot be executed remotely via messaging channels "
            "for security. Please execute shutdown directly on the host machine."
        )

    async def standby(_args: dict[str, Any], _call_id: str) -> str:
        return "Standby is only available in the desktop session; the host stays awake."

    async def save_memory(args: dict[str, Any], _call_id: str) -> str:
        from apps.desktop.src.jarvis_desktop.memory_bridge import update_memory

        category = str(args.get("category") or "notes")
        key = str(args.get("key") or "")
        value = str(args.get("value") or "")
        if not key or not value:
            return "save_memory skipped: missing key or value."
        update_memory({category: {key: {"value": value}}})
        return f"Successfully saved to memory: {category}/{key} = {value}"

    async def recall_memory(args: dict[str, Any], _call_id: str) -> str:
        from apps.desktop.src.jarvis_desktop.memory_bridge import hybrid_search_memory

        query = str(args.get("query") or args.get("q") or "").strip()
        if not query:
            return "Query cannot be empty."
        hits = await asyncio.to_thread(
            hybrid_search_memory,
            query=query,
            limit=int(args.get("limit") or 8),
            category=args.get("category"),
            workspace_dir=_get_workspace_root(),
        )
        if not hits:
            return f"No memories found matching '{query}'."
        lines = [f"Found {len(hits)} relevant memory records:"]
        lines.extend(
            f"- [{hit.get('category', 'general')}] {hit.get('key')}: {hit.get('value')}"
            for hit in hits
        )
        return "\n".join(lines)

    return {
        "shutdown_jarvis": shutdown,
        "standby_jarvis": standby,
        "save_memory": save_memory,
        "recall_memory": recall_memory,
    }


def _channel_specific_tools() -> dict[str, dict[str, Any]]:
    """Channel-only host tools that shipped without a declaration."""

    async def mkdir(_call_id: str, args: dict[str, Any]) -> str:
        raw_path = args.get("path") or args.get("target") or args.get("dir") or ""
        if not raw_path:
            return "mkdir failed: path argument required."
        target = Path(str(raw_path))
        target.mkdir(parents=True, exist_ok=True)
        return f"Directory created: {target.resolve()}"

    async def open_path(_call_id: str, args: dict[str, Any]) -> str:
        raw_target = str(args.get("target") or args.get("path") or "").strip()
        if not raw_target:
            return "open_path failed: target path required."
        if not Path(raw_target).exists():
            return f"open_path failed: path does not exist: {raw_target}"
        if sys.platform == "win32":
            os.startfile(raw_target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":  # pragma: no cover - non-Windows host
            subprocess.Popen(["open", raw_target])
        else:  # pragma: no cover - non-Windows host
            subprocess.Popen(["xdg-open", raw_target])
        return f"Opened: {raw_target}"

    return {
        "mkdir": {
            "name": "mkdir",
            "description": "Create a directory and any missing parents on the host PC.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to create"},
                },
                "required": ["path"],
            },
            "execute": mkdir,
        },
        "open_path": {
            "name": "open_path",
            "description": "Open a file or folder with its default host application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "File or folder path to open"},
                },
                "required": ["target"],
            },
            "execute": open_path,
        },
    }


class ChannelAgentPipeline:
    """Pipeline for executing full agentic turns and host tools from external channels."""

    _instance: Optional[ChannelAgentPipeline] = None

    def __init__(self) -> None:
        self._workspace_root = _get_workspace_root()
        self._tool_declarations: list[dict[str, Any]] = []
        self._plugin_dispatch: dict[str, tuple[Any, str]] = {}
        self._plugin_commands: list[Any] = []
        self._coding_tools: dict[str, Any] = {}
        self._surface: ToolSurface | None = None
        self._initialized = False
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> ChannelAgentPipeline:
        if cls._instance is None:
            cls._instance = ChannelAgentPipeline()
        return cls._instance

    def _ensure_tools_loaded(self, live_host: Any = None) -> None:
        """Build the one tool surface used for both declarations and dispatch."""
        if self._surface is not None:
            # Adopt host tools that only the live desktop session can construct.
            if live_host is not None and hasattr(live_host, "_coding_tools"):
                self._coding_tools.update(live_host._coding_tools)
            return

        from jarvis_sdk.loader import load_all_plugins_from_workspace

        from apps.desktop.src.jarvis_desktop.tool_declarations import (
            TOOL_DECLARATIONS as BASE_TOOL_DECLARATIONS,
        )
        from src.agents.sessions.tools import create_coding_tools
        from src.agents.sessions.tools.channel_tools import (
            create_channel_status_tool,
            create_configure_channel_tool,
        )

        plugin_result = None
        try:
            plugin_result = load_all_plugins_from_workspace(self._workspace_root)
            self._plugin_dispatch = dict(plugin_result.plugin_dispatch)
            self._plugin_commands = list(plugin_result.commands)
        except Exception as e:
            _log.warning("ChannelAgentPipeline: plugin discovery issue: %s", e)

        try:
            tools_list = create_coding_tools(str(self._workspace_root))
            self._coding_tools = {t["name"]: t for t in tools_list if t.get("name")}
            conf_ch = create_configure_channel_tool(live_host)
            status_ch = create_channel_status_tool()
            self._coding_tools[conf_ch["name"]] = conf_ch
            self._coding_tools[status_ch["name"]] = status_ch
        except Exception as e:
            _log.warning("ChannelAgentPipeline: coding tools loading issue: %s", e)

        if live_host is not None and hasattr(live_host, "_coding_tools"):
            self._coding_tools.update(live_host._coding_tools)
        self._coding_tools.update(_channel_specific_tools())

        tool_cfg = _read_canonical_config().get("tools") or {}
        # Channel isolation is policy, not a runtime refusal: local GUI control
        # must not be declared to a transport that can never execute it.
        channel_deny = list(tool_cfg.get("deny") or [])
        channel_deny.extend(("computer", "desktop", "desktop_action", "auto_control"))
        self._surface = build_effective_tool_inventory(
            base_declarations=BASE_TOOL_DECLARATIONS,
            plugin_tools=plugin_result.tool_decls if plugin_result is not None else (),
            plugin_dispatch=self._plugin_dispatch,
            host_tools=self._coding_tools,
            control_executors=_channel_control_executors(),
            allow=tool_cfg.get("allow"),
            deny=channel_deny,
        )
        self._tool_declarations = self._surface.declarations()
        self._initialized = True
        _log.info(
            "ChannelAgentPipeline: admitted %d tools (%s)",
            len(self._surface),
            ", ".join(self._surface.names),
        )

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
            self._ensure_tools_loaded(live_host=live_host)

            # process(action='open_path') opens a host path through the delegated tool.
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
                # Late-bound host tools (e.g. a desktop session's open_path) win
                # here so injected/overridden executors stay honoured.
                open_path_tool = self._coding_tools.get("open_path")
                if open_path_tool is not None:
                    raw = await invoke_host_tool(
                        open_path_tool, {"target": target_val}, f"chan_{tool_name}"
                    )
                    return _stringify_output(raw)

            if self._surface is None:
                return "Tool surface is not initialized for this channel turn."

            return await self._surface_invoke(tool_name, args, f"chan_{tool_name}")

        except Exception as e:
            err_msg = f"Tool '{tool_name}' failed: {e}"
            _log.exception("Channel tool %s error: %s", tool_name, e)
            return err_msg

    async def _surface_invoke(self, tool_name: str, args: dict[str, Any], call_id: str) -> str:
        """Invoke one admitted tool and log its outcome."""
        assert self._surface is not None
        invocation = await self._surface.invoke(tool_name, args, call_id)
        print(f"[CHANNEL] 📤 {tool_name} → {invocation.result_text[:80]}")
        return invocation.result_text

    async def dispatch_turn(self, assembled: Any, live_host: Any = None) -> Optional[str]:
        """Process an inbound channel turn with full tool capabilities and transcript persistence."""
        user_text = (assembled.message.text or "").strip()
        if not user_text:
            return None

        channel_id = assembled.message.channel_id
        sender_id = assembled.message.sender_id
        session_key = assembled.session.session_key

        # Bridge inbound channel turn to Desktop HUD event queue (OpenClaw parity)
        try:
            from jarvis_session_core.system_event_queue import enqueue_system_event

            enqueue_system_event(
                f"[{str(channel_id).upper()}] {str(sender_id)}: {user_text[:100]}",
                {
                    "sessionKey": session_key or "desktop:hud",
                    "type": "channel_inbound",
                    "channel": str(channel_id),
                    "sender": str(sender_id),
                },
            )
        except Exception:
            pass

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
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-flash-lite-latest",
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-3-flash-preview",
            "gemini-2.5-flash",
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

        assert self._surface is not None
        prompt_blocks.append(build_tooling_section(self._surface))
        prompt_blocks.append(
            "[CHANNEL EXECUTION RULES]\n"
            "1. Execute the matching tool in the same turn as the request.\n"
            "2. NEVER claim an action succeeded unless a tool result in this turn reports success.\n"
            "3. NEVER say you cannot access the host PC; if a capability is genuinely missing, "
            "name the exact blocker instead of pretending it worked.\n"
            "4. Keep the channel reply concise and state only what actually happened.\n"
            "5. Save durable personal facts silently with save_memory."
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
            f"[Channel Message from {channel_id} | Sender: {sender_id}]\n{user_text}"
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
        loop_state: dict[str, Any] = {}
        loop_scope = {"runId": session_key}

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
                            call_id = getattr(fc, "id", None)

                            verdict = detect_tool_call_loop(
                                loop_state,
                                fc_name,
                                fc_args,
                                config=_CHANNEL_LOOP_CONFIG,
                                scope=loop_scope,
                            )
                            if verdict.get("level") == "critical":
                                tool_out = str(verdict.get("message") or "Tool loop detected.")
                                _log.warning(
                                    "Channel tool loop blocked (%s) for %s",
                                    verdict.get("detector"),
                                    fc_name,
                                )
                            else:
                                tool_out = await self._execute_channel_tool(
                                    tool_name=fc_name,
                                    args=fc_args,
                                    channel_id=channel_id,
                                    live_host=live_host,
                                )
                                if verdict.get("stuck"):
                                    _log.warning(
                                        "Channel tool loop warning (%s) for %s",
                                        verdict.get("detector"),
                                        fc_name,
                                    )
                                    tool_out = f"{verdict.get('message')}\n\n{tool_out}"
                                record_tool_call(
                                    loop_state,
                                    fc_name,
                                    fc_args,
                                    call_id,
                                    config=_CHANNEL_LOOP_CONFIG,
                                    scope=loop_scope,
                                )
                                record_tool_call_outcome(
                                    loop_state,
                                    {
                                        "toolName": fc_name,
                                        "toolParams": fc_args,
                                        "result": tool_out,
                                        "toolCallId": call_id,
                                        "config": _CHANNEL_LOOP_CONFIG,
                                        "runId": session_key,
                                    },
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
                        working_contents.append(types.Content(role="user", parts=tool_responses))
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

        # If tools executed but model ended without text, report only what actually happened.
        if not final_reply and executed_tool_records:
            failed = sorted(
                {
                    record["name"]
                    for record in executed_tool_records
                    if str(record.get("result", "")).lower().startswith("tool '")
                    and " failed:" in str(record.get("result", "")).lower()
                }
            )
            if failed:
                final_reply = (
                    "I could not complete this on the host PC. Failed: " + ", ".join(failed) + "."
                )
            else:
                completed_tools = ", ".join(record["name"] for record in executed_tool_records)
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

    async def execute_turn(
        self,
        user_text: str,
        channel_id: str = "default",
        sender_id: str = "owner",
        live_host: Any = None,
        session_key_override: str | None = None,
        draft_sink: Any = None,
    ) -> str:
        """Parity dispatch method for Stage 5 Turn Runner."""
        import time
        import types

        session_key = session_key_override or f"{channel_id}:chat_{sender_id}"
        assembled = types.SimpleNamespace(
            turn_id=f"turn_{int(time.time() * 1000)}",
            message=types.SimpleNamespace(
                channel_id=channel_id,
                sender_id=sender_id,
                text=user_text,
            ),
            session=types.SimpleNamespace(
                session_key=session_key,
            ),
        )
        reply = await self.dispatch_turn(assembled, live_host=live_host)
        return reply or ""


__all__ = ["ChannelAgentPipeline"]
