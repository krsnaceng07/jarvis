---
name: zoom-meetings
description: "Join Zoom meetings as a guest through the Zoom Web App, manage participation modes, send spoken messages, and inspect captions."
metadata:
  {
    "openclaw":
      {
        "emoji": "📹",
        "requires": { "plugins": ["zoom-meetings"] },
      },
  }
---

# Zoom Meetings

Use the `zoom_meetings` tool to join Zoom meetings (`zoom.us/j/...` and account subdomains) as a guest via the Zoom Web Client in the browser.

## When to Use

- "Join this Zoom meeting: https://zoom.us/j/123456789"
- "Leave the Zoom meeting"
- "Check Zoom meeting status"
- "Read live captions / transcript from Zoom"
- "Say something in the Zoom meeting"

## Agent Tool: `zoom_meetings`

### Actions and Arguments

| Action | Arguments | Description |
| --- | --- | --- |
| `join` | `url`, `name?`, `passcode?`, `mode?` | Join a Zoom meeting as guest via the Web Client. |
| `leave` | `sessionId?` | Leave the active Zoom meeting. |
| `status` | `sessionId?` | Inspect current session status, duration, and manual action states. |
| `transcript` | `sessionId?` | Retrieve live closed captions and transcript lines. |
| `speak` | `sessionId?`, `message` | Speak a message into the meeting audio bridge. |

## CLI Commands

```bash
openclaw zoommeetings join "https://zoom.us/j/123456789" --name "JARVIS" --mode "agent"
openclaw zoommeetings status
openclaw zoommeetings transcript
openclaw zoommeetings speak --message "Hello everyone"
openclaw zoommeetings leave
openclaw zoommeetings setup
openclaw zoommeetings doctor
```

## Handling Zoom Policy & Manual Actions

When Zoom presents security challenges (authentication, email verification, passcode, CAPTCHA, waiting room, or browser device permissions), the plugin returns `manualAction: true` with `manualActionReason`. Complete the required prompt in the Chrome profile, then resume status or speech.
