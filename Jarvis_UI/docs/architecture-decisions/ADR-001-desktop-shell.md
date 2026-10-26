# ADR-001: Desktop Shell Architecture & WebEngine Host Selection

**Date:** 2026-10-24  
**Status:** Approved  
**Deciders:** JARVIS Architect

## Context
The JARVIS assistant requires a high-performance desktop interface with dense holographic data visualizations, 3D WebGL particle rendering (60 FPS), real-time duplex audio capture with Silero VAD, and minimal memory footprint.

The existing workspace uses Python 3.12+ with PyQt6/PySide6, `sounddevice`, and OpenClaw multi-package architecture.

## Decision
1. **Frontend Architecture:** React 18 with TypeScript, Vite, Tailwind CSS, and Three.js WebGL.
2. **Desktop Host:**
   - Development & Web Distribution: Standalone browser / WebApp via Vite local server (`http://localhost:5173`).
   - Desktop Native Host: PySide6 `QWebEngineView` hosting the React production bundle, retaining single-process Python desktop integration without introducing a competing Electron runtime.
3. **Communication Protocol:** JSON-RPC WebSocket protocol on `ws://127.0.0.1:7433/api/v1/events/ws` with local loopback binding.

## Consequences
- **Positive:** Zero Electron memory overhead; unified Python dependency graph; Three.js runs with native GPU acceleration in WebEngine.
- **Trade-off:** Qt WebEngine requires proper Chromium sandbox configuration on Linux/Windows.
