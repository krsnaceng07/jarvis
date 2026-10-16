"""Model-agnostic strategy selection for human-like computer control.

The strategy is deliberately separate from the model/tool implementation:
any provider can ask for a high-level control task, while JARVIS chooses the
most faithful execution path available for the current target.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ControlChannel(str, Enum):
    """Ordered computer-control channels from safest/highest fidelity to fallback."""

    APP_ADAPTER = "app_adapter"
    BROWSER_DOM = "browser_dom"
    ACCESSIBILITY = "accessibility"
    HUMAN_INPUT = "human_input"


class ControlRisk(str, Enum):
    READ_ONLY = "read_only"
    LOCAL_MUTATION = "local_mutation"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"


@dataclass(frozen=True, slots=True)
class ControlPlan:
    channel: ControlChannel
    action: str
    reason: str
    risk: ControlRisk = ControlRisk.LOCAL_MUTATION
    params: dict[str, Any] = field(default_factory=dict)
    requires_visual_verification: bool = True


_BROWSER_APPS = frozenset({"browser", "chrome", "edge", "chromium", "web", "youtube"})
_APP_ADAPTER_ACTIONS = frozenset(
    {
        "whatsapp_send",
        "whatsapp_search",
        "whatsapp_call",
        "focus_app",
        "calculate",
        "vscode_action",
        "office_action",
        "explorer_action",
        "continuity_resolve",
    }
)
_HUMAN_INPUT_ACTIONS = frozenset(
    {
        "click",
        "double_click",
        "right_click",
        "type",
        "press_key",
        "hotkey",
        "scroll",
        "drag",
        "wait",
        "screenshot",
    }
)
_BROWSER_DOM_ACTIONS = frozenset(
    {
        "open",
        "navigate",
        "snapshot",
        "text",
        "click",
        "type",
        "fill",
        "press",
        "hover",
        "scrollintoview",
        "wait",
        "evaluate",
    }
)
_BROWSER_KIND_ALIASES = {
    "clickcoords": "clickCoords",
    "scrollintoview": "scrollIntoView",
}
_EXTERNAL_SIDE_EFFECT_MARKERS = frozenset(
    {
        "send",
        "submit",
        "buy",
        "purchase",
        "delete",
        "remove",
        "post",
        "publish",
        "call",
        "message",
    }
)


def build_control_plan(raw_args: dict[str, Any]) -> ControlPlan:
    """Choose the best control channel for a high-level desktop/browser request."""

    args = dict(raw_args or {})
    action = _normalize_action(args)
    target_app = str(args.get("app_name") or args.get("application") or args.get("app") or "").lower()
    target_url = str(args.get("url") or args.get("targetUrl") or args.get("target_url") or "").strip()
    command_text = str(args.get("command") or args.get("utterance") or args.get("text") or "").lower()

    if action in _APP_ADAPTER_ACTIONS:
        return ControlPlan(
            channel=ControlChannel.APP_ADAPTER,
            action=action,
            reason="A dedicated application adapter owns this task and can verify the effect.",
            risk=_risk_for(action, command_text),
            params=args,
        )

    if _is_browser_target(target_app, target_url, command_text):
        browser_action = _browser_action_for(action, args)
        return ControlPlan(
            channel=ControlChannel.BROWSER_DOM,
            action=browser_action,
            reason="Browser DOM automation is more precise than screen coordinates for Chrome/web tasks.",
            risk=_risk_for(browser_action, command_text),
            params=_browser_params(args, browser_action),
        )

    if action in _HUMAN_INPUT_ACTIONS:
        return ControlPlan(
            channel=ControlChannel.HUMAN_INPUT,
            action=action,
            reason="No higher-level adapter was selected; use foreground mouse/keyboard input.",
            risk=_risk_for(action, command_text),
            params=args,
        )

    return ControlPlan(
        channel=ControlChannel.ACCESSIBILITY,
        action=action or "inspect",
        reason="Prefer accessibility/UIA inspection before falling back to raw pointer coordinates.",
        risk=_risk_for(action, command_text),
        params=args,
    )


def format_control_plan_for_prompt() -> str:
    """Stable prompt block teaching every model the same control pipeline."""

    return (
        "[HUMAN-LIKE COMPUTER CONTROL PIPELINE]\n"
        "- Decide the control method yourself; do not ask the user whether to use mouse or keyboard.\n"
        "- Prefer dedicated app/API tools when they exist because they have the best verification.\n"
        "- For Chrome/web pages, prefer browser DOM actions: inspect/snapshot, locate element, act, then re-observe.\n"
        "- For native Windows apps, prefer app adapter or accessibility/UIA-style element actions when available.\n"
        "- Use foreground mouse/keyboard only when DOM/app/accessibility routes cannot perform the task faithfully.\n"
        "- After every mutating input, verify using DOM, app state, accessibility state, or the live visual stream.\n"
        "- If the screen/page is loading, waiting, blocked, or visually unchanged, wait/re-observe before the next step.\n"
    )


def _normalize_action(args: dict[str, Any]) -> str:
    action = str(args.get("action") or "").strip().lower()
    if action == "auto":
        return ""
    return action


def _is_browser_target(target_app: str, target_url: str, command_text: str) -> bool:
    if target_app in _BROWSER_APPS:
        return True
    if target_url.startswith(("http://", "https://")):
        return True
    return any(token in command_text for token in ("browser", "chrome", "website", "web page", "youtube"))


def _browser_action_for(action: str, args: dict[str, Any]) -> str:
    if action in _BROWSER_DOM_ACTIONS:
        return action
    if args.get("url") or args.get("targetUrl") or args.get("target_url"):
        return "open"
    if args.get("selector") or args.get("ref") or args.get("x") is not None:
        return "click"
    if args.get("text"):
        return "type"
    return "snapshot"


def _browser_params(args: dict[str, Any], action: str) -> dict[str, Any]:
    params = dict(args)
    params["action"] = action
    if "target_url" in params and "targetUrl" not in params:
        params["targetUrl"] = params["target_url"]
    if action in {"click", "type", "fill", "press", "hover", "scrollintoview", "wait", "evaluate"}:
        params.setdefault("kind", _BROWSER_KIND_ALIASES.get(action.lower(), action))
        params["action"] = "act"
    return params


def _risk_for(action: str, command_text: str) -> ControlRisk:
    combined = f"{action} {command_text}".lower()
    if not action or action in {"snapshot", "text", "screenshot", "wait", "inspect"}:
        return ControlRisk.READ_ONLY
    if any(marker in combined for marker in _EXTERNAL_SIDE_EFFECT_MARKERS):
        return ControlRisk.EXTERNAL_SIDE_EFFECT
    return ControlRisk.LOCAL_MUTATION
