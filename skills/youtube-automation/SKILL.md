---
name: youtube-automation
description: "Control YouTube playback, search, video selection, channel subscription, multi-turn resubscription, tab isolation, and ad skipping using the Application Automation Runtime and Browser Tool with session tab affinity and closed-loop perception."
user-invocable: true
---

# YouTube Automation & Playback Control

Use this skill when controlling YouTube playback, searching videos, playing songs, pausing/resuming, adjusting volume, subscribing/unsubscribing to channels, closing YouTube tabs, or handling YouTube interstitials (ads, cookie consent).

## Operating Loop & Tab Affinity

1. **Perception-First & Display Check**:
   - Always verify whether YouTube is actually open on screen and what stage the page is at (`youtube_get_state()`).
   - If open, adopt the active YouTube tab across the browser context without opening duplicate tabs or destructive page reloads.
   - Ground the current channel name and subscription state (`is_subscribed`, `subscription_button_text`) before executing stateful actions.

2. **Search and Channel Workflows**:
   - For channel searches (e.g. *"Search <channel> and subscribe"*):
     - Search the channel via `youtube_search(query="<channel>")`.
     - Inspect the live results page stage (`channel_state.page_stage`).
     - Target the channel subscribe button on the channel card or channel page.

3. **Multi-Turn Resubscription & Toggle Continuity**:
   - When the user issues consecutive or toggling commands (*"unsubscribe gara"* followed by *"pheri subscribe gara"* or *"subscribe again"*):
     - **Clear Lingering Backdrops**: Unsubscribe dialogs leave `tp-yt-iron-overlay-backdrop` elements that block pointer events. Ensure backdrops are dismissed before clicking.
     - **Precondition Verification**: Check live DOM state. If the target state is already active, report `[Precondition Satisfied]` without duplicate clicks.
     - **Multi-Tier Execution**: Attempt native click $\to$ force click $\to$ JS click fallback.
     - **Closed-Loop Verification**: Poll DOM mutation for up to 3.5s until button text changes to `"Subscribed"` or `"Subscribe"`.
     - **Session Memory**: Track `last_channel`, `last_action`, and `is_subscribed` across turns to maintain conversational context.

4. **Granular YouTube Tools**:
   - `youtube_play(query, title)`: Search and start video playback with verified HTML5 state.
   - `youtube_pause()`: Pause active playback and verify `paused == true`.
   - `youtube_resume()`: Resume playback and verify `paused == false`.
   - `youtube_search(query)`: Search query and view results without autoplaying.
   - `youtube_subscribe()`: Subscribe/resubscribe to channel on current active YouTube tab with DOM mutation verification.
   - `youtube_unsubscribe()`: Unsubscribe from channel via multi-tier dropdown menu, dialog confirmation, and mutation verification.
   - `youtube_close()`: Close only the active YouTube browser tab. Keeps Chrome and other browser tabs open.
   - `youtube_skip_ad()`: Click skip ad button if active.
   - `youtube_set_volume(volume)`: Set volume to 0-100%.
   - `youtube_get_state()`: Inspect display presence, page stage, channel name, subscription status, and playback metrics.

5. **Tab Isolation & Closure Protocol**:
   - When the user asks to close YouTube (*"youtube banda gara"*, *"close youtube"*, *"youtube tab banda gara"*):
     - **NEVER** kill the browser process (`process(action='kill')` on `chrome`).
     - **NEVER** terminate the browser window.
     - Execute `youtube_close()`. This isolates and closes solely the YouTube tab and untracks it from `ActiveTabTracker`, leaving the Chrome browser and all other tabs completely intact.

6. **Contextual Anaphora & Controls**:
   - When the user says *"play it"*, *"pause"*, *"resume"*, *"stop"* without mentioning YouTube:
     - Ground the intent in the active YouTube session tab.
     - If video is paused, call `youtube_resume()`.
     - If video is playing, call `youtube_pause()`.
     - If on search results page, call `youtube_play(query="<top result>")`.

7. **Verify Playback & State Before Answering**:
   - Never claim an action succeeded based on a click event alone (violates mutation verification precedence).
   - Verify HTML5 `<video>` properties for playback, button aria-labels for subscription, and tab status for closure.

8. **Interstitials**:
   - If Google Cookie Consent (*"Before you continue to YouTube"*) or Premium promos appear, dismiss them automatically before executing interactions.
   - If an ad is playing, attempt to click *"Skip Ad"* once the skip countdown has elapsed.
