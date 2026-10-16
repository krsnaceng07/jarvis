"""Node host command handler for Google Meet on paired nodes."""

from __future__ import annotations

import json
import re
import urllib.parse

from .transports.google_meet_platform_adapter import GOOGLE_MEET_PLATFORM_ADAPTER


def normalize_meet_key(value: str | None) -> str | None:
    if not value:
        return None
    try:
        url = urllib.parse.urlparse(value)
        if (url.hostname or "").lower() != "meet.google.com":
            return value
        match = re.match(r"^/([a-z]{3}-[a-z]{4}-[a-z]{3})(?:$|[/?#])", url.path, re.IGNORECASE)
        return match.group(1).lower() if match else value
    except Exception:
        return value


async def handle_google_meet_node_host_command(params_json: str | None = None) -> str:
    params = json.loads(params_json) if params_json else {}
    action = params.get("action", "")

    if action == "setup":
        return json.dumps(
            {
                "ok": True,
                "action": "setup",
                "audioBackend": params.get("audioBackend", "auto"),
                "audioFormat": params.get("audioFormat", "pcm16-24khz"),
                "audioBufferBytes": params.get("audioBufferBytes", 4096),
            }
        )

    if action == "start":
        url = GOOGLE_MEET_PLATFORM_ADAPTER.urls.validate_and_normalize(params.get("url", ""))
        bridge_id = f"meet_node_{normalize_meet_key(url) or 'bridge'}"
        return json.dumps(
            {
                "ok": True,
                "action": "start",
                "launched": False,
                "bridgeId": bridge_id,
                "audioBackend": params.get("audioBackend", "auto"),
                "audioBridge": {
                    "type": "node-command-pair",
                    "outputGeneration": True,
                },
            }
        )

    if action in ("stop", "stopByUrl"):
        return json.dumps({"ok": True, "action": action, "stopped": True})

    return json.dumps({"ok": True, "action": action})
