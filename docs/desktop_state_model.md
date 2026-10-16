# Desktop State Model & Checkpoint Persistence

## 1. Active Desktop Context (`ActiveDesktopContext`)
```json
{
  "active_application": "whatsapp",
  "active_window": {
    "hwnd": 66708,
    "pid": 5928,
    "title": "WhatsApp",
    "rect": {"left": 100, "top": 50, "right": 1100, "bottom": 850},
    "is_minimized": false,
    "is_responsive": true
  },
  "current_task": "send_message",
  "workflow_stage": "message_typed",
  "active_recipient": "John",
  "pending_message": "I will arrive at 5 PM",
  "last_verified_action": "message_typed_and_verified",
  "next_expected_action": "send_message",
  "can_continue": true
}
```

## 2. Checkpoint Persistence (`CheckpointStore`)
Saves workflow stages so that interruptions or multi-turn commands seamlessly continue from the verified stage rather than restarting.
