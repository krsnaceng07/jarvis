# Known Limitations & Standalone Environmental Boundaries

**Document Compliance:** PRD Addendum Section 11 & Gravitas Rule 6

1. **Standalone Execution Mode:** Currently executing in self-contained simulation mode inside `E:/jarvis/Jarvis_UI` without connecting to the live Python agent gateway per explicit user instructions (`"ahile jarvis sang connect garnu chaina"`).
2. **Gesture Mode:** Gesture tracking UI and 3D vision scene are active in simulation mode. Live hand-tracking requires user camera permission and MediaPipe WebAssembly model initialization.
3. **Satellite Data Provider:** Displays dark Earth vector continents, orbital lines, and telemetry hotspots in demo/simulation mode as specified in PRD Section FR-003. Live satellite feed requires external ADS-B / NORAD ephemeris integration.
