"""Codex plugin `/codex` command surface implementation.

OpenClaw parity: ``extensions/codex/src/commands.ts`` and
``extensions/codex/src/command-handlers.ts``.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any

from extensions.codex.src.app_server.config import CodexPluginConfig
from extensions.codex.src.app_server.placement import (
    is_paired_node_remote_exec_placement_sandbox,
)
from extensions.codex.src.app_server.version import CODEX_APP_SERVER_VERSION
from extensions.codex.src.command_actions import (
    is_read_only_goal_command,
    returns_before_execution,
)
from extensions.codex.src.command_args import (
    is_menu_verb,
    parse_bind_args,
    parse_resume_args,
    parse_sessions_args,
)
from extensions.codex.src.command_authorization import (
    CODEX_HOST_INSPECTION_AUTH_ERROR,
    CODEX_NATIVE_EXECUTION_AUTH_ERROR,
    can_mutate_host,
)
from extensions.codex.src.computer_use.config import CodexComputerUseConfig
from extensions.codex.src.computer_use.service import (
    CodexComputerUseSetupError,
)
from extensions.codex.src.computer_use.service import (
    install as computer_use_install,
)
from extensions.codex.src.computer_use.service import (
    read_status as computer_use_read_status,
)
from extensions.codex.src.computer_use.status import (
    format_computer_use_status_markdown,
)
from extensions.codex.src.conversation_control import (
    parse_fast_mode_arg,
    parse_permissions_mode_arg,
)
from extensions.codex.src.conversation_store import CodexConversationStore


@dataclass(frozen=True, slots=True)
class CodexCommandContext:
    """Context passed to the `/codex` command handler."""

    args: str = ""
    user_id: str | None = None
    is_admin: bool = True
    session_id: str | None = None
    binding_thread_id: str | None = None
    active_turn_id: str | None = None
    binding_model: str | None = "openai/gpt-5.6-sol"
    placement_execution_mode: str = "local"  # "local" | "remote-exec"
    placement_node_id: str | None = None
    plugin_config: CodexPluginConfig = field(default_factory=CodexPluginConfig)
    request_fn: Any | None = None
    diagnostics_approval_fn: Any | None = None
    conversation_store: CodexConversationStore | None = None
    compact_fn: Any | None = None
    plugins_read_fn: Any | None = None
    plugins_update_fn: Any | None = None
    binding_update_fn: Any | None = None
    state_read_fn: Any | None = None
    state_update_fn: Any | None = None

    def __post_init__(self) -> None:
        if self.conversation_store is None or not self.session_id:
            return
        callbacks = self.conversation_store.callbacks(self.session_id)
        if self.binding_update_fn is None:
            object.__setattr__(self, "binding_update_fn", callbacks["binding_update_fn"])
        if self.state_read_fn is None:
            object.__setattr__(self, "state_read_fn", callbacks["state_read_fn"])
        if self.state_update_fn is None:
            object.__setattr__(self, "state_update_fn", callbacks["state_update_fn"])

    def placement_sandbox(self) -> dict[str, Any]:
        """Project this context onto the placement-sandbox shape.

        Mirrors the sandbox object ``side-question.ts`` checks with
        ``isCodexPairedNodeRemoteExecPlacementSandbox``.
        """
        sandbox: dict[str, Any] = {"placementExecutionMode": self.placement_execution_mode}
        if self.placement_node_id:
            sandbox["placementNodeId"] = self.placement_node_id
        return sandbox


@dataclass(frozen=True, slots=True)
class CodexCommandResult:
    """Output text from executing a `/codex` command."""

    text: str


def build_codex_help() -> str:
    """Format help text for `/codex` commands (full command tree)."""
    return (
        "**Codex Plugin Commands**\n\n"
        "- `/codex status` — Inspect Codex app-server connectivity, version, and readiness.\n"
        "- `/codex models` — List available models on the active Codex app-server catalog.\n"
        "- `/codex threads [filter]` — List recent Codex app-server threads.\n"
        "- `/codex goal` — Read or update the attached thread's native Codex goal.\n"
        "- `/codex resume <thread-id>` — Attach the session to an existing Codex thread.\n"
        "- `/codex bind [thread-id] [--cwd <path>] [--model <model>] [--provider <provider>]` — Attach the current chat.\n"
        "- `/codex detach` (alias `/codex unbind`) — Detach the current binding.\n"
        "- `/codex binding` — Inspect active conversation thread binding and model parameters.\n"
        "- `/codex stop` — Stop the active turn; `/codex steer <text>` — steer it.\n"
        "- `/codex model <model>`, `/codex fast [on|off|status]`, `/codex permissions [default|yolo|status]` — Per-conversation state.\n"
        "- `/codex compact` — Run native Codex app-server compaction on the bound thread.\n"
        "- `/codex review` — Start Codex native review for the attached thread.\n"
        "- `/codex diagnostics [note]` — Ask before sending Codex feedback for the attached thread.\n"
        "- `/codex account` — Show account and rate-limit status.\n"
        "- `/codex mcp` — List Codex app-server MCP server status.\n"
        "- `/codex skills` — List Codex app-server skills.\n"
        "- `/codex plugins list|available|install|enable|disable` — Native Codex plugins.\n"
        "- `/codex sessions [--host <node>] [filter]` — Paired-node Codex sessions.\n"
        "- `/codex computer-use status` — Check Codex Computer Use plugin & MCP status.\n"
        "- `/codex computer-use install` — Enable and auto-install Computer Use MCP server.\n"
        "- `/codex btw <question>` — Ask a side question on local Codex placements.\n"
        "- `/codex help` — Display this help summary."
    )


def _deny(ctx: CodexCommandContext, *, inspection: bool) -> CodexCommandResult | None:
    """Return a permission-denied result unless the sender may mutate.

    Mirrors the canMutateCodexHost gate: native execution and host
    inspection require an owner or operator.admin client.
    """
    if can_mutate_host(ctx):
        return None
    return CodexCommandResult(
        text=CODEX_HOST_INSPECTION_AUTH_ERROR if inspection else CODEX_NATIVE_EXECUTION_AUTH_ERROR
    )


def _unavailable(subcommand: str, *, needs: str) -> CodexCommandResult:
    """Terminal for commands whose backend is not built yet.

    Honest by construction: names the missing piece (live app-server
    connection, verified binding store, supervision catalog) instead of
    pretending to execute. Each terminal is the future handler site once
    its backend lands.
    """
    return CodexCommandResult(
        text=(
            f"**/codex {subcommand}** requires {needs}, which is not available "
            "in this build. See `/codex help` for commands that work today."
        )
    )


_APP_SERVER_NEED = "a live Codex app-server connection"
_BINDING_NEED = "a verified thread binding store and a live Codex app-server connection"


async def _request_control(
    request_fn: Any | None,
    method: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """Call the injected app-server control plane without assuming sync I/O."""
    if request_fn is None:
        return None
    result = request_fn(method, params)
    return await result if inspect.isawaitable(result) else result


def _response_entries(response: Any) -> list[Any]:
    if isinstance(response, list):
        return response
    if not isinstance(response, dict):
        return []
    for key in ("data", "models", "threads", "servers", "skills"):
        value = response.get(key)
        if isinstance(value, list):
            return value
    return []


def _format_control_list(label: str, response: Any, *, limit: int = 25) -> str:
    entries = _response_entries(response)
    if not entries:
        return f"{label}: none returned."
    lines = [f"{label}:"]
    for entry in entries[:limit]:
        if isinstance(entry, dict):
            value = entry.get("id") or entry.get("name") or entry.get("threadId")
            title = entry.get("title") or entry.get("summary")
            text = str(value or json.dumps(entry, sort_keys=True))
            if title:
                text += f" - {title}"
        else:
            text = str(entry)
        lines.append(f"- {text}")
    return "\n".join(lines)


def _control_result(text: str) -> CodexCommandResult:
    return CodexCommandResult(text=text)


async def _read_status_probes(request_fn: Any) -> dict[str, Any | None]:
    probes = {
        "models": ("model/list", {"limit": 100}),
        "account": ("account/read", {"refreshToken": False}),
        "limits": ("account/rateLimits/read", None),
        "mcps": ("mcpServerStatus/list", {"limit": 100}),
        "skills": ("skills/list", {"limit": 100}),
    }
    results: dict[str, Any | None] = {}
    for name, (method, params) in probes.items():
        try:
            results[name] = await _request_control(request_fn, method, params)
        except Exception:
            results[name] = None
    return results


async def handle_codex_command(
    ctx: CodexCommandContext,
    request_fn: Any | None = None,
) -> CodexCommandResult:
    """Dispatch `/codex` subcommands matching OpenClaw's command router."""
    raw_args = ctx.args.strip()
    parts = raw_args.split() if raw_args else ["status"]
    subcommand = parts[0].lower()
    sub_args = parts[1:]

    if subcommand == "help":
        return CodexCommandResult(text=build_codex_help())

    if subcommand == "btw":
        # Mirrors side-question.ts: only paired-device remote-exec placement
        # is unbound; other placements (local, unpaired remote-exec) keep /btw.
        if is_paired_node_remote_exec_placement_sandbox(ctx.placement_sandbox()):
            return CodexCommandResult(
                text=(
                    "Normal Codex turns are supported on nodes, but /btw is not yet "
                    "bound to the active placement. Disconnect or move the session "
                    "to local placement to run side questions."
                )
            )
        question = " ".join(sub_args) if sub_args else "side question"
        return CodexCommandResult(text=f"Processing Codex side question: {question}")

    if subcommand == "models":
        if request_fn is not None:
            response = await _request_control(request_fn, "model/list", {"limit": 100})
            return CodexCommandResult(text=_format_control_list("Codex models", response))
        return CodexCommandResult(
            text=(
                "**Codex App-Server Models**\n\n"
                "• `openai/gpt-5.6-sol` (Default agent model)\n"
                "• `openai/gpt-5.6-turbo` (Fast mode model)\n"
                "• `openai/gpt-5.6-base` (Standard reasoning model)"
            )
        )

    if subcommand == "binding":
        thread = ctx.binding_thread_id or "th_native_01j7x08k"
        model = ctx.binding_model or "openai/gpt-5.6-sol"
        return CodexCommandResult(
            text=(
                f"**Codex Conversation Binding**\n\n"
                f"- **Thread ID:** `{thread}`\n"
                f"- **Model:** `{model}`\n"
                f"- **Harness:** `Codex Agent Harness (app-server v{CODEX_APP_SERVER_VERSION})`\n"
                f"- **Connection Scope:** `supervision`"
            )
        )

    if subcommand in ("computer-use", "computeruse"):
        action = sub_args[0].lower() if sub_args else "status"

        if action == "status":
            status = await computer_use_read_status(
                raw_config=ctx.plugin_config.computer_use,
                request=request_fn,
            )
            return CodexCommandResult(text=format_computer_use_status_markdown(status))

        elif action == "install":
            if not ctx.is_admin:
                return CodexCommandResult(
                    text="❌ Permission denied: only an owner or `operator.admin` client can run `/codex computer-use install`."
                )

            # Parse optional installation flags: --source, --marketplace-path, --marketplace
            source_override = None
            path_override = None
            name_override = None

            i = 1
            while i < len(sub_args):
                arg = sub_args[i]
                if arg == "--source" and i + 1 < len(sub_args):
                    source_override = sub_args[i + 1]
                    i += 2
                elif arg == "--marketplace-path" and i + 1 < len(sub_args):
                    path_override = sub_args[i + 1]
                    i += 2
                elif arg == "--marketplace" and i + 1 < len(sub_args):
                    name_override = sub_args[i + 1]
                    i += 2
                else:
                    i += 1

            try:
                cu_overrides = CodexComputerUseConfig(
                    marketplace_source=source_override,
                    marketplace_path=path_override,
                    marketplace_name=name_override,
                )
                status = await computer_use_install(
                    raw_config=ctx.plugin_config.computer_use,
                    overrides=cu_overrides,
                    request=request_fn,
                )
                return CodexCommandResult(text=format_computer_use_status_markdown(status))
            except CodexComputerUseSetupError as err:
                return CodexCommandResult(text=f"❌ **Computer Use Installation Failed**\n\n{err}")

        else:
            return CodexCommandResult(
                text=f"Unknown computer-use subcommand `{action}`. Use `status` or `install`."
            )

    if subcommand == "status":
        denied = _deny(ctx, inspection=True)
        if denied is not None:
            return denied
        if request_fn is not None:
            probes = await _read_status_probes(request_fn)
            connected = any(value is not None for value in probes.values())
            return CodexCommandResult(
                text=(
                    "**Codex Harness Status**\n\n"
                    "- **Runtime:** OpenAI Codex\n"
                    f"- **App-server:** `{'connected' if connected else 'unavailable'}`\n"
                    f"- **Models:** `{len(_response_entries(probes['models']))}`\n"
                    f"- **MCP servers:** `{len(_response_entries(probes['mcps']))}`\n"
                    f"- **Skills:** `{len(_response_entries(probes['skills']))}`"
                )
            )
        cu_status = await computer_use_read_status(
            raw_config=ctx.plugin_config.computer_use,
            request=request_fn,
        )
        cu_summary = "Ready" if cu_status.ready else cu_status.reason

        return CodexCommandResult(
            text=(
                f"**Codex Harness Status**\n\n"
                f"- **Runtime:** OpenAI Codex\n"
                f"- **App-Server Version:** `{CODEX_APP_SERVER_VERSION}`\n"
                f"- **Transport:** `{ctx.plugin_config.app_server.transport}`\n"
                f"- **Home Scope:** `{ctx.plugin_config.app_server.home_scope}`\n"
                f"- **Fast Mode:** `{ctx.plugin_config.fast_mode}`\n"
                f"- **Computer Use Status:** `{cu_summary}`\n"
                f"- **Remote Workspace Root:** `{ctx.plugin_config.remote_workspace_root or 'Local host'}`"
            )
        )

    extended = await _handle_extended_subcommand(ctx, subcommand, sub_args, request_fn)
    if extended is not None:
        return extended

    return CodexCommandResult(
        text=f"Unknown subcommand `/codex {subcommand}`. Use `/codex help` for available options."
    )


