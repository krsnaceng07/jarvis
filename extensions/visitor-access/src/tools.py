"""Visitor access agent tools definitions."""

from __future__ import annotations

from typing import Any

from .runtime import visitor_runtime_store


def create_visitor_tools(context: Any = None) -> list[dict[str, Any]]:
    return [
        {
            "name": "visitor_invite",
            "label": "Invite visitor",
            "description": "Grant or renew visitor access to Cloudflare Access application. Provide email or GitHub login; private GitHub emails require explicit email. Grants expire after configured duration (14 days default).",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "Verified email on the visitor's account.",
                    },
                    "github": {"type": "string", "description": "GitHub login, without @."},
                    "days": {"type": "integer", "description": "Grant duration in days."},
                    "forever": {
                        "type": "boolean",
                        "description": "Explicitly grant access without expiry.",
                    },
                },
            },
            "execute": _execute_invite,
        },
        {
            "name": "visitor_revoke",
            "label": "Revoke visitor",
            "description": "Remove visitor access by email or GitHub login. GitHub login removes all recorded grants for that login.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Visitor email."},
                    "github": {"type": "string", "description": "GitHub username."},
                },
            },
            "execute": _execute_revoke,
        },
        {
            "name": "visitor_list",
            "label": "List visitors",
            "description": "List recorded visitor grants, invitation and expiry dates, and drift from Cloudflare Access policy.",
            "parameters": {"type": "object", "properties": {}},
            "execute": _execute_list,
        },
    ]


async def _execute_invite(tool_id: str, raw_input: dict[str, Any]) -> dict[str, Any]:
    runtime = visitor_runtime_store.try_get_runtime()
    if not runtime:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Start the Gateway with visitor-access enabled before managing visitors.",
                }
            ],
            "isError": True,
        }
    try:
        msg = await runtime.service.invite(raw_input)
        return {"content": [{"type": "text", "text": msg}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": runtime.error_text(e)}], "isError": True}


async def _execute_revoke(tool_id: str, raw_input: dict[str, Any]) -> dict[str, Any]:
    runtime = visitor_runtime_store.try_get_runtime()
    if not runtime:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Start the Gateway with visitor-access enabled before managing visitors.",
                }
            ],
            "isError": True,
        }
    try:
        msg = await runtime.service.revoke(raw_input)
        return {"content": [{"type": "text", "text": msg}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": runtime.error_text(e)}], "isError": True}


async def _execute_list(tool_id: str, raw_input: dict[str, Any]) -> dict[str, Any]:
    runtime = visitor_runtime_store.try_get_runtime()
    if not runtime:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Start the Gateway with visitor-access enabled before managing visitors.",
                }
            ],
            "isError": True,
        }
    try:
        msg = await runtime.service.list()
        return {"content": [{"type": "text", "text": msg}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": runtime.error_text(e)}], "isError": True}
