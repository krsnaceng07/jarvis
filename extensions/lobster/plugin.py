"""Lobster infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``lobster`` infra
extension.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin, PluginApi
from .src.jarvis_lobster.input_request import CommandInputResume
from .src.jarvis_lobster.runtime import run_pipeline


def build_lobster_tool() -> dict:
    """Build the lobster tool descriptor."""

    def handler(request: dict) -> dict:
        action = request.get("action", "run")
        cwd = request.get("cwd", ".")

        if action == "run":
            pipeline_str = request.get("pipeline")
            if not pipeline_str:
                return {"ok": False, "reason": "missing_pipeline"}

            try:
                # Use asyncio.run since we are in a sync handler wrapper for now.
                # In actual implementation, we might need an async handler.
                result = asyncio.run(
                    run_pipeline(
                        pipeline_str,
                        cwd=cwd,
                        env={},
                        resume_request=None,
                    )
                )
                if isinstance(result, dict) and result.get("type") == "approval_request":
                    return {
                        "ok": True,
                        "status": "requires_approval",
                        "requiresApproval": result,
                    }
                return {
                    "ok": True,
                    "status": "completed",
                    "output": result,
                }
            except Exception as e:
                return {"ok": False, "reason": str(e)}

        elif action == "resume":
            resume_token = request.get("resumeToken")
            approval_id = request.get("approvalId")
            approve = request.get("approve", False)
            pipeline_str = request.get("pipeline")

            if not resume_token or not approval_id or not pipeline_str:
                return {"ok": False, "reason": "missing_resume_args"}

            resume_req = CommandInputResume(
                resume_token=resume_token,
                approval_id=approval_id,
                approved=approve,
            )

            try:
                result = asyncio.run(
                    run_pipeline(
                        pipeline_str,
                        cwd=cwd,
                        env={},
                        resume_request=resume_req,
                    )
                )

                if isinstance(result, dict) and result.get("type") == "approval_request":
                    return {
                        "ok": True,
                        "status": "requires_approval",
                        "requiresApproval": result,
                    }
                return {
                    "ok": True,
                    "status": "completed",
                    "output": result,
                }
            except Exception as e:
                return {"ok": False, "reason": str(e)}

        return {"ok": False, "reason": f"unknown_action: {action}"}

    return {
        "name": "lobster",
        "description": "Run multi-step tools pipelines using Lobster.",
        "optional": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["run", "resume"],
                    "description": "Action to perform (run or resume)",
                },
                "pipeline": {
                    "type": "string",
                    "description": "Pipeline string or file path.",
                },
                "resumeToken": {
                    "type": "string",
                },
                "approvalId": {
                    "type": "string",
                },
                "approve": {
                    "type": "boolean",
                },
                "cwd": {
                    "type": "string",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        "handler": handler,
    }


@dataclass(frozen=True, slots=True)
class LobsterPlugin(Plugin):
    """Lobster infra descriptor."""

    id: str = "lobster"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Lobster workflow runtime."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook."""
        return None

    def register(self, api: PluginApi) -> None:
        """Register the lobster tool."""
        if hasattr(api, "register_tool"):
            api.register_tool(build_lobster_tool(), {"optional": True})


lobster_plugin = LobsterPlugin()
entry = lobster_plugin
