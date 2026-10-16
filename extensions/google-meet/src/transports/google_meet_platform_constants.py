"""Google Meet transport constants."""

from __future__ import annotations

GOOGLE_MEET_NODE_COMMAND = "googlemeet.chrome"

GOOGLE_MEET_BROWSER_NODE_ADAPTER = {
    "displayName": "Google Meet",
    "nodeCommandName": GOOGLE_MEET_NODE_COMMAND,
    "nodeConfigPath": "plugins.entries.google-meet.config.chromeNode.node",
}
