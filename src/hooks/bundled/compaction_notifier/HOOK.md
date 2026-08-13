---
name: compaction-notifier
description: Notifies the operator when a context compaction event occurs.
events: ["session:compact:after", "session:compact:before"]
always: false
emoji: "🗜️"
hookKey: compaction-notifier
---

# Compaction Notifier Hook

Fires before and after context compaction. Appends a brief notification to
the event's messages list so the channel session runner can surface it to
the operator. Mirrors OpenClaw's `bundled/compaction-notifier` hook.
