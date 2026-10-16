# YouTube Supported Automation Capabilities

This document provides a comprehensive reference of all YouTube automation capabilities supported by the JARVIS Application Automation Runtime.

---

## 1. High-Level Automation Capabilities

| Capability | Command / Action | Description | Supported Pronouns & Phrasings |
|---|---|---|---|
| **Search & Play** | `search_and_play` | Searches YouTube for query, waits for results, clicks first matching video, skips initial ads, and verifies playback. | *"Search Believer and play it"*, *"Play Queen on YouTube"* |
| **Search** | `search` | Enters query into search input, submits form, and updates state to `SEARCH_RESULTS`. | *"Search for Imagine Dragons"*, *"Find lofi hip hop on YouTube"* |
| **Play First Result** | `play_first_result` | Selects and clicks the first video card from the active search results. | *"Play it"*, *"Play the first video"*, *"Start video"* |
| **Play by Title** | `play_video_by_title` | Scans visible video result titles for keywords and selects matching card. | *"Play the official music video"*, *"Play live version"* |
| **Pause** | `pause` | Pauses video playback via HTML5 video API and player controls. | *"Pause"*, *"Pause it"*, *"Stop the music"*, *"Stop video"* |
| **Resume** | `resume` | Resumes playback from the current playback position. | *"Resume"*, *"Resume it"*, *"Continue playing"*, *"Play"* |
| **Toggle Play** | `toggle_play` | Toggles between play and pause depending on current playback state. | *"Toggle playback"*, *"Spacebar"* |
| **Skip Ad** | `skip_ad` | Detects pre-roll/mid-roll ad and clicks *"Skip Ad"* as soon as countdown completes. | *"Skip"*, *"Skip ad"*, *"Skip the ad"*, *"Skip this ad"* |
| **Volume Up** | `volume_up` | Increases player volume by specified step (default +10%). | *"Volume up"*, *"Louder"*, *"Turn it up"*, *"Sound up"* |
| **Volume Down** | `volume_down` | Decreases player volume by specified step (default -10%). | *"Volume down"*, *"Softer"*, *"Turn it down"*, *"Sound down"* |
| **Set Volume** | `set_volume` | Sets player volume to an exact percentage (0 to 100). | *"Set volume to 50%"*, *"Half volume"* |
| **Mute / Unmute** | `mute`, `unmute` | Toggles video player mute state without modifying system audio. | *"Mute"*, *"Mute it"*, *"Unmute"* |
| **Playback Status** | `status` | Queries real-time HTML5 video metrics (`paused`, `currentTime`, `duration`, `volume`, `title`). | *"What's playing?"*, *"Video status"* |

---

## 2. Tab Affinity & Session Continuity

1. **Semantic Labeling**:
   - YouTube tabs are automatically opened and tracked with `label="youtube"`.
   - Subsequent operations address `targetId="youtube"`, resolving directly to the active tab regardless of Chromium process ID changes.
2. **Non-Destructive Tab Reuse**:
   - If user says *"Open YouTube"* while a video is already playing or on search results, JARVIS brings the tab to the foreground without calling `goto("https://www.youtube.com")`.
   - Prevents accidental interruption of active playback or loss of search results.
3. **Contextual Pronoun Grounding**:
   - Commands containing anaphora (*"it"*, *"the song"*, *"this video"*) are resolved by `ContextualResolver`.
   - If the user is viewing search results, *"play it"* maps to `play_first_result`.
   - If the user is on a watch page and the video is paused, *"play it"* or *"resume"* maps to `resume`.

---

## 3. Playback Verification & Mutation Precedence

Following OpenClaw's mutation contract (`src/agents/tools/computer-tool-guidance.ts`):
$$\text{confirmed} > \text{unverifiable} > \text{suspected\_noop}$$

- **No Blind Retries**: A click on a video card or play button is not assumed successful until verified.
- **HTML5 Video Inspection**: The verifier samples the `<video>` element's `currentTime` and `paused` properties across an observation window:
  - If `paused == false` and `currentTime` advances: `effect: "confirmed"`.
  - If video is buffering (`readyState >= 3`): `effect: "confirmed"`.
  - If video remains paused: `effect: "suspected_noop"`.

---

## 4. Automatic Interstitial Recovery

JARVIS automatically intercepts and dismisses blocking overlays:
- **Google Cookie Consent**: Dismisses *"Before you continue to YouTube"* dialogs (`Accept all` / `Agree`).
- **YouTube Premium Prompts**: Dismisses modal prompts offering trials (`No thanks` / `Dismiss`).
- **Video Advertisements**: Identifies ad module overlays and monitors for clickable skip buttons.