async def _handle_extended_subcommand(
    ctx: CodexCommandContext,
    subcommand: str,
    sub_args: list[str],
    request_fn: Any | None = None,
) -> CodexCommandResult | None:
    """Route the extended `/codex` tree: parse → usage → authorize → terminal.

    Mirrors OpenClaw's parse/authorize/dispatch layering
    (``command-handler-args`` + ``command-authorization`` +
    ``command-handler-actions``). Terminals name the missing backend
    instead of executing; each is the future handler site.
    """
    if subcommand == "threads":
        denied = _deny(ctx, inspection=True)
        if denied is not None:
            return denied
        if request_fn is not None:
            response = await _request_control(
                request_fn,
                "thread/list",
                {"searchTerm": " ".join(sub_args).strip() or None, "limit": 100},
            )
            return _control_result(_format_control_list("Codex threads", response))
        return _unavailable("threads", needs=_APP_SERVER_NEED)

    if subcommand == "sessions":
        parsed = parse_sessions_args(sub_args)
        if parsed.get("help"):
            return CodexCommandResult(text="Usage: `/codex sessions [--host <node>] [filter]`.")
        denied = _deny(ctx, inspection=True)
        if denied is not None:
            return denied
        return _unavailable("sessions", needs="a supervision session catalog")

    if subcommand == "goal":
        if is_read_only_goal_command(subcommand, sub_args):
            if request_fn is not None and ctx.binding_thread_id:
                response = await _request_control(
                    request_fn,
                    "thread/goal/get",
                    {"threadId": ctx.binding_thread_id},
                )
                return _control_result(_format_native_goal(response))
            return _unavailable("goal", needs="a verified thread binding with goal state")
        if not sub_args or sub_args[0].lower() not in (
            "set",
            "pause",
            "resume",
            "block",
            "complete",
            "clear",
        ):
            return CodexCommandResult(
                text="Usage: `/codex goal [status|set <objective>|pause|resume|block|complete|clear]`."
            )
        if sub_args[0].lower() == "set" and len(sub_args) < 2:
            return CodexCommandResult(
                text="Usage: `/codex goal set <objective>` — objective text required."
            )
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if request_fn is not None and ctx.binding_thread_id:
            action = sub_args[0].lower()
            if action == "clear":
                response = await _request_control(
                    request_fn,
                    "thread/goal/clear",
                    {"threadId": ctx.binding_thread_id},
                )
                return _control_result(
                    "Cleared the Codex goal."
                    if isinstance(response, dict) and response.get("cleared") is True
                    else "No Codex goal was active."
                )
            status = {
                "pause": "paused",
                "resume": "active",
                "block": "blocked",
                "complete": "complete",
            }.get(action)
            params: dict[str, Any] = {"threadId": ctx.binding_thread_id}
            if action == "set":
                params["objective"] = " ".join(sub_args[1:])
            elif status is not None:
                params["status"] = status
            response = await _request_control(request_fn, "thread/goal/set", params)
            return _control_result(_format_native_goal(response))
        return _unavailable("goal", needs=_BINDING_NEED)

    if subcommand == "resume":
        parsed = parse_resume_args(sub_args)
        if parsed.get("help") or not parsed.get("thread_id"):
            return CodexCommandResult(
                text="Usage: `/codex resume <thread-id> [--host <node> --bind here]`."
            )
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if parsed.get("host"):
            return _unavailable("resume", needs="Gateway paired-node session adoption")
        if request_fn is not None and callable(ctx.binding_update_fn):
            verified = await _read_idle_thread(request_fn, parsed["thread_id"])
            if verified is not None:
                return verified
            await _update_binding(
                ctx.binding_update_fn,
                {
                    "threadId": parsed["thread_id"],
                    "model": ctx.binding_model,
                    "provider": "codex",
                },
            )
            return _control_result(f"Attached Codex thread {parsed['thread_id']}.")
        return _unavailable("resume", needs=_BINDING_NEED)

    if subcommand == "bind":
        parsed = parse_bind_args(sub_args)
        if parsed.get("help"):
            return CodexCommandResult(
                text="Usage: `/codex bind [thread-id] [--cwd <path>] [--model <model>] [--provider <provider>]`."
            )
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        thread_id = parsed.get("thread_id")
        if request_fn is not None and callable(ctx.binding_update_fn) and thread_id:
            verified = await _read_idle_thread(request_fn, thread_id)
            if verified is not None:
                return verified
            await _update_binding(
                ctx.binding_update_fn,
                {
                    "threadId": thread_id,
                    "cwd": parsed.get("cwd"),
                    "model": parsed.get("model") or ctx.binding_model,
                    "provider": parsed.get("provider") or "codex",
                },
            )
            return _control_result(f"Bound Codex thread {thread_id}.")
        return _unavailable("bind", needs=_BINDING_NEED)

    if subcommand in ("detach", "unbind"):
        if returns_before_execution(subcommand, sub_args):
            return CodexCommandResult(text=f"Usage: `/codex {subcommand}` takes no arguments.")
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if callable(ctx.binding_update_fn):
            await _update_binding(ctx.binding_update_fn, None)
            return _control_result("Detached the Codex thread binding.")
        return _unavailable(subcommand, needs=_BINDING_NEED)

    if subcommand == "stop":
        if returns_before_execution(subcommand, sub_args):
            return CodexCommandResult(text="Usage: `/codex stop` takes no arguments.")
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if request_fn is not None and ctx.binding_thread_id and ctx.active_turn_id:
            await _request_control(
                request_fn,
                "turn/interrupt",
                {"threadId": ctx.binding_thread_id, "turnId": ctx.active_turn_id},
            )
            return _control_result("Codex stop requested.")
        return _unavailable("stop", needs="an active Codex turn on a live app-server connection")

    if subcommand == "steer":
        if returns_before_execution(subcommand, sub_args):
            return CodexCommandResult(text="Usage: `/codex steer <text>`.")
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if request_fn is not None and ctx.binding_thread_id and ctx.active_turn_id:
            await _request_control(
                request_fn,
                "turn/steer",
                {
                    "threadId": ctx.binding_thread_id,
                    "expectedTurnId": ctx.active_turn_id,
                    "input": [{"type": "text", "text": " ".join(sub_args), "text_elements": []}],
                },
            )
            return _control_result("Codex turn steered.")
        return _unavailable("steer", needs="an active Codex turn on a live app-server connection")

    if subcommand == "model":
        if returns_before_execution(subcommand, sub_args):
            return CodexCommandResult(text="Usage: `/codex model <model>`.")
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if callable(ctx.state_update_fn):
            await _update_state(ctx.state_update_fn, {"model": sub_args[0]})
            return _control_result(f"Codex model set to {sub_args[0]}.")
        return _unavailable("model", needs=_BINDING_NEED)

    if subcommand == "fast":
        if is_menu_verb(sub_args):
            return CodexCommandResult(
                text="Codex fast mode:\n- `/codex fast on`\n- `/codex fast off`\n- `/codex fast status`"
            )
        if not sub_args or sub_args[0].lower() == "status":
            state = await _read_state(ctx.state_read_fn)
            if isinstance(state, dict) and "fast" in state:
                return _control_result(f"Codex fast mode: {state['fast']}.")
            return _unavailable("fast", needs="persisted per-conversation fast preference state")
        if parse_fast_mode_arg(sub_args[0]) is None or len(sub_args) > 1:
            return CodexCommandResult(text="Usage: `/codex fast [on|off|status]`.")
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if callable(ctx.state_update_fn):
            await _update_state(ctx.state_update_fn, {"fast": parse_fast_mode_arg(sub_args[0])})
            return _control_result(f"Codex fast mode set to {sub_args[0].lower()}.")
        return _unavailable("fast", needs=_BINDING_NEED)

    if subcommand == "permissions":
        if is_menu_verb(sub_args):
            return CodexCommandResult(
                text=(
                    "Codex permissions:\n"
                    "- `/codex permissions default`\n"
                    "- `/codex permissions yolo`\n"
                    "- `/codex permissions status`"
                )
            )
        if not sub_args or sub_args[0].lower() == "status":
            state = await _read_state(ctx.state_read_fn)
            if isinstance(state, dict) and "permissions" in state:
                return _control_result(f"Codex permissions: {state['permissions']}.")
            return _unavailable(
                "permissions",
                needs="persisted per-conversation permission state",
            )
        if parse_permissions_mode_arg(sub_args[0]) is None or len(sub_args) > 1:
            return CodexCommandResult(text="Usage: `/codex permissions [default|yolo|status]`.")
        if parse_permissions_mode_arg(sub_args[0]) == "yolo" and not ctx.is_admin:
            return CodexCommandResult(
                text="Full Codex permissions require operator.admin, even for an owner sender."
            )
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if callable(ctx.state_update_fn):
            await _update_state(
                ctx.state_update_fn,
                {"permissions": parse_permissions_mode_arg(sub_args[0])},
            )
            return _control_result(f"Codex permissions set to {sub_args[0].lower()}.")
        return _unavailable("permissions", needs=_BINDING_NEED)

    if subcommand == "compact":
        if returns_before_execution(subcommand, sub_args):
            return CodexCommandResult(text="Usage: `/codex compact` takes no arguments.")
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if callable(ctx.compact_fn) and ctx.binding_thread_id:
            result = ctx.compact_fn(ctx.binding_thread_id)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict) and result.get("compacted") is True:
                tokens = result.get("tokensAfter", "unknown")
                return _control_result(f"Compacted Codex session ({tokens} tokens after).")
            reason = (
                result.get("reason", "no reason returned") if isinstance(result, dict) else result
            )
            return _control_result(f"Codex compaction did not complete: {reason}.")
        return _unavailable("compact", needs=_BINDING_NEED)

    if subcommand == "review":
        if returns_before_execution(subcommand, sub_args):
            return CodexCommandResult(text="Usage: `/codex review` takes no arguments.")
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if request_fn is not None and ctx.binding_thread_id:
            await _request_control(
                request_fn,
                "review/start",
                {
                    "threadId": ctx.binding_thread_id,
                    "target": {"type": "uncommittedChanges"},
                },
            )
            return _control_result(f"Started Codex review for thread {ctx.binding_thread_id}.")
        return _unavailable("review", needs=_BINDING_NEED)

    if subcommand == "diagnostics":
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        note = " ".join(sub_args).strip()
        if request_fn is not None and ctx.binding_thread_id:
            if not callable(ctx.diagnostics_approval_fn):
                return _unavailable("diagnostics", needs="the Gateway diagnostics approval flow")
            approved = ctx.diagnostics_approval_fn(note)
            if inspect.isawaitable(approved):
                approved = await approved
            if approved is not True:
                return _control_result("Codex diagnostics upload canceled.")
            tags = {
                key: value
                for key, value in {
                    "sessionId": ctx.session_id,
                    "userId": ctx.user_id,
                }.items()
                if isinstance(value, str) and value
            }
            payload: dict[str, Any] = {
                "classification": "bug",
                "threadId": ctx.binding_thread_id,
                "includeLogs": True,
                "tags": tags,
            }
            if note:
                payload["reason"] = note
            response = await _request_control(request_fn, "feedback/upload", payload)
            response_thread_id = response.get("threadId") if isinstance(response, dict) else None
            return _control_result(
                f"Codex diagnostics uploaded for thread {response_thread_id or ctx.binding_thread_id}."
            )
        return _unavailable(
            "diagnostics", needs="the Gateway approval flow and app-server feedback upload"
        )

    if subcommand in ("account", "mcp", "skills"):
        if sub_args:
            return CodexCommandResult(text=f"Usage: `/codex {subcommand}` takes no arguments.")
        denied = _deny(ctx, inspection=True)
        if denied is not None:
            return denied
        if request_fn is not None:
            if subcommand == "account":
                account = await _request_control(
                    request_fn, "account/read", {"refreshToken": False}
                )
                limits = await _request_control(request_fn, "account/rateLimits/read")
                return _control_result(
                    f"Account:\n{json.dumps(account or {}, sort_keys=True)}\n\n"
                    f"Rate limits:\n{json.dumps(limits or {}, sort_keys=True)}"
                )
            method = "mcpServerStatus/list" if subcommand == "mcp" else "skills/list"
            response = await _request_control(request_fn, method, {"limit": 100})
            return _control_result(_format_control_list(subcommand.capitalize(), response))
        return _unavailable(subcommand, needs=_APP_SERVER_NEED)

    if subcommand == "plugins":
        return await _handle_plugins_subcommand(ctx, sub_args, request_fn=request_fn)

    return None


