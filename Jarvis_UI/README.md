# JARVIS Desktop UI — Holographic Command Interface

**Version:** 3.1.1.7  
**Technology Stack:** React 18, TypeScript, Vite, Tailwind CSS, Three.js WebGL, Web Audio API, Web Speech API  
**Target Architecture:** Desktop-First Standalone UI conforming to OpenClaw / JARVIS Autonomous Specifications  
**Workspace Directory:** `E:/jarvis/Jarvis_UI`

---

## 1. Overview

JARVIS Holographic UI is a high-fidelity, desktop-first command interface designed to match the reference visual hierarchy and functional PRD. It features a dark, near-black/navy canvas (`#03060C`), luminous cyan outlines (`#00F0FF`), subtle coordinate grid textures, real 3D Three.js particle hologram point-clouds, and tactile acoustic earcon feedback.

The application is structured to run **completely standalone and fully functional** out of the box, with built-in mock telemetry, interactive state transitions, interactive module drawers, audio synthesizer, and speech synthesis, while being 100% prepared to bind to the Python FastAPI/WebSocket gateway when configured.

---

## 2. Visual Architecture & Zones

The interface strictly adheres to the 3-zone visual composition:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP BAR: Logo • Feedback • Manage Billing • Support • v3.1.1.7 • Awareness • Theme • Profile • Window │
├───────────────────┬────────────────────────────────────────────┬───────────────────────┤
│                   │ UPPER CENTER:                              │ RIGHT WORKSPACE:      │
│ LEFT RAIL:        │ ┌──────────┐ ┌───────────────────────────┐ │ ┌───────────────────┐ │
│ • SAT-LINK FEED   │ │ MEMORY   │ │ MODE: [•new] [•classic] ⚙│ │ │ VOICE | AGENT|NOTES│ │
│ • SATELLITE STREAM│ │ SKILLS   │ │                         │ │ │                   │ │
│   [2D/3D][EXPAND] │ │ CHARACTER│ │   THREE.JS 3D HOLOGRAM  │ │ │   SYSTEM READY    │ │
│ • 3D/2D Earth Map │ │ SETTINGS │ │       PARTICLE BUST     │ │ │   Aapka personal  │ │
│   Today/Map/Alerts│ └──────────┘ │   "Jarvis is listening"   │ │ │   AI assistant... │ │
│ • TODAY HEADLINES │      │       │ [ TERMINATE ] [ (Mic) ]   │ │ │                   │ │
│   01 Tech Innov...│      ▼       └───────────────────────────┘ │ └───────────────────┘ │
│   02 Usman AI...  │ SVG Bus Trace Lines                        │                       │
│   03 Stonic AI... ├────────────────────────────────────────────┤                       │
│   04 Global Mkt...│ LOWER CENTER: VISUAL HUB                   │ BOTTOM COMPOSER:      │
│                   │ [VISUAL HUB][READY] [visual hub][gesture]  │ [Type to JARVIS...] 📎↑│
│                   │ • 3D Layered Isometric Schematic Diagram   │                       │
│                   │ • 4 Prompts: Starship / Blackhole / Fusion │                       │
│                   │ • LIBRARY History Ticker: Oct 13 - Sep 28  │                       │
└───────────────────┴────────────────────────────────────────────┴───────────────────────┘
```

---

## 3. Implemented Subsystems & Controls

### 3.1 Global Top Bar (`src/components/shell/TopBar.tsx`)
- **System Branding:** Configurable JARVIS / Stonic AI branding with neon glow.
- **Top Actions:** Functional modals for Feedback, Sovereign Developer Billing, and Architecture Documentation.
- **System Metadata:** Real-time version pill (`v3.1.1.7`), Awareness heartbeat pulse switch.
- **Theme Selector:** Multi-theme dropdown (`Dark Cyan`, `Cyberpunk Neon`, `Deep Space`, `Obsidian`).
- **Profile:** Operator identity menu with security credentials view.

### 3.2 Central Hologram & State Machine (`src/components/center/`)
- **Three.js WebGL Particle Hologram:** 4,800 parametric particles forming an ethereal AI consciousness head & shoulders bust, with neural plexus wireframe lattice and orbiting data rings.
- **State-Reactive Animation:** Dynamically alters particle velocity, wave perturbation, and rotation speed during `idle`, `listening`, `thinking`, and `speaking` states.
- **Interactive Mouse Tracking:** Smoothly turns to track user cursor position.
- **Mode Selector:** Seamless toggle between `new` and `classic` interface modes.
- **TERMINATE Control:** Chamfered hexagonal button with tactile acoustic alarm (`audioService.playTerminateAlarm()`) that halts running tasks.
- **Microphone Control:** Glowing circular button that toggles listening status and triggers audio earcons.

### 3.3 Connected Modules & Bus Traces (`src/components/center/ModuleConnectorStack.tsx`)
- Four color-coded modules positioned with routed circuit bus lines:
  1. `MEMORY` (Cyan) — Opens SQLite FTS5 + LanceDB vector store modal.
  2. `SKILLS` (Green) — Opens 48 active declarative skills catalog modal.
  3. `CHARACTER` (Red) — Opens Persona tone, speech rate, and behavioral directives modal.
  4. `SETTINGS` (Blue) — Opens Silero VAD threshold, audio device, and gateway port modal.
- SVG Bus Traces with traveling animated white pulse dots linking cards to the central hologram frame.

### 3.4 Visual Hub (`src/components/visual-hub/`)
- **3D Layered Blueprint:** Interactive Three.js isometric stacked wireframe model with floating 3D bar columns and animated data waves.
- **Suggested Prompts:** 4 interactive prompt cards:
  1. *Draw a SpaceX Starship blueprint*
  2. *Show how a black hole bends light*
  3. *Look inside a fusion reactor*
  4. *Plan a crewed mission to Mars*
- **Visual Library Ticker:** Horizontal scrolling history strip displaying recent saved artifacts from Oct 13 to Sep 28.
- **Gesture Tab:** Interactive spatial hand-tracking camera interface stub.

### 3.5 Left Rail — Sat-Link Feed (`src/components/left-panel/`)
- **Globe Canvas:** 3D interactive rotating dark Earth globe with glowing continental coordinate nodes, satellite orbits, and warning hotspots.
- **Mode Toggles:** 2D flat projection / 3D orbital sphere toggle.
- **Map Navigation:** Today, Map, Search, Alerts, More navigation bar.
- **Today Headlines:** 4 numbered intelligence wire cards with live refresh, sharing, and detailed news modal view.

### 3.6 Right Workspace — Voice / Agent / Notes (`src/components/right-panel/`)
- **VOICE Tab:** Reference-faithful `SYSTEM READY` onboarding screen with floating robot badge and bilingual greeting. Live chat stream with message bubbles, copy tools, and speech synthesis.
- **AGENT Tab:** Real-time task inspection showing active pipelines, current execution steps, tools invoked, and task cancellation.
- **NOTES Tab:** Interactive notepad with note creation, auto-save status, editing, deletion, and tag pills.
- **Composer:** Rounded pill input with attachment dialog and send button.

### 3.7 Sound Engine (`src/services/audioService.ts`)
- Pure synthetic Web Audio API synthesizer for zero-dependency HUD sound effects:
  - Tactile UI click
  - 140ms earcon tool dispatch chime
  - Critical termination alarm
  - Microphone activation ping

---

## 4. Getting Started

### Prerequisites
- Node.js `v20+` or `v22+`
- pnpm (`10.x`) or npm

### Installation & Run

```bash
# 1. Navigate to the UI directory
cd E:/jarvis/Jarvis_UI

# 2. Install dependencies (already completed)
pnpm install

# 3. Start development server
pnpm dev

# 4. Or build and preview production build
pnpm build
pnpm preview --port 5173
```

### Running Unit Tests

```bash
pnpm test
```

All 12 unit tests verifying state machine transitions, assistant stores, chat pipelines, notes persistence, and visual hub prompts will execute and pass.
