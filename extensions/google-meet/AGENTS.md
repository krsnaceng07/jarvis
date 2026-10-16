# Google Meet Extension (JARVIS)

Full parity implementation matching OpenClaw's `extensions/google-meet/`.

## Architecture & Surface

The `google-meet` extension provides complete Google Meet automation, REST API integration, Chrome browser proxy interactions, audio routing (Sox / PipeWire), OAuth flows, transcripts, attendance summaries, and artifact export bundles.

### 1. Tool Surface (`google_meet`)
Supports 18 actions:
- `create`: Create a new Google Meet space, optionally joining it.
- `end-active-conference`: End the active conference for a space.
- `resolve-space`: Resolve space metadata from URL or space name.
- `preflight`: Preflight check for OAuth tokens, scopes, and API readiness.
- `calendar-events`: List upcoming calendar events with Meet links.
- `artifacts`: Fetch transcripts, recordings, and smart notes.
- `attendance`: Calculate participant attendance summary, durations, and late/early leave flags.
- `export`: Export meeting bundle (manifest, attendance CSV/MD, text files) as zip or folder.
- `join`: Join a Google Meet room via Chrome or Twilio.
- `leave`: Leave an active meeting session.
- `speak`: Speak text into an active meeting.
- `status`: Get active meeting and audio health status.
- `transcript`: Fetch realtime meeting transcript lines.
- `recover-tab`: Recover Chrome tab from local or remote browser proxy.
- `test-speech`: Run speech playback probe test.
- `test-listen`: Run microphone capture probe test.
- `setup`: Validate runtime audio devices and node setup.
- `doctor`: Run doctor checks and diagnostic repairs.

### 2. Gateway RPC Surface
Registers 16 RPC methods:
- `googlemeet.space.create`
- `googlemeet.space.resolve`
- `googlemeet.space.endActiveConference`
- `googlemeet.space.preflight`
- `googlemeet.calendar.listEvents`
- `googlemeet.artifacts.get`
- `googlemeet.attendance.get`
- `googlemeet.export.bundle`
- `googlemeet.session.join`
- `googlemeet.session.leave`
- `googlemeet.session.speak`
- `googlemeet.session.status`
- `googlemeet.session.transcript`
- `googlemeet.session.recoverTab`
- `googlemeet.probes.testSpeech`
- `googlemeet.probes.testListen`

### 3. Node Host Commands & Node Invoke Policy
- Command `googlemeet.chrome` handled via `handle_google_meet_node_host_command`.
- Enforces `GoogleMeetChromeNodeInvokePolicy` for paired node invocations.

### 4. CLI Subcommands
`googlemeet <subcommand>`:
`doctor`, `auth login`, `auth refresh`, `create`, `end-active-conference`, `resolve-space`, `preflight`, `calendar-events`, `artifacts`, `attendance`, `export`, `join`, `leave`, `speak`, `status`, `transcript`, `recover-tab`, `test-speech`, `test-listen`, `setup`.