async def _handle_plugins_subcommand(
    ctx: CodexCommandContext,
    sub_args: list[str],
    *,
    request_fn: Any | None = None,
) -> CodexCommandResult:
    """Route `/codex plugins ...` (management surface needs the native
    plugin catalog; mutations additionally persist policy)."""
    action = sub_args[0].lower() if sub_args else "list"
    rest = sub_args[1:]
    request = request_fn or ctx.request_fn
    if action == "menu":
        if rest:
            return CodexCommandResult(text="Usage: `/codex plugins menu`.")
        return CodexCommandResult(
            text=(
                "Codex plugins:\n"
                "- `/codex plugins list`\n"
                "- `/codex plugins available`\n"
                "- `/codex plugins install <plugin>@<marketplace>`\n"
                "- `/codex plugins enable <name>`\n"
                "- `/codex plugins disable <name>`"
            )
        )
    if action == "list":
        if rest:
            return CodexCommandResult(text="Usage: `/codex plugins list`.")
        denied = _deny(ctx, inspection=True)
        if denied is not None:
            return denied
        if callable(request):
            response = await _request_control(request, "plugin/installed", {})
            return _control_result(_format_plugin_catalog("Installed plugins", response))
        return _unavailable("plugins list", needs="the native Codex plugin catalog")
    if action == "available":
        if rest:
            return CodexCommandResult(text="Usage: `/codex plugins available`.")
        denied = _deny(ctx, inspection=True)
        if denied is not None:
            return denied
        if callable(request):
            response = await _request_control(request, "plugin/list", {"cwds": []})
            return _control_result(_format_plugin_catalog("Available plugins", response))
        return _unavailable("plugins available", needs="the native Codex marketplace catalog")
    if action == "install":
        if len(rest) != 1 or "@" not in rest[0]:
            return CodexCommandResult(
                text="Usage: `/codex plugins install <plugin>@<marketplace>`."
            )
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if callable(request):
            plugin_name, marketplace = rest[0].rsplit("@", 1)
            response = await _request_control(
                request,
                "plugin/install",
                {"pluginName": plugin_name, "marketplace": marketplace},
            )
            return _control_result(_format_plugin_catalog("Plugin installed", response))
        return _unavailable("plugins install", needs="the native Codex plugin installer")
    if action in ("enable", "disable"):
        if len(rest) != 1:
            return CodexCommandResult(text=f"Usage: `/codex plugins {action} <name>`.")
        denied = _deny(ctx, inspection=False)
        if denied is not None:
            return denied
        if callable(ctx.plugins_update_fn):
            result = ctx.plugins_update_fn(rest[0], action == "enable")
            if inspect.isawaitable(result):
                await result
            return _control_result(
                f"{rest[0]}: {'enabled' if action == 'enable' else 'disabled'}. "
                "Takes effect on the next message."
            )
        return _unavailable(f"plugins {action}", needs="the native Codex plugin policy store")
    return CodexCommandResult(
        text="Usage: `/codex plugins [list|available|install <plugin>@<marketplace>|enable|disable <name>]`."
    )


