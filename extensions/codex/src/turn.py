"""Minimal Codex app-server turn pipeline.

The transport/client is injected by the host. This module owns the protocol
ordering: establish a native thread when needed, then submit one user turn.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from extensions.codex.src.app_server.config import CodexAppServerRuntimeOptions
from extensions.codex.src.plugin_inventory import read_codex_plugin_app_inventory
from extensions.codex.src.plugin_policy import (
    build_codex_plugin_apps_config,
    resolve_codex_plugins_policy,
)

CodexRequest = Callable[[str, dict[str, Any]], Any]


async def complete_codex_turn(
    messages: Sequence[Mapping[str, Any]],
    request: CodexRequest,
    *,
    thread_id: str | None = None,
    model: str | None = None,
    runtime_options: CodexAppServerRuntimeOptions | None = None,
) -> str:
    """Submit one native Codex turn and return its assistant text."""
    resolved_thread_id = thread_id.strip() if isinstance(thread_id, str) else ""
    if not resolved_thread_id:
        start_params = _thread_start_params(model, runtime_options)
        if runtime_options is not None and runtime_options.codex_plugins is not None:
            policy = resolve_codex_plugins_policy({"codexPlugins": runtime_options.codex_plugins})
            inventory = await read_codex_plugin_app_inventory(request, policy)
            start_params["config"] = {
                **(start_params.get("config") or {}),
                **build_codex_plugin_apps_config(policy, inventory=inventory),
            }
        started = await _call(request, "thread/start", start_params)
        resolved_thread_id = _read_thread_id(started)

    text = _latest_user_text(messages)
    if not text:
        raise ValueError("Codex completion requires at least one user message")
    response = await _call(
        request,
        "turn/start",
        {
            "threadId": resolved_thread_id,
            "input": [{"type": "text", "text": text}],
            **({"model": model} if model else {}),
        },
    )
    return _read_assistant_text(response)


def _thread_start_params(
    model: str | None,
    runtime_options: CodexAppServerRuntimeOptions | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"model": model} if model else {}
    if runtime_options is None:
        return params
    if runtime_options.default_workspace_dir:
        params["cwd"] = runtime_options.default_workspace_dir
    params.update(
        {
            "approvalPolicy": runtime_options.approval_policy,
            "approvalsReviewer": runtime_options.approvals_reviewer,
        }
    )
    if runtime_options.network_proxy is not None:
        config = dict(runtime_options.network_proxy["configPatch"])
    else:
        config = {}
        params["sandbox"] = runtime_options.sandbox
    if runtime_options.codex_plugins is not None:
        plugin_policy = resolve_codex_plugins_policy(
            {"codexPlugins": runtime_options.codex_plugins}
        )
        config.update(build_codex_plugin_apps_config(plugin_policy))
    if config:
        params["config"] = config
    if runtime_options.service_tier:
        params["serviceTier"] = runtime_options.service_tier
    return params


async def _call(request: CodexRequest, method: str, params: dict[str, Any]) -> Any:
    result = request(method, params)
    return await result if inspect.isawaitable(result) else result


def _latest_user_text(messages: Sequence[Mapping[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text = "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ).strip()
            if text:
                return text
    return ""


def _read_thread_id(response: Any) -> str:
    thread = response.get("thread") if isinstance(response, dict) else None
    thread_id = thread.get("id") if isinstance(thread, dict) else None
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ValueError("Codex app-server thread/start returned no thread id")
    return thread_id.strip()


def _read_assistant_text(response: Any) -> str:
    if isinstance(response, str) and response.strip():
        return response.strip()
    if isinstance(response, dict):
        for key in ("text", "content", "message"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in ("result", "turn"):
            nested = response.get(key)
            if nested is not None:
                try:
                    return _read_assistant_text(nested)
                except ValueError:
                    pass
    raise ValueError("Codex app-server turn/start returned no assistant text")


__all__ = ["complete_codex_turn"]
