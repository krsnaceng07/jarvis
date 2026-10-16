"""Teams Meetings DOM automation and in-page JavaScript generators."""

from __future__ import annotations

import json
from .teams_urls import normalize_teams_url_for_reuse
from .types import TEAMS_MEETINGS_TRANSCRIPT_MAX_LINES

TEAMS_MEETINGS_CAPTION_SETTLE_MS = 1000


def teams_status_script(
    allow_microphone: bool,
    auto_join: bool,
    guest_name: str,
    caption_session_id: str | None = None,
    capture_captions: bool = True,
    read_only: bool = False,
) -> str:
    allow_mic_json = json.dumps(allow_microphone)
    auto_join_json = json.dumps(auto_join)
    guest_name_json = json.dumps(guest_name)
    caption_session_id_json = json.dumps(caption_session_id)
    capture_captions_json = json.dumps(capture_captions)
    read_only_json = json.dumps(read_only)
    max_lines_json = json.dumps(TEAMS_MEETINGS_TRANSCRIPT_MAX_LINES)
    settle_ms_json = json.dumps(TEAMS_MEETINGS_CAPTION_SETTLE_MS)

    return f"""async () => {{
  const text = (node) => (node?.innerText || node?.textContent || "").trim();
  const manualActionFor = (reason, message) => ({{ reason, message }});
  const allowMicrophone = {allow_mic_json};
  const captionSessionId = {caption_session_id_json};
  const captureCaptions = {capture_captions_json};
  const readOnly = {read_only_json};
  const buttons = () => [...document.querySelectorAll('button, [role="button"]')];
  const buttonLabel = (button) =>
    [
      button.getAttribute("aria-label"),
      button.getAttribute("data-tooltip"),
      button.getAttribute("title"),
      button.getAttribute("data-tid"),
      text(button),
    ]
      .filter(Boolean)
      .join(" ");
  const buttonLabels = buttons().map(buttonLabel).filter(Boolean);
  const notes = [];
  let audioInputRouted;
  let audioInputDeviceLabel;
  let audioInputRouteError;
  let audioOutputRouted;
  let audioOutputDeviceLabel;
  let audioOutputRouteError;

  const findButton = (pattern) =>
    buttons().find((button) => {{
      const label = buttonLabel(button);
      return pattern.test(label) && !button.disabled;
    }});

  const audioDeviceFamily = (value) => {{
    const label = String(value || '');
    if (/\\b(BlackHole\\s+2ch|BlackHole\\s+2ch\\s+\\(Virtual\\))\\b/i.test(label)) return 'blackhole-2ch';
    if (/\\b(JARVIS Meeting Audio|OpenClaw Meeting Audio)\\b/i.test(label)) return 'jarvis-meeting-audio';
    return undefined;
  }};
  const isMeetingAudioDevice = (value) => Boolean(audioDeviceFamily(value));
  const deviceNodeLabel = (node) => [
    node?.getAttribute?.('aria-label'),
    node?.getAttribute?.('data-tooltip'),
    node?.getAttribute?.('title'),
    node?.label,
    node?.textContent,
    node?.innerText,
  ].filter(Boolean).join(' ').trim();

  const waitForUi = () => new Promise((resolve) => setTimeout(resolve, 100));

  // 1. Dismiss App interstitial / launcher prompt
  if (!readOnly) {{
    const continueBrowser = findButton(/continue on this browser|join on the web instead|use web app/i);
    if (continueBrowser) {{
      continueBrowser.click();
      notes.push("Dismissed Teams app interstitial (continued on web).");
      await waitForUi();
    }}
  }}

  // 2. Fill guest name in pre-join
  const nameInputs = [
    ...document.querySelectorAll('input[type="text"], input:not([type]), [data-tid="prejoin-display-name-input"]')
  ];
  const nameInput = nameInputs.find((el) =>
    /name|display name|your name/i.test(el.getAttribute('aria-label') || el.placeholder || el.getAttribute('data-tid') || '')
  );
  if (!readOnly && {auto_join_json} && nameInput && !nameInput.value) {{
    nameInput.focus();
    nameInput.value = {guest_name_json};
    nameInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
    nameInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
    notes.push("Entered guest name: " + {guest_name_json});
  }}

  const pageText = text(document.body).toLowerCase();
  const host = location.hostname.toLowerCase();
  const pageUrl = location.href;

  // 3. Turn Camera OFF before joining
  const camToggle = findButton(/toggle video|camera|turn (?:on|off) camera/i);
  if (!readOnly && camToggle) {{
    const isCamOn = /turn off camera|camera is on|video on/i.test(buttonLabel(camToggle)) ||
                    camToggle.getAttribute('aria-checked') === 'true' ||
                    camToggle.getAttribute('aria-pressed') === 'true';
    if (isCamOn) {{
      camToggle.click();
      notes.push("Turned camera off for guest join.");
      await waitForUi();
    }}
  }}

  // 4. Microphone toggle & Virtual Audio routing
  let micToggle = findButton(/toggle microphone|turn (?:on|off) microphone|mute|unmute/i);
  if (!readOnly && allowMicrophone && micToggle) {{
    const isMicMuted = /turn on microphone|unmute|microphone is muted/i.test(buttonLabel(micToggle)) ||
                       micToggle.getAttribute('aria-checked') === 'false' ||
                       micToggle.getAttribute('aria-pressed') === 'false';
    if (isMicMuted) {{
      micToggle.click();
      notes.push("Unmuted microphone for realtime join.");
      await waitForUi();
    }}
  }} else if (!readOnly && !allowMicrophone && micToggle) {{
    const isMicOn = /turn off microphone|mute|microphone is unmuted/i.test(buttonLabel(micToggle)) ||
                    micToggle.getAttribute('aria-checked') === 'true' ||
                    micToggle.getAttribute('aria-pressed') === 'true';
    if (isMicOn) {{
      micToggle.click();
      notes.push("Muted microphone for observe-only join.");
      await waitForUi();
    }}
  }}

  // 5. Click Join button if in pre-join
  const joinBtn = !readOnly && {auto_join_json}
    ? findButton(/\\bjoin now\\b|\\bjoin meeting\\b|data-tid="prejoin-join-button"/i)
    : null;
  if (joinBtn) {{
    joinBtn.click();
    notes.push("Clicked Join now button.");
  }}

  // 6. In-call detection (Hang up / Leave button visible)
  const inCall = buttons().some((button) =>
    /\\b(hang up|leave|leave call|leave meeting)\\b|data-tid="hangup-button"/i.test(buttonLabel(button))
  );

  // 7. Route virtual audio if in-call and allowMicrophone
  if (inCall && allowMicrophone && typeof navigator !== 'undefined' && navigator.mediaDevices?.enumerateDevices) {{
    try {{
      const devices = await navigator.mediaDevices.enumerateDevices();
      const input = devices.find((d) => d.kind === 'audioinput' && isMeetingAudioDevice(d.label));
      if (input) {{
        audioInputRouted = true;
        audioInputDeviceLabel = input.label;
      }}
      const output = devices.find((d) => d.kind === 'audiooutput' && isMeetingAudioDevice(d.label));
      if (output) {{
        audioOutputRouted = true;
        audioOutputDeviceLabel = output.label;
        const mediaElements = [...document.querySelectorAll('audio, video')].filter((el) => typeof el.setSinkId === 'function');
        for (const el of mediaElements) {{
          if (el.sinkId !== output.deviceId && !readOnly) {{
            await el.setSinkId(output.deviceId);
          }}
        }}
      }}
    }} catch (err) {{
      audioInputRouteError = err?.message || String(err);
    }}
  }}

  // 8. Live Captions Scraping & State
  let captioning = false;
  let captionsEnabledAttempted = false;
  let transcriptLines = 0;
  let lastCaptionAt;
  let lastCaptionSpeaker;
  let lastCaptionText;
  let recentTranscript = [];

  const captionSelector = '[data-tid="closed-captions-renderer"], [role="region"][aria-label*="caption" i], [aria-live="polite"][role="region"], div[aria-live="polite"]';
  const captionState = (() => {{
    if (!captureCaptions) return undefined;
    const w = window;
    if (!inCall && !w.__openclawTeamsCaptions) return undefined;
    if (!w.__openclawTeamsCaptions || (captionSessionId && w.__openclawTeamsCaptions.sessionId !== captionSessionId)) {{
      if (w.__openclawTeamsCaptions?.settleTimer !== undefined) {{
        clearTimeout(w.__openclawTeamsCaptions.settleTimer);
      }}
      w.__openclawTeamsCaptions?.observer?.disconnect?.();
      w.__openclawTeamsCaptions = {{
        sessionId: captionSessionId,
        epoch: crypto.randomUUID(),
        enabledAttempted: false,
        observerInstalled: false,
        observer: undefined,
        droppedLines: 0,
        lines: [],
        settleTimer: undefined,
        visible: []
      }};
    }}
    return w.__openclawTeamsCaptions;
  }})();

  const normalizeCaption = (speaker, captionText) => {{
    if (!captionState) return undefined;
    const clean = String(captionText || "").replace(/\\s+/g, " ").trim();
    const cleanSpeaker = String(speaker || "").replace(/\\s+/g, " ").trim();
    if (!clean || clean.length < 2) return undefined;
    if (/^(turn on live captions|captions)$/i.test(clean)) return undefined;
    return {{ speaker: cleanSpeaker || undefined, text: clean }};
  }};

  const commitLines = (state, entries) => {{
    state.lines.push(...entries.map((entry) => ({{
      at: entry.at,
      speaker: entry.speaker,
      text: entry.text
    }})));
    const excess = state.lines.length - {max_lines_json};
    if (excess > 0) {{
      state.lines.splice(0, excess);
      state.droppedLines = (state.droppedLines || 0) + excess;
    }}
  }};

  const scrapeCaptions = () => {{
    if (!captionState) return;
    const regions = [...document.querySelectorAll(captionSelector)];
    const rows = [];
    for (const region of regions) {{
      const raw = text(region);
      if (!raw) continue;
      const pieces = raw.split(/\\n+/).map((p) => p.trim()).filter(Boolean);
      const row = pieces.length >= 2
        ? normalizeCaption(pieces[0], pieces.slice(1).join(" "))
        : normalizeCaption("", pieces[0] || raw);
      if (row) rows.push({{ ...row, node: region }});
    }}
    if (rows.length === 0) {{
      if (captionState.visible.length > 0 && captionState.settleTimer === undefined) {{
        const pendingState = captionState;
        pendingState.settleTimer = setTimeout(() => {{
          if (window.__openclawTeamsCaptions !== pendingState) return;
          commitLines(pendingState, pendingState.visible);
          pendingState.visible = [];
          pendingState.settleTimer = undefined;
        }}, {settle_ms_json});
      }}
      return;
    }}
    if (captionState.settleTimer !== undefined) {{
      clearTimeout(captionState.settleTimer);
      captionState.settleTimer = undefined;
    }}
    const now = Date.now();
    const nextVisible = [];
    for (const row of rows) {{
      nextVisible.push({{
        at: new Date().toISOString(),
        node: row.node,
        seenAt: now,
        speaker: row.speaker,
        text: row.text
      }});
    }}
    commitLines(captionState, captionState.visible);
    captionState.visible = nextVisible;
  }};

  if (captionState) {{
    if (!readOnly && inCall && !captionState.enabledAttempted) {{
      const captionBtn = findButton(/turn on live captions|closed captions|captions/i);
      if (captionBtn) {{
        captionState.enabledAttempted = true;
        captionsEnabledAttempted = true;
        captionBtn.click();
        notes.push("Attempted to enable Teams live captions.");
      }}
    }}
    if (inCall && !captionState.observerInstalled) {{
      captionState.observerInstalled = true;
      captionState.observer = new MutationObserver(scrapeCaptions);
      captionState.observer.observe(document.body, {{ childList: true, subtree: true, characterData: true }});
      notes.push("Installed Teams caption observer.");
    }}
    if (inCall) scrapeCaptions();
    const lines = [...(captionState.lines || []), ...(captionState.visible || [])];
    const last = lines[lines.length - 1];
    captioning = document.querySelector(captionSelector) !== null || lines.length > 0;
    transcriptLines = (captionState.droppedLines || 0) + lines.length;
    lastCaptionAt = last?.at;
    lastCaptionSpeaker = last?.speaker;
    lastCaptionText = last?.text;
    recentTranscript = lines.slice(-5);
  }}

  // 9. Status & Manual Action Taxonomy
  const lobbyWaiting = !inCall && /someone in the meeting should let you in soon|waiting for the organizer|we.?ve let people in the meeting know you.?re waiting|waiting in the lobby/i.test(pageText);
  let manualAction;

  if (!inCall && (host.includes("login.microsoftonline.com") || host.includes("login.live.com") || /sign in with your work or school account|sign in to join/i.test(pageText))) {{
    manualAction = manualActionFor("teams-login-required", "Sign in to Microsoft Teams in the JARVIS browser profile, then retry.");
  }} else if (!inCall && /verify your identity|enter the code sent to|verification code/i.test(pageText)) {{
    manualAction = manualActionFor("teams-verification-required", "Complete Microsoft email/phone identity verification in the browser profile, then retry.");
  }} else if (lobbyWaiting) {{
    manualAction = manualActionFor("teams-admission-required", "Admit the JARVIS browser participant in Microsoft Teams, then retry speech.");
  }} else if (/permission needed|allow.*(microphone|camera)|blocked.*(microphone|camera)/i.test(pageText)) {{
    manualAction = manualActionFor("teams-permission-required", "Allow microphone/camera permissions for Teams in the JARVIS browser profile, then retry.");
  }}

  const mic = findButton(/toggle microphone|turn (?:on|off) microphone/i);
  const micMuted = mic ? /turn on microphone|unmute|microphone is muted/i.test(buttonLabel(mic)) : undefined;

  return JSON.stringify({{
    inCall,
    micMuted,
    cameraOff: true,
    lobbyWaiting,
    captioning,
    captionsEnabledAttempted,
    transcriptLines,
    lastCaptionAt,
    lastCaptionSpeaker,
    lastCaptionText,
    recentTranscript,
    audioInputRouted,
    audioInputDeviceLabel,
    audioInputRouteError,
    audioOutputRouted,
    audioOutputDeviceLabel,
    audioOutputRouteError,
    manualAction,
    title: document.title,
    url: pageUrl,
    notes
  }});
}}"""