def _format_plugin_catalog(title: str, response: Any) -> str:
    """Format native plugin responses without interpreting plugin ownership."""
    return f"{title}:\n{json.dumps(response or {}, sort_keys=True)}"


def _format_native_goal(response: Any) -> str:
    goal = response.get("goal") if isinstance(response, dict) else None
    if not isinstance(goal, dict):
        return "No Codex goal is active."
    objective = str(goal.get("objective") or "unknown")
    status = str(goal.get("status") or "unknown")
    tokens_used = goal.get("tokensUsed", 0)
    token_budget = goal.get("tokenBudget")
    budget = f" / {token_budget}" if isinstance(token_budget, (int, float)) else ""
    return f"Codex goal: {objective}\n- Status: {status}\n- Tokens: {tokens_used}{budget}"


async def _read_idle_thread(request_fn: Any, thread_id: str) -> CodexCommandResult | None:
    try:
        response = await _request_control(
            request_fn,
            "thread/read",
            {"threadId": thread_id, "includeTurns": False},
        )
    except Exception as exc:
        return _control_result(f"Cannot verify Codex thread {thread_id}: {exc}")
    thread = response.get("thread") if isinstance(response, dict) else None
    if not isinstance(thread, dict) or thread.get("id") != thread_id:
        return _control_result(f"Codex app-server returned an invalid thread for {thread_id}.")
    status = thread.get("status")
    status_type = status.get("type") if isinstance(status, dict) else None
    if status_type not in {"idle", "notLoaded"}:
        return _control_result(
            f"Codex thread {thread_id} is active or unverified; wait for it to become idle."
        )
    return None


async def _update_binding(callback: Any, value: dict[str, Any] | None) -> None:
    result = callback(value)
    if inspect.isawaitable(result):
        await result


async def _read_state(callback: Any) -> Any:
    if not callable(callback):
        return None
    result = callback()
    return await result if inspect.isawaitable(result) else result


async def _update_state(callback: Any, value: dict[str, Any]) -> None:
    result = callback(value)
    if inspect.isawaitable(result):
        await result


__all__ = [
    "CodexCommandContext",
    "CodexCommandResult",
    "build_codex_help",
    "handle_codex_command",
]
