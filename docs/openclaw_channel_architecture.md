# OpenClaw Channel Architecture

This document details the channel platform architecture of OpenClaw (2026.9.2), defining how messaging channels are declared, registered, configured, and operated.

---

## 1. Architectural Philosophy

In OpenClaw, the core agent brain is **completely channel-agnostic**:
- Core never directly imports or depends on any channel library (grammy, aileys, @discordjs, etc.).
- Channels are implemented entirely as bundled extensions under extensions/<channel_id>/.
- Every channel adheres to a strict contract provided by @openclaw/plugin-sdk/channel-core and @openclaw/plugin-sdk/channel-outbound.
- Multiple channels (Telegram, WhatsApp, Discord, Slack, etc.) run concurrently within the gateway.
- Each channel can have multiple configured accounts (multi-account routing).

---

## 2. Channel Plugin Contract (createChatChannelPlugin)

A chat channel plugin exports the result of createChatChannelPlugin(...), which defines 5 structured sub-contracts:

`	ypescript
export const telegramPlugin = createChatChannelPlugin({
  base: { ... },       // Identity, config, setup wizard, accounts, gateway start/stop
  pairing: { ... },    // Pairing code verification and authorization messages
  security: { ... },   // Dm/Group policies, allowlist matching, mention gating
  threading: { ... },  // Thread ID resolution, tool context mapping
  outbound: { ... },   // Outbound delivery adapter, draft streaming, typing
});
`

### 1. ase Sub-Contract
- id: Unique channel identifier (e.g. 	elegram, whatsapp, discord).
- 
ame & description: Human-readable metadata.
- config: Adapter to read, validate, and inspect channel configuration.
  - listAccountIds(cfg): Returns all configured account keys.
  - 
esolveAccount(cfg, accountId): Resolves credentials for a given account.
  - isEnabled(account, cfg): Checks if the account is active.
  - isConfigured(account, cfg): Checks if required tokens/credentials exist.
- gateway: Lifecycle supervisor handlers:
  - startAccount({ account, accountId, cfg, abortSignal, setStatus, log }): Boots the listener/provider.
  - stopAccount({ account, accountId, log }): Gracefully disconnects listeners.
  - logoutAccount({ accountId, cfg }): Clears credentials and stored sessions.

### 2. pairing Sub-Contract
- Enables secure direct-message authorization for unknown senders.
- idLabel: Channel-specific identity label (e.g. 	elegramUserId, whatsappJid).
- message: Template for the approval notification (PAIRING_APPROVED_MESSAGE).
- 
ormalizeAllowEntry: Strips platform prefixes (e.g. /^(telegram|tg):/i).
- 
otify({ cfg, id, message, accountId }): Sends pairing confirmation to user.

### 3. security Sub-Contract
- Implemented via channel security adapters (	elegramSecurityAdapter, whatsappSecurityAdapter).
- 
esolveDmPolicy(cfg, accountId): pairing | llowlist | open | closed.
- 
esolveGroupPolicy(cfg, accountId): open | llowlist | disabled.
- matchesAllowlist(entry, target): Verifies if sender matches configured allowed IDs.
- 
esolveGroupRequireMention(cfg, accountId): Whether the bot must be tagged to respond.

### 4. 	hreading Sub-Contract
- Resolves conversation sub-threads and forum topics.
- 
esolveAutoThreadId({ to, toolContext }): Maps current tool context to target thread.
- matchesToolContextTarget({ target, toolContext }): Verifies target alignment.
- uildToolContext(...): Injects currentChannelId, currentMessagingTarget, and 	hreadId.

### 5. outbound Sub-Contract
- Declares delivery capabilities and outbound transmission mechanics.
- send(to, text, options): Sends message to channel recipient.
- sendMedia(to, media, options): Uploads and sends audio/images/documents.
- sendTyping(to, options): Displays typing/processing indicator.
- sendReaction(to, messageId, emoji, options): Emits status reactions.
- sendEdit(to, messageId, newText, options): In-place text mutation for streaming draft preview.

---

## 3. Channel Capabilities

Channels declare their transport capabilities via structured descriptor flags:

| Capability Flag | Description | Supported Platforms |
| :--- | :--- | :--- |
| draftPreview | Supports progressive editing of a message while streaming. | Telegram, Discord, Slack |
| previewFinalization | Method used to convert draft to final (inalEdit or 
ormalFallback). | Telegram, Discord |
| progressUpdates | Can show step-by-step progress bars or spinner states. | Telegram, Slack, Web |
| ctions | Supports inline clickable buttons and interactive callback responses. | Telegram, Discord, Slack |
| 
ichBlocks | Native rich cards (MarkdownV2, blocks, embeds). | Telegram, Slack, Teams |
| udioVoice | Can send and receive native voice notes / audio messages. | Telegram, WhatsApp, Discord |
| location | Supports structured geographical coordinate payloads. | Telegram, WhatsApp |
| pairing | Supports out-of-band DM pairing authorization. | Telegram, Signal, WhatsApp |

---

## 4. Normalized Session Routing

OpenClaw normalizes channel conversations into canonical, deterministic session keys:

`	ext
Format: <channel>:<accountId>:<peerId>[:topic:<threadId>]

Examples:
- Direct Message:      telegram:default:123456789
- Secondary Account:   telegram:bot_work:987654321
- Group Conversation:  telegram:default:-100123456789
- Forum Topic Thread:  telegram:default:-100123456789:topic:42
- WhatsApp DM:         whatsapp:default:15551234567@s.whatsapp.net
`

Session bindings (SessionBindingRecord) allow mapping dynamic subagents or isolated tasks to specific channel threads while keeping root conversations isolated.
