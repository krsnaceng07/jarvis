---
name: whatsapp
description: "Send messages, search contacts, or manage chats on WhatsApp Desktop with verified delivery."
metadata:
  {
    "openclaw":
      {
        "emoji": "💬",
        "requires": { "apps": ["WhatsApp"] },
      },
  }
---

# WhatsApp Automation

Use WhatsApp automation tools when the user asks to send a message, open a chat, search contacts, or check messages on WhatsApp.

## Core Capabilities
- `whatsapp_send_message(recipient, message)`: Sends exact dictated message with foreground verification and delivery confirmation.
- `whatsapp_open()`: Restores, unminimizes, and brings WhatsApp Desktop to the active foreground.
- `whatsapp_search_contact(query)`: Searches contacts and returns matches.
- `whatsapp_open_chat(recipient)`: Opens conversation with recipient and asserts chat header.
- `whatsapp_get_state()`: Checks whether WhatsApp is running, minimized, or active.

## Safety & Grounding Directives
1. **Zero Blind Typing**: WhatsApp must be unminimized and verified in the active foreground before typing. If WhatsApp cannot be focused, abort immediately to protect other open windows.
2. **Exact Message Preservation**: Send the exact text dictated by the user. Do not reword, summarize, translate, or add unsolicited emojis.
3. **Recipient Verification**: If the contact name is ambiguous or matches multiple people, ask the user to clarify before sending.
4. **Single-Shot Turn Fulfillment**: When `whatsapp_send_message` succeeds, the task is COMPLETE. Do not repeat the call. Confirm to the user via voice that the message has been sent.
