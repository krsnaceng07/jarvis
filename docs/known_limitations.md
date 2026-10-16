# YouTube & Browser Automation: Known Limitations

This document outlines the known boundaries, security limits, and operational limitations of the JARVIS Application Automation Runtime when controlling YouTube and interactive web applications.

---

## 1. Authentication & Security Boundaries

### 1.1 Multi-Factor & Google Account Login
- **Behavior**: If YouTube prompts for Google Sign-In, 2-Step Verification, device approval, or passkey prompts, JARVIS **does not** attempt to bypass or guess credentials.
- **Reporting**: Following OpenClaw parity, JARVIS treats auth dialogs as external blockers and reports the exact manual action required to the user.
- **Persistent Profile Alternative**: To avoid authentication prompts, configure `profile="user"` or use a managed profile with imported Chrome cookies (`action="importprofile"`).

### 1.2 CAPTCHA & Bot Detection
- High-frequency automated interactions may trigger Google bot-detection or reCAPTCHA challenges.
- When an anti-automation interstitial appears, the runtime flags the state as blocked rather than looping mutations.

---

## 2. Media & Playback Limitations

### 2.1 DRM-Protected Streams
- Certain premium, paid rental, or Widevine-protected video streams restrict raw screen canvas capture.
- While playback control (play, pause, seek, volume) works identically via HTML5 media APIs, raw screenshot pixels of the video player viewport may be blanked out by the operating system / Chromium graphics compositor.

### 2.2 Unskippable Advertisements
- YouTube occasionally serves 15–30 second unskippable advertisements.
- The `skip_ad` handler detects when an ad is active. If no skip button is rendered by YouTube, it returns status `"Ad is playing (skip not yet available)"` rather than timing out or clicking false controls.

### 2.3 Network Buffering Latency
- On high-latency or bandwidth-constrained connections, video streams may take several seconds to buffer initial segments.
- The playback verifier polls `readyState`. If the video element is unpaused but has not yet received enough data (`readyState < 3`), it returns `effect: "unverifiable"` instead of falsely declaring playback failed.

---

## 3. Third-Party Embedded Players

- The `YouTubeAdapter` is optimized for `youtube.com`, `m.youtube.com`, and `youtu.be`.
- YouTube video players embedded inside third-party websites via `<iframe>` tags may run inside cross-origin sandboxes. In such cases, generic browser actions (`browser.act`) with CSS selectors must be used rather than the dedicated YouTube adapter.
