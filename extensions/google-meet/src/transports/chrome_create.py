"""Browser-based Google Meet space creation."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from ..browser_manual_action_error import GoogleMeetBrowserManualActionError
from ..config import GoogleMeetConfig
from .chrome_browser_proxy import (
    as_browser_tabs,
    call_browser_proxy_on_node,
    read_browser_tab,
    resolve_chrome_node,
)
from .google_meet_urls import force_meet_english_ui

GOOGLE_MEET_NEW_URL = "https://meet.google.com/new"
GOOGLE_MEET_BROWSER_CREATE_TIMEOUT_MS = 60000
GOOGLE_MEET_BROWSER_STEP_TIMEOUT_MS = 10000
GOOGLE_MEET_BROWSER_NAVIGATION_RETRY_MS = 1000
GOOGLE_MEET_BROWSER_POLL_MS = 500

CREATE_MEET_FROM_BROWSER_SCRIPT = """async () => {
  const meetUrlPattern = /^https:\\/\\/meet\\.google\\.com\\/[a-z]{3}-[a-z]{4}-[a-z]{3}(?:$|[/?#])/i;
  const text = (node) => (node?.innerText || node?.textContent || "").trim();
  const current = () => location.href;
  const manualActionFor = (reason, message) => ({ reason, message });
  const notes = [];
  const findButton = (pattern) =>
    [...document.querySelectorAll("button")].find((button) => {
      const label = [
        button.getAttribute("aria-label"),
        button.getAttribute("data-tooltip"),
        text(button),
      ]
        .filter(Boolean)
        .join(" ");
      return pattern.test(label) && !button.disabled;
    });
  const clickButton = (pattern, note) => {
    const button = findButton(pattern);
    if (!button) {
      return false;
    }
    button.click();
    notes.push(note);
    return true;
  };
  if (!current().startsWith("https://meet.google.com/")) {
    return {
      manualAction: manualActionFor("google-login-required", "Sign in to Google in the JARVIS browser profile, then retry meeting creation."),
      browserUrl: current(),
      browserTitle: document.title,
      notes,
    };
  }
  const href = current();
  if (meetUrlPattern.test(href)) {
    return { meetingUri: href.split(/[?#]/)[0], browserUrl: href, browserTitle: document.title, notes };
  }
  const pageText = text(document.body);
  if (clickButton(/\\buse microphone\\b/i, "Accepted Meet microphone prompt with browser automation.")) {
    return { browserUrl: href, browserTitle: document.title, notes, retryAfterMs: 1000 };
  }
  if (
    clickButton(
      /continue without microphone/i,
      "Continued through Meet microphone prompt with browser automation.",
    )
  ) {
    return { browserUrl: href, browserTitle: document.title, notes, retryAfterMs: 1000 };
  }
  if (/do you want people to hear you in the meeting/i.test(pageText)) {
    return {
      manualAction: manualActionFor("meet-audio-choice-required", "Meet is showing the microphone choice. Click Use microphone in the JARVIS browser profile, then retry meeting creation."),
      browserUrl: href,
      browserTitle: document.title,
      notes,
    };
  }
  if (/allow.*(microphone|camera)|blocked.*(microphone|camera)|permission.*(microphone|camera)/i.test(pageText)) {
    return {
      manualAction: manualActionFor("meet-permission-required", "Allow microphone/camera permissions for Meet in the JARVIS browser profile, then retry meeting creation."),
      browserUrl: href,
      browserTitle: document.title,
      notes,
    };
  }
  if (/couldn't create|unable to create/i.test(pageText)) {
    return {
      manualAction: manualActionFor("browser-control-unavailable", "Resolve the Google Meet page prompt in the JARVIS browser profile, then retry meeting creation."),
      browserUrl: href,
      browserTitle: document.title,
      notes,
    };
  }
  if (location.hostname.toLowerCase() === "accounts.google.com" || /use your google account|to continue to google meet|choose an account|sign in to (join|continue)/i.test(pageText)) {
    return {
      manualAction: manualActionFor("google-login-required", "Sign in to Google in the JARVIS browser profile, then retry meeting creation."),
      browserUrl: href,
      browserTitle: document.title,
      notes,
    };
  }
  return {
    retryAfterMs: 500,
    browserUrl: current(),
    browserTitle: document.title,
    notes,
  };
}"""


def _is_browser_navigation_interruption(error: Any) -> bool:
    msg = str(error)
    return any(
        x in msg.lower() for x in ("execution context was destroyed", "navigation", "target closed")
    )


def _is_google_meet_create_tab(tab: dict[str, Any]) -> bool:
    url = str(tab.get("url") or "")
    if url.startswith("https://meet.google.com/new") or any(
        url.startswith(f"https://meet.google.com/{c}")
        for c in ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j")
    ):
        return True
    return (
        url.startswith("https://accounts.google.com/")
        and "sign in" in str(tab.get("title") or "").lower()
    )


async def create_meet_with_browser_proxy_on_node(params: dict[str, Any]) -> dict[str, Any]:
    runtime = params["runtime"]
    config: GoogleMeetConfig = params["config"]
    node_id = await resolve_chrome_node(
        {"runtime": runtime, "requestedNode": config.chrome_node.node}
    )
    timeout_ms = max(GOOGLE_MEET_BROWSER_CREATE_TIMEOUT_MS, config.chrome.join_timeout_ms)
    step_timeout_ms = min(timeout_ms, GOOGLE_MEET_BROWSER_STEP_TIMEOUT_MS)

    tabs = as_browser_tabs(
        await call_browser_proxy_on_node(
            {
                "runtime": runtime,
                "nodeId": node_id,
                "method": "GET",
                "path": "/tabs",
                "timeoutMs": step_timeout_ms,
            }
        )
    )
    tab = next((t for t in tabs if _is_google_meet_create_tab(t)), None)
    opened_by_plugin = False

    if tab and tab.get("targetId"):
        target_id = tab["targetId"]
        await call_browser_proxy_on_node(
            {
                "runtime": runtime,
                "nodeId": node_id,
                "method": "POST",
                "path": "/tabs/focus",
                "body": {"targetId": target_id},
                "timeoutMs": step_timeout_ms,
            }
        )
    else:
        created_tab = read_browser_tab(
            await call_browser_proxy_on_node(
                {
                    "runtime": runtime,
                    "nodeId": node_id,
                    "method": "POST",
                    "path": "/tabs/open",
                    "body": {"url": force_meet_english_ui(GOOGLE_MEET_NEW_URL)},
                    "timeoutMs": step_timeout_ms,
                }
            )
        )
        if not created_tab or not created_tab.get("targetId"):
            raise RuntimeError("Browser fallback opened Google Meet but did not return a targetId.")
        target_id = created_tab["targetId"]
        tab = created_tab
        opened_by_plugin = True

    notes: set[str] = set()
    deadline = time.time() + (timeout_ms / 1000.0)

    while time.time() <= deadline:
        try:
            evaluated = await call_browser_proxy_on_node(
                {
                    "runtime": runtime,
                    "nodeId": node_id,
                    "method": "POST",
                    "path": "/act",
                    "body": {
                        "kind": "evaluate",
                        "targetId": target_id,
                        "fn": CREATE_MEET_FROM_BROWSER_SCRIPT,
                    },
                    "timeoutMs": step_timeout_ms,
                }
            )
            result = evaluated.get("result", evaluated) if isinstance(evaluated, dict) else {}
            if isinstance(result.get("notes"), list):
                for n in result["notes"]:
                    notes.add(str(n))

            if result.get("meetingUri"):
                return {
                    "source": "browser",
                    "nodeId": node_id,
                    "targetId": target_id,
                    "openedByPlugin": opened_by_plugin,
                    "meetingUri": result["meetingUri"],
                    "browserUrl": result.get("browserUrl"),
                    "browserTitle": result.get("browserTitle"),
                    "notes": list(notes),
                }

            if result.get("manualAction"):
                raise GoogleMeetBrowserManualActionError(
                    {
                        "manualAction": result["manualAction"],
                        "browser": {
                            "nodeId": node_id,
                            "targetId": target_id,
                            "browserUrl": result.get("browserUrl"),
                            "browserTitle": result.get("browserTitle"),
                            "notes": list(notes),
                        },
                    }
                )

            retry_after_ms = result.get("retryAfterMs", GOOGLE_MEET_BROWSER_POLL_MS)
            await asyncio.sleep(retry_after_ms / 1000.0)
        except GoogleMeetBrowserManualActionError:
            raise
        except Exception as err:
            if not _is_browser_navigation_interruption(err):
                raise
            await asyncio.sleep(GOOGLE_MEET_BROWSER_NAVIGATION_RETRY_MS / 1000.0)

    raise RuntimeError(
        "Google Meet did not return a meeting URL from the browser create flow before timeout."
    )