def teams_transcript_script(
    meeting_url: str,
    meeting_session_id: str,
    finalize: bool,
) -> str:
    expected_url = normalize_teams_url_for_reuse(meeting_url)
    expected_url_json = json.dumps(expected_url)
    session_id_json = json.dumps(meeting_session_id)
    finalize_json = json.dumps(finalize)
    max_lines_json = json.dumps(TEAMS_MEETINGS_TRANSCRIPT_MAX_LINES)

    return f"""() => {{
  const expectedMeetingUrl = {expected_url_json};
  const expectedSessionId = {session_id_json};
  let currentMeetingUrl;
  try {{
    const currentUrl = new URL(location.href);
    currentMeetingUrl = currentUrl.origin + currentUrl.pathname.toLowerCase().replace(/\\/$/, "");
  }} catch {{
    return JSON.stringify({{ urlMatched: false }});
  }}
  const state = window.__openclawTeamsCaptions;
  if (state?.sessionId && state.sessionId !== expectedSessionId) {{
    return JSON.stringify({{ urlMatched: true, sessionMatched: false }});
  }}
  if ({finalize_json} && Array.isArray(state?.visible) && state.visible.length > 0) {{
    if (state.settleTimer !== undefined) clearTimeout(state.settleTimer);
    state.settleTimer = undefined;
    state.lines = Array.isArray(state.lines) ? state.lines : [];
    state.lines.push(...state.visible.map((entry) => ({{
      at: entry.at,
      speaker: entry.speaker,
      text: entry.text
    }})));
    state.visible = [];
    const excess = state.lines.length - {max_lines_json};
    if (excess > 0) {{
      state.lines.splice(0, excess);
      state.droppedLines = (state.droppedLines || 0) + excess;
    }}
  }}
  const lines = Array.isArray(state?.lines) ? state.lines : [];
  return JSON.stringify({{
    urlMatched: true,
    sessionMatched: true,
    epoch: typeof state?.epoch === "string" ? state.epoch : undefined,
    droppedLines: Number.isFinite(state?.droppedLines) ? Math.max(0, Math.trunc(state.droppedLines)) : 0,
    lines: lines.map((line) => ({{
      at: typeof line?.at === "string" ? line.at : undefined,
      speaker: typeof line?.speaker === "string" ? line.speaker : undefined,
      text: typeof line?.text === "string" ? line.text : ""
    }})).filter((line) => line.text)
  }});
}}"""


def teams_leave_script(meeting_url: str) -> str:
    return """() => {
  const buttons = [...document.querySelectorAll('button, [role="button"]')];
  const label = (b) => [b.getAttribute("aria-label"), b.getAttribute("data-tid"), b.innerText || ""].join(" ");
  const leaveBtn = buttons.find((b) => !b.disabled && /\\b(hang up|leave|leave call|leave meeting)\\b|data-tid="hangup-button"/i.test(label(b)));
  if (leaveBtn) {
    leaveBtn.click();
    return JSON.stringify({ departed: true, leaveAction: "leave" });
  }
  const confirmBtn = buttons.find((b) => !b.disabled && /\\bconfirm|yes, leave\\b/i.test(label(b)));
  if (confirmBtn) {
    confirmBtn.click();
    return JSON.stringify({ departed: true, leaveAction: "confirm" });
  }
  return JSON.stringify({ departed: false });
}"""
