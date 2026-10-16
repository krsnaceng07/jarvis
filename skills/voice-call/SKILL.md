---
name: voice-call
description: "Initiate and manage outbound voice calls, multi-turn conversations, DTMF tones, and spoken messages via telephony providers."
metadata:
  {
    "openclaw":
      {
        "emoji": "📞",
        "requires": { "plugins": ["voice-call"] },
      },
  }
---

# Voice Call

Use the `voice_call` tool to place outbound phone calls, conduct multi-turn voice conversations with users, send DTMF tones, speak announcements, or check call status.

## When to Use

- Calling a user on their phone to deliver urgent notifications or voice messages
- Interactive voice response (IVR) or multi-turn spoken dialogue with a telephone caller
- Transmitting touch tones (DTMF) to automated phone systems / PIN prompts
- Checking the live status or ending an ongoing phone call

## Agent Tool: `voice_call`

### Actions and Arguments

| Action | Arguments | Description |
| --- | --- | --- |
| `initiate_call` | `message`, `to?`, `mode?`, `dtmfSequence?` | Initiate a new phone call. `to` falls back to configured `toNumber`. `dtmfSequence` is pre-connect digits (conversation mode only). |
| `continue_call` | `callId`, `message` | Continue a multi-turn conversation turn and block for user transcript response. |
| `speak_to_user` | `callId`, `message` | Speak a message into an active call without blocking. |
| `send_dtmf` | `callId`, `digits` | Transmit touch-tone digits into an active call. |
| `end_call` | `callId` | Terminate/hang up an active call session. |
| `get_status` | `callId?` | Inspect active call state or list all active calls when `callId` is omitted. |

## CLI Commands

```bash
openclaw voicecall call --to "+15555550123" --message "Hello from JARVIS"
openclaw voicecall start --to "+15555550123"   # alias for call with pre-connect dtmf
openclaw voicecall continue --call-id <id> --message "Any questions?"
openclaw voicecall speak --call-id <id> --message "One moment please"
openclaw voicecall dtmf --call-id <id> --digits "ww123456#"
openclaw voicecall end --call-id <id>
openclaw voicecall status --call-id <id>
openclaw voicecall tail
openclaw voicecall latency
openclaw voicecall expose --mode funnel
```
