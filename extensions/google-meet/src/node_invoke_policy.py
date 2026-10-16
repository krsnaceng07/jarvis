"""Node invoke policy for Google Meet on paired nodes."""

from __future__ import annotations

from typing import Any
from .config import GoogleMeetConfig
from .transports.google_meet_platform_adapter import GOOGLE_MEET_PLATFORM_ADAPTER
from .transports.google_meet_platform_constants import GOOGLE_MEET_NODE_COMMAND

GOOGLE_MEET_CHROME_NODE_COMMAND = GOOGLE_MEET_NODE_COMMAND
START_MODES = {"agent", "bidi", "realtime", "transcribe"}


class GoogleMeetChromeNodeInvokePolicy:
    def __init__(self, config: GoogleMeetConfig | None = None) -> None:
        self.config = config or GoogleMeetConfig()
        self.command_name = GOOGLE_MEET_CHROME_NODE_COMMAND
        self.denied_code = "GOOGLE_MEET_NODE_POLICY_DENIED"

    def is_allowed(self, ctx_or_params: dict[str, Any]) -> bool:
        if not isinstance(ctx_or_params, dict):
            return False
        params = ctx_or_params.get("params") if "params" in ctx_or_params else ctx_or_params
        if not isinstance(params, dict):
            return False
        res = self.handle({"params": params})
        return bool(res.get("ok"))

    def evaluate(self, call: Any) -> dict[str, Any]:
        if isinstance(call, dict):
            return self.handle(call)
        return {"ok": False, "code": self.denied_code, "message": "Invalid call context"}

    def handle(self, ctx: dict[str, Any]) -> dict[str, Any]:
        params = ctx.get("params")
        if not isinstance(params, dict):
            return {
                "ok": False,
                "code": self.denied_code,
                "message": f"{self.command_name} params must be an object",
            }

        action = str(params.get("action", "")).strip()
        if not action:
            return {
                "ok": False,
                "code": self.denied_code,
                "message": f"{self.command_name} requires action",
            }

        if action in ("query_tabs", "create_room", "focus_tab", "setup"):
            return {"ok": True, "params": params}

        if action == "start":
            url_raw = params.get("url")
            if not isinstance(url_raw, str) or not url_raw.strip():
                return {
                    "ok": False,
                    "code": self.denied_code,
                    "message": f"{self.command_name} start requires url",
                }
            try:
                normalized_url = GOOGLE_MEET_PLATFORM_ADAPTER.urls.validate_and_normalize(url_raw)
            except Exception as err:
                return {
                    "ok": False,
                    "code": self.denied_code,
                    "message": str(err),
                }

            mode = str(params.get("mode", "")).strip()
            if mode and mode not in START_MODES:
                return {
                    "ok": False,
                    "code": self.denied_code,
                    "message": f"{self.command_name} start mode is unsupported: {mode}",
                }

            start_params: dict[str, Any] = {
                "action": "start",
                "url": normalized_url,
                "launch": False if params.get("launch") is False else self.config.chrome.launch,
                "browserProfile": self.config.chrome.browser_profile,
                "joinTimeoutMs": self.config.chrome.join_timeout_ms,
            }
            if mode:
                start_params["mode"] = mode
            return {"ok": True, "params": start_params}

        if action in ("stop", "pullAudio", "pushAudio"):
            bridge_id = str(params.get("bridgeId", "")).strip()
            if not bridge_id:
                return {
                    "ok": False,
                    "code": self.denied_code,
                    "message": f"{self.command_name} {action} requires bridgeId",
                }
            return {"ok": True, "params": params}

        if action == "stopByUrl":
            url_raw = params.get("url")
            if not isinstance(url_raw, str) or not url_raw.strip():
                return {
                    "ok": False,
                    "code": self.denied_code,
                    "message": f"{self.command_name} stopByUrl requires url",
                }
            try:
                normalized_url = GOOGLE_MEET_PLATFORM_ADAPTER.urls.validate_and_normalize(url_raw)
            except Exception as err:
                return {
                    "ok": False,
                    "code": self.denied_code,
                    "message": str(err),
                }
            return {
                "ok": True,
                "params": {"action": "stopByUrl", "url": normalized_url},
            }

        return {
            "ok": False,
            "code": self.denied_code,
            "message": f"{self.command_name} action is unsupported: {action}",
        }


def create_google_meet_chrome_node_invoke_policy(
    config: GoogleMeetConfig | None = None,
) -> GoogleMeetChromeNodeInvokePolicy:
    return GoogleMeetChromeNodeInvokePolicy(config)
